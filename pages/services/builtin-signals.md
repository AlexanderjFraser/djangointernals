---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The signals Django sends

Every `Signal` Django defines, the code that sends it, its sender and its keyword arguments: the request signals, the model signals such as `pre_save` and `m2m_changed`, `post_migrate`, `setting_changed`, `connection_created`, and the login, autoreloader and task signals.

Django's signals are module-level objects: the request signals and `setting_changed` in `django/core/signals.py`; the model signals, `class_prepared`, `pre_migrate` and `post_migrate` in `django/db/models/signals.py`; `connection_created` in `django/db/backends/signals.py`; `template_rendered` in `django/test/signals.py`; the login signals in `django/contrib/auth/signals.py`; the autoreloader's in `django/utils/autoreload.py`; the tasks' in `django/tasks/signals.py`. Django listens to several itself: it closes connections and caches on the request signals, `django.contrib.postgres` registers PostgreSQL's types on `connection_created` ([Opening and closing a connection](../connections/opening.md)), and makes the contrib applications' rows on `post_migrate`.

## Where each signal is sent

| signal | sent by | sender | keyword arguments |
|---|---|---|---|
| `request_started` | a handler (`django/core/handlers/wsgi.py:WSGIHandler.__call__`, `django/core/handlers/asgi.py:ASGIHandler.handle`) | the handler's class | `"environ"`, or `"scope"` under ASGI |
| `request_finished` | closing the response (`django/http/response.py:HttpResponseBase.close`); `ASGIHandler.handle` when there is no response | the handler's class; `None` under the test client | none |
| `got_request_exception` | an exception becoming a 500 (`django/core/handlers/exception.py:response_for_exception`, `get_exception_response`) | `None` | `"request"` |
| `setting_changed` | `django/test/utils.py:override_settings.enable`, `override_settings.disable`; a `TransactionTestCase` with `available_apps` | the settings object's class | `"setting"`, `"value"`, `"enter"` |
| `class_prepared` | `django/db/models/base.py:ModelBase._prepare` | the model class | none |
| `pre_init` | `django/db/models/base.py:Model.__init__` | the model class | `"args"`, `"kwargs"` |
| `post_init` | `Model.__init__` | the model class | `"instance"` |
| `pre_save` | `django/db/models/base.py:Model.save_base` | the model class | `"instance"`, `"raw"`, `"using"`, `"update_fields"` |
| `post_save` | `Model.save_base` | the model class | `"instance"`, `"created"`, `"update_fields"`, `"raw"`, `"using"` |
| `pre_delete` | `django/db/models/deletion.py:Collector.delete` | the model class | `"instance"`, `"using"`, `"origin"` |
| `post_delete` | `Collector.delete` | the model class | `"instance"`, `"using"`, `"origin"` |
| `m2m_changed` | a many-to-many manager (`django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager`) | the through model | `"action"`, `"instance"`, `"reverse"`, `"model"`, `"pk_set"`, `"using"`, `"raw"` |
| `pre_migrate` | `django/core/management/sql.py:emit_pre_migrate_signal` | an `AppConfig` | `"app_config"`, `"verbosity"`, `"interactive"`, `"using"`; from migrate, `"stdout"`, `"apps"`, `"plan"` |
| `post_migrate` | `django/core/management/sql.py:emit_post_migrate_signal` | an `AppConfig` | as `pre_migrate` |
| `connection_created` | `django/db/backends/base/base.py:BaseDatabaseWrapper.connect` | the wrapper's class | `"connection"` |
| `template_rendered` | `django/test/utils.py:instrumented_test_render` | the template | `"template"`, `"context"` |
| `user_logged_in` | `django/contrib/auth/__init__.py:login`, `alogin` | the user's class | `"request"`, `"user"` |
| `user_login_failed` | `django/contrib/auth/__init__.py:authenticate`, `aauthenticate` | `"django.contrib.auth"` | `"credentials"`, secrets masked; `"request"` |
| `user_logged_out` | `django/contrib/auth/__init__.py:logout`, `alogout`, before the session is flushed | the user's class, or the class of `None` | `"request"`, `"user"` |
| `autoreload_started` | `django/utils/autoreload.py:BaseReloader.run` | the reloader | none |
| `file_changed` | `django/utils/autoreload.py:BaseReloader.notify_file_changed`, which restarts unless a receiver returns true | the reloader | `"file_path"` |
| `task_enqueued` | `django/tasks/backends/immediate.py:ImmediateBackend._execute_task`, `django/tasks/backends/dummy.py:DummyBackend._store_result` | the backend's class | `"task_result"` |
| `task_started` | `ImmediateBackend._execute_task` | the backend's class | `"task_result"` |
| `task_finished` | `ImmediateBackend._execute_task` | the backend's class | `"task_result"` |

