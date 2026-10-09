---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Transactions: autocommit, `atomic` and savepoints

Django runs a connection in **autocommit**, each statement a transaction of its own, until code asks for more with `atomic`, and the code it wraps is an **atomic block**. `Atomic.__enter__` and `Atomic.__exit__` turn atomic blocks nested one inside another into a single transaction, with a **savepoint**, a named point in the transaction that can be rolled back to without undoing what came before it, for each inner block that asks for one. They keep their state on the connection, where `BaseDatabaseWrapper.needs_rollback` marks a transaction that must be rolled back.

A database makes its changes in transactions, which become visible to others all at once when they commit and are undone when they roll back. PEP 249, which Django's drivers follow, has a driver open its connection with autocommit off, so that statements gather in a transaction until the program commits; `BaseDatabaseWrapper.connect` turns autocommit on, unless the alias's `"AUTOCOMMIT"` is `False` (`django/db/backends/base/base.py:BaseDatabaseWrapper.connect`). Django's documentation gives the reason: the SQL standard has each statement begin a transaction that must be committed or rolled back explicitly, which is not always convenient, and most databases offer autocommit to spare it (`docs/topics/db/transactions.txt`).

Code that needs several statements to stand or fall together wraps them in `atomic`, as a `with` statement or a decorator. The **outermost block**, the one no other open block contains, begins a transaction as it is entered where autocommit is on, and as it is left commits it, or rolls it back where an exception is leaving or the transaction is marked broken. A block entered inside another makes a savepoint, unless it was made with `savepoint=False` or the transaction is already marked broken, and as it is left releases the savepoint, or rolls back to it and then releases it, so that a failure in an inner block undoes that block's work alone (`django/db/transaction.py:Atomic`).

```text figure=nested-blocks
the blocks                     step                  sent                            the connection afterwards

with atomic():       outer     enter                 BEGIN                           in_atomic_block=True, atomic_blocks=[outer]
  with atomic():     inner     enter                 SAVEPOINT "s(the thread)_x1"    savepoint_ids=["s(the thread)_x1"]
                               exit                  RELEASE SAVEPOINT               savepoint_ids=[]
                               exit, an exception    ROLLBACK TO SAVEPOINT,
                                                     then RELEASE SAVEPOINT          savepoint_ids=[]
  with atomic(savepoint=False):
                     unsaved   enter                 nothing                         savepoint_ids=[None]
                               exit, an exception    nothing                         needs_rollback=True
                     outer     exit                  COMMIT                          in_atomic_block=False, atomic_blocks=[]
                               exit, an exception    ROLLBACK                        in_atomic_block=False, needs_rollback=False
                               or needs_rollback set
                               then, either way      nothing                         autocommit=True
```

*Two blocks inside an outer one, the second made with `savepoint=False`, and the ways out of each, as recorded on SQLite. Other backends send other things: Django sends no `"BEGIN"` of its own there but turns the driver's autocommit off, and on Oracle a release sends nothing.*

The state is the connection's, not the `Atomic` object's. The class's docstring says why: the same instance can be entered again, as a decorator or in several `with` statements, even while it is open, and since each thread has connections of its own this is safe across threads. What `on_commit` keeps beside it is [Work held until the commit: `on_commit`](on-commit.md).

## Autocommit: a statement is its own transaction

`"AUTOCOMMIT"` is `True` unless an alias says otherwise ([Connections by alias: `DATABASES` and `ConnectionHandler`](connections.md)), and `BaseDatabaseWrapper.connect` hands it to `BaseDatabaseWrapper.set_autocommit` as soon as the driver's connection is open ([Opening and closing a connection](lifecycle.md)). `set_autocommit` refuses inside an atomic block, which Django's documentation says would break atomicity: `BaseDatabaseWrapper.validate_no_atomic_block` raises `TransactionManagementError` (`django/db/backends/base/base.py:BaseDatabaseWrapper.set_autocommit`). Turning autocommit on, it calls the backend's `BaseDatabaseWrapper._set_autocommit` with `True`; turning it off, it calls it with `False`, inside `debug_transaction`, which logs a `"BEGIN"` where queries are logged ([Cursors: executing a statement, the query log and execute wrappers](cursors.md)); and given `force_begin_transaction_with_broken_autocommit=True`, which only `Atomic.__enter__` passes, it begins a transaction with the backend's own method instead, where the backend has one, as SQLite's does, and leaves the driver's autocommit as it was. It records the value it was given in `BaseDatabaseWrapper.autocommit`, which `BaseDatabaseWrapper.get_autocommit` returns, and where it turned autocommit on after a commit, it runs the callbacks of `on_commit`. Both `set_autocommit` and `get_autocommit` open the driver's connection first if it is not open.

