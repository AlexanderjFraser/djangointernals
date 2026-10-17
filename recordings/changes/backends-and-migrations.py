"""The habits of the section "What changed in the database backends and migrations", release
by release: what a project or a third-party backend written for an older Django meets in the
backends (a deprecated function; hooks renamed, removed or added; what introspection returns)
and in migrations (what the serializer writes, squashing, unmanaged models). PostgreSQL's and
MySQL's backends are asked without a server, for their classes and settings; nothing is sent.
The default database is SQLite in memory, as _run.py configures it. Where a habit stands for a
third-party backend, it is that connection with one thing changed for the call it records, and
put back after: its operations made a subclass that overrides field_cast_sql, or
has_native_duration_field set on its features. Run by recordings/changes.py under each release;
_run.py says how a habit is written.

The module writes two things into a temporary directory of its own run, which no line names:
`tides`, a module of the project's with a function under functools.cache and a deconstructible
class, which two habits serialize; and `ledger_migrations`, migrations of the application
journal with a squashed migration among them, which the habit that squashes gives journal
through MIGRATION_MODULES.
"""
import atexit
import os
import sys
import tempfile

from _run import configure, habit, main

configure()

SCRATCH = tempfile.TemporaryDirectory()
atexit.register(SCRATCH.cleanup)
sys.path.append(SCRATCH.name)

TIDES = '''\
import functools

from django.utils.deconstruct import deconstructible


@functools.cache
def high_water():
    return 0


@deconstructible
class Chart:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
'''

LEDGER_MIGRATIONS = {
    "0001_initial": '''\
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [migrations.CreateModel("Ledger", [("id", models.AutoField(primary_key=True))])]
''',
    "0002_ledger_page": '''\
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("journal", "0001_initial")]
    operations = [migrations.AddField("ledger", "page", models.IntegerField(default=0))]
''',
    "0001_squashed_0002_ledger_page": '''\
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    replaces = [("journal", "0001_initial"), ("journal", "0002_ledger_page")]
    dependencies = []
    operations = [
        migrations.CreateModel(
            "Ledger",
            [("id", models.AutoField(primary_key=True)), ("page", models.IntegerField(default=0))],
        ),
    ]
''',
    "0003_ledger_note": '''\
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("journal", "0002_ledger_page")]
    operations = [migrations.AddField("ledger", "note", models.TextField(default=""))]
''',
}


def write(path, text):
    with open(os.path.join(SCRATCH.name, path), "w", encoding="utf-8") as file:
        file.write(text)


write("tides.py", TIDES)
os.mkdir(os.path.join(SCRATCH.name, "ledger_migrations"))
write(os.path.join("ledger_migrations", "__init__.py"), "")
for name, text in LEDGER_MIGRATIONS.items():
    write(os.path.join("ledger_migrations", f"{name}.py"), text)


def without_server(engine):
    """A connection of PostgreSQL's or MySQL's backend made from settings alone; nothing opens it."""
    from django.db.utils import ConnectionHandler

    return ConnectionHandler({
        "default": {"ENGINE": "django.db.backends.dummy"},
        "server": {"ENGINE": engine, "NAME": "journal", "USER": "editor", "HOST": "db.journal.example"},
    })["server"]


# The backends


@habit("transaction.savepoint() inside transaction.atomic(): the savepoint's name, the thread's number written (the thread)")
def savepoint_in_atomic():
    import _thread

    from django.db import transaction

    with transaction.atomic():
        sid = transaction.savepoint()
        transaction.savepoint_rollback(sid)
    return sid.replace(str(_thread.get_ident()).replace("-", ""), "(the thread)")


@habit("from django.db.transaction import savepoint_create")
def savepoint_create_import():
    from django.db.transaction import savepoint_create

    return f"{savepoint_create.__module__}.{savepoint_create.__name__}"


@habit("connection.ops.integer_field_range(\"SmallIntegerField\") on SQLite")
def sqlite_small_integer_range():
    from django.db import connection

    return repr(connection.ops.integer_field_range("SmallIntegerField"))


@habit("MySQL's DatabaseWrapper.get_connection_params()[\"charset\"], no \"charset\" in OPTIONS")
def mysql_charset():
    return repr(without_server("django.db.backends.mysql").get_connection_params()["charset"])


@habit("a backend's operations that override field_cast_sql: the WHERE clause of Entry.objects.filter(title=\"Hull\")")
def field_cast_sql_override():
    from django.db import connection
    from django.db.backends.sqlite3.operations import DatabaseOperations
    from journal.models import Entry

    class CastingOperations(DatabaseOperations):
        def field_cast_sql(self, db_type, internal_type):
            return "CAST(%s AS TEXT)"

    query = Entry.objects.filter(title="Hull").query
    kept = connection.ops
    connection.ops = CastingOperations(connection)
    try:
        sql, params = query.get_compiler(connection=connection).as_sql()
    finally:
        connection.ops = kept
    return sql.split(" WHERE ", 1)[1]


@habit("BaseDatabaseOperations.return_insert_columns")
def return_insert_columns():
    from django.db.backends.base.operations import BaseDatabaseOperations

    return BaseDatabaseOperations.return_insert_columns.__qualname__


@habit("PostgreSQL's DatabaseSchemaEditor.sql_delete_column")
def postgresql_sql_delete_column():
    from django.db.backends.postgresql.schema import DatabaseSchemaEditor

    return repr(DatabaseSchemaEditor.sql_delete_column)


@habit("DurationField().get_db_prep_value(timedelta(seconds=1), connection): a backend whose features set "
       "has_native_duration_field and whose operations add no adapt_durationfield_value")
