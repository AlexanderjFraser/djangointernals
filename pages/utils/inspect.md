---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Asking a callable what it accepts: `django/utils/inspect.py`

`django/utils/inspect.py` answers what Django asks of a function a project hands it: whether it accepts `**kwargs`, what its parameters are called, whether a method takes nothing but its instance. Its `signature` and `getfullargspec` wrap `inspect.signature` and `inspect.getfullargspec` so that, on Python 3.14 and later, an annotation naming an undefined class does not make them fail.

Django calls code it did not write with arguments it fixes itself. Some of its registries ask when handed a function, and refuse one whose parameters the later call could not fill; others ask so as to adapt to an override that lacks a parameter a release has added.

## Annotations that cannot be evaluated: `signature` and `getfullargspec`

Python 3.14 evaluates a function's annotations only when they are read, so an annotation may name a class imported only under `typing.TYPE_CHECKING`; `inspect.signature`, which evaluates them by default, then raises `NameError`. Django's `signature` passes `annotationlib.Format.FORWARDREF`: an annotation that resolves is evaluated, and a name that does not is left as an `annotationlib.ForwardRef`. Below 3.14 it calls `inspect.signature` as it is. Django does not use the annotations, the docstring says (`django/utils/inspect.py:signature`).

```python
# harbour/office/receivers.py
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harbour.crew.models import Sailor


def log_arrival(sender, instance, **kwargs): ...


def count_ship(sender, instance): ...


def assign_pilot(ship, pilot: Sailor, *, berth=1, **orders): ...
```

A run on Python 3.14:

```text
inspect.signature(assign_pilot)                  NameError: name 'Sailor' is not defined
inspect.getfullargspec(assign_pilot)             TypeError: unsupported callable
signature(assign_pilot)                          (ship, pilot: Sailor, *, berth=1, **orders)
the annotation of pilot, its type                <class 'annotationlib.ForwardRef'>
getfullargspec(assign_pilot).args                ['ship', 'pilot']
```

`inspect.getfullargspec` on 3.14 takes no format, and calls the private `inspect._signature_from_callable` with the default one, which evaluates the annotations. The docstring of `lazy_annotations` names CPython issue 141560 as fixed in 3.15, and on 3.15 the wrapper passes the format to `inspect.getfullargspec` itself (`django/utils/inspect.py:getfullargspec`). On 3.14 the wrapper calls it inside `lazy_annotations`, which swaps `inspect._signature_from_callable` for `safe_signature_from_callable`, a `functools.partial` of it adding the format, and back on the way out, under a module-level `threading.Lock` (`django/utils/inspect.py:lazy_annotations`).

> **Trap.** The patch is to a module's global: while it stands, every caller of `inspect.getfullargspec`, in any thread, gets forward references. The lock is not reentrant, as the docstring warns: a `lazy_annotations` inside another in one thread waits on itself.

Template code calls `getfullargspec`: `Library`'s tag decorators as a tag is registered, and `FilterExpression.args_check`, counting a filter's arguments, as a template is compiled ([Libraries: `Library`, custom tags and `{% load %}`](../templates/libraries.md); `django/template/library.py:Library.simple_tag`, `django/template/base.py:FilterExpression.args_check`).

## The questions, and their cache

Every question but `is_module_level_function` starts at `_get_callable_parameters`: a bound method is asked as its `__func__` less the first parameter, which its instance fills (`django/utils/inspect.py:_get_callable_parameters`). The parameters come from `_get_func_parameters`, under `functools.lru_cache` of 512 entries keyed by the function and whether the first is dropped, so the bound methods of every instance share one entry; the function read from the class has another. Here endeavour and beagle are the two ships, and the cache, which Django's own calls have filled by then, is emptied before the methods are asked:

```text
func_accepts_kwargs(log_arrival)                 True
func_accepts_kwargs(count_ship)                  False
get_func_args(assign_pilot)                      ['ship', 'pilot', 'berth']
get_func_full_args(assign_pilot)                 [('ship',), ('pilot',), ('berth', 1), ('**orders',)]
_get_func_parameters.cache_clear()
method_has_no_args(Ship.clean)                   True
method_has_no_args(endeavour.clean)              True
method_has_no_args(beagle.clean)                 True
_get_func_parameters.cache_info()                CacheInfo(hits=1, misses=2, maxsize=512, currsize=2)
```

`func_accepts_kwargs` and `func_accepts_var_args` say whether there is a `**` or a `*` parameter, and `get_func_args` names the others. `get_func_full_args` gives each parameter's name, with `*` or `**` where it gathers, and its default if any, passing over `"self"`. `func_supports_parameter` asks whether a name can be passed by keyword; `**kwargs`, which would take it, does not count (`django/utils/inspect.py:func_supports_parameter`).

`method_has_no_args` counts the parameters that are neither `*` nor `**`, and wants none for a bound method and one for anything else (`django/utils/inspect.py:method_has_no_args`). A list's `count`, a built-in of one argument, passes, as `inspect.ismethod` is false for a built-in; `Paginator.count` tests for one first ([Pagination: `Paginator` and `Page`](../services/pagination.md)). `is_module_level_function` is true of a Python function whose qualified name holds no `"<locals>"`, which a method of a module-level class, read from the class, also passes (`django/utils/inspect.py:is_module_level_function`).

## Where Django asks

- `Signal.connect` refuses a receiver without `**kwargs` when `settings.DEBUG` is true ([Signals: `Signal`, receivers and sending](../services/signals.md); `django/dispatch/dispatcher.py:Signal.connect`), and `CheckRegistry.register` such a check whatever the setting ([The system checks](../commands/checks.md); `django/core/checks/registry.py:CheckRegistry.register`).
- `BaseTaskBackend.validate_task` refuses a task whose function is not module-level, or takes a context but not as its first argument ([Background tasks: `Task`, `TaskResult` and the task backends](../services/tasks.md); `django/tasks/backends/base.py:BaseTaskBackend.validate_task`).
- `OperationWriter.serialize` names an operation's positional arguments by `get_func_args` of its `__init__` ([Writing a migration file: `MigrationWriter`](../makemigrations/writer.md); `django/db/migrations/writer.py:OperationWriter.serialize`).
- `_get_from_db` warns where an override of `Model.from_db` takes neither fetch_mode nor `**kwargs` ([Deferred fields in a queryset: `defer` and `only`](../querysets/deferred.md); `django/db/models/query.py:_get_from_db`); the admin warns where an override of `ModelAdmin.get_actions` lacks action_location ([Actions: `response_action` and `delete_selected`](../admin/actions.md); `django/contrib/admin/options.py:ModelAdmin._get_actions_with_action_location`).
- admindocs shows as a field a model's method that takes no argument, `*` or `**`, and lists others with `get_func_full_args` (`django/contrib/admindocs/views.py:ModelDetailView.get_context_data`).