The recordings on this page ran on SQLite: a line at the margin is Python as it was run, with `->` before what it returned, the lines set in under it are the calls it set going, a line `SQL` is a statement as Django handed it to its cursor, and a line that begins sqlite is the statement as SQLite ran it. In the plain case:

```text recording=backends
connection.get_autocommit()  ->  True
connection.autocommit  ->  True
connection.connection.isolation_level  ->  None
Port.objects.create(name='Cork', country='Ireland')
  mark_for_rollback_on_error
  SQL INSERT INTO "fleet_port" ("name", "country") VALUES (%s, %s) RETURNING "fleet_port"."id" with params ('Cork', 'Ireland')
  sqlite INSERT INTO "fleet_port" ("name", "country") VALUES ('Cork', 'Ireland') RETURNING "fleet_port"."id"
  mark_for_rollback_on_error resumes
```

SQLite's driver is in its own autocommit when its connection's isolation_level is `None`. The create sent one `"INSERT"` and nothing began or committed it: SQLite committed the statement as it ended. A model whose parent has a table of its own is saved table by table, and `Model.save_base` wraps that save in `atomic(savepoint=False)` (`django/db/models/base.py:Model.save_base`). Where a failure is to be caught and recovered from, as in `QuerySet.get_or_create`, the ORM uses a plain `atomic` ([Creating, updating and deleting through a queryset](../querysets/writing.md)).

## Turning autocommit off and on, backend by backend

`BaseDatabaseWrapper._set_autocommit` raises `NotImplementedError`, and each backend's throws the driver's own switch (`django/db/backends/base/base.py:BaseDatabaseWrapper._set_autocommit`). PostgreSQL's and Oracle's set the autocommit attribute of the driver's connection, and MySQL's calls the driver connection's autocommit method (`django/db/backends/postgresql/base.py:DatabaseWrapper._set_autocommit`, `django/db/backends/mysql/base.py:DatabaseWrapper._set_autocommit`, `django/db/backends/oracle/base.py:DatabaseWrapper._set_autocommit`). On these three, turning autocommit off is the whole of beginning a transaction: Django sends no statement, and the transaction begins with the next one.

SQLite's `DatabaseWrapper._set_autocommit` sets the driver connection's isolation_level, to `None` for autocommit and to the empty string, the driver's own default, for none (`django/db/backends/sqlite3/base.py:DatabaseWrapper._set_autocommit`). An atomic block calls it only as an outermost block ends, to turn autocommit on again. SQLite's backend is the one of the four with `DatabaseWrapper._start_transaction_under_autocommit`, which sends `"BEGIN"` through Django's cursor, with the mode that `"OPTIONS"` names as `"transaction_mode"` where it names one ([SQLite](sqlite.md)), and leaves the driver in its autocommit (`django/db/backends/sqlite3/base.py:DatabaseWrapper._start_transaction_under_autocommit`). Its docstring gives the reason: staying in autocommit works around a bug of the driver that breaks savepoints when autocommit is disabled, the bug being, in the comment on SQLite's `DatabaseWrapper._savepoint_allowed`, that the driver commits before each savepoint unless isolation_level is `None`. So on SQLite a block's `"BEGIN"` is Django's statement, an `SQL` line in the recordings, and its commit is the driver's.

`BaseDatabaseWrapper.commit` and `BaseDatabaseWrapper.rollback` refuse inside a block as `set_autocommit` does, and call the backend's `BaseDatabaseWrapper._commit` or `BaseDatabaseWrapper._rollback`, which call the driver connection's own. `commit` also sets `BaseDatabaseWrapper.run_commit_hooks_on_set_autocommit_on`; `rollback` sets `BaseDatabaseWrapper.needs_rollback` back to `False` and empties `BaseDatabaseWrapper.run_on_commit` (`django/db/backends/base/base.py:BaseDatabaseWrapper.commit`, `django/db/backends/base/base.py:BaseDatabaseWrapper.rollback`).

## What the connection keeps

