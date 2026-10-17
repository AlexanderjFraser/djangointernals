"""The habits of the section "The versions Django needs: Python, databases and libraries",
release by release: what the installed package declares (the Python it requires, the libraries
it requires and its extras), the oldest server each database backend accepts, what a connection
to a server older than that meets, and what the PostgreSQL and MySQL backends do when imported
with an older driver. What a release declares is the metadata of its wheel from PyPI; what this
commit declares is that of the editable install of the pinned tree, which the module refuses to
read unless it was built at this commit. No server runs: the floors are read from each backend's
features; MySQL's backend opens on a stand-in for MySQLdb.connect whose server answers with the
version the title names; and an older driver is the installed one with its version attributes
made that release's, for the one import the habit records (psycopg 3.1.10's __version__;
mysqlclient 2.1.1's version_info, and no __version__, which that release's module does not
define). Run by recordings/changes.py under each release; _run.py says how a habit is written.
"""
import importlib
import sys

from _run import configure, habit, main

configure()


def installed_is_running():
    """Stop the recording unless the installed Django's metadata is the running Django's. A
    release's is its wheel's from PyPI; this commit's is what the editable install of the pinned
    tree built from its pyproject.toml, and is this commit's only if the install was made at it:
    the install's version carries the time of the commit it was built at, as get_version() does
    of the tree's HEAD."""
    import importlib.metadata

    import django

    installed, running = importlib.metadata.version("Django"), django.get_version()
    if installed != running:
        raise SystemExit(f"the installed Django's metadata is {installed}'s, not {running}'s: install the "
                         f"pinned tree again before recording what the package declares")


installed_is_running()


# What the package declares, which an installer reads


@habit("importlib.metadata.metadata(\"Django\")[\"Requires-Python\"]")
def requires_python():
    import importlib.metadata

    return importlib.metadata.metadata("Django")["Requires-Python"]


@habit("importlib.metadata.requires(\"Django\"): the requirements outside the extras")
def requires():
    import importlib.metadata

    return ", ".join(r for r in importlib.metadata.requires("Django") if "extra ==" not in r)


@habit("importlib.metadata.requires(\"Django\"): the extras")
def requires_extras():
    import importlib.metadata

    return ", ".join(r for r in importlib.metadata.requires("Django") if "extra ==" in r)


# The oldest server each backend accepts


@habit("PostgreSQL's DatabaseFeatures.minimum_database_version")
def postgresql_minimum():
    from django.db.backends.postgresql.features import DatabaseFeatures

    return repr(DatabaseFeatures.minimum_database_version)


@habit("SQLite's DatabaseFeatures.minimum_database_version")
def sqlite_minimum():
    from django.db.backends.sqlite3.features import DatabaseFeatures

    return repr(DatabaseFeatures.minimum_database_version)


@habit("Oracle's DatabaseFeatures.minimum_database_version")
def oracle_minimum():
    from django.db.backends.oracle.features import DatabaseFeatures

    return repr(DatabaseFeatures.minimum_database_version)


class StandInCursor:
    """The driver's cursor, for a server that answers as the version it is given: the SELECT of
    mysql_server_data has a row, with sql_auto_is_null off; any other statement has none."""

    def __init__(self, version):
        self.version = version
        self.rows = []

    def execute(self, query, args=None):
        self.rows = [(self.version, "STRICT_TRANS_TABLES", "InnoDB", 0, 0, 1)] if "VERSION()" in query else []
        return len(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def close(self):
        pass


def stand_in_for(version):
    """A stand-in for MySQLdb.connect: the connection it returns reaches no server."""

    class StandInConnection:
        encoders = {}

        def __init__(self, **params):
            pass

        def autocommit(self, on):
            pass

        def cursor(self):
            return StandInCursor(version)

        def close(self):
            pass

    return StandInConnection


def on_mysql(version, ask):
    """ask(connection) for a connection of MySQL's backend whose server answers as `version`;
    MySQLdb.connect and the version check's record of the alias are put back after."""
    import MySQLdb
    from django.db.backends.base import base
    from django.db.utils import ConnectionHandler

    alias = f"mysql {version}"
    connection = ConnectionHandler({
        "default": {"ENGINE": "django.db.backends.dummy"},
        alias: {"ENGINE": "django.db.backends.mysql", "NAME": "journal", "USER": "editor", "HOST": "db.journal.example"},
    })[alias]
    connect = MySQLdb.connect
    MySQLdb.connect = stand_in_for(version)
    try:
        return ask(connection)
    finally:
        connection.close()
        MySQLdb.connect = connect
        base.RAN_DB_VERSION_CHECK.discard(alias)


@habit("MySQL's DatabaseFeatures.minimum_database_version, the server answering as MySQL 8.4.6")
def mysql_minimum():
    return on_mysql("8.4.6", lambda connection: repr(connection.features.minimum_database_version))


@habit("MySQL's DatabaseFeatures.minimum_database_version, the server answering as MariaDB 11.4.5")
def mariadb_minimum():
    return on_mysql("11.4.5-MariaDB", lambda connection: repr(connection.features.minimum_database_version))


# A server older than the floor


@habit("connection.cursor() on MySQL's backend, the server answering as MySQL 8.0.36")
def mysql_8_0_refused():
    def open_a_cursor(connection):
        connection.cursor().close()
        return "the connection opens"

    return on_mysql("8.0.36", open_a_cursor)


# The drivers the backends import with


ABSENT = object()  # in `versions`: an attribute the driver at that version does not have


def put(driver, name, value):
    if value is ABSENT:
        if hasattr(driver, name):
            delattr(driver, name)
    else:
        setattr(driver, name, value)


def imported_with(module, package, driver, versions):
    """Import `module` afresh with the driver's version attributes as `versions` gives them, set
    or, where ABSENT, taken away; the driver and every module of `package` are put back as they
    were after."""
    parent, _, child = package.rpartition(".")
    kept = {name: sys.modules.pop(name) for name in list(sys.modules) if name == package or name.startswith(package + ".")}
    attributes = {name: getattr(driver, name, ABSENT) for name in versions}
    for name, value in versions.items():
        put(driver, name, value)
    try:
        importlib.import_module(module)
        return "the module is imported"
    finally:
        for name, value in attributes.items():
            put(driver, name, value)
        for name in [name for name in sys.modules if name == package or name.startswith(package + ".")]:
            del sys.modules[name]
        sys.modules.update(kept)
        if package in kept:
            setattr(sys.modules[parent], child, kept[package])


@habit("import django.db.backends.postgresql.base, psycopg's __version__ \"3.1.10\"")
def psycopg_3_1_10():
    import psycopg

    return imported_with("django.db.backends.postgresql.base", "django.db.backends.postgresql", psycopg,
                         {"__version__": "3.1.10"})


@habit("import django.db.backends.mysql.base, MySQLdb as mysqlclient 2.1.1 has it: version_info (2, 1, 1, \"final\", 0), no __version__")
def mysqlclient_2_1_1():
    import MySQLdb

    return imported_with("django.db.backends.mysql.base", "django.db.backends.mysql", MySQLdb,
                         {"version_info": (2, 1, 1, "final", 0), "__version__": ABSENT})


main()
