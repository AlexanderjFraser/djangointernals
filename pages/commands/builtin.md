---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The commands Django ships

The management commands that come with Django, by what each one drives: those of `django/core/management/commands/` and those of the contrib applications, the few whose classes reach into the machinery instead of only filling in `handle`, and the base class behind startproject and startapp, `TemplateCommand`.

Most of Django's commands are thin fronts. Such a command's `handle` reads the options, picks a database connection or a few applications, and hands the work to a subsystem that would do the same if it were called from anywhere else. To know what migrate really does is to know the migration executor, and the command's module is the wrong place to look for that. A few carry their work themselves: inspectdb writes model source from what a database reports, makemessages drives a set of external programs, the shell builds a namespace. So this page is mostly a map from each command to the code that does its work, and from there to the chapter that explains it.

## Django's own commands

These are the modules of `django/core/management/commands/`, which are commands in every project and the only commands where there are no settings.

| command | its `handle` hands the work to | told in |
|---|---|---|
| makemigrations | the autodetector, which compares the models with the state the migration files describe, and the writer, which turns the difference into files `django/db/migrations/autodetector.py:MigrationAutodetector.changes` | [Migrations](../migrations.md) |
| migrate | the executor, which applies or unapplies migrations to reach a target; the command sends the `pre_migrate` and `post_migrate` signals around it `django/db/migrations/executor.py:MigrationExecutor.migrate` | [Migrations](../migrations.md) |
| showmigrations | the loader's graph and the recorder's table, to list migrations or the plan `django/core/management/commands/showmigrations.py:Command.show_list` | [Migrations](../migrations.md) |
| sqlmigrate | the loader, which runs one migration against a schema editor that collects SQL and executes nothing `django/db/migrations/loader.py:MigrationLoader.collect_sql` | [Migrations](../migrations.md) |
| squashmigrations, optimizemigration | the optimizer, which shortens a list of operations, and the writer `django/db/migrations/optimizer.py:MigrationOptimizer.optimize` | [Migrations](../migrations.md) |
| dbshell | the backend's client class, which runs the database's own command-line program `django/db/backends/base/client.py:BaseDatabaseClient.runshell` | [Database backends](../backends.md) |
| inspectdb | the backend's introspection, from whose answers the command prints model source `django/db/backends/base/introspection.py:BaseDatabaseIntrospection` | [Database backends](../backends.md) |
| sqlflush | a function that picks every existing table of the installed, managed models and has the backend's operations build the statements that would empty them `django/core/management/sql.py:sql_flush` | [Database backends](../backends.md) |
| flush | the same statements, executed, and then the `post_migrate` signal `django/db/backends/base/operations.py:BaseDatabaseOperations.execute_sql_flush` | [Database backends](../backends.md) |
| sqlsequencereset | the backend's operations, for the statements that reset the sequences of some applications' tables `django/db/backends/base/operations.py:BaseDatabaseOperations.sequence_reset_sql` | [Database backends](../backends.md) |
| dumpdata | a serializer, fed the rows of the chosen models `django/core/serializers/__init__.py:serialize` | [Caching, files, mail, signals and tasks](../services.md) |
| loaddata | a deserializer, inside one transaction with constraint checking put off to its end `django/core/management/commands/loaddata.py:Command.loaddata` | [Caching, files, mail, signals and tasks](../services.md) |
| createcachetable | nothing else: the command builds the statements for the database cache's table itself `django/core/management/commands/createcachetable.py:Command.create_table` | [Caching, files, mail, signals and tasks](../services.md) |
| sendtestemail | the mail functions `django/core/mail/__init__.py:send_mail` | [Caching, files, mail, signals and tasks](../services.md) |
| makemessages, compilemessages | the GNU gettext programs, run as child processes `django/core/management/utils.py:popen_wrapper` | [Internationalization and time zones](../i18n.md) |
| test | the test runner class, named by `--testrunner` or else by `settings.TEST_RUNNER`, and its method that runs the tests `django/test/runner.py:DiscoverRunner.run_tests` | [The test framework](../testing.md) |
| listurls | a walk over the root URLconf's patterns `django/urls/utils.py:extract_views_from_urlpatterns` | [URL routing](../urls.md) |
| diffsettings | a comparison of the loaded settings with `django/conf/global_settings.py` `django/core/management/commands/diffsettings.py:Command.handle` | [Settings, apps and startup](../startup.md) |
| check | the check framework `django/core/management/base.py:BaseCommand.check` | [The system checks](checks.md) |
| runserver | the development server `django/core/servers/basehttp.py:run` | [The development server](runserver.md) |
| testserver | the code that makes a test database, and then the loaddata and runserver commands, called from code `django/core/management/commands/testserver.py:Command.handle` | [The development server](runserver.md#testserver) |
| startproject, startapp | `TemplateCommand` | [below](#commands-that-write-a-project-templatecommand) |
| shell | an interactive interpreter | [below](#the-shell) |

*The commands of `django/core/management/commands/`, by what does their work.*

> **Changed in 6.2.** listurls is new.

Some functions that several of these share live beside the commands. `emit_pre_migrate_signal` and `emit_post_migrate_signal` send the two signals once for each installed application that has a models module; migrate calls both, and flush the second (`django/core/management/sql.py:emit_post_migrate_signal`). And `run_formatters` runs the Black formatter, if one is installed, over the files or the directory a command has just written; the migration commands that write files and the two template commands call it (`django/core/management/utils.py:run_formatters`).

## The commands of the contrib applications

A contrib application's commands exist in a project that installs the application, and are found like any other application's ([Finding the command](finding.md#the-dictionary-of-commands-get_commands)).

| application | command | what it does |
|---|---|---|
| `django.contrib.auth` | createsuperuser | asks for, or reads from the environment, the fields of the user model, and calls the model manager's method that makes a superuser `django/contrib/auth/management/commands/createsuperuser.py:Command.handle` |
| | changepassword | asks for a password twice, validates it and saves it on the user `django/contrib/auth/management/commands/changepassword.py:Command.handle` |
| `django.contrib.contenttypes` | remove_stale_contenttypes | deletes the content types of installed applications whose model no longer exists, after listing, when it can ask for confirmation, what would go with them `django/contrib/contenttypes/management/commands/remove_stale_contenttypes.py:Command.handle` |
| `django.contrib.sessions` | clearsessions | calls the session engine's method that removes expired sessions `django/contrib/sessions/backends/base.py:SessionBase.clear_expired` |
| `django.contrib.staticfiles` | collectstatic | copies or links into the static files storage the first file found for each path among those the finders list, then lets the storage process them `django/contrib/staticfiles/management/commands/collectstatic.py:Command.collect` |
| | findstatic | asks the finders where a file is `django/contrib/staticfiles/finders.py:find` |
| | runserver | Django's runserver, with static files served ([The development server](runserver.md#which-application-it-serves)) |
| `django.contrib.gis` | inspectdb | Django's inspectdb, taught the geometry column types `django/contrib/gis/management/commands/inspectdb.py:Command` |
| | ogrinspect | prints model source for a layer of a geographic data file `django/contrib/gis/utils/ogrinspect.py:_ogrinspect` |

*The commands of the contrib applications. They belong to [Authentication, sessions and messages](../auth.md) and [Content types, static files and the other contrib apps](../contrib.md).*

Two of them have the name of a command of Django's and take its place, each by subclassing the class it displaces.

The name management has a second use. The auth, contenttypes and sites applications each keep, in a module of that name, the functions that run when migrate has finished its work, to create permissions, content types and the default site among other things, and connect them to `post_migrate` in their `AppConfig.ready` (`django/contrib/auth/management/__init__.py:create_permissions`, `django/contrib/auth/apps.py:AuthConfig.ready`). For an application that connects such receivers in the module itself, migrate and flush import the management module of every installed application at the start of their `handle` (`django/core/management/commands/migrate.py:Command.handle`).

## The few that reach into the machinery

A command usually leaves `BaseCommand` alone and defines `add_arguments` and `handle`. This is what each class of the recorded project's Django does beyond that: which of the attributes that steer the machinery its own class sets, and which methods of the machinery it overrides. The class's `help` text and its message for missing arguments, which many set, are not counted. Classes of `django.core` that do neither are left out, with a line of dots where they were.

```text recording=commands
The commands of django.core and of django.contrib.staticfiles: the base of each, and what its own class sets and overrides of what BaseCommand defines
    django.core
      check  (BaseCommand)
        requires_system_checks = []
      compilemessages  (BaseCommand)
        requires_system_checks = []
      createcachetable  (BaseCommand)
        requires_system_checks = []
      dbshell  (BaseCommand)
        requires_system_checks = []
      diffsettings  (BaseCommand)
        requires_system_checks = []
      ...
      flush  (BaseCommand)
        stealth_options = ["reset_sequences", "allow_cascade", "inhibit_post_migrate"]
      inspectdb  (BaseCommand)
        requires_system_checks = []
        stealth_options = ["table_name_filter"]
      listurls  (BaseCommand)
        overrides __init__
      ...
      makemessages  (BaseCommand)
        requires_system_checks = []
        requires_settings = False
      ...
      migrate  (BaseCommand)
        overrides get_check_kwargs
      ...
      runserver  (BaseCommand)
        stealth_options = ["shutdown_message"]
        suppressed_base_arguments = ["--traceback", "--verbosity"]
        overrides execute, get_check_kwargs
      ...
      shell  (BaseCommand)
        requires_system_checks = []
        requires_settings = False
      ...
      sqlflush  (BaseCommand)
        output_transaction = True
      sqlmigrate  (BaseCommand)
        output_transaction = True
        overrides execute
      sqlsequencereset  (AppCommand)
        output_transaction = True
      ...
      startapp  (templates.TemplateCommand)
        requires_settings = False
      startproject  (templates.TemplateCommand)
        requires_settings = False
      test  (BaseCommand)
        requires_system_checks = []
        overrides run_from_argv
      testserver  (BaseCommand)
        requires_system_checks = []
    django.contrib.staticfiles
      collectstatic  (BaseCommand)
        requires_system_checks = ["staticfiles"]
        overrides __init__
      findstatic  (LabelCommand)
      runserver  (runserver.Command)
```

**About half ask for no system checks**, counting the two template commands, which inherit an empty list from `TemplateCommand`. Two of those run the checks themselves, at a time of their choosing: check, whose whole purpose it is, and test, whose runner calls check once the test databases exist; a comment in the test command says so. The rest are the two that make a project or an application, shell and dbshell, the two for translation files, and inspectdb, diffsettings, createcachetable and testserver.

**Four can run without settings**, the two that create a project or an application, the shell, and makemessages ([Finding the command](finding.md#from-a-name-to-an-object)).

**A handful override a method of the machinery**, and each for a reason of its own.

- test overrides `BaseCommand.run_from_argv`. The test runner class may add arguments to the command's parser, and which class is the runner can itself be an option, `--testrunner`. So the option has to be read from the raw arguments before the parser is built (`django/core/management/commands/test.py:Command.run_from_argv`).
- runserver overrides `execute` and `get_check_kwargs`, to carry `--no-color` to the server's log and to move the checks to the process that serves ([The development server](runserver.md#the-command)).
- migrate overrides `get_check_kwargs`, to have the checks run against the database it will migrate.
- sqlmigrate overrides `execute` to take the colour out of the transaction statements that are put around its output, since the rest of what it prints is not coloured. It also decides in `handle`, for each run, whether those statements are wanted at all: only for a migration that is atomic on a database that can roll back changes to its schema (`django/core/management/commands/sqlmigrate.py:Command.handle`).
- listurls and collectstatic override `__init__`: the first to choose its own style object, the second to set up its lists of files, its storage and a style without colour.

One more is not in the recording because its application is not installed there. The createsuperuser command overrides `__init__`, to find the user model before its arguments are declared, and `execute`, to accept a stream to read from in place of standard input, which it declares as a stealth option, for the benefit of tests (`django/contrib/auth/management/commands/createsuperuser.py:Command.execute`).

## Commands that write a project: `TemplateCommand`

startproject and startapp are one class with two names. Each is a `TemplateCommand` whose `handle` passes on the word "project" or "app", and the project one adds a freshly generated secret key (`django/core/management/templates.py:TemplateCommand`, `django/core/management/commands/startproject.py:Command.handle`).

`TemplateCommand.handle` copies a directory, and renders some of the files on the way (`django/core/management/templates.py:TemplateCommand.handle`).

1. **It checks the name**: a valid Python identifier, and not the name of a module that can already be imported, with which the new one would conflict.
2. **It makes or accepts the target directory.**
3. **It prepares the template engine.** With no settings configured it configures the defaults and calls `django.setup`, so that the engine can run in an empty directory ([Who calls `django.setup`](../startup/callers.md#commands-that-configure-for-themselves)).
4. **It finds the template directory.** By default that is `django/conf/project_template/` or `django/conf/app_template/`. With `--template` it is a directory, or an archive that is unpacked into a temporary place, or a URL that is downloaded first.
5. **It walks the template directory**, creating each directory and file under the target, with the placeholder in a file's or a directory's name replaced by the real name. Compiled Python files are passed over, and so are hidden directories, or with `--exclude` the directories that option names. A file whose extension is one of those to render, `.py` and any that `--extension` adds, or whose name `--name` lists, is passed through the Django template language with the name, the directory, Django's version and a few more values as its context; every other file is copied as it is. A file that already exists at the destination stops the command.
6. **It runs a formatter** over the target directory, if one is installed. It looked for the formatter before step 4, so that nothing a template brought with it could be found in its place.

Two details of step 5 explain the look of the template directories. Their Python files are named with `-tpl` after the extension, and the command removes it when it writes them: a comment gives the reason, that a file full of template tags is not valid Python and must not be compiled when Django is installed. And the rendering is done with autoescaping off.

## The shell

The shell command starts an interactive interpreter in a process where Django has been started. It tries IPython, then bpython, then Python's own `code` module, and uses the first that can be imported, or the one `--interface` names. With `--command` it executes a string and exits, and where the platform allows it does the same with whatever is piped to its standard input (`django/core/management/commands/shell.py:Command.handle`).

What it adds to a bare interpreter is a namespace. `Command.get_auto_imports` in that file returns a list of dotted paths, and each is imported and bound under its last part: the settings object, the default database connection, the ORM's modules of models and of database functions, the function that empties the log of queries, the timezone module, and then every model class the app registry lists, which leaves out the models made automatically for many-to-many relations and the models that have been swapped for others. Where two models have the same name, the one from the application listed earlier in `settings.INSTALLED_APPS` is the one bound. A project changes the list by subclassing the command and overriding that method, in an application of its own (`django/core/management/commands/shell.py:Command.get_auto_imports`).

The command declares that it can run without settings. When there are none, it says that automatic imports are off, and why, and starts the interpreter with an empty namespace.

> **Changed in 6.0.** The settings object, the connection and the modules are imported along with the models. Before, only the models were.
