---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Routing between databases: `ConnectionRouter`

`django.db.router`, the one `ConnectionRouter` of a process, chooses among the aliases of `DATABASES` for code that has not been told which to use: `ConnectionRouter.db_for_read` and `ConnectionRouter.db_for_write` name the alias to read a model from and to write it to, `ConnectionRouter.allow_relation` says whether two instances may be related, and `ConnectionRouter.allow_migrate` whether a migration's operation may run on a database, a question also asked to learn whether a model is kept there. It asks the routers that the setting `DATABASE_ROUTERS` names, in order, and where none of them answers it answers itself.

With one database there is nothing to choose. With several, every query, every save and every migration has to go to one of them, and most of the code that sends them names none: counting the example project's logbooks, the model Logbook, through its manager gives no alias, and neither does saving an instance. Django puts the choice in one place. Code that was given an alias, by `QuerySet.using`, by the argument `using` of `Model.save` or `Model.delete`, or by a manager that `BaseManager.db_manager` gave one, sends its statement there without asking; the ORM's code that was not asks the router. The router answers with an alias, a string, and turning that into a connection is the handler's work ([Connections by alias: `DATABASES` and `ConnectionHandler`](connections.md)).

Where no router of the project answers, the router's own answers make a scheme of their own. A question asked about an instance is answered with that instance's database where it has one, and any other with `"default"`; two instances may be related when they are in one database; and every model may be migrated to every database. Django's guide to several databases calls the first rule the objects' being sticky to their original database (`docs/topics/db/multi-db.txt`).

## The project's router

The example project's one router, LogbookRouter, sends the office's logbooks, the models Logbook and LogEntry, to the database `"archive"`. Its settings name it, `DATABASE_ROUTERS = ["harbour.routers.LogbookRouter"]`. The router is:

```python
# harbour/routers.py
LOGBOOKS = {"logbook", "logentry"}


class LogbookRouter:
    def db_for_read(self, model, **hints):
        if model._meta.model_name in LOGBOOKS:
            return "archive"
        return None

    def db_for_write(self, model, **hints):
        if model._meta.model_name in LOGBOOKS:
            return "archive"
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if model_name in LOGBOOKS:
            return db == "archive"
        return None
```

It answers the two routing questions for the logbooks and returns `None` for every other model, which leaves the question to whatever comes after it. It allows the logbooks' tables in `"archive"` only, and has no opinion on any other table, so every other table is allowed in both databases. It has no `allow_relation`. What follows was recorded from a running Django with that router installed and the project's two SQLite databases; each line is a question and its answer after `->`:

```text recording=backends
settings.DATABASE_ROUTERS  ->  ['harbour.routers.LogbookRouter']
router.routers  ->  [a LogbookRouter]
type(router.routers[0])  ->  harbour.routers.LogbookRouter
```

## `DATABASE_ROUTERS` and `ConnectionRouter.routers`

`django.db` makes the router as it is imported, with no routers of its own (`django/db/__init__.py`). `ConnectionRouter.__init__` keeps what it was given, and `ConnectionRouter.routers`, a cached property, builds the list the first time it is read: from `DATABASE_ROUTERS` where the router was given nothing, an entry that is a string being imported with `import_string` and called with no arguments, and an entry that is anything else being taken as it is (`django/db/utils.py:ConnectionRouter.routers`). So each router class named in the setting is ordinarily made once, and that instance answers the questions of every thread.

The list is kept. A change to the setting after the first question is not seen by `django.db.router`, except where the test framework's receiver of `setting_changed` puts the list of a newly made `ConnectionRouter` in place of the old one (`django/test/signals.py:clear_routers_cache`) ([Overriding settings](../startup/overrides.md)).

## `db_for_read` and `db_for_write`

`ConnectionRouter._router_func` is a function called twice in the class's body, once with each name, and what it returns is bound in the class as `ConnectionRouter.db_for_read` and `ConnectionRouter.db_for_write` (`django/db/utils.py:ConnectionRouter._router_func`). The two methods take a model and keyword arguments, the **hints**, and do the same with them. They go through the routers in order. A router without a method of that name is passed over. A router that has one is called with the model and the hints, and its answer is returned if it is true, while an answer that is not, such as `None`, `False` or an empty string, sends the question on to the next router. Only the looking up of the method is guarded, so an `AttributeError` raised inside a router's method goes to the caller. When the routers are done, a hint `"instance"` whose `ModelState.db` is set decides: its alias is the answer (`django/db/models/base.py:ModelState`). Failing that, the answer is `DEFAULT_DB_ALIAS`, `"default"`.

Here skua is the ship Skua read from `"archive"` and petrel the Petrel read from `"default"`:

```text recording=backends
skua = Ship.objects.using('archive').get(name='Skua')
  SQL (on "archive") SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."name" = %s LIMIT 21 with params ('Skua',)
petrel = Ship.objects.get(name='Petrel')
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."name" = %s LIMIT 21 with params ('Petrel',)
router.db_for_read(Logbook)  ->  'archive'
router.db_for_write(LogEntry)  ->  'archive'
router.db_for_read(Ship)  ->  'default'
skua._state.db  ->  'archive'
router.db_for_write(Ship, instance=skua)  ->  'archive'
router.db_for_write(Ship, instance=petrel)  ->  'default'
```