`BaseDatabaseWrapper.__init__` sets the state on each connection, autocommit starting as `False`, PEP 249's default (`django/db/backends/base/base.py:BaseDatabaseWrapper.__init__`).

| attribute | what it holds |
|---|---|
| `BaseDatabaseWrapper.autocommit` | whether autocommit is on, as `set_autocommit` last left it |
| `BaseDatabaseWrapper.in_atomic_block` | whether an atomic block is open, or an outermost block pretends one is |
| `BaseDatabaseWrapper.savepoint_ids` | a stack with an entry for each block entered inside a transaction: its savepoint's name, or `None` |
| `BaseDatabaseWrapper.atomic_blocks` | a stack of the open `Atomic` objects |
| `BaseDatabaseWrapper.commit_on_exit` | whether the outermost block commits as it ends: `False` where autocommit was off when it was entered |
| `BaseDatabaseWrapper.needs_rollback` | that the transaction is broken, and no statement may be sent until a rollback |
| `BaseDatabaseWrapper.rollback_exc` | the exception `mark_for_rollback_on_error` last stored, inside an atomic block, given as the cause when a statement is refused |
| `BaseDatabaseWrapper.savepoint_state` | the counter that numbers savepoints |
| `BaseDatabaseWrapper.closed_in_transaction` | that the connection was closed inside a block |

*A connection's transaction state. `BaseDatabaseWrapper.connect` empties the two stacks and sets `in_atomic_block`, `needs_rollback` and `closed_in_transaction` to `False`; `commit_on_exit`, `rollback_exc` and `savepoint_state` it leaves.*

## The functions of `django.db.transaction`

Apart from `atomic`, `mark_for_rollback_on_error` and `non_atomic_requests`, each told in a section of its own, the functions of `django.db.transaction` each take an alias, `using=None` meaning `"default"`, find the connection with `get_connection`, and call the connection's method of the same name; `savepoint_create` calls `BaseDatabaseWrapper.savepoint`, and the deprecated `savepoint` calls `savepoint_create` (`django/db/transaction.py`). The checks are all the connection's; the functions add none.

## Entering a block: `Atomic.__enter__`

`atomic(using=None, savepoint=True, durable=False)` makes an `Atomic` of its three arguments; called with a function in place of an alias, as the bare decorator `@atomic` is, it wraps the function in an `Atomic` for `"default"` (`django/db/transaction.py:atomic`). `Atomic` is a `contextlib.ContextDecorator`, so as a decorator it enters itself around each call.

`Atomic.__enter__` goes in four steps (`django/db/transaction.py:Atomic.__enter__`):

1. A durable block is refused where another is open, unless the innermost open block is one that `TestCase` opened.
2. Where no block is open, this block is the outermost: it sets `BaseDatabaseWrapper.commit_on_exit` to `True` and `BaseDatabaseWrapper.needs_rollback` to `False`. If autocommit is already off, it also sets `BaseDatabaseWrapper.in_atomic_block` and sets `commit_on_exit` to `False`: it pretends to be inside a block already, so as to bypass the code that turns autocommit off.
3. Inside an open block, real or pretended, it asks for a savepoint and pushes the name onto `BaseDatabaseWrapper.savepoint_ids`, or pushes `None` where it was made with `savepoint=False` or the transaction is already marked broken, which avoids a useless savepoint and keeps `needs_rollback` from being overwritten before the rollback is done. With no block open, it begins the transaction through `BaseDatabaseWrapper.set_autocommit` and sets `in_atomic_block`.
4. It pushes itself onto `BaseDatabaseWrapper.atomic_blocks`.

Two blocks entered as a `with` statement enters them:

```text recording=backends
outer = transaction.atomic()
inner = transaction.atomic()
the connection holds: in_atomic_block=False, savepoint_ids=[], atomic_blocks=[], commit_on_exit=True, needs_rollback=False
outer.__enter__()
  Atomic.__enter__
    BaseDatabaseWrapper.set_autocommit(autocommit=False, force_begin_transaction_with_broken_autocommit=True)
      DatabaseWrapper._start_transaction_under_autocommit
        SQL BEGIN
        sqlite BEGIN
the connection holds: in_atomic_block=True, savepoint_ids=[], atomic_blocks=[an Atomic], commit_on_exit=True, needs_rollback=False
...
inner.__enter__()
  Atomic.__enter__
    BaseDatabaseWrapper.savepoint
      SQL SAVEPOINT "s(the thread)_x1"
      sqlite SAVEPOINT "s(the thread)_x1"
      -> 's(the thread)_x1'
the connection holds: in_atomic_block=True, savepoint_ids=['s(the thread)_x1'], atomic_blocks=[an Atomic, an Atomic], commit_on_exit=True, needs_rollback=False
```

