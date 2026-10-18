---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: Templates, forms and services
contents: signals, builtin-signals, cache-api, cache-backends, page-cache, http-caching, files, storage, email-messages, mailers, tasks, serializers, fixtures, pagination
---

# Caching, files, mail, signals and tasks

The services that code all over Django, and a project's own, calls into: the signal dispatcher, by which one part of the code hears of another's events; the cache framework; file storage; email; background tasks; and the serializers and the paginator. Four of them share one shape: a setting of backends named by alias, a handler that makes a backend when it is asked for one, and a base class that every backend implements.

The request cycle and the ORM are paths, which a request or a query follows from one end to the other. This chapter describes the places that those paths, and a project's views and models, call out to: to keep a computed value for a while, to save bytes under a name and find them again, to send a message, to run a function later and somewhere else, to tell other code that something has happened. Each is wanted in many places. In the first four, the part that differs from one site to the next, the cache server, where the files go, how mail leaves the machine, what runs a task, is a backend chosen in the settings, and the interface the code calls is the same whichever backend is behind it.

## Backends by alias

`CACHES`, `STORAGES`, `MAILERS` and `TASKS` are each a dictionary of **aliases**, names such as `"default"`, each mapped to a dictionary that names a backend class by its dotted path under `"BACKEND"`, with the options it is to be made with. A **handler** reads its setting when it first needs it, the mail handler at every lookup, and for an alias imports the class and makes an instance: `caches["default"]`, `storages["default"]`, `mailers["default"]`, `task_backends["default"]`. A name of the package stands for the default alias's backend, and for email a property of the handler does (`django/core/cache/__init__.py`, `django/core/files/storage/__init__.py`, `django/tasks/__init__.py`, `django/core/mail/handler.py:MailersHandler`).

| service | setting | handler | an alias's backend | the default |
|---|---|---|---|---|
| the cache | `CACHES` | `caches`, a `CacheHandler` | made at first use, once for each thread or asynchronous context | `cache` |
| file storage | `STORAGES` | `storages`, a `StorageHandler` | made at first use, once for the process | `default_storage` |
| email | `MAILERS` | `mailers`, a `MailersHandler` | made anew at each lookup | `MailersHandler.default` |
| tasks | `TASKS` | `task_backends`, a `TaskBackendHandler` | made at first use, once for each thread or asynchronous context | `default_task_backend` |

*The four services configured by alias. The cache's handler and the tasks' are built on `BaseConnectionHandler`, as the database's handler is; `cache` and `default_task_backend` are proxies that look the default up again at each use, and `default_storage` is a lazy object that looks it up at its first use and keeps it.*

The cache's handler and the tasks' keep what they make in an asgiref `Local`, as the database's handler does, so each thread has its own backend for an alias; unlike the database's, they leave `BaseConnectionHandler.thread_critical` false, so code that `sync_to_async` or `async_to_sync` runs in another thread uses its caller's ([Connections by alias: `DATABASES` and `ConnectionHandler`](backends/connections.md)) (`django/utils/connection.py:BaseConnectionHandler`). At the end of every request `close_caches`, a receiver of `request_finished`, closes the cache backends that the thread has made, which of the backends Django ships only `PyMemcacheCache` acts on (`django/core/cache/__init__.py:close_caches`). The storage handler keeps one instance for each alias in a dictionary of its own, shared by every thread (`django/core/files/storage/handler.py:StorageHandler.__getitem__`). The mail handler keeps nothing: each lookup imports the backend's class and makes a new instance (`django/core/mail/handler.py:MailersHandler.create_connection`).

> **Changed in 6.1.** `MAILERS` is new. The settings that configured the single backend before it, `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT` and the like, are deprecated, as are `django.core.mail.get_connection` and the `connection` argument of the sending functions; until they are removed in Django 2028, `mailers["default"]` falls back to `EMAIL_BACKEND` in a project that does not define `MAILERS` (`docs/releases/6.1.txt`).

Signals, the serializers and the paginator have no backends. A **signal** is an object that keeps a list of functions to call when it is sent, the serializers are a registry of formats, and a paginator is made for one list at a time.

## One save, four services

The harbour office's site lists the voyages its ships have sailed, and tells the harbour master by email when a new one is entered. Its settings name one backend for each service: the cache in local memory, files on the server's disk, mail kept in a list in memory, and tasks run at once:

```python
# harbour/settings.py, in part
INSTALLED_APPS = ["harbour.fleet", "harbour.crew", "harbour.office", "notices"]
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "harbour"},
}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
TASKS = {"default": {"BACKEND": "django.tasks.backends.immediate.ImmediateBackend"}}
DEFAULT_FROM_EMAIL = "office@harbour.example"
```

