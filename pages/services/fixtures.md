---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Fixtures: dumpdata and loaddata

The dumpdata and loaddata commands: how dumpdata chooses models and rows for a serializer, how `sort_dependencies` orders models whose foreign keys are written as natural keys, and how loaddata finds fixture files and saves their objects in one transaction, checking foreign keys at the end.

A **fixture** is a file of serialized model instances. The commands stand on the serializers ([Serialization: `serialize`, `deserialize` and `DeserializedObject`](serializers.md)), dumpdata feeding `serialize` and loaddata saving what `deserialize` gives back.

## dumpdata: the models, the rows and the output

`Command.handle` turns its labels into an ordered dictionary of application configurations, each mapped to a list of models, or to `None` for all of them; with no labels it takes every application that has a models module (`django/core/management/commands/dumpdata.py:Command.handle`). An application given to `--exclude` is left out even where a label names it; a model given to it is skipped later.

As the rows are collected, a proxy is skipped, with a `ProxyModelWarning` where the model it stands for is not among the models listed. A model is dumped where `ConnectionRouter.allow_migrate_model` allows it on the database, which asks only the routers, so an unmanaged model is dumped like any other (`django/db/utils.py:ConnectionRouter.allow_migrate_model`). The rows are the default manager's, or the base manager's with `--all`, ordered by primary key and read with `QuerySet.iterator`, given a chunk size of 2000 where the manager prefetches, which `iterator` then requires (`django/db/models/query.py:QuerySet.iterator`).

`--output` names a file, compressed by its extension: `".gz"`, and `".bz2"`, `".lzma"` and `".xz"` where Python has their modules. A `".zip"`, or an extension whose module is missing, gets the data uncompressed under the name without that extension, with a `RuntimeWarning`.

## Natural keys and `sort_dependencies`

Written as a primary key, a foreign key is not looked up when it is loaded: the value is converted, and the row goes in whether or not its target is there yet (`django/core/serializers/base.py:deserialize_fk_value`). With `--natural-foreign`, a foreign key to a model with a `natural_key` method is written as that key, unless the key is empty, and loading it means finding the target through its default manager's `get_by_natural_key`, so the target should be saved first. Only with that option does dumpdata sort its models, with `sort_dependencies` (`django/core/serializers/__init__.py:sort_dependencies`).

A model's dependencies are the models named, as `"app_label.ModelName"`, in a list its `natural_key` method carries as `"dependencies"`, and each other model with a `natural_key` that one of its foreign keys points to, or one of its many-to-many fields whose table Django made. The sort passes over the models again and again, placing each whose dependencies are placed already or are not among the models given, so a model that depends on nothing is placed in the first pass, in its turn, natural key or not. A pass that places nothing has met a cycle: with `allow_cycles=False` that is a `RuntimeError` naming the models left; dumpdata passes `allow_cycles=True`, and the last model the pass skipped is placed, its dependencies ignored.

With a natural key on Port,

```python
# harbour/fleet/models.py, Port with a natural key
class PortManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class Port(Named):
    country = models.CharField(max_length=40)
    objects = PortManager()

    def natural_key(self):
        return (self.name,)
```

run with `call_command` against the example's database, the command writes the ports first, without their primary keys, and each ship's home port by name; without the two options the ships come first, as the labels give them, each with its home as 1:

```text
dumpdata fleet.Ship fleet.Port --format jsonl --natural-foreign --natural-primary
{"model": "fleet.port","fields": {"name": "Valletta","country": "Malta"}}
{"model": "fleet.port","fields": {"name": "Piraeus","country": "Greece"}}
{"model": "fleet.ship","pk": 1,"fields": {"name": "Endeavour","tonnage": 366,"home": ["Valletta"],"captain": null}}
{"model": "fleet.ship","pk": 2,"fields": {"name": "Beagle","tonnage": 235,"home": ["Valletta"],"captain": null}}
```

## loaddata: finding the files

A label is a name, followed if need be by a format, a compression or both. `Command.parse_name` takes the last dotted part as a compression if it is one, and then requires the last part that remains, where a dot precedes it, to be a public format, refusing the label otherwise; so a name with a dot in it is given with its format (`django/core/management/commands/loaddata.py:Command.parse_name`). The label `"-"` reads standard input, in the format `--format` gives.

`Command.fixture_dirs` lists the `"fixtures"` directory of each installed application that has one, in the order of `INSTALLED_APPS` (only that of `--app` where it is given), then `FIXTURE_DIRS`, then the current directory; `FIXTURE_DIRS` naming a directory twice, or an application's own, is `ImproperlyConfigured` (`django/core/management/commands/loaddata.py:Command.fixture_dirs`). A label with a directory in it is looked for under each, an absolute one only in its own.