## Savepoints

`BaseDatabaseWrapper.savepoint` makes a savepoint and returns its name, or returns `None` and sends nothing where `BaseDatabaseWrapper._savepoint_allowed` says no (`django/db/backends/base/base.py:BaseDatabaseWrapper.savepoint`). The name is `"s"`, the thread's number without its sign, `"_x"`, and the connection's counter `BaseDatabaseWrapper.savepoint_state`, which only `BaseDatabaseWrapper.clean_savepoints` sets back to 0. The statement is written by the connection's operations object (`BaseDatabaseWrapper.ops`): `BaseDatabaseOperations.savepoint_create_sql` writes `"SAVEPOINT"` and the name quoted by `quote_name`, and its siblings `BaseDatabaseOperations.savepoint_commit_sql` and `BaseDatabaseOperations.savepoint_rollback_sql` write `"RELEASE SAVEPOINT"` and `"ROLLBACK TO SAVEPOINT"`; none of the four backends overrides them (`django/db/backends/base/operations.py:BaseDatabaseOperations.savepoint_create_sql`). `BaseDatabaseWrapper.savepoint_commit` and `BaseDatabaseWrapper.savepoint_rollback` send the other two behind the same check, and `savepoint_rollback` also drops the callbacks of `on_commit` registered while the savepoint was on `BaseDatabaseWrapper.savepoint_ids`, where one made with `savepoint_create` of `django.db.transaction` never is ([Work held until the commit: `on_commit`](on-commit.md)).

The check is the flag `BaseDatabaseFeatures.uses_savepoints`, one of the connection's features, and autocommit off, a comment saying savepoints cannot be made outside a transaction (`django/db/backends/base/base.py:BaseDatabaseWrapper._savepoint_allowed`). SQLite's asks for `BaseDatabaseWrapper.in_atomic_block` instead, its comment saying that with autocommit on savepoints make no sense, except inside atomic blocks (`django/db/backends/sqlite3/base.py:DatabaseWrapper._savepoint_allowed`). So on SQLite `savepoint_create` outside a block returns `None` even with autocommit turned off by hand, where the other backends make the savepoint:

```text recording=backends
transaction.set_autocommit(False)
...
connection.in_atomic_block  ->  False
sid = transaction.savepoint_create()
  BaseDatabaseWrapper.savepoint
    DatabaseWrapper._savepoint_allowed  ->  False
    -> None
```

`uses_savepoints` is `True` on all four backends ([What a database can do: `BaseDatabaseFeatures`](features.md)). Oracle's backend never sends `"RELEASE SAVEPOINT"`: its `DatabaseWrapper._savepoint_commit` sends nothing and, where queries are logged, logs a line marked as faked, the comment saying that Oracle cannot release savepoints and that the line keeps the count of queries the same as on the other backends (`django/db/backends/oracle/base.py:DatabaseWrapper._savepoint_commit`).

> **Deprecated.** `django.db.transaction.savepoint` warns with `RemovedInDjango2028Warning` and calls `savepoint_create`. The release notes of 6.1 deprecate it in favour of `savepoint_create`, and the deprecation timeline removes it in 2028 (`django/db/transaction.py:savepoint`, `docs/releases/6.1.txt`).

## Leaving a block: `Atomic.__exit__`

`Atomic.__exit__` first takes the block off the stacks: it pops `BaseDatabaseWrapper.atomic_blocks`, and pops the block's entry from `BaseDatabaseWrapper.savepoint_ids` where that stack has one (`django/db/transaction.py:Atomic.__exit__`). Where that stack is empty, the block is an outermost block that turned autocommit off, and `BaseDatabaseWrapper.in_atomic_block` is set to `False` at once; the comment says this is to allow `BaseDatabaseWrapper.commit` and `BaseDatabaseWrapper.rollback`, which refuse inside a block. Then it takes one of three branches, and a `finally` finishes an outermost block. The first is for a connection closed inside a block, whose transaction the database rolls back by itself: each exit does nothing more, and the outermost's `finally` sets the driver's connection to `None` ([Closed inside an atomic block](lifecycle.md#closed-inside-an-atomic-block)). `__exit__` returns nothing, so an exception that was leaving the block goes on leaving it: `atomic` undoes work for an exception and never swallows one.