An instance's alias is in its state because Django puts it there: `Model.from_db` records the alias a row was read from, and `Model.save_base` the alias an instance was saved to (`django/db/models/base.py:Model.from_db`, `django/db/models/base.py:Model.save_base`) ([An instance and its state](../models/instances.md)). So with no router to say otherwise, an instance read from `"archive"` is saved back to `"archive"`, and its related objects are read from there.

The hint is how a question carries the instance it is about. Django's own callers of `db_for_read` and `db_for_write` give no hint but `"instance"`, or none at all, and a queryset passes on the hints its manager was made with and any that `QuerySet._add_hints` has added since (`django/db/models/query.py:QuerySet._add_hints`). `ConnectionRouter` reads no hint but `"instance"` itself, and passes every hint on to the routers.

## `allow_relation`

`ConnectionRouter.allow_relation` takes two instances and the hints, and asks the routers in order in the same way, with one difference: any answer that is not `None` is final, so a router's `False` refuses the relation where in `db_for_read` it would have sent the question on (`django/db/utils.py:ConnectionRouter.allow_relation`). When no router answers, the relation is allowed if the two instances' `ModelState.db` are equal (`django/db/models/base.py:ModelState`). The project's router has no `allow_relation`, so the default compared `"archive"` with `"default"`:

```text recording=backends
router.allow_relation(skua, petrel)  ->  False
```

The descriptor of a foreign key asks when an instance is assigned:

```text recording=backends
A relation across databases refused: a ship read from "archive" given to a sailor read from "default"
    ada = Sailor.objects.get(name='Ada')
      SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s LIMIT 21 with params ('Ada',)
    ada.ship = skua
      ForwardManyToOneDescriptor.__set__(instance=<Sailor: Ada>, value=<Ship: Skua>)
        ConnectionRouter.allow_relation(<Ship: Skua>, <Sailor: Ada>)  ->  False
        raises ValueError
    raises ValueError: Cannot assign "<Ship: Skua>": the current database router prevents this relation.
    ada._state.db, skua._state.db  ->  ('default', 'archive')
    ada.ship  ->  <Ship: Petrel>
      SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."id" = %s LIMIT 21 with params (1,)
```

`ForwardManyToOneDescriptor.__set__` asked with the ship first and the sailor second, and raised `ValueError` at the refusal, before it set the foreign key's value or its cache: Ada's ship is still the Petrel, read from `"default"` because the descriptor's queryset carried Ada as its hint (`django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.__set__`, `django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.get_queryset`) ([Reading and setting related objects](../models/related-objects.md)). Before it asks, the descriptor fills in an alias missing from either instance: it sets that instance's `ModelState.db` to what `db_for_write` answers for the instance's class, with the other instance as the hint. So an instance never saved, given an object from `"archive"`, is itself put in `"archive"` unless a router says otherwise, and the comparison that follows is between two aliases. `ReverseOneToOneDescriptor.__set__` does the same at the other end of a one-to-one field, and a many-to-many manager asks `allow_relation` of each instance it is given to add, in `_get_target_ids`, and refuses with a message that names both databases (`django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager`) ([Many-to-many relations](../models/many-to-many.md)).

## `allow_migrate`, `allow_migrate_model` and `get_migratable_models`

`ConnectionRouter.allow_migrate` takes an alias, an application's label and the hints, and asks the routers in order as `allow_relation` does: the first answer that is not `None` is final, and with none the answer is `True` (`django/db/utils.py:ConnectionRouter.allow_migrate`). `ConnectionRouter.allow_migrate_model` puts the question for one model: the model's `Options.app_label`, its `Options.model_name` as the hint `model_name`, and the model itself as the hint `model` (`django/db/utils.py:ConnectionRouter.allow_migrate_model`, `django/db/models/options.py:Options`). `ConnectionRouter.get_migratable_models` returns the models of one application that `allow_migrate_model` lets into one database, leaving out those swapped out and, unless `include_auto_created=True` is given, those created automatically (`django/db/utils.py:ConnectionRouter.get_migratable_models`, `django/apps/config.py:AppConfig.get_models`).

```text recording=backends
router.allow_migrate('archive', 'fleet')  ->  True
router.allow_migrate('default', 'office', model_name='logbook')  ->  False
router.allow_migrate_model('default', Logbook)  ->  False
router.allow_migrate_model('archive', Logbook)  ->  True
```

Asked about the fleet with no model, the router had nothing to say, and the default allowed it. A migration's operation on a model's table puts the question through `Operation.allow_migrate_model`, which first refuses a model that `Options.can_migrate` says no to, a proxy, a model that has been swapped out, one that is not managed, or one that needs a vendor or features the connection lacks, and asks the router only after that (`django/db/migrations/operations/base.py:Operation.allow_migrate_model`, `django/db/models/options.py:Options.can_migrate`). The model an operation passes is the one of the migration's state, a historical model, which the guide to several databases warns may lack the class's own attributes, methods and managers, so that a router reading the hint `model` should rely on its `_meta` alone (`django/db/migrations/operations/models.py:CreateModel.database_forwards`, `docs/topics/db/multi-db.txt`) ([Migrations](../migrations.md)).