In each directory `Command.find_fixtures` keeps the files whose names `Command.get_targets` allows: the name, optionally the alias of the database being loaded, a format, and optionally a compression (`django/core/management/commands/loaddata.py:Command.find_fixtures`). So for the label `"arrivals"` the file `"arrivals.default.json"` is loaded only into `"default"`. Two matches in one directory are a `CommandError`; matches in several directories are all loaded. A label that matches no file is a `CommandError`.

## loaddata: one transaction, checked at the end

`Command.handle` runs the load inside `atomic`, so a fixture that fails undoes every object loaded before it (`django/core/management/commands/loaddata.py:Command.handle`).

`Command.loaddata` finds the first label's files before turning foreign key checks off, which its comment says is expensive on some databases, and then loads each label inside `BaseDatabaseWrapper.constraint_checks_disabled` (`django/core/management/commands/loaddata.py:Command.loaddata`). `Command.load_label` opens each file through its compression, a zip having to hold one file, and iterates over `deserialize` with `handle_forward_references=True` and with `--ignorenonexistent`, which skips fields the project no longer has and, but in XML, models. `Command.save_obj` saves each object through `DeserializedObject.save`, unless it is excluded or the router refuses its model.

An object whose natural foreign key names a row not yet loaded has that field deferred, `DEFER_FIELD`, and is saved without it; after the last label, `DeserializedObject.save_deferred_fields` looks the key up again, now refusing a missing row, and saves the object again (`django/core/serializers/base.py:DeserializedObject.save_deferred_fields`). The documentation requires such a foreign key to have `null=True` (`docs/topics/serialization.txt`).

Then `BaseDatabaseWrapper.check_constraints` checks the tables of the models whose objects were saved, and where anything was loaded the statements of the backend's `BaseDatabaseOperations.sequence_reset_sql` move each model's sequence to the largest key in its table, on PostgreSQL and Oracle; the base class, which SQLite and MySQL keep, writes none (`django/core/management/commands/loaddata.py:Command.reset_sequences`) ([The connection object: `BaseDatabaseWrapper` and what a backend provides](../backends/wrapper.md#foreign-key-checks-switched-off-constraint_checks_disabled), [Introspection: reading the schema back](../schema/introspection.md#sequences-sequence_reset_by_name_sql-and-sequence_reset_sql)). Last, a line counts the objects installed; a file of no objects gets a `RuntimeWarning`.

A fixture in a directory of `FIXTURE_DIRS`, whose voyage calls at a port the file gives after it:

```text
# arrivals.json
[
{"model": "fleet.voyage", "pk": 2, "fields": {"ship": 2, "sailed": "2026-10-14", "calls": [3]}},
{"model": "fleet.port", "pk": 3, "fields": {"name": "Marseille", "country": "France"}}
]
```

Loaded with `call_command`, each statement sent shortened:

```text
loaddata arrivals    (FIXTURE_DIRS holds arrivals.json)
  BEGIN
  PRAGMA foreign_keys = OFF
  PRAGMA foreign_keys
  UPDATE "fleet_voyage" ...
  INSERT INTO "fleet_voyage" ...
  SELECT ... FROM "fleet_voyage" INNER JOIN "fleet_ship" ...
  SELECT ... FROM "fleet_port" INNER JOIN "fleet_voyage_calls" ...
  INSERT OR IGNORE INTO "fleet_voyage_calls" ...
  UPDATE "fleet_port" ...
  INSERT INTO "fleet_port" ...
  PRAGMA foreign_key_check("fleet_port")
  PRAGMA foreign_key_check("fleet_voyage")
  Installed 2 object(s) from 1 fixture(s)
mail.outbox: 1 message, 'Beagle sailed on 14 October 2026'
```

The voyage went in before Marseille, its reference by primary key not looked up; on SQLite the pragma cannot turn the checks off inside a transaction, and the foreign keys wait for the commit ([SQLite](../backends/sqlite.md)). The check took the two tables in the order of a set, which varies from run to run, and left out the many-to-many table.

## Raw saves and the receivers

`DeserializedObject.save` calls `Model.save_base` with `raw=True`: the model's own `save` is not called, and the receivers of `pre_save`, `post_save` and `m2m_changed` are told the save is raw ([Serialization: `serialize`, `deserialize` and `DeserializedObject`](serializers.md)) (`django/core/serializers/base.py:DeserializedObject.save`). The many-to-many rows are set after `save_base` returns. The run's first SELECT is the example's task: voyage_saved does not look at raw, and the voyage was new, so it enqueued tell_harbour_master, and the harbour master was sent a message. The documentation suggests that a receiver reaching related fields the load has not supplied return at once when raw is true (`docs/topics/db/fixtures.txt`).

> **Changed in 6.1.** Many-to-many rows set from a fixture send `m2m_changed` with `raw=True` (`docs/releases/6.1.txt`).
