---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Messages: `add_message`, `Message` and `MessageMiddleware`

The messages framework, `django.contrib.messages`, lets one request leave a note for a page that a later request renders. `add_message` and its shortcuts queue a `Message` on the request's **message storage**, `BaseStorage` decides which messages are done with and which are kept, and `MessageMiddleware` makes the storage on the way in and has it store what is left on the way out.

A view that handles a form answers with a redirect, so the page that tells the user what happened is rendered by another request. A message must therefore outlive the request that writes it, and end once a page has shown it. The storage keeps it between requests, in a cookie or in the session ([Message storage: `CookieStorage`, `SessionStorage` and `FallbackStorage`](message-storage.md)). When it ends is decided by one rule of `BaseStorage`, the base class of the storages: a message is done when something iterates over the storage.

## Adding a message: `add_message`

`add_message` takes the request, a level, the text and optional extra tags, and passes them to the storage at `HttpRequest._messages`, which `MessageMiddleware` sets. A request without that attribute is refused in one of two ways. An argument with no `"META"` attribute, which is no request, raises `TypeError`. A request the middleware never saw raises `MessageFailure`, unless `fail_silently=True`, when the message is dropped and the call returns `None` (`django/contrib/messages/api.py:add_message`). The flag excuses only the second; the documentation gives it to a reusable application whose host project may not install messages (`docs/ref/contrib/messages.txt`). On an `HttpRequest` made by hand:

```text
# a run: messages.info(request, "High water at 14:20.")
MessageFailure: You cannot add messages without installing django.contrib.messages.middleware.MessageMiddleware
```

The shortcuts `debug`, `info`, `success`, `warning` and `error` are `add_message` at the level each is named for. `SuccessMessageMixin.form_valid` calls a form view's own and then adds what `SuccessMessageMixin.get_success_message` returns, by default `SuccessMessageMixin.success_message` formatted with the form's cleaned data, as a success message, unless it comes out empty ([The form views](../views/editing.md)) (`django/contrib/messages/views.py:SuccessMessageMixin.form_valid`).

## Levels and tags

A level is an integer. The five of `django/contrib/messages/constants.py` are `DEBUG` 10, `INFO` 20, `SUCCESS` 25, `WARNING` 30 and `ERROR` 40. A storage drops a message whose level is below its own, `BaseStorage.level`, a property that reads `MESSAGE_LEVEL` the first time it is asked and keeps the answer, taking `INFO` where the setting is absent. `set_level` lowers or raises it for one request, and `None` returns it to the setting, but raises `TypeError` while nothing has read or set the storage's level. On a request without a storage `set_level` returns `False` (`django/contrib/messages/storage/base.py:BaseStorage._get_level`, `django/contrib/messages/storage/base.py:BaseStorage._set_level`, `django/contrib/messages/api.py:set_level`).

> **Trap.** `get_level` makes a new storage with `default_storage` before it looks for the request's own, as the default argument of `getattr`. When `MESSAGE_STORAGE` names `FallbackStorage` or `SessionStorage`, that storage refuses to be made on a request without a session, and `get_level` raises `ImproperlyConfigured` (`django/contrib/messages/api.py:get_level`, `django/contrib/messages/storage/session.py:SessionStorage.__init__`).

A level's **tag** is the word a template writes into a class attribute. `get_level_tags` lays `MESSAGE_TAGS` over `DEFAULT_TAGS`, which names each of the five levels in lower case (`django/contrib/messages/utils.py:get_level_tags`). The result is held in `LEVEL_TAGS`, a `SimpleLazyObject` in `django/contrib/messages/storage/base.py`, built when the first tag is asked for and kept for the life of the process. Only `update_level_tags` replaces it, a receiver that `MessagesConfig.ready` connects to `setting_changed`, and only the test framework sends that signal ([The signals Django sends](../services/builtin-signals.md)). So a `MESSAGE_TAGS` changed by `override_settings` is seen, and one assigned to the settings after the first tag is not (`django/contrib/messages/apps.py:update_level_tags`).

> **Changed in 6.0.** The admin gives `DEBUG` and `INFO` messages icons and styling of their own instead of `SUCCESS`'s; `ModelAdmin.message_user` adds at `INFO` by default ([The admin](../admin.md)) (`docs/releases/6.0.txt`).

## `Message`

A `Message` holds three things: `Message.level`, made an integer; `Message.message`, the text; and `Message.extra_tags` (`django/contrib/messages/storage/base.py:Message`). `str()` gives the text, as `{{ message }}` renders it. `Message.tags` joins the extra tags and the level's tag with a space, extra tags first, leaving out an empty one; `Message.level_tag` looks the level up in `LEVEL_TAGS`, and is `""` for a level with no tag. Before a new message is stored, `Message._prepare` turns the text, and the extra tags unless they are `None`, into `str`, in case, its docstring says, they are lazy translations. Two messages are equal when their levels and texts are: the extra tags are not compared.