With no exception and `BaseDatabaseWrapper.needs_rollback` unset, an inner block releases its savepoint, where it made one, and an outermost block that turned autocommit off commits. The `finally` then turns autocommit on again, calling `BaseDatabaseWrapper.set_autocommit` with `True`, which runs the callbacks of `on_commit`:

```text recording=backends
inner.__exit__(None, None, None)
  Atomic.__exit__
    BaseDatabaseWrapper.savepoint_commit('s(the thread)_x1')
      SQL RELEASE SAVEPOINT "s(the thread)_x1"
      sqlite RELEASE SAVEPOINT "s(the thread)_x1"
the connection holds: in_atomic_block=True, savepoint_ids=[], atomic_blocks=[an Atomic], commit_on_exit=True, needs_rollback=False
outer.__exit__(None, None, None)
  Atomic.__exit__
    BaseDatabaseWrapper.commit
      BaseDatabaseWrapper._commit
        sqlite3.Connection.commit
          sqlite COMMIT
    BaseDatabaseWrapper.set_autocommit(autocommit=True)
      DatabaseWrapper._set_autocommit(True)
the connection holds: in_atomic_block=False, savepoint_ids=[], atomic_blocks=[], commit_on_exit=True, needs_rollback=False
connection.get_autocommit()  ->  True
```

### A block an exception leaves

With an exception leaving, or with `needs_rollback` set and none leaving, `__exit__` first sets `needs_rollback` to `False`, to be set again, the comment says, if there is no savepoint to roll back to at this level. An inner block with a savepoint rolls back to it and then releases it, the comment saying the savepoint will not be used again and releasing it spares the database server the overhead. An outermost block that turned autocommit off rolls the transaction back. Here the outer block has created the port Wick and the inner block Thurso, and an exception is handed to the inner block as a `with` statement hands it:

```text recording=backends
inner.__exit__(ValueError, ValueError('no berth'), None)
  Atomic.__exit__(exc_type=ValueError)
    BaseDatabaseWrapper.savepoint_rollback('s(the thread)_x2')
      SQL ROLLBACK TO SAVEPOINT "s(the thread)_x2"
      sqlite ROLLBACK TO SAVEPOINT "s(the thread)_x2"
    BaseDatabaseWrapper.savepoint_commit('s(the thread)_x2')
      SQL RELEASE SAVEPOINT "s(the thread)_x2"
      sqlite RELEASE SAVEPOINT "s(the thread)_x2"
the connection holds: in_atomic_block=True, savepoint_ids=[], atomic_blocks=[an Atomic], commit_on_exit=True, needs_rollback=False
...
sorted(Port.objects.filter(name__in=['Wick', 'Thurso']).values_list('name', flat=True))  ->  ['Wick']
```

An inner block without a savepoint has nothing of its own to roll back to: it sets `needs_rollback`, and the rollback passes to the next block out that can do it. Until one does, the connection refuses statements. Here the outer block created the port Lerwick and the unsaved block Kirkwall, in lines left out:

```text recording=backends
unsaved.__enter__()
  Atomic.__enter__  (an Atomic made with savepoint=False)
the connection holds: in_atomic_block=True, savepoint_ids=[None], atomic_blocks=[an Atomic, an Atomic], commit_on_exit=True, needs_rollback=False
unsaved.__exit__(ValueError, ValueError('no berth'), None)
  Atomic.__exit__(exc_type=ValueError)
the connection holds: in_atomic_block=True, savepoint_ids=[], atomic_blocks=[an Atomic], commit_on_exit=True, needs_rollback=True
Port.objects.count()
  SQL SELECT COUNT(*) AS "__count" FROM "fleet_port"
raises TransactionManagementError: An error occurred in the current transaction. You can't execute queries until the end of the 'atomic' block.
outer.__exit__(None, None, None)
  Atomic.__exit__
    BaseDatabaseWrapper.rollback
      BaseDatabaseWrapper._rollback
        sqlite3.Connection.rollback
          sqlite ROLLBACK
...
sorted(Port.objects.filter(name__in=['Lerwick', 'Kirkwall']).values_list('name', flat=True))  ->  []
```