def native_duration_without_the_hook():
    from datetime import timedelta

    from django.db import connection, models

    field = models.DurationField()
    connection.features.has_native_duration_field = True
    try:
        value = field.get_db_prep_value(timedelta(seconds=1), connection)
    finally:
        del connection.features.has_native_duration_field
    return repr(value)


@habit("connection.introspection.get_relations(cursor, \"journal_volume\") on SQLite, its key declared ON DELETE CASCADE")
def sqlite_get_relations():
    from django.db import connection

    def shown(member):
        return repr(member) if member is None or isinstance(member, str) else member.__name__

    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE "journal_shelf" ("id" integer NOT NULL PRIMARY KEY)')
        cursor.execute(
            'CREATE TABLE "journal_volume" ("id" integer NOT NULL PRIMARY KEY, "shelf_id" integer NOT NULL '
            'REFERENCES "journal_shelf" ("id") ON DELETE CASCADE)'
        )
        relations = connection.introspection.get_relations(cursor, "journal_volume")
    return "{" + ", ".join(
        f"{column!r}: ({', '.join(shown(member) for member in value)})" for column, value in sorted(relations.items())
    ) + "}"


@habit("BaseDatabaseFeatures.prohibits_dollar_signs_in_column_aliases")
def prohibits_dollar_signs():
    from django.db.backends.base.features import BaseDatabaseFeatures

    return repr(BaseDatabaseFeatures.prohibits_dollar_signs_in_column_aliases)


# Migrations


@habit("serializer_factory(tides.high_water).serialize()[0]: a function under functools.cache")
def serialize_cached_function():
    import tides
    from django.db.migrations.serializer import serializer_factory

    return serializer_factory(tides.high_water).serialize()[0]


@habit("serializer_factory(zoneinfo.ZoneInfo(\"Europe/London\")).serialize()[0]")
def serialize_zoneinfo():
    import zoneinfo

    from django.db.migrations.serializer import serializer_factory

    return serializer_factory(zoneinfo.ZoneInfo("Europe/London")).serialize()[0]


@habit("serializer_factory(tides.Chart(**{\"x-scale\": 2, \"depth\": 5})).serialize()[0]: a keyword that is not an identifier")
def serialize_non_identifier_keyword():
    import tides
    from django.db.migrations.serializer import serializer_factory

    return serializer_factory(tides.Chart(**{"x-scale": 2, "depth": 5})).serialize()[0]


@habit("serializer_factory(functools.partial(int, base=2)).serialize()[0]")
def serialize_partial():
    import functools

    from django.db.migrations.serializer import serializer_factory

    return serializer_factory(functools.partial(int, base=2)).serialize()[0]


@habit("serializer_factory(list[int]).serialize()[0]: a generic alias")
def serialize_generic_alias():
    from django.db.migrations.serializer import serializer_factory

    return serializer_factory(list[int]).serialize()[0]


@habit("from django.db.migrations.serializer import DeconstructableSerializer")
def deconstructable_serializer():
    from django.db.migrations.serializer import DeconstructableSerializer

    return f"{DeconstructableSerializer.__module__}.{DeconstructableSerializer.__name__}"


@habit("squashmigrations journal 0003_ledger_note, where 0001_squashed_0002_ledger_page is among the migrations "
       "it squashes: what the new migration replaces")
def squash_a_squashed_migration():
    import importlib
    import io

    from django.core.management import call_command
    from django.test import override_settings

    directory = os.path.join(SCRATCH.name, "ledger_migrations")
    before = set(os.listdir(directory))
    with override_settings(MIGRATION_MODULES={"journal": "ledger_migrations"}):
        call_command("squashmigrations", "journal", "0003_ledger_note", interactive=False, verbosity=0,
                     stdout=io.StringIO(), stderr=io.StringIO())
    written = sorted(set(os.listdir(directory)) - before - {"__pycache__"})
    importlib.invalidate_caches()
    lines = []
    for file_name in written:
        name = file_name[:-3]
        migration = importlib.import_module(f"ledger_migrations.{name}").Migration
        lines.append(f"{name} replaces {migration.replaces!r}")
    return "\n".join(lines)


@habit("MigrationAutodetector, as makemigrations journal runs it, when an unmanaged model (Meta.managed = False) gains a field: "
       "the operations")
def unmanaged_model_gains_a_field():
    from django.db import models
    from django.db.migrations.autodetector import MigrationAutodetector
    from django.db.migrations.graph import MigrationGraph
    from django.db.migrations.questioner import MigrationQuestioner
    from django.db.migrations.state import ModelState, ProjectState

    def ledger(*fields):
        state = ProjectState()
        state.add_model(ModelState(
            "journal", "Ledger", [("id", models.AutoField(primary_key=True)), *fields], {"managed": False},
        ))
        return state

    before = ledger()
    after = ledger(("note", models.TextField(default="")))
    questioner = MigrationQuestioner(specified_apps={"journal"})  # makemigrations journal: an initial migration may be made
    changes = MigrationAutodetector(before, after, questioner).changes(graph=MigrationGraph())
    return repr([type(operation).__name__ for migration in changes.get("journal", []) for operation in migration.operations])


@habit("AddField on an unmanaged model (Meta.managed = False), applied by a schema editor that collects its SQL: the statements")
def unmanaged_add_field_sql():
    from django.db import connection, migrations, models
    from django.db.migrations.state import ModelState, ProjectState

    before = ProjectState()
    before.add_model(ModelState(
        "journal", "Logbook", [("id", models.AutoField(primary_key=True))], {"managed": False},
    ))
    operation = migrations.AddField("logbook", "note", models.TextField(default=""))
    after = before.clone()
    operation.state_forwards("journal", after)
    with connection.schema_editor(collect_sql=True) as editor:
        operation.database_forwards("journal", editor, before, after)
    return repr(editor.collected_sql)


main()
