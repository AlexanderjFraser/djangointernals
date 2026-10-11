---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The questioner: `MigrationQuestioner`

The questioner is the object the autodetector asks what the two project states it compares do not tell it; makemigrations asks one itself before a merge. `MigrationQuestioner` asks no one, `InteractiveMigrationQuestioner` asks the person at the terminal, and `NonInteractiveMigrationQuestioner` answers what it can and ends the command with status 3 where it cannot.

Two edits to Repair, in the example's repair yard, show why the autodetector has questions.

```python
# harbour/yard/models.py, in Repair
begun = models.DateField()                 # first edit: it was called started
foreman = models.CharField(max_length=60)  # second edit: a new field
```

After the first, a date field is gone and a date field has come: one column renamed, or one dropped and another made ([The autodetector: fields, indexes and constraints](autodetector-fields.md)). After the second, a column that may not be null needs a value for the rows already there, and the model gives none. The autodetector does not guess: it calls a method of the **questioner** it was made with.

## `MigrationQuestioner`: answers without asking

`MigrationQuestioner`, the base class, keeps what it is made with: `MigrationQuestioner.defaults`, a dictionary from a method's name to its answer; `MigrationQuestioner.specified_apps`, a set of labels; and `MigrationQuestioner.dry_run`, which only the interactive subclass reads. `MigrationQuestioner.ask_rename`, and likewise the questions of a model renamed and of a merge, return what the dictionary has under the method's name, and false where it has nothing. The questions that want a value for existing rows return `None` whatever the dictionary holds, as does `MigrationQuestioner.ask_unique_callable_default_addition` (`django/db/migrations/questioner.py:MigrationQuestioner`).

An autodetector made with no questioner makes a `MigrationQuestioner()` for itself (`django/db/migrations/autodetector.py:MigrationAutodetector.__init__`), and so never blocks: migrate's check for changes to the models that are in no migration (`django/core/management/commands/migrate.py:Command.handle`) is made with one ([The migrate command, showmigrations and sqlmigrate](migrate.md)). `makemigrations --merge` with `--noinput` asks `MigrationQuestioner(defaults={"ask_merge": True})` (`django/core/management/commands/makemigrations.py:Command.handle_merge`).

## `ask_initial`: whether an application gets its first migration

`MigrationAutodetector.arrange_for_graph` asks `MigrationQuestioner.ask_initial` of each application that has migrations to be written and no leaf node in the graph, and on a no drops them ([From operations to migrations: dependencies, order and names](dependencies.md)). What becomes of an application with no migrations yet is told whole in [The makemigrations command](makemigrations.md).

A label in `MigrationQuestioner.specified_apps` gets a yes; makemigrations puts there the labels on its command line. For any other, the graph having nothing for the application, `ask_initial` looks for a migrations package with no migration in it, as the application template makes one (`django/conf/app_template/migrations/`). It imports the migrations module, by the dotted path `MigrationLoader.migrations_module` gives, lists its directory, and says yes where no file there but `__init__.py` ends in `.py`. A package spread over several directories has no one directory to list and gets a no. `MigrationQuestioner.defaults` is read, with no for want of an entry, only where there is no module to list: the label is no installed application's, `MIGRATION_MODULES` gives `None` for it, or the import fails (`django/db/migrations/questioner.py:MigrationQuestioner.ask_initial`).

## `InteractiveMigrationQuestioner`: asking at the terminal

`InteractiveMigrationQuestioner` writes its questions to `InteractiveMigrationQuestioner.prompt_output`, an `OutputWrapper` around `sys.stdout` unless it is given another, and reads each answer with `input()`, given no prompt: the answers come from standard input wherever the questions go (`django/db/migrations/questioner.py:InteractiveMigrationQuestioner.__init__`).

`InteractiveMigrationQuestioner._boolean_input` asks whether something was renamed or is to be merged, and takes an empty first answer for no, the default every caller gives it. `InteractiveMigrationQuestioner._choice_input` puts the other questions the class overrides as choices numbered from 1, the last of which is to quit and edit the model: `sys.exit(3)`.

`InteractiveMigrationQuestioner._ask_default` is where the first choice leads when a value is wanted. It reads a line and evaluates it as a Python expression, with the built-in eval, in a scope that holds, beside the built-ins, `datetime`, the module, and `timezone`, which is `django.utils.timezone`, and returns what it gives. A line that raises an exception gets a message and the prompt again, as does an empty one, except from `InteractiveMigrationQuestioner.ask_auto_now_add_addition`, where it stands for `"timezone.now"`. The word exit ends the process with status 1, not the 3 of a choice to quit (`django/db/migrations/questioner.py:InteractiveMigrationQuestioner`). In the recording, asking is an interactive questioner, and keyboard, in place of standard input, holds the answers typed ahead; `stdout |` begins a line the questioner wrote and `stdin  |` a line `input()` read.

```text recording=migrations
keyboard.lines = ['1', 'timezone.now']
answer = asking.ask_not_null_addition('foreman', 'repair')
  stdout | It is impossible to add a non-nullable field 'foreman' to repair without specifying a default. This is because the database needs something to populate existing rows.
  stdout | Please select a fix:
  stdout |  1) Provide a one-off default now (will be set on all existing rows with a null value for this column)
  stdout |  2) Quit and manually define a default value in models.py.
  stdout | Select an option:
  stdin  | 1
  stdout | Please enter the default value as valid Python.
  stdout | The datetime and django.utils.timezone modules are available, so it is possible to provide e.g. timezone.now as a value.
  stdout | Type 'exit' to exit this prompt
  stdout | >>>
  stdin  | timezone.now
answer  ->  the function now
```