*The signals Django defines, and what a receiver is given besides `"signal"` and `"sender"` (`django/dispatch/dispatcher.py:Signal.send`). The login signals belong to [The user of a request: `login`, `logout` and `AuthenticationMiddleware`](../auth/login.md) and [Authenticating: `authenticate` and the backends](../auth/authenticating.md), the autoreloader's to [The autoreloader](../commands/autoreload.md), the tasks' to [Background tasks: `Task`, `TaskResult` and the task backends](tasks.md).*

## The request cycle and the test framework

The request signals and the receivers Django connects to them are in the table of [The two entry points](../handlers/entry.md).

Every send of `setting_changed` is in the test framework. `override_settings` sends it for each setting as an override begins, with `"enter"` true, and again as it ends, by `Signal.send_robust`, with the restored value; a `TransactionTestCase` with `available_apps` sends it for `"INSTALLED_APPS"` (`django/test/testcases.py:TransactionTestCase._pre_setup`). Most of its receivers throw away what was built from the old value ([Overriding settings](../startup/overrides.md)). `template_rendered` is sent only once `setup_test_environment` has made `instrumented_test_render` the templates' render method (`django/test/utils.py:setup_test_environment`).

## A model class and its instances

`class_prepared` is sent at the end of `ModelBase._prepare`, when the class is complete and not yet registered ([`ModelBase`: a class statement becomes a model](../models/metaclass.md)). It is sent for every model that is not abstract, migrations' historical models included: rendering the harbour's project state sent it once for each model.

`Model.__init__` sends `pre_init` before it sets anything and `post_init` at its end, each time it runs, whether or not anything listens, and so for each row a query fetches, which `Model.from_db` makes by calling the class with the row's values as `"args"` ([An instance and its state](../instance/state.md)). `from_db` sets `ModelState.db` and `ModelState.adding` only after the class returns, so to a receiver of `post_init` a fetched instance looks new and from no database (`django/db/models/base.py:Model.from_db`). An unpickled instance, one read from a cache among them, is made without calling the class and sends neither (`django/db/models/base.py:model_unpickle`).

## Saving: `pre_save` and `post_save`

`Model.save_base` sends `pre_save` before it writes any table and `post_save` after the last, except for a through model Django made ([Saving an instance](../instance/saving.md)). `QuerySet.update`, `QuerySet.bulk_create` and `QuerySet.bulk_update` send neither.

Django passes `"raw"` true only from `DeserializedObject.save`, which calls `save_base` itself, past the model's `save`, so that a fixture's rows are written as they stand; since 6.1 it passes `"raw"` to `m2m_changed` too ([Serialization: `serialize`, `deserialize` and `DeserializedObject`](serializers.md)) (`django/core/serializers/base.py:DeserializedObject.save`). Django's reference warns such a receiver not to query or change other rows, since the database may not be consistent yet (`docs/ref/signals.txt`).

`"update_fields"` is `None` unless the save was limited, and then a `frozenset`: of the names the caller gave, or, for an instance with deferred fields, of attnames `Model.save` picks itself. Given an empty list, `save` returns before either signal.

The sender is always the instance's own class, a proxy's or a child's. Saving an Officer, a child of Sailor with a table of its own, sent both signals for Officer alone, since `save_base` writes a parent's row without a signal; deleting it sent each delete signal for Officer and again for Sailor, whose row the collector holds as an instance of Sailor.

## `m2m_changed`

A many-to-many manager sends `m2m_changed` in pairs around each change, with an `"action"` of `"pre_add"`, `"post_add"`, `"pre_remove"`, `"post_remove"`, `"pre_clear"` or `"post_clear"`; `set` sends those of the changes it makes ([Many-to-many relations](../relations/many-to-many.md)). `"pk_set"` is, for an addition, the keys that had no row yet, looked up by a query; for a removal, the keys the caller named, whether a row had them or not; for a clearing, `None`.

## Deleting: `pre_delete` and `post_delete`

`Collector.delete` sends `pre_delete` for every instance it holds before any row goes, and `post_delete` after each model's rows, inside its transaction; `"origin"` is the instance or queryset whose `delete` was called ([Deleting: the `Collector`](../instance/deleting.md)). Rows it deletes without holding them are not announced, and a receiver connected for a model, or for every sender, makes `Collector.can_fast_delete` refuse to delete that model's rows unseen. Nor are rows of a through model Django made, or rows the database deletes for `DB_CASCADE` (`docs/releases/6.1.txt`).

## `pre_migrate` and `post_migrate`

Each is sent once for every application in the registry that has a models module (`django/core/management/sql.py:emit_post_migrate_signal`). The migrate command sends both around the executor and adds `"stdout"`, `"plan"` and `"apps"`, a registry of historical models ([The migrate command, showmigrations and sqlmigrate](../migrations/migrate.md)). `post_migrate` has two more senders that add none of them: the flush command, after emptying a database that had tables unless its caller inhibits it, and a `TransactionTestCase` with `available_apps`, for the applications it keeps (`django/core/management/commands/flush.py:Command.handle`). A receiver therefore needs a default for `"apps"`, as `create_permissions` has (`django/contrib/auth/management/__init__.py:create_permissions`).