The application notices holds the site's own code. A task sends the harbour master a message about one voyage:

```python
# notices/tasks.py
from django.core.mail import send_mail
from django.tasks import task

from harbour.fleet.models import Voyage


@task
def tell_harbour_master(voyage_id):
    voyage = Voyage.objects.select_related("ship").get(pk=voyage_id)
    return send_mail(
        subject=f"{voyage.ship} sailed on {voyage.sailed:%d %B %Y}",
        message=f"Voyage {voyage.pk}: the {voyage.ship} has sailed.",
        from_email=None,
        recipient_list=["master@harbour.example"],
    )
```

A receiver of `post_save`, connected when the application's `AppConfig.ready` imports its module, hears of each save of a voyage. It deletes the cached list, and for a new voyage enqueues the task:

```python
# notices/receivers.py
from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver

from harbour.fleet.models import Voyage
from notices.tasks import tell_harbour_master


@receiver(post_save, sender=Voyage)
def voyage_saved(sender, instance, created, **kwargs):
    cache.delete("sailings")
    if created:
        tell_harbour_master.enqueue(instance.pk)
```

The view keeps the list in the cache for five minutes, and builds it only when the cache does not have it:

```python
# notices/views.py, in part
def list_sailings():
    voyages = Voyage.objects.select_related("ship").order_by("sailed")
    return [f"{voyage.sailed}  {voyage.ship}" for voyage in voyages]


def sailings(request):
    lines = cache.get_or_set("sailings", list_sailings, 300)
    return HttpResponse("\n".join(lines), content_type="text/plain")
```

A run of the example, with Django's test client making the requests, a voyage of Endeavour's already in the table, and the number of SQL statements sent counted for each request:

```text
GET /sailings/  200, 1 query
  2026-10-12  Endeavour
GET /sailings/  200, 0 queries
  2026-10-12  Endeavour

Voyage.objects.create(ship=beagle, sailed=date(2026, 10, 14))
  the task's result: SUCCESSFUL, return value 1
  cache.get("sailings"): None
  mail.outbox: 1 message, 'Beagle sailed on 14 October 2026'
    from office@harbour.example to master@harbour.example, sent by the mailer 'default'

GET /sailings/  200, 1 query
  2026-10-12  Endeavour
  2026-10-14  Beagle
```

The first request found nothing in the cache under `"sailings"`, called list_sailings, which sent the query, and stored the list; the second found it and sent nothing to the database (`django/core/cache/backends/base.py:BaseCache.get_or_set`). The cache stored the list under `":1:sailings"`, the key the code gave with the cache's prefix, empty here, and its version, 1, in front of it (`django/core/cache/backends/base.py:default_key_func`).

Saving Beagle's voyage set the rest going, inside the call to `create`. `Model.save_base` sent `post_save` once the row was written ([Saving an instance](models/saving.md)); the signal called voyage_saved, its one receiver for that sender; the receiver deleted the key and enqueued the task; and the immediate backend ran the task inside `enqueue`, so the message had been sent, and the result marked successful, before `enqueue` returned to the receiver:

```text figure=one-save
Voyage.objects.create(ship=beagle, sailed=date(2026, 10, 14))
  INSERT INTO "fleet_voyage" ...
  post_save.send(sender=Voyage, instance=voyage, created=True, ...)   the signal
    voyage_saved(...)                      the receiver notices connected
      cache.delete("sailings")             the cache, caches["default"], a LocMemCache: the key ":1:sailings"
      tell_harbour_master.enqueue(2)       the task backend, task_backends["default"], an ImmediateBackend
        a TaskResult, READY                task_enqueued sent
        RUNNING                            task_started sent
          tell_harbour_master(2)
            SELECT the voyage and its ship
            send_mail(...)                 the mailer, the default, a locmem EmailBackend
              mail.outbox  <-  "Beagle sailed on 14 October 2026"
        SUCCESSFUL, return value 1         task_finished sent
```

*What saving one voyage set going in the example: the signal called its receiver, which used the cache and enqueued a task; the immediate backend ran the task at once, and the task sent its message through the default mailer.*

The third request found the key gone and built the list again, with Beagle's voyage in it. None of the code names the backends behind `cache`, `enqueue` or `send_mail`. With Redis behind the cache, the key would have been deleted on a server; with an SMTP mailer, the message would have left the machine; with `DummyBackend` behind the tasks, `enqueue` would have returned a result still marked ready, and no message would have been sent.