> **Trap.** The command makemigrations checks the history of migrations in each database that some model may be migrated to, where routers are installed, and it asks with `model_name=` the model's `Options.object_name`, where `allow_migrate_model` and the migration executor pass the lower-case `Options.model_name` (`django/core/management/commands/makemigrations.py:Command.handle`). A router that, like the project's, compares `model_name` with lower-case names and returns `None` when none matches gives no answer to that question, and the default, `True`, stands, so makemigrations checks the history even of a database that such a router keeps every model out of.

```text recording=backends
Logbook._meta.model_name  ->  'logbook'
Logbook._meta.object_name  ->  'Logbook'
router.allow_migrate('default', 'office', model_name=Logbook._meta.model_name)  ->  False
router.allow_migrate('default', 'office', model_name=Logbook._meta.object_name)  ->  True
```

## Where Django asks

Of the router's callers, the queryset is the one most code meets. Asked for a count, the queryset reads its `QuerySet.db`, which has no alias of its own and is not marked for writing, so it asks `db_for_read`:

```text recording=backends
A queryset asks the router: Logbook.objects.count() is sent to "archive"
    Logbook.objects.count()
      QuerySet.count
        QuerySet.db
          ConnectionRouter.db_for_read(Logbook)  (the function _router_func made)
            LogbookRouter.db_for_read(Logbook)  ->  'archive'
            -> 'archive'
        Query.get_count(using='archive')
          Query.get_compiler(using='archive')
            BaseConnectionHandler.__getitem__('archive')
          SQL (on "archive") SELECT COUNT(*) AS "__count" FROM "office_logbook"
```

The answer went to `Query.get_count`, and `Query.get_compiler` took `connections["archive"]` to make the compiler with. `QuerySet.db` asks again each time it is read, and asks `db_for_write` once a method that writes, or `QuerySet.select_for_update`, has marked the queryset (`django/db/models/query.py:QuerySet.db`) ([Clones: how a queryset is built](../querysets/chaining.md)); `RawQuerySet.db` asks only `db_for_read` (`django/db/models/query.py:RawQuerySet.db`) ([Raw querysets](../querysets/raw.md)); and `BaseManager.db` asks `db_for_read` with the manager's hints, which `db_manager` sets with or without an alias (`django/db/models/manager.py:BaseManager.db`, `django/db/models/manager.py:BaseManager.db_manager`) ([Managers](../models/managers.md)).

Beyond the queryset and the manager, `Model.save`, `Model.delete` and the related managers, given no alias, ask `db_for_write` with their instance as the hint (`django/db/models/base.py:Model.save`, `django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager`) ([Saving an instance](../models/saving.md)), and the command migrate, the test databases, dumpdata and loaddata ask through `allow_migrate_model` whether a model is kept in a database before they make its table or write out or load its rows (`django/core/management/commands/migrate.py:Command.sync_apps`, `django/db/backends/base/creation.py:BaseDatabaseCreation.serialize_db_to_string`) ([Test databases: `BaseDatabaseCreation`](creation.md)).

## Where Django does not ask

`django.db.connection` is a `ConnectionProxy` for `connections["default"]` (`django/db/__init__.py`), and a cursor taken from it runs on `"default"` whatever the router would say. The functions of `django.db.transaction` take `"default"` where they are given no alias, without asking (`django/db/transaction.py:get_connection`) ([Transactions: autocommit, `atomic` and savepoints](transactions.md)). So under the project's router, a Logbook created inside `atomic()` with no alias goes to `"archive"`, where no transaction is open: it is committed as its statement ends, and stays when the block rolls back:

```text recording=backends
block = transaction.atomic()
block.__enter__()
  Atomic.__enter__
    SQL BEGIN
Logbook.objects.create(title='Skua, 2026')
  ConnectionRouter.db_for_write(Logbook)  (the function _router_func made)  ->  'archive'
  SQL (on "archive") INSERT INTO "office_logbook" ("title") VALUES (%s) RETURNING "office_logbook"."id" with params ('Skua, 2026',)
connections['default'].in_atomic_block  ->  True
connections['archive'].in_atomic_block  ->  False
block.__exit__(ValueError, ValueError('no berth'), None)
  Atomic.__exit__(exc_type=ValueError)
    BaseDatabaseWrapper.rollback
Logbook.objects.filter(title='Skua, 2026').exists()  ->  True
  SQL (on "archive") SELECT %s AS "a" FROM "office_logbook" WHERE "office_logbook"."title" = %s LIMIT 1 with params (1, 'Skua, 2026')
```

A block meant to hold a model's writes names the model's alias, `atomic(using=router.db_for_write(Logbook))`, as Django's admin does for the model it edits (`django/contrib/admin/options.py:ModelAdmin.changeform_view`).