## When a message is done: `BaseStorage`

`BaseStorage` keeps two lists. The messages added during this request wait in a queue. The messages kept from earlier requests are the property `BaseStorage._loaded_messages`, which calls the subclass's `BaseStorage._get` the first time it is read and keeps what it returns, so a request that neither reads nor adds a message never loads them. `BaseStorage.add` drops an empty message and one below the level without a word, and otherwise appends a `Message` to the queue and sets `BaseStorage.added_new` (`django/contrib/messages/storage/base.py:BaseStorage.add`).

Reading is where a message ends, and iteration is the only reading that counts. `BaseStorage.__iter__` sets `BaseStorage.used`, moves the queue onto the end of the loaded list, and iterates over that. `len()` and `in` count and search both lists, loading the earlier messages, and leave `used` alone; and since no storage defines `__bool__`, Python's truth test of a storage is its length (`django/contrib/messages/storage/base.py:BaseStorage.__iter__`).

On the way out, `BaseStorage.update` stores what is left, in one of three cases (`django/contrib/messages/storage/base.py:BaseStorage.update`):

- **Iterated.** Only the queue is stored: the messages added after the last iteration. When there are none, the subclass is given an empty list, and clears what it held.
- **Not iterated, something added.** The earlier messages are stored with the new ones after them, so a note no page has shown stays ahead of a newer one.
- **Neither.** Nothing is done, and the storage stays as an earlier response left it.

It returns what the subclass's `BaseStorage._store` could not store. The documentation's way to keep messages after iterating over them is to set `used` back to `False` (`docs/ref/contrib/messages.txt`).

A template reaches the storage through the context processor `django/contrib/messages/context_processors.py:messages`, which gives it as `"messages"`, the storage itself (an empty list without the middleware), beside `"DEFAULT_MESSAGE_LEVELS"`, the five levels by name ([The context: `Context`, `RequestContext` and context processors](../templates/context.md)). So `{% for message in messages %}` ends the messages and `{% if messages %}` does not. In this run nora posts to a view of the office's, then visits a page that never mentions messages, one that only counts them, and berths:

```python
# harbour/office/views.py
@login_required
def notices(request):
    messages.debug(request, "Tide table reloaded.")
    messages.info(request, "High water at 14:20.")
    messages.warning(request, "Gale warning for Piraeus.", extra_tags="weather")
    messages.error(request, "Beagle has no berth.")
    return redirect("berths")
```

```text
# a run: each response, and what it rendered but "Signed in as nora." and the form; board.html is
# {% if messages %}<p>{{ messages|length }} notices waiting.</p>{% endif %}
POST /notices/   302 to /berths/  "messages" set
GET /ships/      200              "messages" not touched
    <p>Ships in harbour: Endeavour, Beagle.</p>
GET /board/      200              "messages" not touched
    <p>3 notices waiting.</p>
GET /berths/     200              "messages" deleted
    <p class="info">High water at 14:20.</p>
    <p class="weather warning">Gale warning for Piraeus.</p>
    <p class="error">Beagle has no berth.</p>
GET /berths/     200              "messages" not touched
```

The debug message was below the level and never queued. The two pages between neither iterated nor added, so the cookie the first response set stayed in the browser; berths iterated, showed all three in the order they were added, and deleted it. `MessagesTestMixin.assertMessages` lists the storage of a test response's request and compares the list by `Message`'s equality ([The test framework](../testing.md)).

## `MessageMiddleware`

`MessageMiddleware.process_request` puts a storage on every request as `HttpRequest._messages`, made by `default_storage`, which imports the class `MESSAGE_STORAGE` names, `FallbackStorage` by default, at each call (`django/contrib/messages/storage/__init__.py:default_storage`). With that default the middleware must come after `SessionMiddleware`, for the reason [Authentication, sessions and messages](../auth.md) gives.

`MessageMiddleware.process_response` calls the storage's `BaseStorage.update`, when the request has a storage. What it could not store is lost, and when `settings.DEBUG` is true the middleware raises `ValueError`, "Not all temporary messages could be stored." (`django/contrib/messages/middleware.py:MessageMiddleware.process_response`). The default storage leaves none, since `SessionStorage` keeps whatever it is given; `CookieStorage` alone leaves what its cookie cannot hold, and a run of it with `settings.DEBUG` true raised the error. `MessageMiddleware.async_capable` is false (6.2), so under ASGI the middleware runs synchronously ([Sync and async in one chain](../handlers/async.md)).