## Signals

A `Signal` keeps a list of **receivers**, each a callable connected to it, by `Signal.connect` or the `receiver` decorator, either for every **sender** or for one. The sender is the object the event concerns, and for the model signals it is a model class. `Signal.send` calls the receivers connected for that sender or for every sender, in the order they were connected, with the signal, the sender and the keyword arguments of the send, and returns each receiver with what it returned (`django/dispatch/dispatcher.py:Signal.send`). A receiver that raises stops the send, and the exception reaches the code that sent the signal; `Signal.send_robust` instead catches each `Exception`, logs it and returns it in that receiver's place.

A receiver is held by a weak reference unless it is connected with `weak=False`, so a function or a method that nothing else keeps alive drops out of the list by itself (`django/dispatch/dispatcher.py:Signal.connect`). Receivers that are coroutine functions are called after the others, together and concurrently, and `Signal.asend`, the send for asynchronous code, calls the synchronous ones through `sync_to_async` ([Signals: `Signal`, receivers and sending](services/signals.md)). Django sends signals of its own, among them when a request starts and finishes, as a model instance is made, before and after an instance is saved or deleted, before and after migrations run, and when a setting is overridden; they are listed with where each is sent in [The signals Django sends](services/builtin-signals.md).

## The cache

Every cache backend Django ships is a subclass of `BaseCache`, whose methods `get`, `set`, `add`, `delete`, `touch`, `incr`, `clear` and the like each have an asynchronous twin. The base class makes the key a backend stores from the key the code gives, and reads the **timeout**, how long an entry is kept: when a call gives none, the `"TIMEOUT"` of the cache's settings, 300 seconds unless they say otherwise; for `None`, for ever (`django/core/cache/backends/base.py:BaseCache.__init__`, `django/core/cache/backends/base.py:BaseCache.get_backend_timeout`). The package's docstring describes a cache as a set of values, of any type that can be pickled, under string keys ([The cache API: `caches` and `BaseCache`](services/cache-api.md)). The backends keep entries in a process's memory, in files, in a database table, in Memcached or in Redis, and one keeps nothing ([The cache backends](services/cache-backends.md)).

Among the uses Django makes of the cache API itself are two caches. The **page cache** keeps whole responses: `FetchFromCacheMiddleware` answers a `"GET"` or a `"HEAD"` from the cache before the view runs, and `UpdateCacheMiddleware` stores a response that may be kept, under a key made from the method, the URL, the values of the request headers that the response's `"Vary"` names and, where they are on, the language and the time zone ([The page cache: `UpdateCacheMiddleware`, `FetchFromCacheMiddleware` and `cache_page`](services/page-cache.md)). The template tag `{% cache %}` keeps a fragment of a template ([The libraries to load: static, i18n, l10n, tz and cache](templates/loadable-libraries.md)). Beside them, `django/utils/cache.py` writes the headers that tell a browser or a proxy how long it may keep a response, and decides whether a request's preconditions let Django answer 304 Not Modified or 412 Precondition Failed instead of sending the response again ([Cache headers and conditional requests: `django/utils/cache.py`](services/http-caching.md)) (`django/utils/cache.py:get_conditional_response`).

## Files and storage

A `File` wraps a Python file object, or anything that reads like one, and gives it a name, a size and a way to be read in chunks; `ContentFile` makes one from bytes or a string held in memory ([Files: `File`, `ContentFile` and their helpers](services/files.md)) (`django/core/files/base.py:File`). A **storage** saves such a file under a name and gives it back. `Storage.save` asks the storage for a name that is free, which by default is the name given if it is free and fits the field, and otherwise that name with an underscore and seven random characters added before its extension, shortened where the field's length requires; it saves the content and returns the name it used, which is the name a `django.db.models.FileField` keeps in its column (`django/core/files/storage/base.py:Storage.save`). `FileSystemStorage` keeps files under `MEDIA_ROOT` and gives each a URL under `MEDIA_URL`, unless it is made with a location and a URL of its own ([File storage: `Storage`, `FileSystemStorage` and `storages`](services/storage.md)); what a file field does with a storage is in [File fields](models/files.md).

## Email