The autodetector makes the value typed the default of the operation's field and gives the operation `preserve_default=False` (`django/db/migrations/autodetector.py:MigrationAutodetector._generate_added_field`, `django/db/migrations/autodetector.py:MigrationAutodetector.generate_altered_fields`): a one-off default ([The field operations, and those on indexes and constraints](field-operations.md)).

`InteractiveMigrationQuestioner.ask_unique_callable_default_addition` is a warning with two choices: a callable default will not give the rows there are unique values, since the value that fills them is made once (`docs/howto/writing-migrations.txt`), and one may go on with the migration, as the first step towards one written by hand, or quit. `MigrationAutodetector._generate_added_field` puts the question of a managed model's new field that is unique and whose default is callable, a function typed as a one-off default included, and does not read the answer.

In a dry run of makemigrations (`--dry-run` or `--check`) the methods built on `_choice_input` return `None` unasked, and where a value was wanted that `None` is the field's default; the yes-or-no questions are still put.

## `NonInteractiveMigrationQuestioner`: logging, and status 3

`NonInteractiveMigrationQuestioner` is given, besides what its base class `MigrationQuestioner` takes, a verbosity, 1 unless told otherwise, and a function to call with a message, kept as `NonInteractiveMigrationQuestioner.log` (`django/db/migrations/questioner.py:NonInteractiveMigrationQuestioner.__init__`). It overrides the questions that want a value and has the base class's answers to the rest.

`NonInteractiveMigrationQuestioner.ask_not_null_addition` and `NonInteractiveMigrationQuestioner.ask_auto_now_add_addition` log why the field was not migrated (`NonInteractiveMigrationQuestioner.log_lack_of_migration`, silent at verbosity 0) and call `sys.exit(3)`, as the interactive questioner's choice to quit does. `NonInteractiveMigrationQuestioner.ask_not_null_alteration` lets the command go on: it logs, at any verbosity, and returns `NOT_PROVIDED`, on which the autodetector makes the `AlterField` with the field as the model has it (`django/db/migrations/questioner.py:NonInteractiveMigrationQuestioner`).

The class never asks whether the run is dry. Where it is not merging, makemigrations makes one under `--noinput`, with no defaults ([The makemigrations command](makemigrations.md)), so to a rename it says no, and a renamed field is taken for one removed and one added. After the first edit to Repair that ends the command, dry run or not:

```text recording=migrations
python manage.py makemigrations yard --dry-run --noinput
  stdout | Field 'begun' on model 'repair' not migrated: it is impossible to add a non-nullable field without specifying a default.
  exit status 3
```

## The questions

In the table a question is a method of `MigrationQuestioner`, the method that asks it one of `MigrationAutodetector` unless the cell says otherwise, `defaults` and `specified_apps` are the questioner's attributes, and `NOT_PROVIDED` is `django.db.models.NOT_PROVIDED`, the value a field has for no default.

| question | asked by |
|---|---|
| `ask_initial` | `arrange_for_graph`, of an application with no leaf node |
| `ask_rename_model` | `generate_renamed_models`, of a model that may be another renamed |
| `ask_rename` | `create_renamed_fields`, of a field that may be another renamed |
| `ask_not_null_addition` | `_generate_added_field`, of a managed model's new field with no value for existing rows |
| `ask_auto_now_add_addition` | `_generate_added_field`, in place of `ask_not_null_addition`, for a date or time field with `auto_now_add` |
| `ask_unique_callable_default_addition` | `_generate_added_field`, of a managed model's new unique field whose default is callable; the answer is not read |
| `ask_not_null_alteration` | `generate_altered_fields`, of a managed model's field made not null with no default |
| `ask_merge` | makemigrations (`django/core/management/commands/makemigrations.py:Command.handle_merge`), of each application it is to merge |

*Who puts each question, and of what.*

| question | base class | interactive | non-interactive |
|---|---|---|---|
| `ask_initial` | yes for a label in `specified_apps` or a package with no migration in it; `defaults`, or no, for want of a module; else no | the base's | the base's |
| `ask_rename_model` | `defaults`, or no | yes or no; an empty first answer is no | the base's |
| `ask_rename` | `defaults`, or no | yes or no; an empty first answer is no | the base's |
| `ask_not_null_addition` | `None` | 1: a value typed. 2: `sys.exit(3)` | logs unless verbosity is 0, then `sys.exit(3)` |
| `ask_auto_now_add_addition` | `None` | 1: a value typed, `"timezone.now"` offered. 2: `sys.exit(3)` | logs unless verbosity is 0, then `sys.exit(3)` |
| `ask_unique_callable_default_addition` | `None` | 1: `None`. 2: `sys.exit(3)` | the base's |
| `ask_not_null_alteration` | `None` | 1: a value typed. 2: `NOT_PROVIDED`. 3: `sys.exit(3)` | logs; `NOT_PROVIDED` |
| `ask_merge` | `defaults`, or no | yes or no; an empty first answer is no | the base's |

*What each class answers. A number is a choice the interactive questioner offers, outside a dry run.*
