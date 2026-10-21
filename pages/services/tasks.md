---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Background tasks: `Task`, `TaskResult` and the task backends

`django.tasks` describes work to be done outside the request: the `task` decorator turns a module-level function into a `Task`, `Task.enqueue` hands it and its arguments to a backend of `TASKS`, and the backend answers with a `TaskResult` that records what became of it. Django ships two backends, `ImmediateBackend` and `DummyBackend`, and no worker.

Work sent off to run later needs a description that can be checked and carried elsewhere, a place to accept it, and a record for its caller: `Task`, the backend and `TaskResult`. Running tasks in the background is left to backends from outside Django (`docs/topics/tasks.txt`). The example's task, tell_harbour_master, is on the opening page ([Caching, files, mail, signals and tasks](../services.md)).

## `TASKS` and `task_backends`

`TASKS` maps aliases to backends; its default names `ImmediateBackend` under `"default"` (`django/conf/global_settings.py`). `TaskBackendHandler` is a `BaseConnectionHandler`, which makes one backend for an alias in each thread or asynchronous context that asks ([Connections by alias: `DATABASES` and `ConnectionHandler`](../connections/aliases.md)). Its `TaskBackendHandler.create_connection` imports the class under `"BACKEND"` and makes it with the alias and the alias's dictionary; a failed import, and an alias `TASKS` lacks, raise `InvalidTaskBackend` (`django/tasks/__init__.py:TaskBackendHandler`). `default_task_backend` is a `ConnectionProxy` for `"default"`. `clear_tasks_handlers`, a receiver of `setting_changed`, empties the handler when `TASKS` changes (`django/tasks/signals.py:clear_tasks_handlers`).

`BaseTaskBackend.__init__` keeps the alias, the names under `"QUEUES"` as a set (`{"default"}` without the key) and the dictionary under `"OPTIONS"`. Flags, all false in the base, say what a backend can do: `BaseTaskBackend.supports_defer`, `BaseTaskBackend.supports_async_task`, `BaseTaskBackend.supports_priority` and `BaseTaskBackend.supports_get_result`, the last for results read from any thread or process (`django/tasks/backends/base.py:BaseTaskBackend`). A backend must implement `BaseTaskBackend.enqueue`; the base runs it for `BaseTaskBackend.aenqueue` through `sync_to_async`, and its `BaseTaskBackend.get_result` raises `NotImplementedError`. The system check `check_tasks` runs each backend's `BaseTaskBackend.check` (`django/tasks/checks.py:check_tasks`).

## The `task` decorator

`task` is used bare or with options (`django/tasks/base.py:task`). It makes an instance of the `BaseTaskBackend.task_class` of the backend under the alias from the function and the values for `Task.priority`, `Task.queue_name`, `Task.backend` and `Task.takes_context`. Since 6.1 any other keyword argument goes to that class too, for a subclass that declares it (`docs/releases/6.1.txt`). `Task.run_after` alone is refused: a `TypeError` says to set it with `Task.using`. So the backend is asked for, and the task validated, as the module that defines it is imported.

## `Task`

`Task` is a frozen dataclass with keyword-only fields: `Task.func`, `priority` (0), `backend` and `queue_name` (`"default"`), `run_after` (the earliest time to run) and `takes_context` (`django/tasks/base.py:Task`). `Task.using` returns a copy made by `dataclasses.replace`; an argument left at `None` keeps the old value, so it cannot take a `run_after` away.

A task holds its backend's alias, and `Task.get_backend` looks it up in `task_backends` at each call: a task enqueued from two threads goes to two instances of it, and after `TASKS` is overridden, to the new backend. `Task.enqueue` and `Task.aenqueue` hand the task and its arguments to it; `Task.get_result` asks it for a result by id, and raises `TaskResultMismatch` when the result is another function's. `Task.call` and `Task.acall` run the function in place, through `async_to_sync` or `sync_to_async` where it is of the other kind.

## Validation: `BaseTaskBackend.validate_task`

`Task.__post_init__` passes every new task to its backend's `BaseTaskBackend.validate_task`, so a task is checked when the decorator makes it, when `using` copies it and when it is unpickled; both built-in backends check it again in `enqueue` (`django/tasks/backends/base.py:BaseTaskBackend.validate_task`). Each check raises `InvalidTask`, in this order:

1. The function is a Python function whose qualified name holds no `"<locals>"` (`django/utils/inspect.py:is_module_level_function`).
2. A coroutine function needs `supports_async_task`.
3. With `takes_context`, the function's first parameter is named context.
4. A priority other than 0 needs `supports_priority`, and is a whole number from -100 to 100.
5. A `run_after` needs `supports_defer`, and with `USE_TZ` is an aware datetime.
6. The queue is one of `"QUEUES"`, unless that is an empty list.

## Arguments and return values as JSON

`TaskResult.__post_init__` passes the arguments through `normalize_json`, which keeps strings, integers, floats, booleans and `None`, makes mappings dictionaries and other sequences lists, decodes bytes as UTF-8, and refuses anything else with `TypeError`, bytes that will not decode with `ValueError` (`django/utils/json.py:normalize_json`). The result is made in `enqueue`, so a date is refused there, and a tuple reaches the function as a list; `ImmediateBackend` normalizes the return value too. The documentation's reason: both are serialized to JSON (`docs/topics/tasks.txt`).

## `TaskResult`

