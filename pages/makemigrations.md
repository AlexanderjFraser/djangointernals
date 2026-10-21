---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The database
contents: autodetector, autodetector-fields, questioner, dependencies, optimizer, serializer, writer, makemigrations, rewriting
---

# Making migrations

makemigrations compares two descriptions of the models, the one the migrations on disk add up to and the one the code gives now, and writes the difference as migrations: the autodetector finds the operations, orders them and cuts them into migrations, the optimizer folds them, and the writer turns each into the text of a file.

A migration file is applied on each database the project is migrated on, so it has to be right when it is written, and makemigrations writes one by comparing two descriptions. One is the **from-state**, the project state the migrations on disk add up to; the other is the **to-state**, the project state read off the model classes as the code has them now ([Migrations](migrations.md#the-project-state)). makemigrations reads both, finds the operations that turn the first into the second, puts them in an order that can run and cuts them into migrations that depend on one another, folds what can be said as one, fits the result to the history already on disk, and writes each migration as a module of Python. It sends no database anything that changes it. Along the line, the thing it carries changes form: model states, then operations, then migrations with names not yet final, then numbered migrations, then text. And at one side of the line stands a person, for what two states cannot settle.

One currency runs through both ends. What a field's `deconstruct` returns, the arguments that would make the field again, is how the fields of two states are compared, since two field objects are equal when they have the same creation counter and the same model, not when they are made alike; and it is what is written into the file. That is why a field given a new `verbose_name` makes an `AlterField`, and why a field whose `deconstruct` returns a value Django cannot write stops the writer (`django/db/models/fields/__init__.py:Field.deconstruct`).

The example is harbour, whose models [Models and fields](models.md) lists, with the fourth application, yard, that [Migrations](migrations.md) adds to it and edits. In a recording the lines are what a running Django did. Where an order is the point the lines are calls, nested as they were made. Only the lines a passage is about are written. A method is written by the class that declares it. An arrow is followed by what a call returned. Square brackets after the writer's `as_string` name the migration being written. `stdout |` begins a line a command printed and `stdin  |` a line typed in answer to it, and a bar a line of a file; a line beginning `python manage.py` is a command line, run as a process of its own. Every recording of this chapter ran on SQLite.

## The first makemigrations

Harbour's four applications began with no package of migrations, and makemigrations with no labels made nothing for them: such an application has its first migration written only where its label is given. Given the four labels, it wrote a migration for each, and a second for crew. An application whose package of migrations holds no Python file but `"__init__.py"`, as a new application's does, has its first written without being named ([The makemigrations command](makemigrations/makemigrations.md)). Look for the from-state, empty since there were no files, the to-state, and the migrations the autodetector returned before and after they were named:

```text recording=migrations
makemigrations.Command.handle('fleet', 'crew', 'office', 'yard')
  MigrationLoader.__init__(connection=None, ignore_no_migrations=True)
    MigrationLoader.build_graph
  MigrationLoader.check_consistent_history(the connection "default")
  InteractiveMigrationQuestioner.__init__(specified_apps={'crew', 'fleet', 'office', 'yard'}, dry_run=False)
  MigrationLoader.project_state  ->  a ProjectState of 0 model states, its registry not rendered
  ProjectState.from_apps(the main registry)  ->  a ProjectState of 13 model states, its registry not rendered
  MigrationAutodetector.__init__(from_state=a ProjectState of 0 model states, its registry not rendered, to_state=a ProjectState of 13 model states, its registry not rendered, questioner=an InteractiveMigrationQuestioner)
  MigrationAutodetector.changes(graph=the graph (0 nodes), trim_to_apps={'crew', 'fleet', 'office', 'yard'}, convert_apps={'crew', 'fleet', 'office', 'yard'})
    MigrationAutodetector._detect_changes(convert_apps={'crew', 'fleet', 'office', 'yard'}, graph=the graph (0 nodes))  ->  {'crew': [crew.auto_1, crew.auto_2], 'fleet': [fleet.auto_1], 'office': [office.auto_1], 'yard': [yard.auto_1]}
    MigrationAutodetector.arrange_for_graph(graph=the graph (0 nodes))
      -> {'crew': [crew.0001_initial, crew.0002_initial], 'fleet': [fleet.0001_initial], 'office': [office.0001_initial], 'yard': [yard.0001_initial]}
  makemigrations.Command.write_migration_files(changes={'crew': [crew.0001_initial, crew.0002_initial], 'fleet': [fleet.0001_initial], 'office': [office.0001_initial], 'yard': [yard.0001_initial]})
    MigrationWriter.as_string  [crew.0001_initial]
```

The **loader** finds the migration files and builds from them the graph that orders them; there are no files yet, so the graph has no nodes and the from-state is empty. This loader is made with no connection: it does not ask which migrations a database has had. The check that follows it is a separate matter, that the history recorded in the database is not out of order (`django/core/management/commands/makemigrations.py:Command.handle`). The to-state, read off the models of the four applications, has thirteen model states: harbour's eleven, the proxy Veteran among them and the abstract Named not, and yard's two.

## Comparing: the autodetector

The **autodetector**, a `MigrationAutodetector`, is given the two states and finds operations that turn the first into the second (`django/db/migrations/autodetector.py:MigrationAutodetector._detect_changes`). It sorts the models of both into those kept, added and removed, matching them by name, and then calls its **generators** in a fixed order, each named for one kind of change: renamed models first; then models deleted and created, and the options of those kept; then the indexes and constraints that go and the fields renamed; then fields removed, added and altered; and last the indexes and constraints that are new, the constraints altered, and the table's name. Two fields are compared by their deconstructions ([The autodetector: comparing two project states](makemigrations/autodetector.md), [The autodetector: fields, indexes and constraints](makemigrations/autodetector-fields.md)).

What the autodetector produces first is a flat list of operations for each application, and each operation carries its **needs**: `OperationDependency` tuples, each naming a model or a field and what must first have been done, such as its creation or its removal, before the operation can run (`django/db/migrations/autodetector.py:OperationDependency`). A need names a thing, not an operation, so a need for a thing's creation can be met by whichever operation creates it.

## The person at the side of the line

Some questions two states cannot settle, and the autodetector asks its **questioner**, as makemigrations itself does before a merge. Repair has lost a date field called started and gained a date field called begun: one column renamed, or one dropped and another made? A field that cannot be null is added to a model whose table may have rows, and the model gives no value for them: what is to go in them? An application has no migrations: is it to have its first? Two migrations of one application both claim to be its newest: are they to be merged? `MigrationQuestioner` asks no one; `InteractiveMigrationQuestioner` puts some of them to the person at the terminal; and `NonInteractiveMigrationQuestioner`, which makemigrations makes for the autodetector under `--noinput`, answers what it can and ends the command with status 3 where it cannot, as the interactive one does where the person picks its choice to quit (`django/db/migrations/questioner.py:NonInteractiveMigrationQuestioner`) ([The questioner: `MigrationQuestioner`](makemigrations/questioner.md)).

Yard's models were then edited, four changes at once:

```text recording=migrations
The models of yard, second version: harbour/yard/models.py, each line put in marked + and each line taken out marked -; four changes at once: Dock.name made longer, Dock.metres added, Repair.started renamed begun, and an index on Repair
    |   from django.db import models
    |
    |
    |   class Dock(models.Model):
    |       """A dry dock of the repair yard, in one of the fleet's ports."""
    |
    | -     name = models.CharField(max_length=40)
    | +     name = models.CharField(max_length=80)
    |       port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)
    | +     metres = models.PositiveSmallIntegerField(default=120)
    |
    |
    |   class Repair(models.Model):
    |       """A ship in a dock, under repair."""
    |
    |       ship = models.ForeignKey("fleet.Ship", on_delete=models.CASCADE)
    |       dock = models.ForeignKey(Dock, on_delete=models.PROTECT)
    | -     started = models.DateField()
    | +     begun = models.DateField()
    |       notes = models.TextField(blank=True)
    | +
    | +     class Meta:
    | +         indexes = [models.Index(fields=["dock", "begun"], name="repair_by_dock")]
```

```text recording=migrations
python manage.py makemigrations yard
  stdout | Was repair.started renamed to repair.begun (a DateField)? [y/N]
  stdin  | y
  stdout | Migrations for 'yard':
  stdout |   harbour/yard/migrations/0002_rename_started_repair_begun_dock_metres_and_more.py
  stdout |     ~ Rename field started on repair to begun
  stdout |     + Add field metres to dock
  stdout |     ~ Alter field name on dock
  stdout |     + Create index repair_by_dock on field(s) dock, begun of model repair
```

This time the from-state is not empty: the loader's graph has five nodes, and running their operations' state halves ([Migrations](migrations.md#a-migration-is-a-list-of-operations)) gives the thirteen models as they were; the to-state has yard's as they are now. The four changes come out as four operations, and one of them needed the question, since whether a column was renamed or one dropped and another made is something only a person knows.

## Ordering, cutting and fitting

An operation cannot run before what it needs exists, and the needs decide the order twice. Inside each application the list is sorted so that each operation follows what it needs. Across applications the lists are cut into migrations in rounds, each migration depending on a migration of each other application whose models or fields it needs (`django/db/migrations/autodetector.py:MigrationAutodetector._build_migration_list`). Harbour shows why the cutting is needed. Among the fields of its models that point from one application into another, these make a circle:

```python
# harbour/fleet/models.py, in Ship
captain = models.OneToOneField("crew.Sailor", null=True, blank=True, on_delete=models.SET_NULL, related_name="command")

# harbour/crew/models.py, in Sailor
ship = models.ForeignKey("fleet.Ship", on_delete=models.CASCADE, related_name="crew")
pilots_into = models.ManyToManyField("fleet.Port", through="office.Licence", related_name="pilots")

# harbour/office/models.py, in Licence
sailor = models.ForeignKey("crew.Sailor", on_delete=models.CASCADE)
port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)
```

A ship names a sailor and a sailor names a ship, so neither application can be created whole before the other. When a round takes nothing, the autodetector goes round again in what its code calls **chop mode**, in which a list can be cut short: crew's first migration creates Sailor, and Officer with it, without the two fields that point out of crew; fleet's migration and office's can then run; crew's second adds the two fields, and the proxy Veteran ([From operations to migrations: dependencies, order and names](makemigrations/dependencies.md)). Before a migration leaves the autodetector its operations go through the **optimizer**, which folds operations that can be said as one, a field added to a model just created becoming a field of the `CreateModel` ([The optimizer: `MigrationOptimizer` and `reduce`](makemigrations/optimizer.md)).

Then the migrations are fitted to the history, and of an application with no migrations the questioner is asked whether it is to have its first. `MigrationAutodetector.arrange_for_graph` numbers each after its application's newest migration, where it has one, gives the first of them a dependency on that migration, and names it: as `--name` says where it was given, otherwise `"initial"` for an application's first, and for the rest what `Migration.suggest_name` returns, cut to a hundred characters (`django/db/migrations/autodetector.py:MigrationAutodetector.arrange_for_graph`). Last, the new migrations of applications not asked for are dropped, unless a kept migration depends on a migration of that application, which is why makemigrations given only yard's label can write a migration for fleet too (`django/db/migrations/autodetector.py:MigrationAutodetector._trim_to_apps`).

## Writing

The **writer** turns each migration into the text of a module, once for each file (`django/db/migrations/writer.py:MigrationWriter.as_string`). That means turning every value inside every operation, each field with its arguments, into Python source that makes the value again when the file is imported: an object with a `deconstruct` method is written as a call with the arguments it returns, and a value for which Django has no serializer stops the command when the text is made ([Serializing values: `serializer_factory` and `deconstruct`](makemigrations/serializer.md), [Writing a migration file: `MigrationWriter`](makemigrations/writer.md)). The command around all of it, with its options, is [The makemigrations command](makemigrations/makemigrations.md).

The figure draws the line from its two descriptions to its files, with the person at its side and the other ways onto it.

```text figure=the-stations
makemigrations: from two descriptions of the models to files; no database is changed

read      the migration files   -- MigrationLoader: the graph, then each migration's state halves -->  the from-state
          the models            -- ProjectState.from_apps -->                                          the to-state
              |
compare   the autodetector: models matched by name; generators in a fixed order; fields compared by deconstruct
              |   operations, each with its needs                  asks the questioner:  renamed, or dropped and made?
              |                                                                          a value for rows already there?
order     a sort inside each application; rounds across them; chop mode after a round that takes nothing
              |   migrations, named for now
fold      the optimizer, migration by migration
              |
fit       numbers and names; the first a dependency on its application's newest migration, where it has one; applications not asked for dropped, unless needed
              |   numbered migrations                              asks the questioner:  a first migration?
write     the writer's text, each value through the serializer, as deconstruct returned it  -->  the files

off the line, makemigrations itself asks the questioner before a merge:  a merge?
joining the line for the optimizer and the writer, on migrations already written: makemigrations --update, squashmigrations, optimizemigration
```

*The stations of makemigrations, in the order the thing carried passes them, and what it is between them. The questions stand beside the stations that ask them, and the merge's off the line; the three commands that rewrite migrations join the line for the optimizer and the writer.*

## Rewriting what is written

Three commands load migrations that already exist and can send them through the same optimizer and writer: makemigrations `--update` folds the new changes into each application's newest migration, squashmigrations writes one migration that replaces a run of others, and optimizemigration folds one migration's operations again ([Rewriting migrations: `--update`, squashmigrations and optimizemigration](makemigrations/rewriting.md)). A migration that replaces others is applied in their place only where the database has had none of them, which is the loader's choice (`django/db/migrations/loader.py:MigrationLoader.replace_migration`; [Replacing migrations: `replaces`](migrations/replacing.md)).

## The neighbours

What a migration is, its operations and their two halves, the project state and the graph, and how migrate applies the files this chapter writes, are [Migrations](migrations.md)'s. `Field.deconstruct` and the model's options, which the comparison and the writing both read, are [Models and fields](models.md)'s (`django/db/models/fields/__init__.py:Field.deconstruct`). How a command is found and run is in [Management commands](commands.md), and the user model, which a setting can swap and on which a migration with a relation to it depends through that setting, is in [The user model: `AbstractBaseUser`, `User` and `AUTH_USER_MODEL`](auth/user-model.md).
