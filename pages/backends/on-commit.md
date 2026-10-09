---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Work held until the commit: `on_commit`

`on_commit` registers a function to be called when the current transaction commits. The connection keeps such callbacks in `BaseDatabaseWrapper.run_on_commit`, each with the savepoints of the atomic blocks open when it was registered; `BaseDatabaseWrapper.run_and_clear_commit_hooks` calls them once the connection is back in autocommit after the commit, and a rollback to one of those savepoints, a rollback, and closing or opening the connection throw them away.

Some work has to follow a change to the database and must not happen unless the change is kept; Django's documentation gives a background task, an email and a cache invalidation as examples (`docs/topics/db/transactions.txt`). Code inside an atomic block cannot do such work itself, for it cannot know whether the transaction will commit: a block around it may yet roll back. `on_commit` hands the work to the connection, which keeps it beside the transaction's state ([Transactions: autocommit, `atomic` and savepoints](transactions.md)), runs it after the commit, and drops it with the rollback.

## Registering a callback

`django.db.transaction.on_commit` takes the function, an alias (`using=None` for `"default"`) and `robust=False`, and calls `BaseDatabaseWrapper.on_commit` on the alias's connection (`django/db/transaction.py:on_commit`). The method refuses anything that cannot be called with `TypeError`, and then does one of three things (`django/db/backends/base/base.py:BaseDatabaseWrapper.on_commit`). Inside an atomic block it appends a tuple to `BaseDatabaseWrapper.run_on_commit`: the set of the names in `BaseDatabaseWrapper.savepoint_ids`, the function, and the robust flag. Outside a block with autocommit off it raises `TransactionManagementError`. Outside a block in autocommit, where there is no transaction to wait for, it calls the function at once.

The recordings below ran on SQLite; in the first, a line at the margin is Python as it was run, the lines set in under it are the calls it set going, nested as they were made and only those the passage is about, `->` is what a call or a question returned, and a line `SQL` is a statement as Django handed it to its cursor. Two callbacks registered in an outermost block, the second inside an inner block:

```text recording=backends
transaction.on_commit(first_callback)
  BaseDatabaseWrapper.on_commit(first_callback)
connection.run_on_commit  ->  [(set(), the function first_callback, False)]
inner.__enter__()
  Atomic.__enter__
    BaseDatabaseWrapper.savepoint
      SQL SAVEPOINT "s(the thread)_x6"
      -> 's(the thread)_x6'
transaction.on_commit(second_callback)
  BaseDatabaseWrapper.on_commit(second_callback)
connection.run_on_commit  ->  [(set(), the function first_callback, False), ({'s(the thread)_x6'}, the function second_callback, False)]
```

An outermost block, the one no other open block contains, entered in autocommit turns autocommit off and puts nothing in `savepoint_ids`, so a callback registered in it, as the first was, has an empty set. Every other block puts its savepoint there, or `None` where it makes none: one made with `savepoint=False`, or entered while the transaction waits for a rollback. The set therefore holds the savepoint of every block then open, and rolling back to one drops the callbacks of the blocks inside it too (`django/db/transaction.py:Atomic.__enter__`).

## When the callbacks run

An inner block's exit leaves `BaseDatabaseWrapper.run_on_commit` as it is, unless it rolls back to its savepoint. Where the exit of an outermost block entered in autocommit commits, the callbacks run in its `finally`, as autocommit is turned on again (`django/db/transaction.py:Atomic.__exit__`):

```text recording=backends
inner.__exit__(None, None, None)
  Atomic.__exit__
    BaseDatabaseWrapper.savepoint_commit('s(the thread)_x6')
      SQL RELEASE SAVEPOINT "s(the thread)_x6"
connection.run_on_commit  ->  [(set(), the function first_callback, False), ({'s(the thread)_x6'}, the function second_callback, False)]
outer.__exit__(None, None, None)
  Atomic.__exit__
    BaseDatabaseWrapper.commit
      BaseDatabaseWrapper._commit
    BaseDatabaseWrapper.set_autocommit(autocommit=True)
      DatabaseWrapper._set_autocommit(True)
      BaseDatabaseWrapper.run_and_clear_commit_hooks
        first_callback runs
        second_callback runs
connection.run_on_commit  ->  []
```