A `TaskResult` records one enqueueing: the task, a `TaskResult.id`, a `TaskResult.status`, the times it was enqueued, started, last attempted and finished, the arguments, the alias, `TaskResult.errors` and `TaskResult.worker_ids` (`django/tasks/base.py:TaskResult`). It is frozen, and the backends change it with `object.__setattr__`. The status is a `TaskResultStatus`: `TaskResultStatus.READY` when enqueued or ready to run again, `RUNNING`, `FAILED` when the function raised or could not start, `SUCCESSFUL`.

`TaskResult.return_value` gives the return value only for `SUCCESSFUL`, and otherwise raises `ValueError`, which, its docstring says, tells a task that did not succeed from one that returned `None`. `TaskResult.is_finished` is true for the final two statuses. `TaskResult.attempts` counts `worker_ids`; `TaskContext.attempt`, on the context passed first to a task with `takes_context`, reads it. `TaskResult.refresh` copies the status, times, errors, workers and return value of the backend's result (`django/tasks/base.py:TaskResult.refresh`).

A failure adds a `TaskError` to `errors`: the dotted path of the exception's class and the traceback as text. `TaskError.exception_class` imports the class only when asked, splitting the path at its last dot, so a class nested in another, as `Model.DoesNotExist` is, is not found (`django/tasks/base.py:TaskError.exception_class`, `django/utils/module_loading.py:import_string`).

## `ImmediateBackend`: run inside `enqueue`

`ImmediateBackend` supports coroutine functions and priorities, not `run_after` or reading results back. `ImmediateBackend.enqueue` validates the task, makes a `READY` result, runs it, and returns that same object (`django/tasks/backends/immediate.py:ImmediateBackend.enqueue`, `django/tasks/backends/immediate.py:ImmediateBackend._execute_task`):

1. It sets the time enqueued and sends `task_enqueued`.
2. It marks the result `RUNNING`, sets the start and attempt times, appends its `ImmediateBackend.worker_id` to `worker_ids`, and sends `task_started`.
3. It calls the function through `Task.call` with the normalized arguments, a `TaskContext` before them if the task takes one, and keeps the return value through `normalize_json`.
4. It lets `KeyboardInterrupt` through. Any other `BaseException`, a return value that will not normalize among them, becomes a `TaskError`, the result `FAILED`, and `task_finished` is sent inside the `except` block. An exception whose class is defined inside a function escapes instead, as the `ValueError` of `qualname`, which gives such a class no dotted path, and leaves the result `RUNNING` (`django/utils/module_loading.py:qualname`).
5. Otherwise the result becomes `SUCCESSFUL`, and `task_finished` is sent.

The signals' sender is the backend's class ([The signals Django sends](builtin-signals.md)). `django/tasks/signals.py` connects to each a receiver that logs to `"django.tasks"`: DEBUG on enqueueing, INFO on start and success, ERROR on failure with the exception, which `sys.exc_info` still holds because the signal is sent inside the handler, as the receiver's comment says (`django/tasks/signals.py:log_task_finished`). In a run of the example, a handler on that logger prints each record's level and the end of its message; voyage 99 does not exist:

```text
result = tell_harbour_master.enqueue(1)
  log DEBUG  enqueued backend=default
  log INFO   state=RUNNING
  log INFO   state=SUCCESSFUL
result.status  ->  'SUCCESSFUL'
result.return_value  ->  1

result = tell_harbour_master.enqueue(99)
  log DEBUG  enqueued backend=default
  log INFO   state=RUNNING
  log ERROR  state=FAILED, with the traceback
result.status  ->  'FAILED'
result.return_value  ->  raises ValueError: Task failed
result.errors[0].exception_class_path  ->  'harbour.fleet.models.Voyage.DoesNotExist'
result.errors[0].exception_class  ->  raises ModuleNotFoundError: No module named 'harbour.fleet.models.Voyage'; 'harbour.fleet.models' is not a package
```

The failure did not reach the caller, so a receiver such as voyage_saved would not have been interrupted by it.

## `DummyBackend`: kept, never run

`DummyBackend` supports deferring, coroutine functions and priorities, and runs nothing. `DummyBackend.enqueue` validates the task, makes a `READY` result, appends it to `DummyBackend.results`, sends `task_enqueued`, and returns a deep copy, "to prevent mutation issues", says the comment (`django/tasks/backends/dummy.py:DummyBackend.enqueue`). `DummyBackend.get_result` searches that list; results, another comment says, are scoped to the current thread, hence `supports_get_result` is false: each thread has its own instance. `DummyBackend.clear` empties the list. Here the alias reserve is a `DummyBackend`:

```text
with override_settings(TASKS={"default": ImmediateBackend, "reserve": DummyBackend}):
  held = tell_harbour_master.using(backend="reserve")
  result = held.enqueue(1)
    log DEBUG  enqueued backend=reserve
  result.status  ->  'READY'
  result.return_value  ->  raises ValueError: Task has not finished yet
  task_backends["reserve"].results[0] is result  ->  False
  held.get_result(result.id).status  ->  'READY'
  tell_harbour_master.get_result(result.id)  ->  raises NotImplementedError: This backend does not support retrieving or refreshing results.
  len(mail.outbox)  ->  0
```

Through tell_harbour_master, `Task.get_result` asked the task's own alias, `"default"`.

## Pickling a task

Since 6.1 a `Task` pickles as its fields, the function replaced by `Task.module_path`, its dotted path (`django/tasks/base.py:Task.__reduce__`). `Task._reconstruct` imports the path, expects the `Task` the decorator bound there, and takes its function; the task made again is validated against that process's backend for its alias. A `TaskResult` pickles with its task inside it (`docs/releases/6.1.txt`).