An `EmailMessage` holds a message's parts: its subject, body, sender, recipients, attachments and extra headers. It writes nothing until it is asked: `EmailMessage.message` builds a message object of the standard library's `email` package from the parts and headers the message holds, adding a `"Date"` and a `"Message-ID"` unless its headers give them ([Email messages: `EmailMessage` and `EmailMultiAlternatives`](services/email-messages.md)) (`django/core/mail/message.py:EmailMessage.message`). An **email backend** sends a list of messages, through `BaseEmailBackend.send_messages`: the SMTP backend opens a connection to the server if none is open, sends each message and closes the connection again if it opened it; the others write messages to the console or to files, keep them in a list in memory, or drop them. `send_mail`, `mail_admins` and the other functions of `django.core.mail` build their messages and send them through a mailer, the default unless `using=` names another ([Sending email: `mailers` and the email backends](services/mailers.md)).

## Tasks

A **task** is a module-level function wrapped by the `task` decorator into a `Task`, which holds the function and the options it is to be run with: its backend's alias, its queue, its priority, the earliest time it may run, and whether it is given a context. A task is checked against its backend as it is made, and `Task.enqueue` hands it and its arguments to the backend, which returns a `TaskResult`, through which the caller follows the task's status and, once it has succeeded, its return value (`django/tasks/base.py:Task.enqueue`). Django defines what a task is and how one is enqueued; it does not run a queue of its own. Its two backends are for development and tests: `ImmediateBackend` runs the task inside `enqueue`, and `DummyBackend` keeps the result and never runs it (`docs/topics/tasks.txt`). A backend that queues tasks for workers in other processes comes from outside Django ([Background tasks: `Task`, `TaskResult` and the task backends](services/tasks.md)).

> **Changed in 6.0.** The tasks framework, `django.tasks`, is new (`docs/releases/6.0.txt`).

## Serializers and the paginator

A **serializer** writes model instances out, as text in every format but the internal `"python"`, and a deserializer reads them back as instances not yet saved. Each format, `"json"`, `"jsonl"`, `"xml"`, `"yaml"` and `"python"`, is a module with a `Serializer` and a `Deserializer` class, built on the classes of those names in `django/core/serializers/base.py` (`django/core/serializers/__init__.py:BUILTIN_SERIALIZERS`). Each object comes back wrapped in a `DeserializedObject`, whose `DeserializedObject.save` writes the row as it was given, without calling the model's own `save`, and tells the signals that the save is raw ([Serialization: `serialize`, `deserialize` and `DeserializedObject`](services/serializers.md)). The dumpdata and loaddata commands are built on them ([Fixtures: dumpdata and loaddata](services/fixtures.md)).

The `Paginator` cuts a list or a queryset into pages of a given size. It counts the objects, with the list's `count` method where it has one that takes no argument, as a queryset does, and gives each page a slice, which on a queryset becomes a LIMIT and, past the first page, an OFFSET in its SQL ([Pagination: `Paginator` and `Page`](services/pagination.md)) (`django/core/paginator.py:Paginator.page`).

## Where the services meet the rest of Django

The handler sends `request_started` as a request arrives, and the response's `close` sends `request_finished`; the receivers Django connects to them are in [The two entry points](handlers/entry.md). `Model.__init__` sends `pre_init` and `post_init` as it makes an instance ([An instance and its state](models/instances.md)); `Model.save_base` sends `pre_save` and `post_save` around a save ([Saving an instance](models/saving.md)); the `Collector` sends `pre_delete` and `post_delete` around the instances it deletes ([Deleting: the `Collector`](models/deleting.md)); and a many-to-many manager sends `m2m_changed` ([Many-to-many relations](models/many-to-many.md)). The migrate command sends `pre_migrate` and `post_migrate` ([The migrate command, showmigrations and sqlmigrate](migrations/migrate.md)), and a test's change of a setting sends `setting_changed`, most of whose receivers throw away what was built from the old value ([Overriding settings](startup/overrides.md)).

The decorators `cache_control`, `never_cache` and `condition` are in [View decorators](views/decorators.md), and `cache_page`, a middleware made a decorator, in [A middleware as a decorator](views/middleware-decorators.md). A file field and its `FieldFile` are in [File fields](models/files.md), and an uploaded file, before it reaches a storage, in [Multipart parsing and upload handlers](http/uploads.md). The list view's use of the paginator is in [The generic views](views/generic.md), and the commands' table in [The commands Django ships](commands/builtin.md). Errors are mailed to `ADMINS` by a logging handler ([Logging](startup/logging.md)). The test framework's outbox and its override of the mailers belong to [The test environment: `setup_test_environment`](testing/environment.md); the sessions kept in a cache, to [The session backends](auth/session-backends.md); and the static files' storage, to [Static file storages: `ManifestStaticFilesStorage` and hashed names](contrib/static-storage.md).