`BaseDatabaseWrapper.commit` sets `BaseDatabaseWrapper.run_commit_hooks_on_set_autocommit_on`, and `BaseDatabaseWrapper.set_autocommit`, when it turns autocommit on with the flag set, calls `BaseDatabaseWrapper.run_and_clear_commit_hooks` and then clears the flag (`django/db/backends/base/base.py:BaseDatabaseWrapper.set_autocommit`). `run_and_clear_commit_hooks` refuses inside an atomic block, puts an empty list in the place of `run_on_commit`, and calls the callbacks it took, in the order they were registered (`django/db/backends/base/base.py:BaseDatabaseWrapper.run_and_clear_commit_hooks`). A callback runs with the transaction over, autocommit on and no block open: a query it makes is a transaction of its own, and a callback it registers with `on_commit` runs at once.

> **Why.** Django's documentation gives the reason the callbacks wait for autocommit and do not run in `commit` itself: a query made in a callback would otherwise open an implicit transaction and keep the connection from going back into autocommit (`docs/topics/db/transactions.txt`).

Under autocommit turned off by hand, an atomic block's callbacks are kept as in any other block, and its exit, which leaves the commit to the code, runs none of them (`django/db/transaction.py:Atomic.__exit__`). They run when the code calls `commit` and then turns autocommit on again; here a rollback comes between:

```text recording=backends
transaction.on_commit(second_callback)
  BaseDatabaseWrapper.on_commit(second_callback)
outer.__exit__(None, None, None)
  Atomic.__exit__
    BaseDatabaseWrapper.savepoint_commit('s(the thread)_x9')
      SQL RELEASE SAVEPOINT "s(the thread)_x9"
transaction.commit()
  BaseDatabaseWrapper.commit
    BaseDatabaseWrapper._commit
transaction.rollback()
  BaseDatabaseWrapper.rollback
    BaseDatabaseWrapper._rollback
connection.run_on_commit  ->  []
transaction.set_autocommit(True)
  BaseDatabaseWrapper.set_autocommit(autocommit=True)
    DatabaseWrapper._set_autocommit(True)
    BaseDatabaseWrapper.run_and_clear_commit_hooks
```

> **Trap.** `BaseDatabaseWrapper.rollback` empties the list even after a commit: a transaction committed by hand loses its callbacks to a rollback before autocommit is turned on again, and `run_and_clear_commit_hooks` finds nothing to run.

## What throws the callbacks away

`BaseDatabaseWrapper.savepoint_rollback` keeps only the tuples of `BaseDatabaseWrapper.run_on_commit` whose set does not hold the savepoint's name (`django/db/backends/base/base.py:BaseDatabaseWrapper.savepoint_rollback`). A savepoint made with `savepoint_create` is in no set, and rolling back to it drops nothing; rolling back to a block's takes the callbacks registered while the block was open:

```text recording=backends
connection.run_on_commit  ->  [(set(), the function first_callback, False), ({'s(the thread)_x7'}, the function second_callback, False)]
inner.__exit__(ValueError, ValueError('no berth'), None)
  Atomic.__exit__(exc_type=ValueError)
    BaseDatabaseWrapper.savepoint_rollback('s(the thread)_x7')
      SQL ROLLBACK TO SAVEPOINT "s(the thread)_x7"
    BaseDatabaseWrapper.savepoint_commit('s(the thread)_x7')
      SQL RELEASE SAVEPOINT "s(the thread)_x7"
connection.run_on_commit  ->  [(set(), the function first_callback, False)]
```

`BaseDatabaseWrapper.rollback` empties the list, so a transaction rolled back, by its outermost block or by hand, runs none of its callbacks (`django/db/backends/base/base.py:BaseDatabaseWrapper.rollback`). `BaseDatabaseWrapper.close` empties it before it looks for a connection to close, even where it then finds none, though SQLite's `close` does not call it for a database in memory (`django/db/backends/base/base.py:BaseDatabaseWrapper.close`, `django/db/backends/sqlite3/base.py:DatabaseWrapper.close`); and `BaseDatabaseWrapper.connect` empties it last, after sending `connection_created` (`django/db/backends/base/base.py:BaseDatabaseWrapper.connect`; [Opening and closing a connection](lifecycle.md)). Outside a block a callback runs at once; inside one, a rollback drops it; and with autocommit turned off by hand and no block open, `on_commit` refuses:

```text recording=backends
transaction.on_commit(first_callback)
  BaseDatabaseWrapper.on_commit(first_callback)
    first_callback runs
outer.__enter__()
transaction.on_commit(second_callback)
  BaseDatabaseWrapper.on_commit(second_callback)
outer.__exit__(ValueError, ValueError('no berth'), None)
  Atomic.__exit__(exc_type=ValueError)
    BaseDatabaseWrapper.rollback
      BaseDatabaseWrapper._rollback
    BaseDatabaseWrapper.set_autocommit(autocommit=True)
      DatabaseWrapper._set_autocommit(True)
connection.run_on_commit  ->  []
transaction.set_autocommit(False)
transaction.on_commit(first_callback)  ->  raises TransactionManagementError: on_commit() cannot be used in manual transaction management
```

## A callback that fails, and `robust=True`

A callback registered with `robust=True` is called inside a `try`: an `Exception` from it is logged with its traceback to the logger `"django.db.backends.base"`, and the next callback runs (`django/db/backends/base/base.py:BaseDatabaseWrapper.run_and_clear_commit_hooks`). A line beginning log is that logger's record:

```text recording=backends
transaction.on_commit(failing_callback, robust=True)
  BaseDatabaseWrapper.on_commit(failing_callback, robust=True)
transaction.on_commit(second_callback)
  BaseDatabaseWrapper.on_commit(second_callback)
outer.__exit__(None, None, None)
  Atomic.__exit__
    BaseDatabaseWrapper.commit
      BaseDatabaseWrapper._commit
    BaseDatabaseWrapper.set_autocommit(autocommit=True)
      DatabaseWrapper._set_autocommit(True)
      BaseDatabaseWrapper.run_and_clear_commit_hooks
        log django.db.backends.base ERROR: Error calling failing_callback in on_commit() during transaction (the callback failed).
        second_callback runs
```

Registered without `robust=True`, a failing callback's exception leaves `BaseDatabaseWrapper.run_and_clear_commit_hooks`, then `BaseDatabaseWrapper.set_autocommit`, then the `finally` of the outermost block's `Atomic.__exit__`, and the `with` statement raises it (`django/db/transaction.py:Atomic.__exit__`). The callbacks after the failing one were held only in the list `run_and_clear_commit_hooks` took, and are gone:

```text recording=backends
transaction.on_commit(failing_callback)
  BaseDatabaseWrapper.on_commit(failing_callback)
transaction.on_commit(second_callback)
  BaseDatabaseWrapper.on_commit(second_callback)
outer.__exit__(None, None, None)
  Atomic.__exit__
    BaseDatabaseWrapper.commit
      BaseDatabaseWrapper._commit
    BaseDatabaseWrapper.set_autocommit(autocommit=True)
      DatabaseWrapper._set_autocommit(True)
      BaseDatabaseWrapper.run_and_clear_commit_hooks  raises ValueError
raises ValueError: the callback failed
connection.run_on_commit  ->  []
```

Django's documentation likens this to calling the functions one after another without `on_commit`: a failure stops the ones after it (`docs/topics/db/transactions.txt`). The function `on_commit` calls at once, outside a block, is treated the same way (`django/db/backends/base/base.py:BaseDatabaseWrapper.on_commit`).

> **Trap.** An exception from a block's end is not always a rollback. A callback that fails without `robust=True` makes the `with` statement raise after the transaction has committed, and the work of the block is in the database.

## In tests

Where its databases support transactions, `TestCase` runs each test inside an atomic block that it rolls back, so no transaction of a test commits and no callback runs (`django/test/testcases.py:TestCase._fixture_setup`). `TestCase.captureOnCommitCallbacks` collects the callbacks added to `BaseDatabaseWrapper.run_on_commit` on an alias while its body runs and, with `execute=True`, calls them as it leaves, logging the failure of a robust one. It calls them inside the test's block, where a callback that registers another only adds it to the list, so it goes on until those it called have added no more (`django/test/testcases.py:TestCase.captureOnCommitCallbacks`). [The test framework](../testing.md) has the rest.