The count was refused before it reached SQLite, and the outer block rolled back though no exception left it, taking with it Lerwick as well as Kirkwall.

### When the release, the commit or the rollback fails

A release that raises `DatabaseError` is answered with a rollback to the savepoint and a release, and the `DatabaseError` is raised again; where those raise too, `needs_rollback` is set, which the comment says marks the transaction for a rollback at a higher level without hiding the first exception, and a failed rollback to a savepoint in the exception branch sets it too. A commit that raises `DatabaseError` is answered with a rollback before it is raised again. Where a rollback of the transaction raises, there or in the exception branch, the connection is closed (SQLite's backend ignores this for an in-memory database), the comment saying that an error during a rollback means something went wrong with the connection, and the `finally`'s `set_autocommit(True)`, finding no driver's connection, opens a new one. Here a stand-in for the driver's connection raises at the commit and at the rollback; the calls of the block's entry and query are left out:

```text recording=backends
with transaction.atomic(): Port.objects.count()
  Atomic.__exit__
    BaseDatabaseWrapper.commit
      BaseDatabaseWrapper._commit
        FailingDriverConnection.commit  raises sqlite3.OperationalError
        raises OperationalError
    BaseDatabaseWrapper.rollback
      BaseDatabaseWrapper._rollback
        FailingDriverConnection.rollback  raises sqlite3.OperationalError
        raises OperationalError
    DatabaseWrapper.close
...
    BaseDatabaseWrapper.set_autocommit(autocommit=True)
      BaseDatabaseWrapper.connect
...
raises OperationalError: disk I/O error
```

## `needs_rollback`: a transaction marked broken

`BaseDatabaseWrapper.needs_rollback` marks a transaction as past use, as one in which a statement has failed may be. Django's documentation says that on PostgreSQL every later statement in it fails until the transaction ends, and that after a `DatabaseError` inside a block the transaction is broken and is rolled back at the block's end (`docs/topics/db/transactions.txt`). Django refuses such statements itself, on every backend: `CursorWrapper._execute`, `CursorWrapper._executemany` and `CursorWrapper.callproc` each call `BaseDatabaseWrapper.validate_no_broken_transaction` before the statement reaches the driver, and while `needs_rollback` is set it raises `TransactionManagementError` from `BaseDatabaseWrapper.rollback_exc` (`django/db/backends/utils.py:CursorWrapper._execute`, `django/db/backends/base/base.py:BaseDatabaseWrapper.validate_no_broken_transaction`).

- The mark is set by an exit with no savepoint to roll back to, by the failure of a rollback to a savepoint or of the release that follows one, by `BaseDatabaseWrapper.close` inside a block, by `set_rollback(True)` and by `mark_for_rollback_on_error`.
- It is cleared by a rollback: the exit of a block with a savepoint or of an outermost block that turned autocommit off, or `BaseDatabaseWrapper.rollback` under autocommit turned off by hand. `set_rollback(False)` clears it without one, and so do an outermost block's entry and `BaseDatabaseWrapper.connect`.

Catching the exception inside the block does not clear it. Here a create inside a block makes a second ship named Petrel at the first one's home port, which a unique constraint on a ship's name and home port forbids, and the exception is caught there:

```text recording=backends
Ship.objects.create(name='Petrel', tonnage=480, home_id=petrel.home_id)
  mark_for_rollback_on_error
  mark_for_rollback_on_error resumes
    raises IntegrityError
raises IntegrityError: UNIQUE constraint failed: fleet_ship.name, fleet_ship.home_id
connection.needs_rollback  ->  True
type(connection.rollback_exc)  ->  django.db.utils.IntegrityError
Port.objects.count()
  SQL SELECT COUNT(*) AS "__count" FROM "fleet_port"
raises TransactionManagementError: An error occurred in the current transaction. You can't execute queries until the end of the 'atomic' block.
type(caught)  ->  django.db.transaction.TransactionManagementError
type(caught.__cause__)  ->  django.db.utils.IntegrityError
```

Only `mark_for_rollback_on_error` sets `rollback_exc`, and nothing sets it back to `None`: where an exit set the mark, as the unsaved block's did above, the refusal gives as its cause whatever exception was stored last, in this transaction or an earlier one.

## `mark_for_rollback_on_error`

`mark_for_rollback_on_error` is a context manager that opens nothing: it lets an exception pass through and, on its way, where it is an `Exception` and an atomic block is open, sets `BaseDatabaseWrapper.needs_rollback` and stores the exception as `BaseDatabaseWrapper.rollback_exc` (`django/db/transaction.py:mark_for_rollback_on_error`). Its docstring gives it as equivalent to running the code bare under autocommit and inside `atomic(savepoint=False)` otherwise, and says `Model.save` and its kin need it to avoid starting a transaction under autocommit when a single query is executed. Its callers are `Model.save_base` for a model without parents, `QuerySet.update`, and `Collector.delete` where it deletes one object that can be deleted fast (`django/db/models/query.py:QuerySet.update`, `django/db/models/deletion.py:Collector.delete`).

## `set_rollback` and `get_rollback`

`BaseDatabaseWrapper.set_rollback` sets `BaseDatabaseWrapper.needs_rollback` by hand and `BaseDatabaseWrapper.get_rollback` returns it; both raise `TransactionManagementError` outside an atomic block, with the message that the rollback flag does not work outside one (`django/db/backends/base/base.py:BaseDatabaseWrapper.set_rollback`). The docstring of `django.db.transaction.set_rollback` says what each value is for: `True` makes the innermost enclosing block made with `savepoint=True`, the default, roll back as it exits, without an exception; `False` prevents that rollback, and is to be used only after rolling back to a known-good state, as otherwise the block is broken and data may be corrupted (`django/db/transaction.py:set_rollback`). In an outermost block, with no exception:

```text recording=backends
transaction.set_rollback(True)
the connection holds: in_atomic_block=True, savepoint_ids=[], atomic_blocks=[an Atomic], commit_on_exit=True, needs_rollback=True
outer.__exit__(None, None, None)
  Atomic.__exit__
    BaseDatabaseWrapper.rollback
      BaseDatabaseWrapper._rollback
        sqlite3.Connection.rollback
          sqlite ROLLBACK
```

## Durable blocks

`atomic(durable=True)` makes a block that must be outermost: `Atomic.__enter__` raises `RuntimeError` where a block is already open, before it changes anything (`django/db/transaction.py:Atomic.__enter__`). The docstring gives what this guarantees, that the changes made in a durable block are committed when it exits without an error, which holds where autocommit was on as the block was entered and nothing has marked the transaction for rollback. The outer block, entered first, is left by the exception and rolls back:

```text recording=backends
with transaction.atomic(), transaction.atomic(durable=True): pass
  Atomic.__enter__
    BaseDatabaseWrapper.set_autocommit(autocommit=False, force_begin_transaction_with_broken_autocommit=True)
      DatabaseWrapper._start_transaction_under_autocommit
        SQL BEGIN
        sqlite BEGIN
  Atomic.__enter__  (an Atomic made with durable=True)  raises RuntimeError
  Atomic.__exit__(exc_type=RuntimeError)
    BaseDatabaseWrapper.rollback
      BaseDatabaseWrapper._rollback
        sqlite3.Connection.rollback
          sqlite ROLLBACK
    BaseDatabaseWrapper.set_autocommit(autocommit=True)
      DatabaseWrapper._set_autocommit(True)
raises RuntimeError: A durable atomic block cannot be nested within another atomic block.
```

The check looks only at the innermost open block, and lets the durable block through where that block's `Atomic._from_testcase` is set. `TestCase` sets it on the blocks it opens around a class of tests and around each test, so a durable block that code under a test opens directly inside them is let through, and one opened inside another block of the test's code is refused (`django/test/testcases.py:TestCase._enter_atomics`) ([The test framework](../testing.md)).

## Autocommit turned off by hand

`django.db.transaction.set_autocommit(False)` turns autocommit off with no block open, and leaves the transaction to the code: Django sends nothing to begin it, and the code ends it with `commit` or `rollback`. On SQLite the driver's isolation_level becomes the empty string, and the driver sends a `"BEGIN"` of its own before the first statement that changes a row:

```text recording=backends
transaction.set_autocommit(False)
  BaseDatabaseWrapper.set_autocommit(autocommit=False)
    debug_transaction(connection, 'BEGIN')
    DatabaseWrapper._set_autocommit(False)
    debug_transaction resumes
connection.connection.isolation_level  ->  ''
Port.objects.create(name='Mallaig', country='Scotland')
  SQL INSERT INTO "fleet_port" ("name", "country") VALUES (%s, %s) RETURNING "fleet_port"."id" with params ('Mallaig', 'Scotland')
  sqlite BEGIN
  sqlite INSERT INTO "fleet_port" ("name", "country") VALUES ('Mallaig', 'Scotland') RETURNING "fleet_port"."id"
```

An atomic block entered later, with autocommit still off, pretends, as its entry does in that case: `BaseDatabaseWrapper.commit_on_exit` is `False`, and even the outermost block makes a savepoint, unless it was made with `savepoint=False`, and releases it as it ends, leaving the commit of the driver's transaction to the code (`django/db/transaction.py:Atomic.__enter__`, `django/db/transaction.py:Atomic.__exit__`):

```text recording=backends
outer.__enter__()
  Atomic.__enter__
    BaseDatabaseWrapper.savepoint
      SQL SAVEPOINT "s(the thread)_x5"
      sqlite SAVEPOINT "s(the thread)_x5"
      -> 's(the thread)_x5'
the connection holds: in_atomic_block=True, savepoint_ids=['s(the thread)_x5'], atomic_blocks=[an Atomic], commit_on_exit=False, needs_rollback=False
...
outer.__exit__(None, None, None)
  Atomic.__exit__
    BaseDatabaseWrapper.savepoint_commit('s(the thread)_x5')
      SQL RELEASE SAVEPOINT "s(the thread)_x5"
      sqlite RELEASE SAVEPOINT "s(the thread)_x5"
the connection holds: in_atomic_block=False, savepoint_ids=[], atomic_blocks=[], commit_on_exit=False, needs_rollback=False
```

Django's documentation asks the code to end the transaction before it turns autocommit on again, and `BaseDatabaseWrapper.close_if_unusable_or_obsolete` closes a connection whose autocommit differs from its alias's `"AUTOCOMMIT"` at a request's start and end (`django/db/backends/base/base.py:BaseDatabaseWrapper.close_if_unusable_or_obsolete`) ([Opening and closing a connection](lifecycle.md)). An alias with `"AUTOCOMMIT"` set to `False` opens every connection in this state. `on_commit` refuses here outside a block ([Work held until the commit: `on_commit`](on-commit.md)).

## `"ATOMIC_REQUESTS"` and `non_atomic_requests`

`"ATOMIC_REQUESTS"` is `False` unless an alias says otherwise. Where it is `True`, `BaseHandler.make_view_atomic` wraps the view in `atomic` for that alias before calling it, so that a view that returns commits its work and one that raises rolls it back; the handler's side is in [The centre of the chain](../handlers/view.md) (`django/core/handlers/base.py:BaseHandler.make_view_atomic`). `non_atomic_requests` marks a view to be left out, for `"default"` when it is used bare and for the alias it is given otherwise: `_non_atomic_requests` wraps the view in a function that carries the set of aliases to leave out, the view's own set with the alias added where the view already has one, so the decorator can be stacked for several aliases (`django/db/transaction.py:_non_atomic_requests`). Three views, and requests to two of them as far as the last view's call, with SQLite's own lines and the driver's rollback left out:

```text recording=backends
# the views of the script's own:
  def write(request):
      Port.objects.create(name="Scrabster", country="Scotland")
      return HttpResponse("written")
  def fail(request):
      Port.objects.create(name="Stornoway", country="Scotland")
      raise ValueError("the view failed")
  @transaction.non_atomic_requests
  def plain(request):
      Port.objects.create(name="Kyle", country="Scotland")
      return HttpResponse("written")
settings.ROOT_URLCONF = (path('write/', write), path('fail/', fail), path('plain/', plain))
...
response = handler.get_response(RequestFactory().get('/fail/'))
  BaseHandler.make_view_atomic(fail)  ->  a function that calls fail inside an Atomic (made by contextlib's ContextDecorator, Atomic's base class)
  Atomic.__enter__
    SQL BEGIN
  fail(request)
    SQL INSERT INTO "fleet_port" ("name", "country") VALUES (%s, %s) RETURNING "fleet_port"."id" with params ('Stornoway', 'Scotland')
    raises ValueError
  Atomic.__exit__(exc_type=ValueError)
    BaseDatabaseWrapper.rollback
response.status_code  ->  500
response = handler.get_response(RequestFactory().get('/plain/'))
  BaseHandler.make_view_atomic(plain)  ->  plain as it was given
  plain(request)
```

The marked view is called as it was given, so its insert runs under autocommit, a transaction of its own.
