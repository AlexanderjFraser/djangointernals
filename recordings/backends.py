"""A recording of Django's database backends: how a connection is made for an alias and a
thread, opened and closed; how a statement goes through Django's cursor to the driver and its
rows come back; how transactions, savepoints and on_commit callbacks are kept; and what a
backend's features, operations object, schema editor, introspection and creation do, on SQLite
and, for the questions that need no server, on PostgreSQL, MySQL, MariaDB and Oracle.

    python recordings/backends.py > recordings/backends.txt

Chapter 11 of the book (pages/backends.md and the pages under it) is written against this
output. It needs the pinned Django (the project's virtual environment has it), the small project
beside it, `harbour/`, which chapters 8 to 10 record over too (a shipping line in three
applications, `fleet`, `crew` and `office`), with a router written for this recording,
`harbour/routers.py`; and the drivers of three other backends, psycopg 3.3.6, mysqlclient 2.3.0
and oracledb 26.0.1 (`requirements.txt`), whose servers never run. The databases are two SQLite
files made for the run. Run it again after a re-pin: where the output changes, the chapter has to.

The words. A connection is an instance of a backend's DatabaseWrapper, Django's object for one
alias of DATABASES in one thread, written `the connection "default"`. The backend is the package
ENGINE names; a DatabaseWrapper, DatabaseOperations, DatabaseFeatures, DatabaseSchemaEditor or
DatabaseCreation written without a module is SQLite's. The driver is the DB-API module, sqlite3;
the driver's connection is what its connect returned, which the connection holds as its attribute
`connection`; the driver's cursor is a SQLiteCursorWrapper, SQLite's backend's subclass of the
driver's Cursor. A cursor, alone, is Django's CursorWrapper around it. A statement is SQL sent to
the database; what the script runs is a line of Python.

The blocks are of three kinds, and a block may mix them. Where the order of calls is the point,
the lines are calls, nested as they were made: the calls a block is about and no others, so
everything between the lines ran and is left out. A line of Python is what the script ran, as it
ran it; under it stand the calls it set going, of those the block is about, and every statement
it sent: a line of Python with no `SQL` line under it sent none. Some lines of Python are run
with none of their calls written down; the statements they sent stand under them all the same. A
method is written by the class that declares it; `DatabaseFeatures.__init__
(BaseDatabaseFeatures.__init__)` is the class of the object and, in parentheses, the class whose
method ran. A call on a connection other than "default", or on one of its helper objects, says
which: `(on "archive")`. Arguments follow, each by its name, those left at their defaults passed
over. What a call returned follows `->`, put into words when it was returned; `raises` names an
exception, once, at the innermost written-down call it left, and again with its message under
the line of Python it ended; an exception of the driver's is named with its module
(`sqlite3.ProgrammingError`), Django's and Python's by the class alone. A generator (a context
manager's body is one) is written where its body first runs, and `X resumes` each time it runs
again; what it calls stands under that. A call written `sqlite3.Cursor.execute` is a method of
the driver's, written in C, by the driver's class that declares it: what it was given and
returned is not written. A function written in C that is called from C, as SQLite calls a
converter registered with it or an aggregate's step, is not seen and not written. The line
`sqlite3.connect(...)` is the driver's connect, with the arguments it was given.

A second kind of block puts one question to a running Django on each line: the expression, then
`->` and its value, with any statement it sent and any warning it set off (`warns`) under it; a
question that raised has the exception's name and message for its value. The third kind writes
down what an object holds, a thing to a line; `the connection holds:` writes five of the
connection's attributes by name.

Two kinds of line stand for a statement. A line `SQL` is a statement as Django handed it to its
cursor, with Django's `%s` placeholders and its parameters: the script's own execute wrapper,
put outermost on each connection of `connections` as Django makes it (the script makes none of
them itself), and on the two connections of MySQL's backend that the blocks with a stand-in
open, writes it. The wrapper writes the line before Django's cursor checks the
transaction (validate_no_broken_transaction): a `SQL` line followed by a `raises` and no `sqlite`
line was refused before it reached the database. `SQL (on "archive")` names the alias where it
is not "default"; `with each of [...] (executemany)` gives executemany's rows. A line `sqlite`
is a statement as SQLite ran it, with the parameters bound: the driver's trace callback, set on
each of the driver's connections as it is made, writes it, so it shows the statements a new
connection runs, the BEGIN and COMMIT the driver issues itself, and what Django's backend sends
past its own cursor. A statement on several lines is written on one. The `sqlite` lines are
written only in the blocks about opening a connection (and a version check that fails), Django's
cursor (and a doubled percent sign), a statement sent before the applications are ready (in an
interpreter of its own, where no `SQL` line is written), the debug cursor (and the query log of an
atomic block), execute wrappers (where the `SQL` lines are taken off), transactions (not
on_commit), the probe of supports_json_field, a datetime on its way in (and an aware one given to
the cursor), SQLite's callbacks and its aggregate, and OPTIONS. The statements a
connection runs as it opens are never `SQL` lines, so they are written only in those blocks;
elsewhere a line of Python or a question that opened a connection has none of them under it.
Django commits by calling the driver's commit, which is not an `SQL` line: where `sqlite` lines
are written the COMMIT stands under `sqlite3.Connection.commit` where the driver's calls are
written, and alone where they are not; elsewhere a BEGIN stands with no statement after it to
close it. The script stops if putting a call into words ever sends a statement, so that no line
of either kind is the script's own doing.

Other lines. `# ...` says what the script is about to do or has set up, where no line of Python
says it; under such a line some blocks show the code of the script's own functions (a router,
execute wrappers, a receiver, views, callbacks, a model), in which `note(...)` writes a line of
this output and `brief(...)` puts a value into words. A line `log` is a log record given to the
script's handler, with the names of its extra attributes. `reads connection.features.X  ->  value`
and `reads connection.operators[...]` are written by stand-ins the script puts on the connection
for one block, which its title says. An atomic block entered and left by hand, `outer.__enter__()`
and `outer.__exit__(None, None, None)`, is what a `with` statement calls at its start and end, and
`inner.__exit__(ValueError, ValueError('no berth'), None)` what it calls when that exception leaves
its body. After a line of Python that raised, `caught` is the exception it raised.

Stand-ins. Where a block needs what no server here gives, a stand-in of the script's own takes its
place, its code shown under a `#` line and its part said in the title: for the three blocks on
MySQL's backend opened with no server, MySQLdb.connect is StandInConnection, a driver's connection
whose cursor answers as a server of MySQL 8.4 would; FailingDriverConnection is a driver's
connection of SQLite whose commit and rollback raise; `unusable` is set as a connection's
is_usable; and bool_converter wraps the converter Django's backend registers with the driver for
"bool", which the driver calls from C, so that each call is written, `(written by bool_converter)`.
The calls of a stand-in are written by its own class.

How things are put into words: an instance by its repr; a class in an answer with its module; a
module as `the module ...`; a function by its name; a queryset by its class, model and result
cache; a list of more than six things as its first two and how many more, but under `full(...)`,
which writes a value whole as its repr. `named(field, name)` (a field given a name, as a
class statement gives it), `columns(field)` (db_type on each of the four connections in turn),
`sql_for(queryset, connection)` (as_sql of the queryset's compiler for that connection),
`insert_sql(connection, ports)` (the statements bulk_create would send: an InsertQuery of the
ports' name and country, compiled with the returning fields execute_sql would set),
`inserts_for(connection, objects, field names, ...)` (the same for any model, fields and
conflict options of bulk_create, the returning fields set as QuerySet._batched_insert sets them,
or, with returning=True, as Model.save sets them for one object), `flags(name)` (a feature flag
on each of six connections in turn), and `delete_sql(queryset, connection)` and
`update_sql(queryset, connection, **values)` (the DeleteQuery that QuerySet._raw_delete makes,
and the UpdateQuery that QuerySet.update makes, compiled for that connection) are helpers of the
script's own used in questions.

What differs between runs is written the same way every time. The run's directory, a temporary
one, is left out of every path, so that a database file is written by its name,
`harbour.sqlite3`; a thread's identifier, in the message `... thread id N ...`, is written by the
thread's part, `(the main thread)`, `(the second thread)`, `(the thread sync_to_async used)`, and
in a savepoint's name, which holds it, as `s(the thread)_x1`; a memory address is left out; a duration in the query log or a log
record is `0.000`; close_at, a time of time.monotonic, is asked only as a difference. The clock,
django.utils.timezone.now, returns 10 April 2026, 09:00 UTC. A set is sorted. These are this
build's: SQLite 3.50.4 and its limit of 32766 parameters to a statement (max_query_params),
multiprocessing's start method ('spawn', on Windows), and no rlwrap on the path (Oracle's command
line would begin with it).

Several parts run in an interpreter of their own, and their titles say so: the database files
and their first rows are made by one before anything is recorded, so that the recording's process
opens its first connection in its first block; the first use of `connections` is another; a
statement sent before the applications are ready a third; the five blocks on test databases a
fourth, in which no `SQL` line is written and a comment counts the statements a line of Python
sent; and TIME_ZONE on a connection where USE_TZ is False a
fifth. A few blocks change a setting of "default" in its settings_dict (CONN_MAX_AGE,
CONN_HEALTH_CHECKS, ATOMIC_REQUESTS) or switch a feature or a flag of the connection, as their
first lines and titles say, and put back what they changed; the last two blocks each add an alias
("memory", "immediate"), which stays to the end. The connections of PostgreSQL, MySQL, MariaDB and
Oracle (23, and 19 where a block says so) are made by ConnectionHandlers of the script's own, with
their servers' versions set by hand (as the lines say), and a guard stops the script if one of
them tries to connect; the two of MySQL's backend opened on the stand-in have no guard, and a
connection of SQLite's backend for an alias of its own, "aged", is made the same way for one
block. The blocks that open MySQL's backend on the stand-in take their alias, "mysql", out of
RAN_DB_VERSION_CHECK again as they end, and the blocks on altering a column drop the tables they
made. The rows the recording begins with are listed at its top; blocks add rows as they go and
the flush empties two tables.

    RECORD_EVERYTHING=django.db.backends,sqlite3 python recordings/backends.py    every call in the modules with that prefix, and the driver's methods
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# `harbour` imports from this directory, as it would from a project's. The directory goes last
# on the path and not first, where Python puts a script's own: `http.py` in it has the name of
# a package of the standard library, which Django imports.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != HERE] + [HERE]

import asyncio  # noqa: E402
import atexit  # noqa: E402
import datetime  # noqa: E402
import decimal  # noqa: E402
import enum  # noqa: E402
import functools  # noqa: E402
import inspect  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import sqlite3  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import types  # noqa: E402
import warnings  # noqa: E402
import weakref  # noqa: E402
import zoneinfo  # noqa: E402

import django  # noqa: E402
from django.conf import settings  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # the same bytes on every machine
EVERYTHING = tuple(p for p in os.environ.get("RECORD_EVERYTHING", "").split(",") if p)
PART = sys.argv[1] if len(sys.argv) > 1 else None

# The run's directory, made by the script when it runs whole and handed to each part it runs in
# an interpreter of its own. Its path is never written: see `normalised`.
SCRATCH = os.environ.get("RECORDING_SCRATCH") or tempfile.mkdtemp()
os.environ["RECORDING_SCRATCH"] = SCRATCH
DATABASE = os.path.join(SCRATCH, "harbour.sqlite3")
ARCHIVE = os.path.join(SCRATCH, "archive.sqlite3")

settings.configure(
    DEBUG=False,
    SECRET_KEY="recording",
    INSTALLED_APPS=["harbour.fleet", "harbour.crew", "harbour.office"],
    DATABASES={
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DATABASE},
        "archive": {"ENGINE": "django.db.backends.sqlite3", "NAME": ARCHIVE},
    },
    DATABASE_ROUTERS=["harbour.routers.LogbookRouter"],
    DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    MEDIA_ROOT=os.path.join(SCRATCH, "media"),
    USE_TZ=True,
    TIME_ZONE="Europe/Oslo",
)

LINES = []
MAIN_THREAD = threading.get_ident()
THREAD_NAMES = {MAIN_THREAD: "(the main thread)"}


class Stacks:
    """The watched frames open at this moment, which give the depth of the next line: one
    stack to a thread, so that a line is nested only under earlier lines of its own thread. A
    thread other than the script's starts one step in, under the line of Python that is running."""

    def __init__(self):
        self.by = {}

    def mine(self) -> list:
        return self.by.setdefault(threading.get_ident(), [])

    def append(self, frame) -> None:
        self.mine().append(frame)

    def pop(self):
        return self.mine().pop()

    def __getitem__(self, index):
        return self.mine()[index]

    def __len__(self) -> int:
        return len(self.mine()) + (0 if threading.get_ident() == MAIN_THREAD else 1)

    def __bool__(self) -> bool:
        return bool(self.mine())

    def clear(self) -> None:
        self.by.clear()


STACK = Stacks()
AT = {}  # where in LINES the line of each open watched call is, by the frame
SEEN = {}  # generator and coroutine frames already written down, each with its generator
PENDING = []  # the watched call that has just returned: (frame, depth, its line, what is to be said of its value)
RAISED = []  # exceptions already written down, at the innermost watched call they left
RESUMABLE = 0x20 | 0x80 | 0x200  # a generator, a coroutine, an asynchronous generator


class CCall:
    """A watched call of a function written in C (the driver's), open on the stack."""

    def __init__(self, function):
        self.function = function


def flush() -> None:
    """Say what the call that has just returned gave back, if that is to be said: on the
    call's own line where nothing was written under it, and on a line of its own otherwise."""
    while PENDING:
        frame, depth, at, said = PENDING.pop(0)
        if said is not None:
            if at == len(LINES) - 1:
                LINES[at] += f"  ->  {said}"
            else:
                LINES.append("  " * depth + f"-> {said}")


def note(text: str) -> None:
    flush()
    LINES.append("  " * len(STACK) + text)


def reset() -> None:
    LINES.clear()
    STACK.clear()
    AT.clear()
    SEEN.clear()
    RAISED.clear()


def normalised(line: str) -> str:
    """What differs from run to run, put the same way every time: see the docstring."""
    for path in (SCRATCH + os.sep, SCRATCH.replace("\\", "\\\\") + "\\\\", SCRATCH.replace("\\", "/") + "/"):
        line = line.replace(path, "")
    line = line.replace(SCRATCH, "(the run's directory)")
    line = re.sub(r"\bs\d+_x(\d+)", r"s(the thread)_x\1", line)
    line = re.sub(r"thread id (\d+)", lambda m: "thread id " + THREAD_NAMES.get(int(m.group(1)), m.group(1)), line)
    line = re.sub(r" at 0x[0-9A-Fa-f]+", "", line)
    line = re.sub(r"'time': '\d+\.\d{3}'", "'time': '0.000'", line)
    line = re.sub(r"\(\d+\.\d{3}\) ", "(0.000) ", line)
    line = re.sub(r"'duration': [0-9.e-]+", "'duration': 0.000", line)
    return line.rstrip()


def show(title: str) -> None:
    flush()
    print(title)
    for line in LINES:
        print("    " + normalised(line))
    print()
    reset()


# ---------------------------------------------------------------------------------------------
# The recorder.

RULES = {}  # the set in force
C_RULES = {}  # the driver's functions written in C that are watched, by their qualified names, with the label of each
LABELLING = False  # whether a call is being put into words at this moment: a statement sent then is a fault of this script's
LISTENING = False  # whether a statement sent to the database is written down
SQLITE = False  # whether a statement SQLite ran is written down as a line `sqlite`
AFTER = {}  # (module, qualname) -> what to say of the value a call returned


def plain(frame) -> str:
    return short(frame.f_code.co_qualname)


def short(qualname: str) -> str:
    """A qualified name without the functions it is defined inside."""
    return qualname.rsplit("<locals>.", 1)[-1]


MODULE_RULES = {}  # module -> the label of every function in it, for the block in force


def find(module: str, qualname: str):
    label = RULES.get((module, qualname))
    if label is not None:
        return label
    label = MODULE_RULES.get(module)
    if label is not None and "<" not in qualname:  # a module's functions, but not the expressions they iterate over
        return label
    if EVERYTHING and module.startswith(EVERYTHING):
        return plain
    return None


def c_name(function) -> str | None:
    """The qualified name of one of the driver's methods written in C, by the driver's class
    that declares it, or None for another function."""
    owner = getattr(function, "__self__", None)
    if isinstance(owner, (sqlite3.Cursor, sqlite3.Connection)):
        for klass in type(owner).__mro__:
            if klass.__module__ == "sqlite3" and function.__name__ in vars(klass):
                return f"sqlite3.{klass.__name__}.{function.__name__}"
    return None


def profile(frame, event, arg):
    global LABELLING
    if event == "c_call":
        if frame.f_globals.get("__name__") == "__main__":
            return  # the script's own calls of the driver, as when it sets the trace callback
        name = c_name(arg)
        if name is None or (name not in C_RULES and not (EVERYTHING and "sqlite3" in EVERYTHING)):
            return
        note(C_RULES.get(name) or name)
        STACK.append(CCall(arg))
        return
    if event in ("c_return", "c_exception"):
        if STACK and isinstance(STACK[-1], CCall) and STACK[-1].function == arg:
            flush()
            STACK.pop()
        return
    code = frame.f_code
    if code is UNWINDING:
        return
    if event == "call":
        label = find(frame.f_globals.get("__name__", ""), code.co_qualname)
        if label is None:
            return
        if code.co_flags & RESUMABLE:  # every resumption is a call event
            known = SEEN.get(id(frame))
            if known is not None and known() is frame.f_generator:
                note(f"{short(code.co_qualname)} resumes")
                STACK.append(frame)
                return
        flush()  # what the call before this one returned is said first
        LABELLING = True
        try:
            text = label(frame)
        except Exception:  # a fault of this script's: Python would drop the hook and carry on
            import traceback
            traceback.print_exc()
            os._exit(1)
        LABELLING = False
        if text is None:
            return
        if code.co_flags & RESUMABLE:
            SEEN[id(frame)] = weakref.ref(frame.f_generator)
        note(text)
        AT[id(frame)] = len(LINES) - 1
        STACK.append(frame)
    elif event == "return":
        if STACK and STACK[-1] is frame:
            flush()
            after = None if code.co_flags & RESUMABLE else AFTER.get((frame.f_globals.get("__name__", ""), code.co_qualname))
            LABELLING = True
            try:
                said = after(frame, arg) if after else None
            except Exception:
                if arg is not None:  # a fault of this script's
                    import traceback
                    traceback.print_exc()
                    os._exit(1)
                said = None  # an exception is leaving the frame, and unwinding() is about to say so
            LABELLING = False
            PENDING.append((frame, len(STACK), AT.pop(id(frame), -1), said))
            STACK.pop()


def unwinding(code, offset, exception):
    """An exception is leaving a function. The profile hook has just been told that the
    function returned None: where it was a watched call, take that back, and say what was
    raised, once, at the innermost watched call the exception leaves."""
    frame = sys._getframe(1)
    if PENDING and PENDING[-1][0] is frame:
        _, depth, at, _ = PENDING.pop()
        if not any(e is exception for e in RAISED) and not isinstance(exception, (StopIteration, StopAsyncIteration, GeneratorExit)):
            RAISED.append(exception)
            if at == len(LINES) - 1:
                LINES[at] += f"  raises {raised_name(exception)}"
            else:
                LINES.append("  " * depth + f"raises {raised_name(exception)}")


def raised_name(exception: BaseException) -> str:
    """An exception's class by its name, and, where it is not Django's or Python's own (the driver's), with its module."""
    kind = type(exception)
    if kind.__module__ == "builtins" or kind.__module__.startswith("django."):
        return kind.__name__
    return f"{kind.__module__}.{kind.__name__}"


UNWINDING = unwinding.__code__
MONITOR = sys.monitoring.PROFILER_ID
sys.monitoring.use_tool_id(MONITOR, "recordings/backends.py")
sys.monitoring.register_callback(MONITOR, sys.monitoring.events.PY_UNWIND, unwinding)
sys.monitoring.set_events(MONITOR, sys.monitoring.events.PY_UNWIND)


class recorded:
    """`with recorded(RULES):` writes down, of what runs in the block, the calls those
    rules name; `with recorded(RULES, sqlite=True):` also each statement SQLite ran."""

    def __init__(self, rules: dict, sqlite: bool = False, c: tuple = (), after: dict | None = None, modules: dict | None = None):
        self.rules = rules
        self.sqlite = sqlite
        self.c = c
        self.after = after or {}
        self.modules = modules or {}

    def __enter__(self):
        global RULES, LISTENING, SQLITE, C_RULES
        RULES = self.rules
        MODULE_RULES.clear()
        MODULE_RULES.update(self.modules)
        C_RULES = {name: name for name in self.c}
        self.kept = dict(AFTER)
        AFTER.update(self.after)
        LISTENING = True
        SQLITE = self.sqlite
        sys.setprofile(profile)

    def __exit__(self, *exc):
        global LISTENING, SQLITE, RULES, C_RULES
        sys.setprofile(None)
        LISTENING = False
        SQLITE = False
        flush()
        AFTER.clear()
        AFTER.update(self.kept)
        RULES, C_RULES = {}, {}
        MODULE_RULES.clear()


class sqlite_lines:
    """`with sqlite_lines():` writes down each statement SQLite ran, for lines of Python that record no calls."""

    def __enter__(self):
        global SQLITE, LISTENING
        SQLITE = LISTENING = True

    def __exit__(self, *exc):
        global SQLITE, LISTENING
        SQLITE = LISTENING = False


def _raises():
    raise KeyError("probe")


def self_test() -> None:
    """The line `raises X` depends on the profile hook being told of a return before
    sys.monitoring reports the unwinding. Prove it on this Python before anything is recorded."""
    global RULES
    with recorded({("__main__", "_raises"): plain}):
        try:
            _raises()
        except KeyError:
            pass
    if LINES != ["_raises  raises KeyError"]:
        raise SystemExit(f"recordings/backends.py: this Python reports an exception leaving a function otherwise than expected: {LINES!r}")
    reset()
    RULES = {}


self_test()

ASKING = {}  # the names a line of Python or a question may use, and the names a line binds


class Said(str):
    """An answer already put into words, to be written as it is and not as a string's repr."""

    __repr__ = str.__str__


def message(raised: BaseException) -> str:
    """An exception's message on one line: a newline inside it is written \\n."""
    return str(raised).replace("\n", "\\n")


def full(value) -> Said:
    """A value written whole, as its repr: a list of more than six things is not shortened."""
    return Said(repr(value))


def warned_lines(warned) -> None:
    for warning in warned:
        LINES.append("  " * len(STACK) + f"warns {warning.category.__name__}: {warning.message}")


def ask(expression: str, brief_: bool = False) -> None:
    """One question and its answer, on one line. The question is evaluated as it is written
    down, so the line cannot say one thing and the script do another."""
    global LISTENING
    watching, listening = sys.getprofile(), LISTENING
    sys.setprofile(None)  # a question is its answer and nothing else: no calls are written down under it
    flush()
    before = len(LINES)
    LISTENING = True
    with warnings.catch_warnings(record=True) as warned:
        warnings.simplefilter("always")
        try:
            value = eval(expression, ASKING)
            said = value if isinstance(value, Said) else answer(value)
        except Exception as raised:
            said = f"raises {raised_name(raised)}" + ("" if brief_ else f": {message(raised)}")
    warned_lines(warned)
    LISTENING = listening
    LINES[before:] = ["  " * len(STACK) + f"{expression}  ->  {said}", *("  " + line for line in LINES[before:])]
    sys.setprofile(watching)


def do(statement: str) -> None:
    """A line of Python, written down and then run, with what it sets going written under it.
    A name the line binds can be used by the lines and questions after it. Every statement it
    sends is written under it."""
    global LISTENING
    note(statement)
    STACK.append(None)
    listening, LISTENING = LISTENING, True
    with warnings.catch_warnings(record=True) as warned:
        warnings.simplefilter("always")
        try:
            exec(statement, ASKING)
        except Exception as raised:
            flush()
            LINES.append("  " * (len(STACK) - 1) + f"raises {raised_name(raised)}: {message(raised)}")
            ASKING["caught"] = raised  # what the next questions may ask about
        finally:
            flush()
    LISTENING = listening
    warned_lines(warned)
    STACK.pop()


def quietly(statement: str) -> None:
    """A line of Python that is written down and run with none of its calls recorded: under it
    stand only the statements it sent to the database."""
    global LISTENING
    watching, listening = sys.getprofile(), LISTENING
    sys.setprofile(None)
    note(statement)
    STACK.append(None)
    LISTENING = True
    try:
        exec(statement, ASKING)
    except Exception as raised:
        LINES.append("  " * (len(STACK) - 1) + f"raises {raised_name(raised)}: {message(raised)}")
    finally:
        flush()
        STACK.pop()
        LISTENING = listening
        sys.setprofile(watching)


def step(words: str) -> None:
    """A line that says what the script is about to do, where no line of Python says it."""
    note(f"# {words}")


def code(*things) -> None:
    """The source of the script's own functions or classes, each line under the `#` line before it, its blank lines left out."""
    for thing in things:
        for text in inspect.getsource(thing).splitlines():
            if text.strip():
                note("  " + text)


async def ado(statement: str) -> None:
    """`do` for a line of Python that awaits."""
    import ast

    note(statement)
    STACK.append(None)
    try:
        result = eval(compile(statement, "<line>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT), ASKING)
        if inspect.iscoroutine(result):
            await result
    except Exception as raised:
        flush()
        LINES.append("  " * (len(STACK) - 1) + f"raises {raised_name(raised)}: {message(raised)}")
    finally:
        flush()
        STACK.pop()


async def aask(expression: str) -> None:
    """`ask` for a question that awaits."""
    import ast

    global LISTENING
    flush()
    before = len(LINES)
    listening, LISTENING = LISTENING, True
    try:
        value = eval(compile(expression, "<question>", "eval", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT), ASKING)
        if inspect.iscoroutine(value):
            value = await value
        said = answer(value)
    except Exception as raised:
        said = f"raises {raised_name(raised)}: {message(raised)}"
    LISTENING = listening
    LINES[before:] = ["  " * len(STACK) + f"{expression}  ->  {said}", *("  " + line for line in LINES[before:])]


def on_second_thread(*lines) -> None:
    """Lines of Python and questions run on a second thread, which the main thread waits for:
    each is ("do", text) or ("ask", text)."""
    step("on a second thread, which the main thread waits for:")

    def run():
        THREAD_NAMES[threading.get_ident()] = "(the second thread)"
        for kind, text in lines:
            (do if kind == "do" else ask)(text)
        flush()

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()


# ---------------------------------------------------------------------------------------------
# The statements, as Django handed them to its cursor and as SQLite ran them.


def query_sent(execute, sql, params, many, context):
    """The script's execute wrapper, outermost on each connection of `connections`: it writes
    the line `SQL`."""
    if LABELLING:
        sys.stderr.write(f"recordings/backends.py: putting a call into words sent a statement to the database: {sql}\n")
        os._exit(1)
    if LISTENING:
        where = "" if context["connection"].alias == "default" else f' (on "{context["connection"].alias}")'
        sql = one_line(sql)
        if many:
            rows = params if isinstance(params, (list, tuple)) else "an iterator"
            note(f"SQL{where} {sql} with each of {rows!r} (executemany)")
        else:
            note(f"SQL{where} {sql} with params {params!r}" if params else f"SQL{where} {sql}")
    return execute(sql, params, many, context)


def ran(statement: str) -> None:
    """The driver's trace callback, set on every connection of the driver's that is made: it
    writes the line `sqlite`."""
    if LABELLING:
        sys.stderr.write(f"recordings/backends.py: putting a call into words ran a statement in SQLite: {statement}\n")
        os._exit(1)
    if LISTENING and SQLITE:
        note(f"sqlite {one_line(statement)}")


def one_line(sql: str) -> str:
    """A statement written on several lines, on one: each line break and the spaces around it become one space."""
    return re.sub(r"\s*\n\s*", " ", sql.strip())


_connect = sqlite3.dbapi2.connect


def connect(*args, **kwargs):
    """The driver's connect, with the trace callback set on what it returns before anything runs on it."""
    if ("sqlite3", "connect") in RULES or (EVERYTHING and "sqlite3" in EVERYTHING):
        flush()
        note("sqlite3.connect(" + ", ".join([*(repr(a) for a in args), *(f"{k}={v!r}" for k, v in kwargs.items())]) + ")")
    made = _connect(*args, **kwargs)
    made.set_trace_callback(ran)
    return made


sqlite3.dbapi2.connect = connect


def listen(conn) -> None:
    """Put the script's execute wrapper on a connection, outermost."""
    if query_sent not in conn.execute_wrappers:
        conn.execute_wrappers.insert(0, query_sent)


# ---------------------------------------------------------------------------------------------
# How values and calls are said.


def a(name: str) -> str:
    """A thing by its class's name, with the article the name is read with."""
    return ("an " if name[0] in "AEIOU" and not name.startswith(("One", "Use")) else "a ") + name


def brief(value) -> str:
    """A value in few words."""
    from django.db import models
    from django.db.backends.base.base import BaseDatabaseWrapper
    from django.db.backends.utils import CursorWrapper
    from django.dispatch import Signal

    if isinstance(value, BaseDatabaseWrapper):
        return f'the connection "{value.alias}"'
    if isinstance(value, CursorWrapper):
        return a(type(value).__name__)
    if isinstance(value, sqlite3.Cursor):
        return f"the driver's cursor, {a(type(value).__name__)}"
    if isinstance(value, sqlite3.Connection):
        return "the driver's connection"
    for helper in ("ops", "features", "introspection", "creation", "client", "validation"):
        owner = getattr(value, "connection", None)
        if isinstance(owner, BaseDatabaseWrapper) and getattr(owner, helper, None) is value:
            return f'{HELPER_NAMES[helper]} of "{owner.alias}"'
    if isinstance(value, Signal):
        return SIGNAL_NAMES.get(id(value), "a Signal")
    if isinstance(value, models.Model):
        return repr(value)
    if isinstance(value, models.QuerySet):
        fetched = value._result_cache
        return f"{a(type(value).__name__)} of {value.model.__name__}, " + ("no result cache" if fetched is None else f"a result cache of {len(fetched)}")
    if isinstance(value, models.Field):
        model = getattr(value, "model", None)
        return f"{model.__name__}.{value.name}" if inspect.isclass(model) else f"an unbound {type(value).__name__}"
    if isinstance(value, BaseException):
        return f"{type(value).__name__}({str(value)!r})"
    if isinstance(value, models.expressions.BaseExpression):
        return repr(value)
    if isinstance(value, (datetime.date, datetime.timedelta, datetime.time)):
        return repr(value).replace("datetime.timezone.utc", "UTC").replace("datetime.", "")
    if isinstance(value, (zoneinfo.ZoneInfo, datetime.timezone)):
        return repr(value)
    if isinstance(value, enum.Enum):
        return f"{type(value).__name__}.{value.name}"
    if isinstance(value, types.ModuleType):
        return f"the module {value.__name__}"
    if inspect.isclass(value):
        return value.__name__
    if isinstance(value, types.MethodType):
        return f"the method {short(value.__qualname__)} of {brief(value.__self__)}"
    if isinstance(value, (types.FunctionType, types.BuiltinFunctionType)):
        return f"the function {short(value.__qualname__)}"
    if isinstance(value, functools.partial):
        return f"a partial of {brief(value.func)}"
    if isinstance(value, list):
        return "[" + ", ".join(several(value)) + "]"
    if isinstance(value, tuple):
        return "(" + ", ".join(several(value)) + ("," if len(value) == 1 else "") + ")"
    if isinstance(value, (set, frozenset)):
        return "{" + ", ".join(sorted(brief(v) for v in value)) + "}" if value else "set()"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k!r}: {brief(v)}" for k, v in value.items()) + "}"
    if isinstance(value, (str, bytes, int, float, bool, type(None), decimal.Decimal)):
        return repr(value)
    return a(type(value).__name__)


def answer(value) -> str:
    """The answer to a question, as brief puts it, but for a class, which is written with its module."""
    if inspect.isclass(value):
        return f"{value.__module__}.{value.__qualname__}"
    return brief(value)


HELPER_NAMES = {
    "ops": "the operations object", "features": "the features", "introspection": "the introspection",
    "creation": "the creation", "client": "the client", "validation": "the validation",
}
SIGNAL_NAMES = {}


def several(values) -> list:
    if len(values) > 6:
        return [brief(values[0]), brief(values[1]), f"and {len(values) - 2} more"]
    return [brief(v) for v in values]


SIGNATURES = {}


def defaults(frame) -> dict:
    code = frame.f_code
    if code not in SIGNATURES:
        found = {}
        try:
            thing = sys.modules[frame.f_globals["__name__"]]
            for part in code.co_qualname.split("."):
                thing = inspect.getattr_static(thing, part)
            thing = getattr(thing, "__func__", thing)
            found = {n: p.default for n, p in inspect.signature(thing).parameters.items() if p.default is not p.empty}
        except Exception:
            pass
        SIGNATURES[code] = found
    return SIGNATURES[code]


def differs(value, default) -> bool:
    if default is None or isinstance(default, bool):
        return value is not default
    try:
        return bool(value != default)
    except Exception:
        return True


def given(frame, *leave_out) -> str:
    """The arguments a function was called with: each parameter by its name, those left at
    their defaults passed over; the one parameter of a function that has only one by its
    value alone; then what was passed as *args and **kwargs."""
    info = inspect.getargvalues(frame)
    had = defaults(frame)
    names = [n for n in info.args if n not in ("self", "cls") and n not in leave_out]
    positional = [n for n in names if n in frame.f_code.co_varnames[:frame.f_code.co_argcount]]
    alone = len(names) == 1 and names[0] not in had and not info.varargs and not info.keywords

    def named(some) -> list:
        return [
            brief(frame.f_locals[n]) if alone else f"{n}={brief(frame.f_locals[n])}"
            for n in some if not (n in had and not differs(frame.f_locals[n], had[n]))
        ]

    said = named(positional)
    if info.varargs:
        said += [brief(v) for v in frame.f_locals[info.varargs]]
    said += named([n for n in names if n not in positional])
    if info.keywords:
        said += [f"{k}={brief(v)}" for k, v in frame.f_locals[info.keywords].items()]
    return ", ".join(said)


def on(frame) -> str:
    """The connection a method of a connection or of one of its helpers ran on, where it is not "default"."""
    from django.db.backends.base.base import BaseDatabaseWrapper

    owner = frame.f_locals.get("self")
    if not isinstance(owner, BaseDatabaseWrapper):
        owner = getattr(owner, "connection", None) or getattr(owner, "db", None)
    if isinstance(owner, BaseDatabaseWrapper) and owner.alias != "default":
        return f'  (on "{owner.alias}")'
    return ""


def generic(frame) -> str:
    said = given(frame)
    return (f"{short(frame.f_code.co_qualname)}({said})" if said else short(frame.f_code.co_qualname)) + on(frame)


def without(*leave_out):
    def said(frame) -> str:
        text = given(frame, *leave_out)
        return (f"{short(frame.f_code.co_qualname)}({text})" if text else short(frame.f_code.co_qualname)) + on(frame)
    return said


def bare(frame) -> str:
    """A call by its name alone, and the connection where it is not "default"."""
    return short(frame.f_code.co_qualname) + on(frame)


def watch(module: str, *qualnames, label=None) -> dict:
    return {(module, name): label or generic for name in qualnames}


def value_after(frame, value) -> str:
    return brief(value)


def says(module: str, *qualnames, how=value_after) -> None:
    for name in qualnames:
        AFTER[(module, name)] = how


B = "django.db.backends.base.base"
BO = "django.db.backends.base.operations"
BF = "django.db.backends.base.features"
BS = "django.db.backends.base.schema"
BC = "django.db.backends.base.creation"
BI = "django.db.backends.base.introspection"
U = "django.db.backends.utils"
S3 = "django.db.backends.sqlite3.base"
S3O = "django.db.backends.sqlite3.operations"
S3F = "django.db.backends.sqlite3.features"
S3S = "django.db.backends.sqlite3.schema"
S3C = "django.db.backends.sqlite3.creation"
S3I = "django.db.backends.sqlite3.introspection"
S3FN = "django.db.backends.sqlite3._functions"
DBU = "django.db.utils"
DB = "django.db"
CU = "django.utils.connection"
TX = "django.db.transaction"
CO = "django.db.models.sql.compiler"
QS = "django.db.models.query"
DSP = "django.dispatch.dispatcher"
DDL = "django.db.backends.ddl_references"


def signal_sent(frame) -> str | None:
    """Signal.send, by the signal's name and its sender; a signal the chapter does not name
    (a model's pre_init and post_init) is not written."""
    signal = frame.f_locals["self"]
    if id(signal) not in SIGNAL_NAMES:
        return None
    return f"Signal.send  ({SIGNAL_NAMES[id(signal)]}, sender={brief(frame.f_locals.get('sender'))})"


def decoded(frame) -> str:
    """The lambda that the SQLite backend's decoder() makes, by the function it was made for."""
    return f"decoder({frame.f_locals['conv_func'].__name__})'s lambda({frame.f_locals['s']!r})"


def with_value(name: str):
    """A call by its name and the value of one of its arguments."""
    def said(frame) -> str:
        return f"{short(frame.f_code.co_qualname)}({brief(frame.f_locals[name])})" + on(frame)
    return said


def first_only(frame) -> str:
    """A call by its name and its first argument after self."""
    names = [n for n in frame.f_code.co_varnames[: frame.f_code.co_argcount] if n not in ("self", "cls")]
    return f"{short(frame.f_code.co_qualname)}({brief(frame.f_locals[names[0]])})" + on(frame)


def atomic_entered(frame) -> str:
    block = frame.f_locals["self"]
    said = [f"using={block.using!r}"] if block.using not in (None, "default") else []
    said += ["savepoint=False"] if not block.savepoint else []
    said += ["durable=True"] if block.durable else []
    return "Atomic.__enter__" + (f"  (an Atomic made with {', '.join(said)})" if said else "")


def atomic_left(frame) -> str:
    kind = frame.f_locals["exc_type"]
    return "Atomic.__exit__" + (f"(exc_type={kind.__name__})" if kind else "")


# ---------------------------------------------------------------------------------------------
# The parts that run in an interpreter of their own.


def make_database() -> None:
    """The two database files, their tables and their first rows: made in an interpreter of
    their own, so that the recording's process opens its first connection in its first block."""
    django.setup()
    from django.db import connections, router
    from django.apps import apps
    from harbour.crew.models import Officer, Rank, Sailor
    from harbour.fleet.models import Port, Ship, Voyage
    from harbour.office.models import Berth, Licence, LogEntry, Logbook, Manifest
    from django.utils import timezone

    now = datetime.datetime(2026, 4, 10, 9, 0, tzinfo=datetime.UTC)
    timezone.now = lambda: now
    for alias in ("default", "archive"):
        with connections[alias].schema_editor() as editor:
            for model in apps.get_models():
                if not model._meta.proxy and router.allow_migrate_model(alias, model):
                    editor.create_model(model)
    bergen = Port.objects.create(name="Bergen", country="Norway")
    leith = Port.objects.create(name="Leith", country="Scotland")
    lisbon = Port.objects.create(name="Lisbon", country="Portugal")
    petrel = Ship.objects.create(name="Petrel", tonnage=480, home=bergen)
    gannet = Ship.objects.create(name="Gannet", tonnage=1200, home=leith)
    ada = Sailor.objects.create(name="Ada", ship=petrel)
    Sailor.objects.create(name="Bram", ship=petrel)
    cora = Officer.objects.create(name="Cora", ship=gannet, rank=Rank.MASTER)
    Sailor.objects.create(name="Dag", ship=gannet)
    Sailor.objects.filter(name__in=["Ada", "Cora"]).update(signed_on=datetime.datetime(2011, 6, 1, 8, 0, tzinfo=datetime.UTC))
    gannet.captain = cora
    gannet.save()
    spring = Voyage.objects.create(ship=petrel, sailed=datetime.date(2026, 3, 2))
    spring.calls.add(leith, lisbon)
    autumn = Voyage.objects.create(ship=gannet, sailed=datetime.date(2025, 10, 6))
    autumn.calls.add(bergen)
    Licence.objects.create(sailor=ada, port=bergen, granted=datetime.date(2019, 5, 1))
    Berth.objects.create(port=bergen, number=1, metres=90)
    Manifest.objects.create(voyage=spring, crates=40, kilos_each=25)
    hull = Port.objects.using("archive").create(name="Hull", country="England")
    Ship.objects.using("archive").create(name="Skua", tonnage=300, home=hull)
    first = Logbook.objects.create(title="Petrel, 2025")
    Logbook.objects.create(title="Gannet, 2025")
    LogEntry.objects.create(book=first, line="Left Bergen at dawn.")
    LogEntry.objects.create(book=first, line="Fog off Shetland.")

    print('The rows the recording begins with, in "default"')
    print("    Port: " + ", ".join(f"{p.pk} {p.name} ({p.country})" for p in Port.objects.order_by("pk")))
    print("    Ship: " + ", ".join(f"{s.pk} {s.name} ({s.tonnage} tons, home {s.home.name}, captain {s.captain.name if s.captain else 'none'})" for s in Ship.objects.order_by("pk")))
    print("    Sailor: " + ", ".join(f"{s.pk} {s.name} (ship {s.ship.name}, signed on {s.signed_on:%Y-%m-%d %H:%M} UTC)" for s in Sailor.objects.order_by("pk")))
    print("    Officer: " + ", ".join(f"{o.pk} {o.name} ({o.rank})" for o in Officer.objects.order_by("pk")))
    print("    Voyage: " + ", ".join(f"{v.pk} (ship {v.ship.name}, sailed {v.sailed}, calls at {' and '.join(p.name for p in v.calls.order_by('pk'))})" for v in Voyage.objects.order_by("pk")))
    print("    Licence: " + ", ".join(f"{x.pk} ({x.sailor.name} into {x.port.name})" for x in Licence.objects.order_by("pk")))
    print("    Berth: " + ", ".join(f"{b.port.name} {b.number} ({b.metres} m)" for b in Berth.objects.order_by("port_id", "number")))
    print("    Manifest: " + ", ".join(f"{m.serial} (voyage {m.voyage_id}, {m.crates} crates of {m.kilos_each} kg, stamped {m.stamped})" for m in Manifest.objects.order_by("serial")))
    print('and in "archive", which has every table, and the only tables of Logbook and LogEntry')
    print("    Port: " + ", ".join(f"{p.pk} {p.name} ({p.country})" for p in Port.objects.using("archive").order_by("pk")))
    print("    Ship: " + ", ".join(f"{s.pk} {s.name} ({s.tonnage} tons, home {s.home.name})" for s in Ship.objects.using("archive").order_by("pk")))
    print("    Logbook: " + ", ".join(f"{b.pk} {b.title!r}" for b in Logbook.objects.order_by("pk")))
    print("    LogEntry: " + ", ".join(f"{e.pk} (logbook {e.book_id}, {e.line!r})" for e in LogEntry.objects.order_by("pk")))
    print()
    connections.close_all()


def run_part(name: str) -> None:
    """Run a part of the recording in an interpreter of its own, and print what it printed."""
    sys.stdout.flush()
    done = subprocess.run([sys.executable, os.path.abspath(__file__), name], capture_output=True, encoding="utf-8")
    if done.returncode:
        sys.exit(f"recordings/backends.py: the part {name!r} failed:\n{done.stderr}")
    sys.stdout.write(done.stdout)
    sys.stdout.flush()


def helper_made(frame) -> str:
    """The __init__ of a helper object, by the class of the object and, in parentheses, the class whose method ran."""
    made = type(frame.f_locals["self"]).__name__
    ran_ = short(frame.f_code.co_qualname)
    return f"{made}.__init__  ({ran_})" if not ran_.startswith(made + ".") else ran_


def first_use() -> None:
    """Block 2, in an interpreter of its own: `connections` before anything has asked it for a
    connection, which is before django.setup() imports the first model."""
    from django.db import connection, connections

    def not_yet(label):
        """Written only where the connection "default" has not been made in this thread."""
        def said(frame):
            return None if hasattr(connections._connections, "default") else label(frame)
        return said

    ASKING.update(connections=connections, connection=connection, sys=sys, django=django, full=full)
    makes = watch(CU, "BaseConnectionHandler.settings", "BaseConnectionHandler.configure_settings", label=generic) | {
        (CU, "BaseConnectionHandler.__getitem__"): not_yet(generic),
        ("django.db.models.options", "Options.contribute_to_class"): not_yet(lambda f: f"Options.contribute_to_class(cls={f.f_locals['cls'].__name__}, name={f.f_locals['name']!r})"),
    } | watch(
        DBU, "ConnectionHandler.configure_settings", label=bare,
    ) | watch(DBU, "ConnectionHandler.create_connection", "load_backend") | watch("importlib", "import_module", label=not_yet(lambda f: f"import_module({f.f_locals['name']!r})" if f.f_locals["name"].startswith("django.db.backends") or f.f_locals["name"].endswith(".models") else None)) | {
        (B, "BaseDatabaseWrapper.__init__"): lambda f: f"{type(f.f_locals['self']).__name__}.__init__(settings_dict=connections.settings['default'], alias={f.f_locals['alias']!r})  (BaseDatabaseWrapper.__init__)",
        ("django.db.backends.base.client", "BaseDatabaseClient.__init__"): helper_made,
        (BC, "BaseDatabaseCreation.__init__"): helper_made,
        (BF, "BaseDatabaseFeatures.__init__"): helper_made,
        (BI, "BaseDatabaseIntrospection.__init__"): helper_made,
        (BO, "BaseDatabaseOperations.__init__"): helper_made,
        ("django.db.backends.base.validation", "BaseDatabaseValidation.__init__"): helper_made,
    }
    makes[(CU, "BaseConnectionHandler.configure_settings")] = bare
    says(DBU, "ConnectionHandler.create_connection", "load_backend")
    says(DBU, "ConnectionHandler.configure_settings", how=lambda f, v: f"a dict of {len(v)}: {', '.join(repr(k) for k in v)}, each with its defaults filled in")
    ask("'settings' in vars(connections)")
    ask("'django.db.backends.sqlite3.base' in sys.modules")
    with recorded(makes):
        do("django.setup()")
    ask("'settings' in vars(connections)")
    ask("connections.all(initialized_only=True)")
    ask("'django.db.backends.sqlite3.base' in sys.modules")
    with recorded(makes):
        do("conn = connections['default']")
    ask("connections['default'] is conn")
    ask("conn.settings_dict is connections.settings['default']")
    ask("conn.connection")
    ask("type(conn)")
    ask("conn.alias")
    ask("type(connection)")
    ask("connection == connections['default']")
    ask("connection is connections['default']")
    ask("connection.alias")
    show("connections before and after the first use (an interpreter of its own): the first model class asks for the connection \"default\", and the handler makes it")


def test_databases() -> None:
    """The five blocks on test databases, in an interpreter of their own: a test database made and
    destroyed changes the settings of the process."""
    django.setup()
    from django.db import connection, connections
    from django.db.backends.base.base import BaseDatabaseWrapper

    sent = []

    def counting(execute, sql, params, many, context):
        """The execute wrapper of this part: it counts the statements, which are too many to write."""
        if LABELLING:
            sys.stderr.write(f"recordings/backends.py: putting a call into words sent a statement to the database: {sql}\n")
            os._exit(1)
        sent.append(sql)
        return execute(sql, params, many, context)

    def counted_do(statement: str) -> None:
        sent.clear()
        do(statement)
        note(f"  # {len(sent)} statements were sent while this line ran: none is written")

    connection.execute_wrappers.append(counting)
    ASKING.update(connection=connection, connections=connections, settings=settings, os=os, run_directory=SCRATCH, sys=sys, full=full)
    creating = watch(BC, "BaseDatabaseCreation.create_test_db", "BaseDatabaseCreation.destroy_test_db") | watch(
        S3C, "DatabaseCreation._get_test_db_name", "DatabaseCreation._create_test_db", "DatabaseCreation._destroy_test_db",
    ) | {
        ("django.core.management", "call_command"): lambda f: f"call_command({f.f_locals['command_name']!r}, " + ", ".join(f"{k}={v!r}" for k, v in f.f_locals["options"].items()) + ")",
    } | watch(S3, "DatabaseWrapper.close", label=bare) | watch(B, "BaseDatabaseWrapper.close", "BaseDatabaseWrapper.connect", label=bare)
    says(S3C, "DatabaseCreation._get_test_db_name", "DatabaseCreation._create_test_db")
    says(BC, "BaseDatabaseCreation.create_test_db")

    ask("connection.settings_dict['TEST']")
    quietly("connection.settings_dict['TEST']['NAME'] = os.path.join(run_directory, 'test_harbour.sqlite3')")
    quietly("old_name = connection.settings_dict['NAME']")
    ask("old_name")
    ask("settings.DATABASES['default'] is connection.settings_dict")
    with recorded(creating):
        counted_do("test_name = connection.creation.create_test_db(verbosity=0, autoclobber=True)")
    ask("test_name")
    ask("settings.DATABASES['default']['NAME']")
    ask("connection.settings_dict['NAME']")
    ask("os.path.exists(test_name)")
    ask("full(sorted(connection.introspection.table_names()))")
    with recorded(creating):
        counted_do("connection.creation.destroy_test_db(old_name, verbosity=0)")
    ask("os.path.exists(test_name)")
    ask("settings.DATABASES['default']['NAME']")
    ask("connection.settings_dict['NAME']")
    show("A test database, made and destroyed (an interpreter of its own): with TEST's NAME given, a file; its name replaces NAME in the settings, migrate makes the tables, and destroy_test_db removes the file and puts NAME back")

    quietly("connection.settings_dict['TEST']['NAME'] = None")
    with recorded(creating):
        counted_do("test_name = connection.creation.create_test_db(verbosity=0, autoclobber=True)")
    ask("test_name")
    ask("connection.settings_dict['NAME']")
    ask("connection.is_in_memory_db()")
    with recorded(creating):
        counted_do("connection.creation.destroy_test_db(old_name, verbosity=0)")
    ask("connection.settings_dict['NAME']")
    ask("connection.connection is None")
    show("The same with no TEST NAME (an interpreter of its own): SQLite's test database is then in memory, and destroy_test_db's close leaves its driver's connection open")

    import multiprocessing

    ASKING.update(multiprocessing=multiprocessing, BaseDatabaseWrapper=BaseDatabaseWrapper)
    quietly("connection.close()")
    ask("connection.creation.test_db_signature()")
    quietly("connection.settings_dict['TEST']['NAME'] = os.path.join(run_directory, 'test_harbour.sqlite3')")
    ask("connection.creation.test_db_signature()")
    counted_do("test_name = connection.creation.create_test_db(verbosity=0, autoclobber=True)")
    ask("connection.settings_dict['NAME']")
    ask("connection.creation.get_test_db_clone_settings('2')['NAME']")
    ask("multiprocessing.get_start_method()")
    quietly("connection.settings_dict['NAME'] = ':memory:'")
    ask("connection.creation.get_test_db_clone_settings('2')['NAME']")
    ask("connection.creation.test_db_signature()")
    quietly("connection.settings_dict['NAME'] = test_name")
    ask("connection.creation.serialize_db_to_string()")
    show("Clones and signatures (an interpreter of its own): what tells two test databases apart, the name of a clone for a second test process, asked once the test database is made, as a test run asks it, and the serialized rows, none here")

    cloning = watch(BC, "BaseDatabaseCreation.clone_test_db", label=without("verbosity")) | watch(
        S3C, "DatabaseCreation._clone_test_db", label=without("verbosity"),
    ) | watch(S3C, "DatabaseCreation.setup_worker_connection", label=first_only) | watch(B, "BaseDatabaseWrapper.connect", label=bare) | {
        (S3C, "DatabaseCreation.get_test_db_clone_settings"): first_only,
    }
    says(S3C, "DatabaseCreation.get_test_db_clone_settings", how=lambda f, v: f"the connection's settings with 'NAME': {v['NAME']!r}")
    ask("connection.settings_dict['NAME']")
    with recorded(cloning):
        counted_do("connection.creation.clone_test_db('2', verbosity=0)")
    ask("os.path.exists(os.path.join(run_directory, 'test_harbour_2.sqlite3'))")
    with recorded(cloning):
        counted_do("connection.creation.setup_worker_connection('2')  # as the second worker process calls it, here in this one")
    ask("connection.settings_dict['NAME']")
    ask("full(sorted(connection.introspection.table_names()))")
    show("A clone for a second test process, and that process's connection (an interpreter of its own, start method spawn): clone_test_db copies the test database's file, and setup_worker_connection copies the clone into a database in memory and connects to it")

    quietly("BaseDatabaseWrapper.close(connection)  # the base class's close, which SQLite's skips for a database in memory")
    quietly("connection.settings_dict['NAME'] = old_name")
    quietly("connection.settings_dict['TEST'].update(NAME=None, MIGRATE=False)")
    ask("settings.MIGRATION_MODULES")
    migrating = watch(BC, "BaseDatabaseCreation.create_test_db") | {
        ("django.core.management", "call_command"): lambda f: f"call_command({f.f_locals['command_name']!r}, " + ", ".join(f"{k}={v!r}" for k, v in f.f_locals["options"].items()) + ")"
        + (f"  (settings.MIGRATION_MODULES is then {settings.MIGRATION_MODULES!r})" if f.f_locals["command_name"] == "migrate" else ""),
    }
    with recorded(migrating):
        counted_do("test_name = connection.creation.create_test_db(verbosity=0, autoclobber=True)")
    ask("settings.MIGRATION_MODULES")
    ask("full(sorted(connection.introspection.table_names()))")
    show("A test database with TEST's MIGRATE False (an interpreter of its own): create_test_db sets every application's migrations to None for the migrate command, which then makes the tables from the models, and puts MIGRATION_MODULES back")
    connections.close_all()


def before_ready() -> None:
    """A block in an interpreter of its own: a statement sent before django.setup() has made the applications ready."""
    from django.apps import apps
    from django.db import connection

    ASKING.update(apps=apps, connection=connection, django=django)
    executing = watch(U, "CursorWrapper.execute", "CursorWrapper._execute_with_wrappers", "CursorWrapper._execute", label=bare)
    ask("apps.ready")
    quietly("connection.ensure_connection()")
    with recorded(executing, sqlite=True):
        do("with connection.cursor() as cursor: cursor.execute('SELECT COUNT(*) FROM fleet_ship')")
    do("django.setup()")
    ask("apps.ready")
    with recorded(executing, sqlite=True):
        do("with connection.cursor() as cursor: cursor.execute('SELECT COUNT(*) FROM fleet_ship')")
    quietly("connection.close()")
    show("A statement sent before the applications are ready (an interpreter of its own, before django.setup()): CursorWrapper._execute warns, and sends it all the same")


def time_zone_without_use_tz() -> None:
    """A block in an interpreter of its own: a connection with TIME_ZONE set where USE_TZ is False."""
    from django.db.utils import ConnectionHandler

    ASKING.update(settings=settings, ConnectionHandler=ConnectionHandler)
    quietly("settings.USE_TZ = False")
    quietly("zoned = ConnectionHandler({'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': 'harbour.sqlite3', 'TIME_ZONE': 'Europe/Oslo'}})['default']")
    with recorded(watch(B, "BaseDatabaseWrapper.cursor", "BaseDatabaseWrapper._cursor", "BaseDatabaseWrapper.ensure_connection", "BaseDatabaseWrapper.connect",
                        "BaseDatabaseWrapper.check_settings", "BaseDatabaseWrapper.get_connection_params", label=bare) | watch(
                  S3, "DatabaseWrapper.get_connection_params", label=bare)):
        do("zoned.cursor()")
    ask("zoned.connection is None")
    show("TIME_ZONE on a connection where USE_TZ is False (an interpreter of its own): check_settings refuses it as the connection opens, before any driver's connection is made")


PARTS = {
    "make-database": make_database, "first-use": first_use, "test-databases": test_databases, "before-ready": before_ready,
    "use-tz-off": time_zone_without_use_tz,
}

if PART is not None:
    PARTS[PART]()
    sys.exit(0)


def tidy() -> None:
    from django.db import connections

    for conn in connections.all(initialized_only=True):
        try:
            conn.close()
        except Exception:
            pass
    shutil.rmtree(SCRATCH, ignore_errors=True)


atexit.register(tidy)

PIN = json.load(open(os.path.join(os.path.dirname(HERE), "pin.json"), encoding="utf-8"))["trees"]["django"]["commit"]
print(f"Django {django.VERSION[0]}.{django.VERSION[1]} in development, at the commit {PIN}, on Python {sys.version_info[0]}.{sys.version_info[1]}"
      f" with SQLite {sqlite3.sqlite_version}, and the project harbour:\n"
      "INSTALLED_APPS = ['harbour.fleet', 'harbour.crew', 'harbour.office'], DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField',\n"
      "DEBUG = False, USE_TZ = True, TIME_ZONE = 'Europe/Oslo', DATABASE_ROUTERS = ['harbour.routers.LogbookRouter'],\n"
      "DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': 'harbour.sqlite3'},\n"
      "             'archive': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': 'archive.sqlite3'}},\n"
      "and the clock at 2026-04-10 09:00 UTC\n")
run_part("make-database")

# ---------------------------------------------------------------------------------------------
# Django is set up, nothing recorded. No connection is opened here.

django.setup()

from django.core import signals  # noqa: E402
from django.core.handlers.wsgi import WSGIHandler  # noqa: E402
from django.db import (  # noqa: E402
    DEFAULT_DB_ALIAS, DatabaseError, IntegrityError, OperationalError, close_old_connections, connection, connections, models, reset_queries,
    router, transaction,
)
from django.db.backends.signals import connection_created  # noqa: E402
from django.db.utils import ConnectionHandler, ConnectionRouter, load_backend  # noqa: E402
from django.utils import timezone  # noqa: E402

from harbour.crew.models import Officer, Sailor  # noqa: E402
from harbour.fleet.models import Port, Ship, Voyage  # noqa: E402
from harbour.office.models import Berth, Licence, LogEntry, Logbook, Manifest  # noqa: E402

NOW = datetime.datetime(2026, 4, 10, 9, 0, tzinfo=datetime.UTC)
timezone.now = lambda: NOW  # the recording's clock: see the docstring

SIGNAL_NAMES.update({
    id(signals.request_started): "request_started", id(signals.request_finished): "request_finished",
    id(connection_created): "connection_created", id(signals.got_request_exception): "got_request_exception",
})

for made in connections.all(initialized_only=True):  # "default", which django.setup() made
    listen(made)
_create_connection = connections.create_connection


def create_connection(alias):
    """`connections`' create_connection, with the script's execute wrapper put on each connection as
    Django makes it: the script makes no connection of its own."""
    made = _create_connection(alias)
    listen(made)
    return made


connections.create_connection = create_connection

ASKING.update(
    models=models, connection=connection, connections=connections, router=router, transaction=transaction, signals=signals,
    datetime=datetime, decimal=decimal, Decimal=decimal.Decimal, zoneinfo=zoneinfo, time=time, threading=threading, asyncio=asyncio, timezone=timezone,
    DatabaseError=DatabaseError, IntegrityError=IntegrityError, OperationalError=OperationalError, DEFAULT_DB_ALIAS=DEFAULT_DB_ALIAS,
    ConnectionHandler=ConnectionHandler, ConnectionRouter=ConnectionRouter, load_backend=load_backend,
    close_old_connections=close_old_connections, reset_queries=reset_queries, connection_created=connection_created, WSGIHandler=WSGIHandler,
    Port=Port, Ship=Ship, Voyage=Voyage, Sailor=Sailor, Officer=Officer, Licence=Licence, Manifest=Manifest, Berth=Berth,
    Logbook=Logbook, LogEntry=LogEntry, said=lambda value: Said(brief(value)), brief=brief, Said=Said, full=full,
)

# ---------------------------------------------------------------------------------------------
# 1. The spine.

OPENING = watch(
    B, "BaseDatabaseWrapper.cursor", "BaseDatabaseWrapper._cursor", "BaseDatabaseWrapper.close_if_health_check_failed",
    "BaseDatabaseWrapper.ensure_connection", "BaseDatabaseWrapper.connect", "BaseDatabaseWrapper.init_connection_state",
    "BaseDatabaseWrapper.check_database_version_supported", "BaseDatabaseWrapper._prepare_cursor", "BaseDatabaseWrapper.make_cursor",
    "BaseDatabaseWrapper.validate_thread_sharing", label=bare,
) | watch(B, "BaseDatabaseWrapper.set_autocommit") | watch(
    S3, "DatabaseWrapper.get_connection_params", "DatabaseWrapper.get_new_connection", "DatabaseWrapper.create_cursor",
    "DatabaseWrapper.get_database_version", label=bare,
) | watch(S3, "DatabaseWrapper._set_autocommit") | watch(S3FN, "register", label=bare) | {
    (DSP, "Signal.send"): signal_sent,
    ("sqlite3", "connect"): bare,
}
says(S3, "DatabaseWrapper.get_connection_params", "DatabaseWrapper.get_new_connection", "DatabaseWrapper.create_cursor", "DatabaseWrapper.get_database_version")
says(B, "BaseDatabaseWrapper.make_cursor", "BaseDatabaseWrapper.cursor")
EXECUTING = watch(
    U, "CursorWrapper.execute", "CursorWrapper._execute_with_wrappers", "CursorWrapper._execute", label=bare,
) | watch(S3, "SQLiteCursorWrapper.execute", "SQLiteCursorWrapper.convert_query", label=bare)
FETCHING = watch(CO, "SQLCompiler.execute_sql", "SQLCompiler.results_iter", "SQLCompiler.get_converters", "SQLCompiler.apply_converters", label=bare) | watch(
    S3O, "DatabaseOperations.get_db_converters", label=lambda f: f"DatabaseOperations.get_db_converters({brief(f.f_locals['expression'])})",
) | {(CO, "cursor_iter"): lambda f: f"cursor_iter(itersize={f.f_locals['itersize']})"} | {
    (S3, "decoder.<locals>.<lambda>"): decoded,
    ("django.utils.dateparse", "parse_datetime"): generic,
    (S3O, "DatabaseOperations.convert_datetimefield_value"): with_value("value"),
}
says(S3O, "DatabaseOperations.get_db_converters", how=lambda f, v: "[" + ", ".join(short(c.__qualname__) for c in v) + "]")
says(CO, "SQLCompiler.get_converters", how=lambda f, v: "{" + ", ".join(f"{pos}: [{', '.join(short(c.__qualname__) for c in convs)}]" for pos, (convs, _) in v.items()) + "}")
says("django.utils.dateparse", "parse_datetime")
says(S3O, "DatabaseOperations.convert_datetimefield_value")
CLOSING = watch(DB, "close_old_connections", label=bare) | watch(
    B, "BaseDatabaseWrapper.close_if_unusable_or_obsolete", "BaseDatabaseWrapper.get_autocommit", "BaseDatabaseWrapper.close", "BaseDatabaseWrapper._close", label=bare,
) | watch(S3, "DatabaseWrapper.close", label=bare)
DRIVER = ("sqlite3.Connection.execute", "sqlite3.Connection.cursor", "sqlite3.Cursor.execute", "sqlite3.Cursor.fetchmany",
          "sqlite3.Cursor.close", "sqlite3.Connection.close", "sqlite3.Connection.commit", "sqlite3.Connection.rollback")
with recorded(OPENING | EXECUTING | FETCHING | CLOSING, sqlite=True, c=DRIVER):
    do("sailors = list(Sailor.objects.filter(ship__name='Petrel'))")
    do("signals.request_finished.send(sender=WSGIHandler)")
show("One query, from the connection to the driver and back")

# ---------------------------------------------------------------------------------------------
# Connections.

run_part("first-use")

quietly("given = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': 'harbour.sqlite3'}}")
quietly("handler = ConnectionHandler(given)")
ask("handler.settings is given")
for key, value in ASKING["handler"].settings["default"].items():
    note(f"settings['default'][{key!r}]: {value!r}")
show("What configure_settings fills in: a ConnectionHandler of the script's own, given ENGINE and NAME, and its settings afterwards, a key to a line")

quietly("empty = ConnectionHandler({})")
ask("empty.settings['default']['ENGINE']")
ask("type(empty['default'])")
ask("empty['default'].cursor()")
ask("empty['default'].close()")
ask("ConnectionHandler({'other': {'ENGINE': 'django.db.backends.sqlite3'}}).settings")
ask("ConnectionHandler({'default': {}}).settings['default']['ENGINE']")
ask("connections['nosuch']")
ask("load_backend('django.db.backends.nosuch')")
ask("load_backend('harbour.nosuch')")
show("No databases, a backend that is not there, and an alias that is not there")

ask("type(empty['default'])")
ask("empty['default'].rollback()")
ask("empty['default'].features.uses_savepoints")
ask("empty['default'].savepoint()")
ask("empty['default'].commit()")
show("The dummy backend's connection: rollback() returns None where commit() raises, and savepoint() returns None, its features saying it uses no savepoints (the connection of ConnectionHandler({}) from the block before)")

quietly("main_connection = connections['default']")
ask("main_connection.connection is None")
on_second_thread(
    ("ask", "connections.all(initialized_only=True)"),
    ("ask", "connections['default'] is main_connection"),
    ("ask", "connections.all(initialized_only=True)"),
    ("ask", "main_connection.allow_thread_sharing"),
    ("ask", "main_connection.cursor()"),
)
ask("main_connection.connection is None")
do("main_connection.inc_thread_sharing()")
on_second_thread(
    ("ask", "main_connection.allow_thread_sharing"),
    ("ask", "main_connection.cursor().execute('SELECT COUNT(*) FROM fleet_ship').fetchone()"),
)
do("main_connection.dec_thread_sharing()")
ask("main_connection.allow_thread_sharing")
ask("main_connection.dec_thread_sharing()")
show("A connection for each thread: the second thread is given its own, and may use the main thread's only while it is shared")

from asgiref.sync import sync_to_async  # noqa: E402

ASKING.update(sync_to_async=sync_to_async)


def on_the_other_thread(begins: bool) -> None:
    """Unrecorded: the thread sync_to_async runs things on is named, and its connection closed at the end."""
    THREAD_NAMES[threading.get_ident()] = "(the thread sync_to_async used)"
    if not begins:
        connections["default"].close()


async def in_the_loop() -> None:
    await sync_to_async(on_the_other_thread)(True)
    ask("threading.current_thread() is threading.main_thread()")
    ask("connections['default'].cursor()")
    ask("Ship.objects.count()")
    await aask("await sync_to_async(threading.current_thread)() is threading.main_thread()")
    await aask("await sync_to_async(connections.__getitem__)('default') is main_connection")
    await aask("await sync_to_async(threading.get_ident)() == await sync_to_async(threading.get_ident)()")
    await aask("await sync_to_async(Ship.objects.count)()")
    await sync_to_async(on_the_other_thread)(False)


ASKING.update(in_the_loop=in_the_loop)
do("asyncio.run(in_the_loop())  # the script's coroutine, whose lines stand under this one")
show("Inside an event loop: a connection refuses to be used there, and sync_to_async runs the work on another thread, which has its own connection")


async def asks_first():
    """A task of the script's own: what it asks of connections is the connection "default"."""
    return connections["default"]


async def in_a_new_loop() -> None:
    await ado("first, second = await asyncio.gather(asks_first(), asks_first())")
    ask("first is second")
    ask("first is main_connection")
    ask("connections['default'] is main_connection")
    ask("connections['default'] is first")
    await ado("third, fourth = await asyncio.gather(asks_first(), asks_first())")
    ask("third is fourth is connections['default']")
    ask("threading.current_thread() is threading.main_thread()")


ASKING.update(asks_first=asks_first, in_a_new_loop=in_a_new_loop)
step("a task of the script's own:")
code(asks_first)
do("asyncio.run(in_a_new_loop())  # the script's coroutine, whose lines stand under this one; nothing in it has asked for a connection before")
show("In an event loop's thread, connections are kept for each task's context: the main thread's connection is not given, tasks gathered before the coroutine asks each make their own, and tasks gathered after it share the coroutine's")

REQUEST = {(DSP, "Signal.send"): signal_sent} | watch(DB, "reset_queries", "close_old_connections", label=bare) | watch(
    B, "BaseDatabaseWrapper.close_if_unusable_or_obsolete", "BaseDatabaseWrapper.close", label=bare,
) | watch(S3, "DatabaseWrapper.close", label=bare)
quietly("Ship.objects.count()")
ask("connection.connection is None")
with recorded(REQUEST):
    do("signals.request_started.send(sender=WSGIHandler, environ={})")
    ask("connection.connection is None")
    quietly("Ship.objects.count()")
    do("signals.request_finished.send(sender=WSGIHandler)")
ask("connection.connection is None")
show("A request's start and end, sent by hand as WSGIHandler sends them: each connection made in this thread is asked whether to close (CONN_MAX_AGE is 0)")

# ---------------------------------------------------------------------------------------------
# Routing between databases.

import harbour.routers  # noqa: E402

ASKING.update(settings=settings, harbour=harbour)
ask("settings.DATABASE_ROUTERS")
ask("router.routers")
ask("type(router.routers[0])")
step("the module harbour/routers.py:")
for text in inspect.getsource(harbour.routers).splitlines():
    note("  " + text if text else "")
show("A router of the project's own: the class DATABASE_ROUTERS names, which sends the office's logbooks to \"archive\"")

quietly("skua = Ship.objects.using('archive').get(name='Skua')")
quietly("petrel = Ship.objects.get(name='Petrel')")
ask("router.db_for_read(Logbook)")
ask("router.db_for_write(LogEntry)")
ask("router.db_for_read(Ship)")
ask("skua._state.db")
ask("router.db_for_write(Ship, instance=skua)")
ask("router.db_for_write(Ship, instance=petrel)")
ask("Ship.objects.using('archive').get(name='Skua')._state.db")
ask("router.allow_migrate('archive', 'fleet')")
ask("router.allow_migrate('default', 'office', model_name='logbook')")
ask("router.allow_migrate_model('default', Logbook)")
ask("router.allow_migrate_model('archive', Logbook)")
ask("router.allow_relation(skua, petrel)")
show("Routing questions: the router's answer where it gives one, the instance's database or \"default\" where it gives none")

ask("Logbook._meta.model_name")
ask("Logbook._meta.object_name")
ask("router.allow_migrate('default', 'office', model_name=Logbook._meta.model_name)")
ask("router.allow_migrate('default', 'office', model_name=Logbook._meta.object_name)")
ask("router.allow_migrate_model('default', Logbook)")
show("allow_migrate asked with the class's own name, as makemigrations asks it: LogbookRouter knows the lower-case name only, gives no answer, and the migration is allowed")


def route_said(frame) -> str:
    action = frame.f_code.co_freevars and frame.f_locals.get("action")
    hints = frame.f_locals.get("hints") or {}
    extra = "".join(f", {k}={brief(v)}" for k, v in hints.items())
    return f"ConnectionRouter.{action}({frame.f_locals['model'].__name__}{extra})  (the function _router_func made)"


ROUTING = watch(QS, "QuerySet.count", "QuerySet.db", label=bare) | {
    (DBU, "ConnectionRouter._router_func.<locals>._route_db"): route_said,
    ("harbour.routers", "LogbookRouter.db_for_read"): lambda f: f"LogbookRouter.db_for_read({f.f_locals['model'].__name__})",
    ("django.db.models.sql.query", "Query.get_count"): lambda f: f"Query.get_count(using={f.f_locals['using']!r})",
    ("django.db.models.sql.query", "Query.get_compiler"): lambda f: f"Query.get_compiler(using={f.f_locals['using']!r})",
    (CU, "BaseConnectionHandler.__getitem__"): generic,
}
says(DBU, "ConnectionRouter._router_func.<locals>._route_db")
says("harbour.routers", "LogbookRouter.db_for_read")
with recorded(ROUTING):
    do("Logbook.objects.count()")
show("A queryset asks the router: Logbook.objects.count() is sent to \"archive\"")

quietly("ada = Sailor.objects.get(name='Ada')")
with recorded({
    ("django.db.models.fields.related_descriptors", "ForwardManyToOneDescriptor.__set__"):
        lambda f: f"ForwardManyToOneDescriptor.__set__(instance={brief(f.f_locals['instance'])}, value={brief(f.f_locals['value'])})",
    (DBU, "ConnectionRouter.allow_relation"): lambda f: f"ConnectionRouter.allow_relation({brief(f.f_locals['obj1'])}, {brief(f.f_locals['obj2'])})",
}, after={(DBU, "ConnectionRouter.allow_relation"): value_after}):
    do("ada.ship = skua")
ask("ada._state.db, skua._state.db")
ask("ada.ship")
show("A relation across databases refused: a ship read from \"archive\" given to a sailor read from \"default\"")

ROUTED_ATOMIC = {(TX, "Atomic.__enter__"): atomic_entered, (TX, "Atomic.__exit__"): atomic_left} | watch(
    B, "BaseDatabaseWrapper.rollback", "BaseDatabaseWrapper.commit", label=bare,
) | {(DBU, "ConnectionRouter._router_func.<locals>._route_db"): route_said}
says(DBU, "ConnectionRouter._router_func.<locals>._route_db")
quietly("block = transaction.atomic()")
with recorded(ROUTED_ATOMIC):
    do("block.__enter__()")
    do("Logbook.objects.create(title='Skua, 2026')")
    ask("connections['default'].in_atomic_block")
    ask("connections['archive'].in_atomic_block")
    do("block.__exit__(ValueError, ValueError('no berth'), None)")
ask("Logbook.objects.filter(title='Skua, 2026').exists()")
show("atomic() given no database is on \"default\" and asks no router: the logbook the router sends to \"archive\" is written there, outside the block, and the block's rollback leaves it")

# ---------------------------------------------------------------------------------------------
# The connection object.

quietly("connection.close()")
ask("type(connections['default'])")
ask("connection.vendor")
ask("connection.display_name")
ask("connection.Database")
ask("connection.SchemaEditorClass")
ask("type(connection.ops)")
ask("type(connection.features)")
ask("type(connection.introspection)")
ask("type(connection.creation)")
ask("type(connection.client)")
ask("type(connection.validation)")
ask("connection.ops.connection is connections['default']")
ask("connection.connection")
ask("full(list(connection.settings_dict))")
ask("connection.settings_dict['NAME']")
show("What a connection carries: its class, the backend's names for itself, the driver, and the helper objects it made")

SHORE = {"NAME": "harbour", "USER": "purser", "PASSWORD": "tide", "HOST": "db.harbour.example", "PORT": "5432", "OPTIONS": {}}
ASKING.update(shore=SHORE)
from django.db.backends.sqlite3.client import DatabaseClient as SQLiteClient  # noqa: E402

ASKING.update(SQLiteClient=SQLiteClient)
step("no client ran: settings_to_cmd_args_env is a class method that only builds the command line and its environment")
ask("shore")
ask("full(SQLiteClient.settings_to_cmd_args_env({'NAME': 'harbour.sqlite3'}, []))")
for backend, name in (("postgresql", "PostgreSQLClient"), ("mysql", "MySQLClient"), ("oracle", "OracleClient")):
    quietly(f"{name} = load_backend('django.db.backends.{backend}').DatabaseWrapper.client_class")
    ask(f"full({name}.settings_to_cmd_args_env(shore, []))")
show("dbshell's command line, for each backend: what settings_to_cmd_args_env makes of one set of settings (no client ran)")

# ---------------------------------------------------------------------------------------------
# Opening and closing.

import django.db.backends.base.base as base_module  # noqa: E402

ASKING.update(base_module=base_module)
ask("connection.connection is None")
ask("sorted(base_module.RAN_DB_VERSION_CHECK)")
with recorded(OPENING, sqlite=True, c=DRIVER):
    do("first = connection.cursor()")
    do("second = connection.cursor()")
ask("first is second")
ask("first.cursor is second.cursor")
ask("first.cursor.connection is second.cursor.connection is connection.connection")
quietly("first.close(); second.close()")
show("Opening a connection: the first cursor opens it, and the second opens nothing; the version check ran when the first block opened this alias, and runs once for each alias in a process")

quietly("aged = ConnectionHandler({'default': {'ENGINE': 'django.db.backends.dummy'}, 'aged': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': connection.settings_dict['NAME']}})['aged']")
quietly("aged.features.minimum_database_version = (3, 99)  # set by hand on this connection's features: above this build's SQLite")
ask("'aged' in base_module.RAN_DB_VERSION_CHECK")
with recorded(OPENING, sqlite=True, c=DRIVER):
    do("aged.cursor()")
ask("aged.connection is None")
ask("'aged' in base_module.RAN_DB_VERSION_CHECK")
with recorded(OPENING, sqlite=True, c=DRIVER):
    do("aged.cursor()")
quietly("aged.close()")
show("A version check that fails, on a connection of its own alias, \"aged\", made by a ConnectionHandler of the script's own: connect raises after the driver's connection is made, keeps it, and leaves the alias unchecked, so the next cursor opens nothing and checks nothing")

ENDING = {(DSP, "Signal.send"): signal_sent} | watch(DB, "close_old_connections", label=bare) | watch(
    B, "BaseDatabaseWrapper.close_if_unusable_or_obsolete", "BaseDatabaseWrapper.close", label=bare,
) | watch(B, "BaseDatabaseWrapper.get_autocommit", label=bare) | watch(S3, "DatabaseWrapper.close", "DatabaseWrapper.is_usable", label=bare)
says(B, "BaseDatabaseWrapper.get_autocommit")
says(S3, "DatabaseWrapper.is_usable")
quietly("connections['archive'].close()")
quietly("connection.close()")
quietly("connection.settings_dict['CONN_MAX_AGE'] = None")
quietly("Ship.objects.count()")
ask("connection.close_at")
with recorded(ENDING):
    do("signals.request_finished.send(sender=WSGIHandler)")
ask("connection.connection is None")
quietly("connection.close()")
quietly("connection.settings_dict['CONN_MAX_AGE'] = 60")
quietly("Ship.objects.count()")
ask("59 < connection.close_at - time.monotonic() <= 60")
with recorded(ENDING):
    do("signals.request_finished.send(sender=WSGIHandler)")
ask("connection.connection is None")
quietly("connection.close()")
quietly("connection.settings_dict['CONN_MAX_AGE'] = 0")
quietly("Ship.objects.count()")
ask("connection.close_at <= time.monotonic()")
with recorded(ENDING):
    do("signals.request_finished.send(sender=WSGIHandler)")
ask("connection.connection is None")
show("Closing at a request's end, by CONN_MAX_AGE: None keeps the connection, 60 keeps it until close_at (a time of time.monotonic, 60 seconds after the connection opened), and 0 closes it")

quietly("connection.settings_dict['CONN_MAX_AGE'] = None")
quietly("Ship.objects.count()")
quietly("transaction.set_autocommit(False)")
with recorded(ENDING):
    do("signals.request_finished.send(sender=WSGIHandler)")
ask("connection.connection is None")
quietly("Ship.objects.count()")
do("with connection.cursor() as cursor: cursor.execute('SELEC 1')")
ask("connection.errors_occurred")
with recorded(ENDING):
    do("signals.request_finished.send(sender=WSGIHandler)")
ask("connection.connection is None")
ask("connection.errors_occurred")
quietly("connection.settings_dict['CONN_MAX_AGE'] = 0")
quietly("connection.close()")
show("Whatever CONN_MAX_AGE says (None here), a request's end closes a connection left with autocommit off, and keeps one that saw an error if it is usable")

HEALTH = {(DSP, "Signal.send"): signal_sent} | watch(B, "BaseDatabaseWrapper.close_if_unusable_or_obsolete", "BaseDatabaseWrapper.close_if_health_check_failed", label=bare) | watch(
    S3, "DatabaseWrapper.is_usable", label=bare,
)
quietly("connection.settings_dict['CONN_HEALTH_CHECKS'] = True")
quietly("connection.settings_dict['CONN_MAX_AGE'] = None")
quietly("Ship.objects.count()")
ask("connection.health_check_enabled")
ask("connection.health_check_done")
with recorded(HEALTH):
    do("signals.request_started.send(sender=WSGIHandler, environ={})")
    ask("connection.health_check_done")
    do("Ship.objects.count()")
    ask("connection.health_check_done")
    do("Port.objects.count()")
quietly("connection.settings_dict['CONN_HEALTH_CHECKS'] = False")
quietly("connection.settings_dict['CONN_MAX_AGE'] = 0")
quietly("connection.close()")
show("Health checks, with CONN_HEALTH_CHECKS on and CONN_MAX_AGE None: after a request starts, the next cursor asks is_usable, and the one after does not")


def unusable():
    """A stand-in of the script's own for the connection's is_usable: it says the connection cannot be used."""
    return False


ASKING.update(unusable=unusable)
UNHEALTHY = {(DSP, "Signal.send"): signal_sent} | watch(
    B, "BaseDatabaseWrapper.close_if_unusable_or_obsolete", "BaseDatabaseWrapper.close_if_health_check_failed", "BaseDatabaseWrapper.close",
    "BaseDatabaseWrapper.connect", label=bare,
) | watch(B, "BaseDatabaseWrapper.set_autocommit") | watch(S3, "DatabaseWrapper.close", label=bare) | {
    ("__main__", "unusable"): lambda f: "unusable  (the stand-in set as the connection's is_usable)",
}
says("__main__", "unusable")
step("a stand-in of the script's own for is_usable, set on the connection \"default\" for this block:")
code(unusable)
quietly("connection.settings_dict['CONN_HEALTH_CHECKS'] = True")
quietly("connection.settings_dict['CONN_MAX_AGE'] = None")
quietly("Ship.objects.count()")
quietly("connection.is_usable = unusable")
with recorded(UNHEALTHY):
    do("signals.request_started.send(sender=WSGIHandler, environ={})")
    ask("connection.health_check_done")
    do("Ship.objects.count()")
    ask("connection.health_check_done")
quietly("del connection.is_usable")
quietly("connection.settings_dict['CONN_HEALTH_CHECKS'] = False")
quietly("connection.settings_dict['CONN_MAX_AGE'] = 0")
quietly("connection.close()")
show("A health check that fails (is_usable replaced by a stand-in that answers False): the next cursor closes the connection and opens a new one before its statement")

ATOMIC_CLOSE = watch(TX, "Atomic.__enter__", "Atomic.__exit__", label=bare) | watch(
    B, "BaseDatabaseWrapper.close", "BaseDatabaseWrapper.ensure_connection", "BaseDatabaseWrapper.connect", label=bare,
) | watch(S3, "DatabaseWrapper.close", "DatabaseWrapper.create_cursor", label=bare)
quietly("Ship.objects.count()")
quietly("block = transaction.atomic()")
with recorded(ATOMIC_CLOSE, sqlite=True, c=("sqlite3.Connection.close", "sqlite3.Connection.cursor", "sqlite3.Connection.commit", "sqlite3.Connection.rollback")):
    quietly("block.__enter__()")
    do("connection.close()")
    ask("connection.closed_in_transaction")
    ask("connection.needs_rollback")
    ask("connection.connection is None")
    do("Ship.objects.count()")
    do("block.__exit__(None, None, None)")
    ask("connection.connection is None")
    ask("connection.in_atomic_block")
    do("Ship.objects.count()")
show("A connection closed inside an atomic block: the driver's connection is closed, Django keeps it until the block ends, and the next query fails")


def opened(sender, connection, **kwargs):
    """A receiver of connection_created, of the script's own: it writes what it is given."""
    note(f"opened(sender={brief(sender)}, connection={brief(connection)}, **{brief(kwargs)})")


ASKING.update(opened=opened)
TEMPORARY = watch(B, "BaseDatabaseWrapper.temporary_connection", "BaseDatabaseWrapper.connect", "BaseDatabaseWrapper.close", label=bare) | {
    (DSP, "Signal.send"): signal_sent,
}
step("the receiver of the script's own (note writes a line of this output, and brief puts a value into words):")
for text in inspect.getsource(opened).splitlines():
    note("  " + text)
quietly("connection.close()")
quietly("connection_created.connect(opened)")
with recorded(TEMPORARY):
    do("with connection.temporary_connection() as cursor: cursor.execute('SELECT COUNT(*) FROM fleet_port')")
    ask("connection.connection is None")
    quietly("connection_created.disconnect(opened)")
    quietly("Ship.objects.count()")
    do("with connection.temporary_connection() as cursor: cursor.execute('SELECT COUNT(*) FROM fleet_port')")
    ask("connection.connection is None")

show("temporary_connection closes the connection only if it opened it; a receiver of connection_created of the script's own is given the class and the connection")

CURSORING = watch(B, "BaseDatabaseWrapper.cursor", "BaseDatabaseWrapper.validate_no_broken_transaction", label=bare) | watch(
    U, "CursorWrapper.__enter__", "CursorWrapper.__exit__", "CursorWrapper.execute", "CursorWrapper._execute_with_wrappers",
    "CursorWrapper._execute", label=bare,
) | {
    (U, "CursorWrapper.__getattr__"): with_value("attr"),
    (S3, "SQLiteCursorWrapper.execute"): bare,
    (S3, "SQLiteCursorWrapper.convert_query"): lambda f: "SQLiteCursorWrapper.convert_query" + (f"(param_names={f.f_locals['param_names']!r})" if f.f_locals["param_names"] else ""),
}
CURSOR_DRIVER = ("sqlite3.Cursor.execute", "sqlite3.Cursor.fetchall", "sqlite3.Cursor.close")
with recorded(CURSORING, sqlite=True, c=CURSOR_DRIVER, after={(S3, "SQLiteCursorWrapper.convert_query"): value_after}):
    do("with connection.cursor() as cursor: cursor.execute('SELECT name, tonnage FROM fleet_ship WHERE tonnage > %s', [500]); rows = cursor.fetchall()")
ask("rows")
show("A statement through Django's cursor: the parameters' placeholders are rewritten for the driver, which binds them")

with recorded(CURSORING, sqlite=True, c=CURSOR_DRIVER, after={(S3, "SQLiteCursorWrapper.convert_query"): value_after}):
    do("with connection.cursor() as cursor: cursor.execute('SELECT name FROM fleet_ship WHERE tonnage > %(tonnage)s', {'tonnage': 500}); rows = cursor.fetchall()")
ask("rows")
show("Parameters by name: a dict of parameters, and %(name)s rewritten as :name")

quietly("cursor = connection.cursor()")
ask("type(cursor)")
ask("type(cursor.cursor)")
ask("type(cursor.execute('SELECT COUNT(*) FROM fleet_ship'))")
ask("cursor.execute('SELECT COUNT(*) FROM fleet_ship') is cursor.cursor")
ask("cursor.execute('SELECT COUNT(*) FROM fleet_ship').fetchone()")
quietly("cursor.close()")
show("What execute returns on SQLite: the driver's cursor, the SQLiteCursorWrapper inside Django's cursor, and not Django's cursor")

PERCENT = watch(S3, "SQLiteCursorWrapper.execute", label=bare) | {
    (S3, "SQLiteCursorWrapper.convert_query"): lambda f: "SQLiteCursorWrapper.convert_query" + (f"(param_names={f.f_locals['param_names']!r})" if f.f_locals["param_names"] else ""),
}
with recorded(PERCENT, sqlite=True, c=("sqlite3.Cursor.execute",), after={(S3, "SQLiteCursorWrapper.convert_query"): value_after}):
    do("with connection.cursor() as cursor: cursor.execute(\"SELECT name FROM fleet_ship WHERE name LIKE 'P%%'\"); rows = cursor.fetchall()")
    ask("rows")
    do("with connection.cursor() as cursor: cursor.execute(\"SELECT name FROM fleet_ship WHERE name LIKE 'P%%' AND tonnage > %s\", [100]); rows = cursor.fetchall()")
    ask("rows")
    do("with connection.cursor() as cursor: cursor.execute(\"SELECT '%%s', %s\", ['x']); rows = cursor.fetchall()")
    ask("rows")
    do("with connection.cursor() as cursor: cursor.execute(\"SELECT '%%s'\"); rows = cursor.fetchall()")
    ask("rows")
show("A doubled percent sign on SQLite: with parameters, convert_query turns each %s into ? and %% into %; with none (params is None), the statement goes to the driver as it was written, %% and all")

run_part("before-ready")


class Records(logging.Handler):
    """A handler of the script's own: it writes each record it is given as a line `log`."""

    def emit(self, record):
        extra = {k: getattr(record, k) for k in ("alias", "duration", "params", "sql") if hasattr(record, k)}
        note(f"log {record.name} {record.levelname}: {record.getMessage()}" + (f"  (extra: {', '.join(sorted(extra))})" if extra else ""))


RECORDS = Records()
DEBUGGING = watch(B, "BaseDatabaseWrapper.cursor", "BaseDatabaseWrapper.make_debug_cursor", label=bare) | watch(
    U, "CursorDebugWrapper.execute", "CursorDebugWrapper.executemany", "CursorDebugWrapper.debug_sql", "CursorWrapper.execute",
    "CursorWrapper.executemany", label=bare,
) | watch(S3O, "DatabaseOperations.last_executed_query", label=bare) | watch(
    S3O, "DatabaseOperations._quote_params_for_last_executed_query", label=first_only,
) | watch(S3F, "DatabaseFeatures.max_query_params", label=bare)
says(B, "BaseDatabaseWrapper.make_debug_cursor")
says(S3O, "DatabaseOperations.last_executed_query", "DatabaseOperations._quote_params_for_last_executed_query")
DEBUG_DRIVER = ("sqlite3.Cursor.execute", "sqlite3.Cursor.executemany", "sqlite3.Connection.cursor", "sqlite3.Cursor.fetchone")
quietly("connection.force_debug_cursor = True")
ask("connection.queries_logged")
step("the logger django.db.backends is set to DEBUG for this block, and given the script's handler, which writes each record as a line `log`")
backends_logger = logging.getLogger("django.db.backends")
backends_logger.setLevel(logging.DEBUG)
backends_logger.addHandler(RECORDS)
with recorded(DEBUGGING, sqlite=True, c=DEBUG_DRIVER):
    do("with connection.cursor() as cursor: cursor.execute('SELECT name FROM fleet_ship WHERE tonnage > %s', [500])")
    ask("full(connection.queries)")
    do("with connection.cursor() as cursor: cursor.executemany('UPDATE crew_sailor SET name = %s WHERE id = %s', [('Ada', 1), ('Bram', 2), ('Dag', 4)])")
    ask("full(connection.queries)")
    do("reset_queries()")
    ask("connection.queries")
backends_logger.removeHandler(RECORDS)
backends_logger.setLevel(logging.NOTSET)
quietly("connection.force_debug_cursor = False")
show("The debug cursor and the query log, with force_debug_cursor set (DEBUG is False): each statement is written to queries_log and to the logger django.db.backends")

LOGGED_TRANSACTION = {(TX, "Atomic.__enter__"): atomic_entered, (TX, "Atomic.__exit__"): atomic_left} | watch(
    B, "BaseDatabaseWrapper.commit", "BaseDatabaseWrapper._commit", label=bare,
) | watch(S3, "DatabaseWrapper._start_transaction_under_autocommit", label=bare) | watch(
    U, "CursorDebugWrapper.execute", label=bare,
) | watch(U, "debug_transaction", label=lambda f: f"debug_transaction(connection, {f.f_locals['sql']!r})")
quietly("connection.force_debug_cursor = True")
step("the logger django.db.backends is set to DEBUG for this block, and given the script's handler, which writes each record as a line `log`")
backends_logger.setLevel(logging.DEBUG)
backends_logger.addHandler(RECORDS)
with recorded(LOGGED_TRANSACTION, sqlite=True, c=("sqlite3.Connection.commit",)):
    do("with transaction.atomic(): Ship.objects.count()")
    ask("full(connection.queries)")
    do("reset_queries()")
backends_logger.removeHandler(RECORDS)
backends_logger.setLevel(logging.NOTSET)
quietly("connection.force_debug_cursor = False")
show("The query log of an atomic block, with force_debug_cursor set: BEGIN is a statement through the debug cursor, and COMMIT, the driver's commit, is logged by debug_transaction")


def counted(execute, sql, params, many, context):
    note(f"counted is given execute={brief(execute)}, sql={sql!r}, params={params!r}, many={many!r}, context={brief(context)}")
    return execute(sql, params, many, context)


def outer(execute, sql, params, many, context):
    note("outer begins")
    try:
        return execute(sql, params, many, context)
    finally:
        note("outer ends")


def inner(execute, sql, params, many, context):
    note(f"inner begins, and is given execute={brief(execute)}")
    try:
        return execute(sql, params, many, context)
    finally:
        note("inner ends")


def refuse(execute, sql, params, many, context):
    raise PermissionError(f"not here: {sql}")


ASKING.update(counted=counted, outer=outer, inner=inner, refuse=refuse)
step("the execute wrappers of the script's own:")
for function in (counted, outer, inner, refuse):
    for text in inspect.getsource(function).splitlines():
        note("  " + text)
step("the script's own wrapper, which writes the SQL lines, is taken off for this block: the sqlite lines say what reached SQLite")
connection.execute_wrappers.remove(query_sent)
ask("connection.execute_wrappers")
with sqlite_lines():
    do("with connection.execute_wrapper(counted): Ship.objects.filter(tonnage__gt=500).count()")
    do("with connection.execute_wrapper(outer), connection.execute_wrapper(inner): Port.objects.count()")
    do("with connection.execute_wrapper(refuse): Port.objects.count()")
ask("connection.execute_wrappers")
listen(connection)
show("Execute wrappers of the script's own: what a wrapper is given, two nested, and one that refuses")

TRANSLATING = watch(U, "CursorWrapper._execute", label=bare) | {
    (DBU, "DatabaseErrorWrapper.__exit__"): lambda f: None if f.f_locals["exc_type"] is None else f"DatabaseErrorWrapper.__exit__(exc_type={answer(f.f_locals['exc_type'])})",
}
with recorded(TRANSLATING, c=("sqlite3.Cursor.execute",)):
    do("with connection.cursor() as cursor: cursor.execute('INSERT INTO fleet_port (id, name, country) VALUES (%s, %s, %s)', [1, 'Bergen', 'Norway'])")
ask("type(caught)")
ask("type(caught.__cause__)")
ask("caught.args")
ask("isinstance(caught, DatabaseError)")
ask("connection.errors_occurred")
with recorded(TRANSLATING, c=("sqlite3.Cursor.execute",)):
    do("with connection.cursor() as cursor: cursor.execute('SELEC 1')")
ask("type(caught)")
ask("type(caught.__cause__)")
ask("connection.errors_occurred")
quietly("connection.close()")
show("A driver's error, translated: the driver's exception is replaced by Django's class of the same name, and errors_occurred is set after OperationalError and not after IntegrityError")

CHUNKED = watch(QS, "QuerySet.iterator", "QuerySet._iterator", label=generic) | watch(
    CO, "SQLCompiler.execute_sql", label=without("result_type"),
) | watch(B, "BaseDatabaseWrapper.chunked_cursor", "BaseDatabaseWrapper.cursor", label=bare) | {(CO, "cursor_iter"): lambda f: f"cursor_iter(itersize={f.f_locals['itersize']})"}
with recorded(CHUNKED, c=("sqlite3.Cursor.fetchmany",)):
    do("ships = list(Ship.objects.iterator(chunk_size=1))")
ask("ships")
ask("connection.features.can_use_chunked_reads")
show("The chunked cursor: iterator(chunk_size=1) asks for chunked_cursor, which on SQLite is the plain cursor, and the rows are fetched one at a time")

# ---------------------------------------------------------------------------------------------
# Transactions.


def held() -> None:
    """A line `the connection holds`: five of the connection's attributes, by name."""
    names = ("in_atomic_block", "savepoint_ids", "atomic_blocks", "commit_on_exit", "needs_rollback")
    note("the connection holds: " + ", ".join(f"{name}={brief(getattr(connection, name))}" for name in names))


TRANSACTING = {(TX, "Atomic.__enter__"): atomic_entered, (TX, "Atomic.__exit__"): atomic_left} | watch(
    B, "BaseDatabaseWrapper.set_autocommit", "BaseDatabaseWrapper.savepoint_commit", "BaseDatabaseWrapper.savepoint_rollback",
) | watch(
    B, "BaseDatabaseWrapper.savepoint", "BaseDatabaseWrapper.commit", "BaseDatabaseWrapper._commit", "BaseDatabaseWrapper.rollback",
    "BaseDatabaseWrapper._rollback", label=bare,
) | watch(S3, "DatabaseWrapper._start_transaction_under_autocommit", label=bare) | watch(S3, "DatabaseWrapper._set_autocommit")
TRANSACTING[(B, "BaseDatabaseWrapper.savepoint_commit")] = first_only
TRANSACTING[(B, "BaseDatabaseWrapper.savepoint_rollback")] = first_only
says(B, "BaseDatabaseWrapper.savepoint")
TX_DRIVER = ("sqlite3.Connection.commit", "sqlite3.Connection.rollback")
SAVING = {(TX, "mark_for_rollback_on_error"): bare, (TX, "Atomic.__enter__"): atomic_entered, (TX, "Atomic.__exit__"): atomic_left} | watch(
    B, "BaseDatabaseWrapper.commit", label=bare,
)
quietly("Ship.objects.count()")
ask("connection.get_autocommit()")
ask("connection.autocommit")
ask("connection.connection.isolation_level")
with recorded(SAVING, sqlite=True, c=TX_DRIVER):
    do("Port.objects.create(name='Cork', country='Ireland')")
    do("Officer.objects.create(name='Fen', ship=petrel, rank='mate')")
show("Autocommit, the plain case: a create outside any block is one statement, which SQLite commits by itself; a model with a parent's table is saved inside atomic(savepoint=False)")

quietly("outer = transaction.atomic()")
quietly("inner = transaction.atomic()")
with recorded(TRANSACTING, sqlite=True, c=TX_DRIVER):
    held()
    do("outer.__enter__()")
    held()
    quietly("Port.objects.create(name='Oban', country='Scotland')")
    do("inner.__enter__()")
    held()
    quietly("Port.objects.create(name='Ayr', country='Scotland')")
    do("inner.__exit__(None, None, None)")
    held()
    do("outer.__exit__(None, None, None)")
    held()
ask("connection.get_autocommit()")
show("Two atomic blocks, nested: the outer begins a transaction and commits it, the inner makes a savepoint and releases it (outer.__enter__() and outer.__exit__(None, None, None) are what a with statement calls)")

with recorded(TRANSACTING, sqlite=True, c=TX_DRIVER):
    do("outer.__enter__()")
    quietly("Port.objects.create(name='Wick', country='Scotland')")
    do("inner.__enter__()")
    quietly("Port.objects.create(name='Thurso', country='Scotland')")
    do("inner.__exit__(ValueError, ValueError('no berth'), None)")
    held()
    do("outer.__exit__(None, None, None)")
ask("sorted(Port.objects.filter(name__in=['Wick', 'Thurso']).values_list('name', flat=True))")
show("An exception leaves the inner block (inner.__exit__ is given it, as a with statement does): back to the savepoint, which is then released, and the outer block commits what it did itself")

quietly("unsaved = transaction.atomic(savepoint=False)")
with recorded(TRANSACTING, sqlite=True, c=TX_DRIVER):
    do("outer.__enter__()")
    quietly("Port.objects.create(name='Lerwick', country='Scotland')")
    do("unsaved.__enter__()")
    held()
    quietly("Port.objects.create(name='Kirkwall', country='Scotland')")
    do("unsaved.__exit__(ValueError, ValueError('no berth'), None)")
    held()
    do("Port.objects.count()")
    do("outer.__exit__(None, None, None)")
    held()
ask("sorted(Port.objects.filter(name__in=['Lerwick', 'Kirkwall']).values_list('name', flat=True))")
show("An inner block without a savepoint: the exception can only mark the transaction, the next query in the outer block is refused, and the outer block rolls back")

REMEMBERING = TRANSACTING | {(TX, "mark_for_rollback_on_error"): bare}
with recorded(REMEMBERING, sqlite=True, c=TX_DRIVER):
    do("outer.__enter__()")
    do("Ship.objects.create(name='Petrel', tonnage=480, home_id=petrel.home_id)")
    ask("connection.needs_rollback")
    ask("type(connection.rollback_exc)")
    do("Port.objects.count()")
    ask("type(caught)")
    ask("type(caught.__cause__)")
    do("outer.__exit__(None, None, None)")
show("An error Django remembers: a failed create inside a block, caught there, marks the transaction for rollback, and the next query is refused with the error as its cause")


class FailingDriverConnection:
    """A stand-in of the script's own for the driver's connection: it hands everything to the driver's connection it holds,
    but its commit and rollback raise the driver's OperationalError, as they might where the database has gone away."""

    def __init__(self, real):
        self.real = real

    def __getattr__(self, name):
        return getattr(self.real, name)

    def commit(self):
        raise sqlite3.OperationalError("disk I/O error")

    def rollback(self):
        raise sqlite3.OperationalError("disk I/O error")


ASKING.update(FailingDriverConnection=FailingDriverConnection, sqlite3=sqlite3)
FAILING = {(TX, "Atomic.__enter__"): atomic_entered, (TX, "Atomic.__exit__"): atomic_left} | watch(
    B, "BaseDatabaseWrapper.commit", "BaseDatabaseWrapper._commit", "BaseDatabaseWrapper.rollback", "BaseDatabaseWrapper._rollback",
    "BaseDatabaseWrapper.close", "BaseDatabaseWrapper._close", "BaseDatabaseWrapper.connect", label=bare,
) | watch(B, "BaseDatabaseWrapper.set_autocommit") | watch(S3, "DatabaseWrapper.close", label=bare) | watch(
    "__main__", "FailingDriverConnection.commit", "FailingDriverConnection.rollback", label=bare,
)
step("a stand-in of the script's own for the driver's connection:")
code(FailingDriverConnection)
quietly("Ship.objects.count()")
quietly("connection.connection = FailingDriverConnection(connection.connection)")
with recorded(FAILING, sqlite=True, c=("sqlite3.Connection.close",)):
    do("with transaction.atomic(): Port.objects.count()")
ask("type(caught)")
ask("type(caught.__cause__)")
ask("type(connection.connection)")
ask("connection.in_atomic_block, connection.get_autocommit()")
show("An outermost block whose commit fails and whose rollback fails too (the driver's connection replaced by a stand-in whose commit and rollback raise): Atomic.__exit__ closes the connection, raises the commit's error, and its last step, set_autocommit(True), opens a new connection")

with recorded(TRANSACTING, sqlite=True, c=TX_DRIVER):
    do("outer.__enter__()")
    quietly("Port.objects.create(name='Brora', country='Scotland')")
    do("transaction.set_rollback(True)")
    held()
    do("outer.__exit__(None, None, None)")
ask("Port.objects.filter(name='Brora').exists()")
ask("transaction.get_rollback()")
ask("transaction.set_rollback(True)")
with recorded(TRANSACTING, sqlite=True, c=TX_DRIVER):
    do("with transaction.atomic(), transaction.atomic(durable=True): pass")
with sqlite_lines():
    quietly("outer.__enter__()")
    ask("transaction.savepoint()")
    ask("transaction.savepoint_create()")
    quietly("outer.__exit__(None, None, None)")
show("set_rollback, a durable block inside another, and the deprecated savepoint()")

MANUAL = TRANSACTING | watch(U, "debug_transaction", label=lambda f: f"debug_transaction(connection, {f.f_locals['sql']!r})")
with recorded(MANUAL, sqlite=True, c=TX_DRIVER):
    do("transaction.set_autocommit(False)")
    ask("connection.connection.isolation_level")
    quietly("Port.objects.create(name='Mallaig', country='Scotland')")
    do("transaction.commit()")
    quietly("Port.objects.create(name='Ullapool', country='Scotland')")
    do("outer.__enter__()")
    held()
    quietly("Port.objects.create(name='Tarbert', country='Scotland')")
    do("outer.__exit__(None, None, None)")
    held()
    do("transaction.commit()")
    do("transaction.set_autocommit(True)")
ask("connection.connection.isolation_level")
show("Autocommit turned off by hand: the driver begins a transaction before the first change and commit() ends it; an atomic block inside such a transaction makes a savepoint and leaves the commit to the caller")

with recorded(TRANSACTING | watch(S3, "DatabaseWrapper._savepoint_allowed", label=bare), sqlite=True, c=TX_DRIVER,
              after={(S3, "DatabaseWrapper._savepoint_allowed"): value_after}):
    do("transaction.set_autocommit(False)")
    ask("connection.in_atomic_block")
    do("sid = transaction.savepoint_create()")
    ask("sid")
    do("transaction.set_autocommit(True)")
show("savepoint_create() with autocommit turned off by hand, outside any atomic block: SQLite's backend allows a savepoint only inside an atomic block, so none is made, nothing is sent, and the answer is None")


from django.core.handlers.base import BaseHandler  # noqa: E402
from django.http import HttpResponse  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.urls import path  # noqa: E402


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


ASKING.update(write=write, fail=fail, plain=plain, path=path, BaseHandler=BaseHandler, RequestFactory=RequestFactory)
step("the views of the script's own:")
for function in (write, fail, plain):
    for text in inspect.getsource(function).splitlines():
        note("  " + text)
quietly("settings.ROOT_URLCONF = (path('write/', write), path('fail/', fail), path('plain/', plain))")
quietly("connection.settings_dict['ATOMIC_REQUESTS'] = True")
quietly("handler = BaseHandler(); handler.load_middleware()")
REQUESTS = {(TX, "Atomic.__enter__"): atomic_entered, (TX, "Atomic.__exit__"): atomic_left} | watch(
    "django.core.handlers.base", "BaseHandler.make_view_atomic", label=lambda f: f"BaseHandler.make_view_atomic({f.f_locals['view'].__name__})",
) | watch(B, "BaseDatabaseWrapper.commit", "BaseDatabaseWrapper.rollback", label=bare) | {
    ("__main__", "write"): lambda f: "write(request)", ("__main__", "fail"): lambda f: "fail(request)", ("__main__", "plain"): lambda f: "plain(request)",
}
says("django.core.handlers.base", "BaseHandler.make_view_atomic", how=lambda f, v: (
    f"a function that calls {v.__wrapped__.__name__} inside an Atomic (made by contextlib's ContextDecorator, Atomic's base class)"
    if v.__code__.co_qualname.startswith("ContextDecorator.") else f"{v.__name__} as it was given"
))
with recorded(REQUESTS, sqlite=True, c=TX_DRIVER):
    do("response = handler.get_response(RequestFactory().get('/write/'))")
    ask("response.status_code")
    do("response = handler.get_response(RequestFactory().get('/fail/'))")
    ask("response.status_code")
    do("response = handler.get_response(RequestFactory().get('/plain/'))")
    ask("response.status_code")
ask("sorted(Port.objects.filter(name__in=['Scrabster', 'Stornoway', 'Kyle']).values_list('name', flat=True))")
quietly("connection.settings_dict['ATOMIC_REQUESTS'] = False")
quietly("del settings.ROOT_URLCONF")
show("ATOMIC_REQUESTS on for \"default\": the handler wraps the view in atomic, which commits after a view that returns and rolls back after one that raises; a view marked non_atomic_requests is not wrapped (a URLconf of three paths, a tuple set as ROOT_URLCONF for this block)")

# ---------------------------------------------------------------------------------------------
# on_commit.


def first_callback():
    note("first_callback runs")


def second_callback():
    note("second_callback runs")


def failing_callback():
    raise ValueError("the callback failed")


ASKING.update(first_callback=first_callback, second_callback=second_callback, failing_callback=failing_callback)
COMMITTING = TRANSACTING | watch(B, "BaseDatabaseWrapper.run_and_clear_commit_hooks", label=bare) | {
    (B, "BaseDatabaseWrapper.on_commit"): lambda f: f"BaseDatabaseWrapper.on_commit({f.f_locals['func'].__name__}" + (", robust=True)" if f.f_locals["robust"] else ")"),
}
step("the callbacks of the script's own:")
for function in (first_callback, second_callback, failing_callback):
    for text in inspect.getsource(function).splitlines():
        note("  " + text)
with recorded(COMMITTING):
    do("outer.__enter__()")
    do("transaction.on_commit(first_callback)")
    ask("connection.run_on_commit")
    do("inner.__enter__()")
    do("transaction.on_commit(second_callback)")
    ask("connection.run_on_commit")
    do("inner.__exit__(None, None, None)")
    ask("connection.run_on_commit")
    do("outer.__exit__(None, None, None)")
    ask("connection.run_on_commit")
show("Callbacks held until the commit: each is kept with the savepoints open when it was registered, and the outermost block's exit runs them after the commit")

with recorded(COMMITTING):
    do("outer.__enter__()")
    do("transaction.on_commit(first_callback)")
    do("inner.__enter__()")
    do("transaction.on_commit(second_callback)")
    ask("connection.run_on_commit")
    do("inner.__exit__(ValueError, ValueError('no berth'), None)")
    ask("connection.run_on_commit")
    do("outer.__exit__(None, None, None)")
show("A savepoint rolled back takes its callbacks: savepoint_rollback keeps only the callbacks registered outside it")

with recorded(COMMITTING):
    do("transaction.on_commit(first_callback)")
    do("outer.__enter__()")
    do("transaction.on_commit(second_callback)")
    do("outer.__exit__(ValueError, ValueError('no berth'), None)")
    ask("connection.run_on_commit")
    quietly("transaction.set_autocommit(False)")
    ask("transaction.on_commit(first_callback)")
    quietly("transaction.rollback(); transaction.set_autocommit(True)")
show("Outside a transaction a callback runs at once; a rollback discards the callbacks; under autocommit turned off by hand, on_commit refuses")

with recorded(COMMITTING):
    do("transaction.set_autocommit(False)")
    do("outer.__enter__()")
    do("transaction.on_commit(first_callback)")
    do("outer.__exit__(None, None, None)")
    ask("connection.run_on_commit")
    do("transaction.commit()")
    ask("connection.run_commit_hooks_on_set_autocommit_on")
    do("transaction.set_autocommit(True)")
    do("transaction.set_autocommit(False)")
    do("outer.__enter__()")
    do("transaction.on_commit(second_callback)")
    do("outer.__exit__(None, None, None)")
    do("transaction.commit()")
    do("transaction.rollback()")
    ask("connection.run_on_commit")
    do("transaction.set_autocommit(True)")
show("on_commit inside an atomic block under autocommit turned off by hand: the callback waits past the block and past commit(), and runs when set_autocommit(True) turns autocommit back on; a rollback() between the commit and that drops it, though the transaction was committed")

step("the logger django.db.backends.base is given the script's handler for this block")
logging.getLogger("django.db.backends.base").addHandler(RECORDS)
with recorded(COMMITTING):
    do("outer.__enter__()")
    do("transaction.on_commit(failing_callback, robust=True)")
    do("transaction.on_commit(second_callback)")
    do("outer.__exit__(None, None, None)")
    do("outer.__enter__()")
    do("transaction.on_commit(failing_callback)")
    do("transaction.on_commit(second_callback)")
    do("outer.__exit__(None, None, None)")
    ask("connection.run_on_commit")
    ask("connection.in_atomic_block")
    ask("connection.get_autocommit()")
    ask("connection.run_commit_hooks_on_set_autocommit_on")
logging.getLogger("django.db.backends.base").removeHandler(RECORDS)
quietly("connection.close()")
show("A callback that fails: with robust=True it is logged and the next callback runs; without, the exception leaves the block's exit after the commit, and the callbacks after it are dropped")

# ---------------------------------------------------------------------------------------------
# Features.

quietly("Ship.objects.count()")
ask("connection.Database.sqlite_version_info")
for flag in ("minimum_database_version", "uses_savepoints", "can_release_savepoints", "can_rollback_ddl", "can_return_columns_from_insert",
             "can_return_rows_from_bulk_insert", "has_select_for_update", "supports_over_clause", "supports_transactions", "atomic_transactions",
             "can_use_chunked_reads", "interprets_empty_strings_as_nulls", "supports_update_conflicts_with_target",
             "supports_aggregate_order_by_clause"):
    ask(f"connection.features.{flag}")
ask("'max_query_params' in vars(type(connection.features))")
ask("connection.features.max_query_params")
ask("'supports_json_field' in vars(connection.features)")
with sqlite_lines():
    ask("connection.features.supports_json_field")
ask("'supports_json_field' in vars(connection.features)")
ask("connection.features.supports_json_field")
show("What SQLite's features say: a flag to a line, among them one that depends on the SQLite version (supports_aggregate_order_by_clause), max_query_params (this build's limit), and one that runs a statement the first time it is read")

# ---------------------------------------------------------------------------------------------
# Operations.

for question in (
    "connection.ops.quote_name('fleet_ship')", "connection.ops.quote_name('\"fleet_ship\"')", "connection.ops.limit_offset_sql(5, 15)",
    "connection.ops.limit_offset_sql(5, None)", "connection.ops.no_limit_value()", "connection.ops.distinct_sql([], [])",
    "connection.ops.for_update_sql()", "connection.ops.date_extract_sql('month', '\"fleet_voyage\".\"sailed\"', ())",
    "connection.ops.datetime_extract_sql('month', '\"crew_sailor\".\"signed_on\"', (), 'Europe/Oslo')",
    "connection.ops.datetime_trunc_sql('month', '\"crew_sailor\".\"signed_on\"', (), 'Europe/Oslo')",
    "connection.ops.combine_expression('^', ['\"fleet_ship\".\"tonnage\"', '%s'])", "connection.ops.combine_expression('+', ['\"fleet_ship\".\"tonnage\"', '%s'])",
    "connection.ops.lookup_cast('iexact')", "connection.ops.prep_for_like_query('50%_off')", "connection.ops.max_name_length()",
    "connection.ops.max_in_list_size()", "connection.ops.explain_query_prefix()", "connection.ops.compiler('SQLCompiler')",
    "connection.ops.compiler_module", "connection.ops.savepoint_create_sql('s1')", "connection.ops.pk_default_value()",
    "connection.operators['icontains']", "connection.pattern_ops['contains']",
):
    ask(question)
show("What SQLite's operations object writes: the dialect's pieces, each asked for alone")


class Reads(dict):
    """connection.operators or connection.pattern_ops, set on the connection for one block: each key read is written."""

    def __init__(self, name: str, data: dict):
        super().__init__(data)
        self.name = name

    def __getitem__(self, key):
        value = super().__getitem__(key)
        note(f"reads connection.{self.name}[{key!r}]  ->  {value!r}")
        return value


class FeatureReads:
    """connection.features, replaced for one block by this stand-in: each attribute read is written, and answered by the features."""

    def __init__(self, real):
        object.__setattr__(self, "_real", real)

    def __getattr__(self, name):
        value = getattr(self._real, name)
        note(f"reads connection.features.{name}  ->  {brief(value)}")
        return value


QUOTED = []


def quote_counted(frame):
    QUOTED.append(frame.f_locals["name"])
    return None


ASKED_OPS = {BO: generic, S3O: generic}
quietly("shown = Ship.objects.filter(name__icontains='e').order_by('name')[1:3]")
step("for this block, connection.operators, connection.pattern_ops and connection.features are stand-ins that write each read; every method of the operations object is written but quote_name, whose calls are counted")
connection.operators = Reads("operators", type(connection._connections["default"]).operators)
connection.pattern_ops = Reads("pattern_ops", type(connection._connections["default"]).pattern_ops)
REAL_FEATURES = connection.features
connection.features = FeatureReads(REAL_FEATURES)
with recorded({(S3O, "DatabaseOperations.quote_name"): quote_counted, (CO, "SQLCompiler.as_sql"): bare}, modules=ASKED_OPS,
              after={(BO, "BaseDatabaseOperations.limit_offset_sql"): value_after, (BO, "BaseDatabaseOperations.lookup_cast"): value_after,
                     (S3O, "DatabaseOperations.no_limit_value"): value_after, (BO, "BaseDatabaseOperations.prep_for_like_query"): value_after,
                     (BO, "BaseDatabaseOperations.compiler"): value_after}):
    do("sql, params = shown.query.get_compiler('default').as_sql()")
connection.features = REAL_FEATURES
del connection.operators
del connection.pattern_ops
note(f"# DatabaseOperations.quote_name was called {len(QUOTED)} times, for {', '.join(sorted(set(QUOTED)))}")
ask("sql")
ask("params")
show("The compiler asks the operations object, the features and the connection's operators as it compiles Ship.objects.filter(name__icontains='e').order_by('name')[1:3]")

from django.db.models.sql.subqueries import InsertQuery  # noqa: E402

for alias in ("postgresql", "mysql", "oracle"):
    load_backend(f"django.db.backends.{alias}")
DIALECTS = ConnectionHandler({
    "default": {"ENGINE": "django.db.backends.dummy"},
    "postgresql": {"ENGINE": "django.db.backends.postgresql", "NAME": "harbour", "USER": "purser", "HOST": "db.harbour.example"},
    "mysql": {"ENGINE": "django.db.backends.mysql", "NAME": "harbour", "USER": "purser", "HOST": "db.harbour.example"},
    "oracle": {"ENGINE": "django.db.backends.oracle", "NAME": "harbour", "USER": "purser", "HOST": "db.harbour.example"},
    "mariadb": {"ENGINE": "django.db.backends.mysql", "NAME": "harbour", "USER": "purser", "HOST": "db.harbour.example"},
    "oracle19": {"ENGINE": "django.db.backends.oracle", "NAME": "harbour", "USER": "purser", "HOST": "db.harbour.example"},
})


def no_server(*args, **kwargs):
    """The guard on the three connections that have no server: a statement that would need one stops the script."""
    import traceback

    sys.stdout.flush()
    sys.stderr.write("recordings/backends.py: a question needed a database server, and no server runs here\n")
    traceback.print_stack(limit=12)
    os._exit(1)


def sql_for(queryset, conn) -> Said:
    """What the queryset's compiler for the connection writes: the statement and its parameters, as as_sql returns them."""
    sql, params = queryset.query.get_compiler(connection=conn).as_sql()
    return Said(repr((sql, tuple(params))))


def insert_sql(conn, ports) -> Said:
    """The statements bulk_create would send for these ports on the connection: an InsertQuery of their name and country,
    compiled with the returning fields execute_sql sets where the backend can return rows from a bulk insert."""
    query = InsertQuery(Port)
    query.insert_values([Port._meta.get_field("name"), Port._meta.get_field("country")], ports)
    compiler = query.get_compiler(connection=conn)
    compiler.returning_fields = Port._meta.db_returning_fields if conn.features.can_return_rows_from_bulk_insert else None
    return Said(repr([(sql, tuple(params)) for sql, params in compiler.as_sql()]))


def serverless(conn):
    """Put the guard on a connection made without a server, and give it back."""
    conn.connect = no_server
    conn.ensure_connection = no_server
    return conn


ASKING.update(DIALECTS=DIALECTS, sql_for=sql_for, insert_sql=insert_sql, sqlite=connections["default"])
quietly("postgresql, mysql, oracle = DIALECTS['postgresql'], DIALECTS['mysql'], DIALECTS['oracle']")
for alias in ("postgresql", "mysql", "oracle", "mariadb", "oracle19"):
    serverless(DIALECTS[alias])
quietly("postgresql.pg_version = 170000")
quietly("mysql.mysql_server_data = {'version': '8.4.6', 'sql_mode': 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION', 'default_storage_engine': 'InnoDB', 'sql_auto_is_null': False, 'lower_case_table_names': False, 'has_zoneinfo_database': True}")
quietly("oracle.oracle_version = (23, 4)")
quietly("oracle.operators, oracle.pattern_ops = oracle._standard_operators, oracle._standard_pattern_ops")
for name in ("sqlite", "postgresql", "mysql", "oracle"):
    ask(f"type({name})")
for question in (
    "{}.ops.quote_name('fleet_ship')", "{}.ops.limit_offset_sql(5, 15)", "{}.ops.limit_offset_sql(5, None)", "{}.ops.no_limit_value()",
    "{}.ops.for_update_sql()", "{}.ops.date_extract_sql('month', '\"fleet_voyage\".\"sailed\"', ())",
    "{}.ops.datetime_trunc_sql('month', '\"crew_sailor\".\"signed_on\"', (), 'Europe/Oslo')",
    "{}.ops.combine_expression('^', ['\"fleet_ship\".\"tonnage\"', '%s'])", "{}.ops.lookup_cast('iexact', 'CharField')",
    "{}.ops.max_name_length()", "{}.ops.max_in_list_size()", "{}.ops.explain_query_prefix()", "{}.operators['icontains']",
):
    for name in ("sqlite", "postgresql", "mysql", "oracle"):
        ask(question.format(name))
show("Four operations objects asked the same questions: SQLite's, and PostgreSQL's, MySQL's and Oracle's made without a server (PostgreSQL 17, MySQL 8.4 and Oracle 23 assumed, with the operators an Oracle connection chooses when its test statement succeeds; nothing was sent)")

quietly("voyages = Voyage.objects.filter(sailed__month=3, ship__name__icontains='pet').order_by('-sailed')[:5]")
for name in ("sqlite", "postgresql", "mysql", "oracle"):
    ask(f"sql_for(voyages, {name})")
quietly("ports = [Port(name='Hull', country='England'), Port(name='Whitby', country='England')]")
for name in ("sqlite", "postgresql", "mysql", "oracle"):
    ask(f"insert_sql({name}, ports)")
show("One queryset and one bulk insert, written for four backends by their own compilers (PostgreSQL 17, MySQL 8.4 and Oracle 23 assumed; no server ran, nothing was sent)")

from django.core.management.color import no_style  # noqa: E402
from django.db.models.constants import OnConflict  # noqa: E402
from django.db.models.sql.subqueries import DeleteQuery, UpdateQuery  # noqa: E402


def flags(name) -> Said:
    """The feature flag on each connection of FLAGGED in turn."""
    return Said(", ".join(f"{label} {brief(getattr(conn.features, name))}" for label, conn in FLAGGED.items()))


def inserts_for(conn, objs, names, returning=None, **conflict) -> list:
    """The statements and parameters SQLInsertCompiler.as_sql writes on the connection for these objects: an InsertQuery of the
    named fields, as QuerySet._insert makes it, with bulk_create's conflict options (on_conflict, and the update_fields and
    unique_fields by name); with the model's returning fields where `returning` is true, as Model.save sets them for one object,
    and, where it is not given, where QuerySet._batched_insert sets them."""
    model = type(objs[0])
    opts = model._meta
    on_conflict = conflict.get("on_conflict")
    query = InsertQuery(
        model, on_conflict=on_conflict, update_fields=[opts.get_field(n) for n in conflict.get("update_fields", ())],
        unique_fields=[opts.get_field(n) for n in conflict.get("unique_fields", ())],
    )
    query.insert_values([opts.get_field(n) for n in names], objs)
    compiler = query.get_compiler(connection=conn)
    if returning is None:
        returning = conn.features.can_return_rows_from_bulk_insert and on_conflict in (None, OnConflict.UPDATE)
    compiler.returning_fields = opts.db_returning_fields if returning else None
    return [(sql, tuple(params)) for sql, params in compiler.as_sql()]


def delete_sql(queryset, conn) -> Said:
    """The statement and parameters of the DeleteQuery that QuerySet._raw_delete makes of the queryset, compiled for the connection."""
    query = queryset.query.clone()
    query.__class__ = DeleteQuery
    sql, params = query.get_compiler(connection=conn).as_sql()
    return Said(repr((sql, tuple(params))))


def update_sql(queryset, conn, **values) -> Said:
    """The statement and parameters of the UpdateQuery that QuerySet.update makes of the queryset and the values, compiled for the
    connection (for an ordering that names no annotation, which update would rewrite first)."""
    query = queryset.query.chain(UpdateQuery)
    query.add_update_values(values)
    query.clear_select_clause()
    sql, params = query.get_compiler(connection=conn).as_sql()
    return Said(repr((sql, tuple(params))))


ASKING.update(flags=flags, inserts_for=inserts_for, delete_sql=delete_sql, update_sql=update_sql, no_style=no_style, OnConflict=OnConflict)
quietly("mariadb, oracle19 = DIALECTS['mariadb'], DIALECTS['oracle19']")
quietly("mariadb.mysql_server_data = {'version': '11.4.5-MariaDB', 'sql_mode': 'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION', 'default_storage_engine': 'InnoDB', 'sql_auto_is_null': False, 'lower_case_table_names': False, 'has_zoneinfo_database': True}")
quietly("oracle19.oracle_version = (19, 24)")
FLAGGED = {"sqlite": connections["default"], "postgresql": DIALECTS["postgresql"], "mysql": DIALECTS["mysql"], "mariadb": DIALECTS["mariadb"],
           "oracle": DIALECTS["oracle"], "oracle19": DIALECTS["oracle19"]}
for flag in ("minimum_database_version", "can_return_columns_from_insert", "can_return_rows_from_bulk_insert", "has_select_for_update_of",
             "supports_frame_exclusion", "max_query_params"):
    ask(f"flags({flag!r})")
quietly("bound = ConnectionHandler({'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'harbour', 'OPTIONS': {'server_side_binding': True}}})['default']")
serverless(ASKING["bound"])
ask("bound.features.max_query_params")
quietly("returning_off = ConnectionHandler({'default': {'ENGINE': 'django.db.backends.oracle', 'NAME': 'harbour', 'OPTIONS': {'use_returning_into': False}}})['default']")
serverless(ASKING["returning_off"])
ask("returning_off.features.can_return_columns_from_insert")
show("Features that differ by backend, by server version and by OPTIONS (PostgreSQL 17, MySQL 8.4, MariaDB 11.4, Oracle 23 and Oracle 19 assumed; no server ran): flags(name) is the flag on each connection in turn")

for question in ("{}.display_name", "{}.mysql_is_mariadb", "{}.ops.regex_lookup('regex')", "{}.ops.regex_lookup('iregex')", "{}.features.minimum_database_version",
                 "{}.features.has_native_uuid_field", "{}.features.supports_expression_indexes", "{}.features.supports_any_value",
                 "{}.features.update_can_self_select", "{}.features.supports_default_in_lead_lag", "sorted({}.features.supported_explain_formats)"):
    for name in ("mysql", "mariadb"):
        ask(question.format(name))
show("MySQL's backend asked as MySQL 8.4 and as MariaDB 11.4 (assumed; no server ran): the version string's \"MariaDB\" is what mysql_is_mariadb reads, and the regular expressions and the flags that follow from it")

for name in ("postgresql", "mysql", "mariadb"):
    for arguments in ("", "analyze=True", "format='json'", "format='json', analyze=True"):
        ask(f"{name}.ops.explain_query_prefix({arguments})")
show("explain_query_prefix on PostgreSQL, MySQL and MariaDB (PostgreSQL 17, MySQL 8.4 and MariaDB 11.4 assumed; no server ran): PostgreSQL puts the options in parentheses, MySQL leaves the format out where it analyzes, and MariaDB's ANALYZE replaces EXPLAIN")

ask("postgresql.ops.distinct_sql(['\"fleet_ship\".\"name\"'], [()])")
ask("sqlite.ops.distinct_sql(['\"fleet_ship\".\"name\"'], [()])")
ask("full(postgresql.ops.sql_flush(no_style(), ['office_licence', 'office_berth'], reset_sequences=True))")
ask("full(postgresql.ops.sequence_reset_sql(no_style(), [Port]))")
ask("postgresql.ops.prep_for_iexact_query('50%_off')")
ask("sqlite.ops.prep_for_iexact_query('50%_off')")
show("PostgreSQL's operations object beside SQLite's (PostgreSQL 17 assumed; no server ran): DISTINCT ON, a flush in one TRUNCATE that restarts the identities, a sequence set to the largest key, and iexact's value left as it is, where the base class escapes it as for LIKE")

quietly("arithmetic = Voyage.objects.annotate(due=models.F('sailed') + datetime.timedelta(days=3), gap=models.F('sailed') - models.Value(datetime.date(2026, 1, 1))).values('due', 'gap')")
for name in ("sqlite", "postgresql", "mysql", "oracle"):
    ask(f"sql_for(arithmetic, {name})")
show("A date plus a duration, and a date less a date, written for four backends (PostgreSQL 17, MySQL 8.4 and Oracle 23 assumed; nothing was sent): SQLite calls functions Django registers, MySQL counts microseconds, PostgreSQL and Oracle add with +, and each subtracts in its own way")

quietly("framed = Ship.objects.annotate(nearby=models.Window(models.Sum('tonnage'), order_by=models.F('tonnage').asc(), frame=models.ValueRange(start=-3, end=0))).values('name', 'nearby')")
for name in ("sqlite", "postgresql", "mysql", "oracle"):
    ask(f"sql_for(framed, {name})")
show("A window frame of a range of values, ValueRange(start=-3, end=0), written for four backends (PostgreSQL 17, MySQL 8.4 and Oracle 23 assumed; nothing was sent): PostgreSQL's features refuse a fixed distance, and the others write RANGE BETWEEN 3 PRECEDING AND CURRENT ROW")

for name in ("sqlite", "postgresql", "mysql", "oracle", "oracle19"):
    ask(f"{name}.ops.compile_json_path(['tags', -1])")
show("A JSON path with a negative index, from compile_json_path (PostgreSQL 17, MySQL 8.4, Oracle 23 and Oracle 19 assumed; no server ran): [#-1] on SQLite, [last-0] on Oracle 23, refused where the features say the backend cannot count from the end")

quietly("petrels_crew = Sailor.objects.filter(ship__name='Petrel')")
ask("delete_sql(petrels_crew, sqlite)")
ask("delete_sql(petrels_crew, mysql)")
quietly("heaviest_first = Ship.objects.order_by('-tonnage')")
ask("update_sql(heaviest_first, sqlite, tonnage=models.F('tonnage') + 1)")
ask("update_sql(heaviest_first, mysql, tonnage=models.F('tonnage') + 1)")
show("MySQL's own compilers beside SQLite's (MySQL 8.4 assumed; nothing was sent): a delete across a join is DELETE ... FROM with the join where SQLite's is a subquery, and an update keeps the queryset's ORDER BY")

from django.apps.registry import Apps  # noqa: E402

beacons = Apps()


class Beacon(models.Model):
    class Meta:
        app_label = "moorings"
        apps = beacons


ASKING.update(Beacon=Beacon)
step("a model of the script's own with no field but its key, in an Apps registry of its own:")
code(Beacon)
quietly("due = [Voyage(ship_id=1, sailed=datetime.date(2026, 5, 1)), Voyage(ship_id=2, sailed=datetime.date(2026, 5, 9))]")
ask("full(inserts_for(oracle, due, ['ship', 'sailed']))")
ask("full(inserts_for(oracle19, due, ['ship', 'sailed']))")
ask("full(inserts_for(oracle, [Port(name='Hull', country='England')], ['name', 'country'], returning=True))")
ask("full(inserts_for(oracle, [Beacon()], [], returning=True))")
ask("full(inserts_for(oracle, [Beacon(), Beacon()], []))")
ask("full(inserts_for(oracle19, [Beacon(), Beacon()], []))")
show("Oracle's inserts (Oracle 23 and Oracle 19 assumed; nothing was sent): the rows as SELECTs joined by UNION ALL, each value cast for its field, FROM DUAL before 23; one row with its key read back by RETURNING ... INTO a BoundVar; and a model with no field but its key")

from django.db.backends.oracle.base import FormatStylePlaceholderCursor, OracleParam  # noqa: E402

ASKING.update(FormatStylePlaceholderCursor=FormatStylePlaceholderCursor, OracleParam=OracleParam)
quietly("placeholders = object.__new__(FormatStylePlaceholderCursor)  # without its __init__, which asks the driver's connection for a cursor")
quietly("placeholders.database = oracle")
quietly("[(statement, values)] = inserts_for(oracle, ports, ['name', 'country'])")
ask("statement")
ask("values")
do("fixed, oracle_params = placeholders._fix_for_params(statement, values, unify_by_values=True)  # as execute calls it")
ask("fixed")
ask("oracle_params")
ask("placeholders._param_generator(oracle_params)")
do("fixed, oracle_params = placeholders._fix_for_params(statement, values)  # as executemany calls it, for its first row of parameters")
ask("fixed")
ask("placeholders._param_generator(oracle_params)")
do("fixed, oracle_params = placeholders._fix_for_params('SELECT \"ID\" FROM \"FLEET_PORT\" WHERE \"NAME\" = %(name)s', {'name': 'Hull'})")
ask("fixed")
ask("placeholders._param_generator(oracle_params)")
show("Oracle's placeholders, on a FormatStylePlaceholderCursor made without a driver's cursor for the connection \"oracle\" (Oracle 23 assumed; nothing was sent): _fix_for_params writes :arg0, :arg1 and on for %s, one name for equal values in execute's form, and :name for %(name)s; _param_generator gives what the driver would be handed")

quietly("placeholders19 = object.__new__(FormatStylePlaceholderCursor)")
quietly("placeholders19.database = oracle19")
quietly("long_text = 'ø' * 2001")
ask("len(long_text), len(long_text.encode())")
ask("full(OracleParam(long_text, placeholders, True).input_size)")
quietly("aware = datetime.datetime(2026, 3, 14, 18, 30, tzinfo=zoneinfo.ZoneInfo('Europe/Oslo'))")
ask("OracleParam(aware, placeholders, True).force_bytes")
ask("full(OracleParam(aware, placeholders, True).input_size)")
ask("OracleParam(True, placeholders, True).force_bytes")
ask("full(OracleParam(True, placeholders, True).input_size)")
ask("OracleParam(True, placeholders19, True).force_bytes")
ask("full(OracleParam(True, placeholders19, True).input_size)")
show("OracleParam, what Oracle's cursor makes of each parameter (Oracle 23 and Oracle 19 assumed; nothing was sent): a string of more than 4000 bytes in UTF-8 is bound as a CLOB, an aware datetime loses its zone with no conversion under USE_TZ, and True is bound as a boolean on 23 and as 1 on 19")

ask("oracle.ops.quote_name('name_left_in_lowercase')")
ask("oracle.ops.quote_name('\"name_left_in_lowercase\"')")
ask("postgresql.ops.quote_name('\"name_left_in_lowercase\"')")
show("Oracle's quote_name upper-cases a name it is given already quoted, as it does one it quotes itself; PostgreSQL's leaves a quoted name as it is (no server ran)")

quietly("test_params = oracle.creation._get_test_db_params()")
ask("full({key: value for key, value in test_params.items() if key != 'password'})")
ask("len(test_params['password'])")
ask("oracle.settings_dict['TEST']")
show("The parameters of Oracle's test database, for the settings of \"oracle\" (NAME harbour, USER purser, no TEST options; no server ran): names made with test_, the sizes' defaults, and a password of 30 random characters, of which only the length is written")

from django.db.backends.postgresql.psycopg_any import IsolationLevel  # noqa: E402

ASKING.update(IsolationLevel=IsolationLevel)
quietly("shore_postgresql = ConnectionHandler({'default': {'ENGINE': 'django.db.backends.postgresql', **shore}})['default']")
serverless(ASKING["shore_postgresql"])
ask("shore_postgresql.get_connection_params()")
quietly("tuned = ConnectionHandler({'default': {'ENGINE': 'django.db.backends.postgresql', **shore, 'OPTIONS': {'isolation_level': IsolationLevel.SERIALIZABLE, 'assume_role': 'harbourmaster', 'server_side_binding': True, 'pool': True, 'sslmode': 'require'}}})['default']")
serverless(ASKING["tuned"])
ask("tuned.get_connection_params()")
quietly("serviced = ConnectionHandler({'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': None, 'OPTIONS': {'service': 'harbour', 'sslmode': 'require'}}})['default']")
serverless(ASKING["serviced"])
ask("serviced.settings_dict['OPTIONS']")
ask("serviced.get_connection_params()")
ask("serviced.settings_dict['OPTIONS']")
show("PostgreSQL's connection parameters, what psycopg's connect would be given (no server ran): the settings and OPTIONS, with Django's own options taken out; and with NAME None, the database \"postgres\", the alias's own OPTIONS losing \"service\"")

import MySQLdb  # noqa: E402

MB = "django.db.backends.mysql.base"
MF = "django.db.backends.mysql.features"


class StandInCursor:
    """A stand-in of the script's own for the driver's cursor. The statement of mysql_server_data is answered with a row as a server
    of MySQL 8.4 would give it, with sql_auto_is_null on; an insert of a NULL is refused with the error a server gives; any other
    statement has no rows."""

    def execute(self, query, args=None):
        if query.startswith("INSERT") and None in (args or ()):
            raise MySQLdb.OperationalError(1048, "Column 'name' cannot be null")
        self.rows = [("8.4.6", "ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES", "InnoDB", 1, 0, 1)] if "VERSION()" in query else []
        return len(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def close(self):
        pass


class StandInConnection:
    """A stand-in of the script's own for the driver's connection, which MySQLdb.connect returns: nothing reaches a server."""

    def __init__(self, **params):
        pass

    def autocommit(self, on):
        pass

    def cursor(self):
        return StandInCursor()

    def close(self):
        pass


def mysql_params_said(frame, value) -> str:
    return "{" + ", ".join(f"{key!r}: " + ("django_conversions" if key == "conv" else repr(item)) for key, item in value.items()) + "}"


MYSQL_OPENING = watch(
    B, "BaseDatabaseWrapper.connect", "BaseDatabaseWrapper.init_connection_state", "BaseDatabaseWrapper.check_database_version_supported",
    "BaseDatabaseWrapper.temporary_connection", "BaseDatabaseWrapper.close", label=bare,
) | watch(B, "BaseDatabaseWrapper.set_autocommit") | watch(
    MB, "DatabaseWrapper.get_connection_params", "DatabaseWrapper.get_new_connection", "DatabaseWrapper.init_connection_state",
    "DatabaseWrapper.get_database_version", "DatabaseWrapper.mysql_server_data", label=bare,
) | watch(MB, "DatabaseWrapper._set_autocommit") | watch(MF, "DatabaseFeatures.is_sql_auto_is_null_enabled", label=bare) | {
    (DSP, "Signal.send"): signal_sent,
    ("__main__", "StandInConnection.__init__"): lambda f: "StandInConnection.__init__  (MySQLdb.connect in these blocks)",
    ("__main__", "StandInConnection.autocommit"): generic,
    ("__main__", "StandInConnection.close"): bare,
    ("__main__", "StandInCursor.execute"): bare,
}
MYSQL_SAID = {
    (MB, "DatabaseWrapper.get_connection_params"): mysql_params_said, (MB, "DatabaseWrapper.get_database_version"): value_after,
    (MB, "DatabaseWrapper.mysql_server_data"): value_after, (MF, "DatabaseFeatures.is_sql_auto_is_null_enabled"): value_after,
}
ASKING.update(MySQLdb=MySQLdb, StandInConnection=StandInConnection)
step("for the three blocks on MySQL's backend opened with no server, MySQLdb.connect is StandInConnection, a class of the script's own:")
code(StandInCursor, StandInConnection)
DRIVERS_CONNECT = MySQLdb.connect
MySQLdb.connect = StandInConnection
quietly("mysql_opened = ConnectionHandler({'default': {'ENGINE': 'django.db.backends.dummy'}, 'mysql': {'ENGINE': 'django.db.backends.mysql', 'NAME': 'harbour', 'USER': 'purser', 'HOST': 'db.harbour.example'}})['mysql']")
listen(ASKING["mysql_opened"])
ask("'mysql' in base_module.RAN_DB_VERSION_CHECK")
with recorded(MYSQL_OPENING, after=MYSQL_SAID):
    do("mysql_opened.cursor()")
    do("mysql_opened.close()")
    do("mysql_opened.cursor()")
show("Opening a connection of MySQL's backend, on a stand-in for the driver's connection (no server ran; the stand-in answers as MySQL 8.4 with sql_auto_is_null on): the version check reads mysql_server_data through Django's cursor, and both settings go in one statement; opened again, the connection sends the settings and not the SELECT")

TRANSLATED_MYSQL = watch(U, "CursorWrapper._execute", label=bare) | {
    (MB, "CursorWrapper.execute"): lambda f: "CursorWrapper.execute  (MySQL's backend's, around the driver's cursor)",
    ("__main__", "StandInCursor.execute"): bare,
    (DBU, "DatabaseErrorWrapper.__exit__"): lambda f: None if f.f_locals["exc_type"] is None else f"DatabaseErrorWrapper.__exit__(exc_type={answer(f.f_locals['exc_type'])})",
}
with recorded(TRANSLATED_MYSQL):
    do("with mysql_opened.cursor() as cursor: cursor.execute('INSERT INTO fleet_port (name, country) VALUES (%s, %s)', [None, 'Norway'])")
ask("type(caught)")
ask("caught.args")
ask("type(caught.__context__)")
ask("caught.__cause__")
ask("mysql_opened.errors_occurred")
quietly("mysql_opened.close()")
base_module.RAN_DB_VERSION_CHECK.discard("mysql")  # put back as the block before found it
show("MySQL's CursorWrapper given the driver's OperationalError 1048, a column that cannot be null, by the stand-in's cursor (no server ran): it raises Django's IntegrityError in its place, which DatabaseErrorWrapper passes on as it is, and errors_occurred stays unset")

quietly("mysql_asked = ConnectionHandler({'default': {'ENGINE': 'django.db.backends.dummy'}, 'mysql': {'ENGINE': 'django.db.backends.mysql', 'NAME': 'harbour', 'USER': 'purser', 'HOST': 'db.harbour.example'}})['mysql']")
listen(ASKING["mysql_asked"])
ask("mysql_asked.connection is None")
with recorded(MYSQL_OPENING, after=MYSQL_SAID):
    do("server = mysql_asked.mysql_server_data")
ask("mysql_asked.connection is None")
base_module.RAN_DB_VERSION_CHECK.discard("mysql")  # put back as the block found it
MySQLdb.connect = DRIVERS_CONNECT
show("mysql_server_data asked of a connection of MySQL's backend that is not open, on the same stand-in (no server ran): temporary_connection opens it, opening asks mysql_server_data again, and the SELECT is sent twice before the connection is closed")

# ---------------------------------------------------------------------------------------------
# Inserts.

INSERTING = watch(QS, "QuerySet.bulk_create", label=lambda f: f"QuerySet.bulk_create([{len(f.f_locals['objs'])} of Port], batch_size={f.f_locals['batch_size']})") | watch(
    QS, "QuerySet._batched_insert", label=lambda f: f"QuerySet._batched_insert([{len(f.f_locals['objs'])} of Port], batch_size={f.f_locals['batch_size']})",
) | watch(QS, "QuerySet._insert", label=lambda f: f"QuerySet._insert([{len(f.f_locals['objs'])} of Port])") | watch(
    BO, "BaseDatabaseOperations.bulk_batch_size", label=lambda f: f"BaseDatabaseOperations.bulk_batch_size(fields=[{', '.join(x.name for x in f.f_locals['fields'])}], objs=[{len(f.f_locals['objs'])} of Port])",
) | watch(S3F, "DatabaseFeatures.max_query_params", label=bare) | watch("django.db.models.sql.compiler", "SQLInsertCompiler.execute_sql", label=bare) | {
    (TX, "Atomic.__enter__"): atomic_entered, (TX, "Atomic.__exit__"): atomic_left,
} | watch(B, "BaseDatabaseWrapper.commit", label=bare)
says(BO, "BaseDatabaseOperations.bulk_batch_size")
says(S3F, "DatabaseFeatures.max_query_params")
with recorded(INSERTING):
    do("made = Port.objects.bulk_create([Port(name=f'Skerry {n}', country='Faroe') for n in range(1, 6)], batch_size=2)")
ask("[port.pk for port in made]")
show("bulk_create in batches of 2, fewer than the backend's 16383: the batches are sent inside atomic(savepoint=False), and RETURNING gives each new row's key")

CONFLICTS = watch(S3O, "DatabaseOperations.insert_statement", "DatabaseOperations.on_conflict_suffix_sql", label=lambda f: f"{short(f.f_code.co_qualname)}(on_conflict={brief(f.f_locals['on_conflict'])})")
says(S3O, "DatabaseOperations.insert_statement", "DatabaseOperations.on_conflict_suffix_sql")
with recorded(CONFLICTS):
    do("Ship.objects.bulk_create([Ship(name='Petrel', tonnage=480, home_id=1), Ship(name='Fulmar', tonnage=650, home_id=1)], ignore_conflicts=True)")
    do("Ship.objects.bulk_create([Ship(name='Petrel', tonnage=480, home_id=1)], update_conflicts=True, unique_fields=['name', 'home'], update_fields=['tonnage'])")
ask("list(Ship.objects.order_by('pk').values_list('name', 'tonnage'))")
show("Conflicts: ignore_conflicts writes INSERT OR IGNORE, and update_conflicts an ON CONFLICT clause naming the unique fields")

quietly("pair = [Ship(name='Petrel', tonnage=480, home_id=1), Ship(name='Fulmar', tonnage=650, home_id=1)]")
for name in ("postgresql", "mysql", "mariadb"):
    ask(f"full(inserts_for({name}, pair, ['name', 'tonnage', 'home', 'captain'], on_conflict=OnConflict.IGNORE))")
for name in ("postgresql", "mysql", "mariadb"):
    ask(f"full(inserts_for({name}, pair[:1], ['name', 'tonnage', 'home', 'captain'], on_conflict=OnConflict.UPDATE, update_fields=['tonnage'], unique_fields=['name', 'home']))")
show("Conflicts on PostgreSQL, MySQL and MariaDB, the statements bulk_create would send (PostgreSQL 17, MySQL 8.4 and MariaDB 11.4 assumed; nothing was sent): ON CONFLICT DO NOTHING and DO UPDATE with EXCLUDED; INSERT IGNORE, and ON DUPLICATE KEY UPDATE, with an alias for the new row on MySQL and VALUE() on MariaDB")

KEYED = watch("django.db.models.sql.compiler", "SQLInsertCompiler.execute_sql", "SQLInsertCompiler.as_sql", label=bare) | watch(
    BO, "BaseDatabaseOperations.last_insert_id", label=lambda f: f"BaseDatabaseOperations.last_insert_id(cursor, table_name={f.f_locals['table_name']!r}, pk_name={f.f_locals['pk_name']!r})",
) | {(U, "CursorWrapper.__getattr__"): with_value("attr")}
says(BO, "BaseDatabaseOperations.last_insert_id")
quietly("connection.features.can_return_columns_from_insert = False")
with recorded(KEYED):
    do("stromness = Port.objects.create(name='Stromness', country='Scotland')")
ask("stromness.pk")
quietly("del connection.features.can_return_columns_from_insert")
ask("connection.features.can_return_columns_from_insert")
show("A key read back without RETURNING, with can_return_columns_from_insert switched off for this block: the driver's cursor's lastrowid")

# ---------------------------------------------------------------------------------------------
# Values in and out.

GOING_IN = watch("django.db.models.fields", "DateTimeField.get_db_prep_value", label=lambda f: f"DateTimeField.get_db_prep_value({brief(f.f_locals['value'])}, prepared={f.f_locals['prepared']})") | watch(
    S3O, "DatabaseOperations.adapt_datetimefield_value", label=with_value("value"),
) | watch(S3, "adapt_datetime", "adapt_date", label=first_only) | watch("django.utils.timezone", "make_naive", label=lambda f: f"make_naive({brief(f.f_locals['value'])}, {brief(f.f_locals['timezone'])})")
says(S3O, "DatabaseOperations.adapt_datetimefield_value")
says(S3, "adapt_datetime")
says("django.utils.timezone", "make_naive")
quietly("bram = Sailor.objects.get(name='Bram')")
quietly("bram.signed_on = datetime.datetime(2026, 3, 14, 18, 30, tzinfo=zoneinfo.ZoneInfo('Europe/Oslo'))")
with recorded(GOING_IN, sqlite=True):
    do("bram.save(update_fields=['signed_on'])")
    do("with connection.cursor() as cursor: cursor.execute('SELECT %s', [datetime.datetime(2026, 3, 14, 18, 30)])")
show("A datetime on its way in: Django makes it naive in the connection's time zone (UTC) and hands the driver a string; the adapter Django's backend registers with the driver runs only for a datetime given to the cursor")

COMING_OUT = watch(CO, "SQLCompiler.get_converters", "SQLCompiler.apply_converters", label=bare) | watch(
    S3O, "DatabaseOperations.get_db_converters", label=lambda f: f"DatabaseOperations.get_db_converters({brief(f.f_locals['expression'])})",
) | watch("django.db.models.fields", "Field.get_db_converters", label=bare) | {
    (S3, "decoder.<locals>.<lambda>"): decoded,
    ("django.utils.dateparse", "parse_datetime"): generic,
    (S3O, "DatabaseOperations.convert_datetimefield_value"): with_value("value"),
    ("django.utils.timezone", "make_aware"): lambda f: f"make_aware({brief(f.f_locals['value'])}, {brief(f.f_locals['timezone'])})",
}
says(S3O, "DatabaseOperations.get_db_converters", how=lambda f, v: "[" + ", ".join(short(c.__qualname__) for c in v) + "]")
says(CO, "SQLCompiler.get_converters", how=lambda f, v: "{" + ", ".join(f"{pos}: [{', '.join(short(c.__qualname__) for c in convs)}]" for pos, (convs, _) in v.items()) + "}")
says("django.utils.timezone", "make_aware")
with recorded(COMING_OUT, c=("sqlite3.Cursor.fetchmany",)):
    do("signed_on = Sailor.objects.values_list('signed_on', flat=True).get(name='Bram')")
ask("signed_on")
ask("signed_on.tzinfo")
ask("timezone.localtime(signed_on)")
ask("connection.timezone")
ask("connection.timezone_name")
ask("connection.settings_dict['TIME_ZONE']")
show("…and out: for the column declared datetime the driver calls the converter Django's backend registered with it, and the operations object's converter makes the value aware in the connection's time zone")

with recorded(watch(S3, "adapt_datetime", label=first_only), sqlite=True):
    do("with connection.cursor() as cursor: cursor.execute('SELECT %s', [datetime.datetime(2026, 3, 14, 18, 30, tzinfo=zoneinfo.ZoneInfo('Europe/Oslo'))]); row = cursor.fetchone()")
ask("row")
show("An aware datetime given to the cursor itself: no field makes it naive, and the adapter Django's backend registers with the driver writes it with its offset")

RAW_IN = watch("django.db.models.sql.query", "RawQuery._execute_query", label=bare) | watch(
    BO, "BaseDatabaseOperations.adapt_unknown_value", label=first_only,
) | watch(S3O, "DatabaseOperations.adapt_datetimefield_value", label=with_value("value")) | watch(
    "django.utils.timezone", "make_naive", label=lambda f: f"make_naive({brief(f.f_locals['value'])}, {brief(f.f_locals['timezone'])})",
)
says(BO, "BaseDatabaseOperations.adapt_unknown_value")
with recorded(RAW_IN):
    do("signed = list(Sailor.objects.raw('SELECT id, name FROM crew_sailor WHERE signed_on > %s ORDER BY id', [datetime.datetime(2026, 1, 1, tzinfo=zoneinfo.ZoneInfo('Europe/Oslo'))]))")
ask("signed")
show("A datetime given to QuerySet.raw: with no field to say what it is, RawQuery hands each parameter to adapt_unknown_value, which adapts a datetime as a DateTimeField's")

from django.db.models.functions import Trunc  # noqa: E402

ASKING.update(Trunc=Trunc)
TRUNCATED = watch(CO, "SQLCompiler.get_converters", label=bare) | watch(
    S3O, "DatabaseOperations.convert_datetimefield_value", label=with_value("value"),
) | watch("django.db.models.functions.datetime", "TruncBase.convert_value", label=with_value("value")) | watch(
    BO, "BaseDatabaseOperations.convert_trunc_expression", label=with_value("value"),
) | {("django.utils.timezone", "make_aware"): lambda f: f"make_aware({brief(f.f_locals['value'])}, {brief(f.f_locals['timezone'])})"}
says(BO, "BaseDatabaseOperations.convert_trunc_expression")
with recorded(TRUNCATED):
    do("month = Sailor.objects.annotate(month=Trunc('signed_on', 'month')).values_list('month', flat=True).get(name='Bram')")
ask("month")
show("A Trunc of a datetime on its way out: SQLite truncates in Oslo's time and gives text; the backend's converter makes it aware in the connection's zone, UTC, and then the expression's converter, convert_trunc_expression, puts the current time zone, Oslo's, in its place")

VALUES_OUT = watch(S3O, "DatabaseOperations.convert_booleanfield_value", "DatabaseOperations.convert_datefield_value", label=with_value("value")) | watch(
    S3O, "DatabaseOperations.get_decimalfield_converter", label=lambda f: f"DatabaseOperations.get_decimalfield_converter({brief(f.f_locals['expression'])})",
) | watch(S3O, "DatabaseOperations.get_decimalfield_converter.<locals>.converter", label=lambda f: f"converter({f.f_locals['value']!r})  (the function get_decimalfield_converter made)") | watch(
    S3O, "DatabaseOperations._create_decimal", label=first_only,
) | {(S3, "decoder.<locals>.<lambda>"): decoded, ("django.utils.dateparse", "parse_date"): generic}
for key in ((S3O, "DatabaseOperations.convert_booleanfield_value"), (S3O, "DatabaseOperations.convert_datefield_value"),
            (S3O, "DatabaseOperations.get_decimalfield_converter.<locals>.converter"), (S3O, "DatabaseOperations._create_decimal"),
            ("django.utils.dateparse", "parse_date")):
    AFTER[key] = value_after
REGISTERED_BOOL = sqlite3.converters["BOOL"]  # b"1".__eq__, which Django's SQLite backend registers with the driver


def bool_converter(value):
    """The converter registered with the driver for "bool", b"1".__eq__, wrapped for this block so that each call is written."""
    converted = REGISTERED_BOOL(value)
    note(f'b"1".__eq__({value!r})  ->  {converted!r}  (written by bool_converter)')
    return converted


step('for this block, the converter registered with the driver for "bool", b"1".__eq__, is wrapped in a function of the script\'s own:')
code(bool_converter)
sqlite3.register_converter("bool", bool_converter)
with recorded(VALUES_OUT):
    do("stamped = Manifest.objects.values_list('stamped', flat=True).get()")
    do("rate = Ship.objects.annotate(rate=models.Value(Decimal('12.50'), output_field=models.DecimalField(max_digits=5, decimal_places=2))).values_list('rate', flat=True).first()")
    do("sailed = Voyage.objects.values_list('sailed', flat=True).get(pk=1)")
sqlite3.register_converter("bool", REGISTERED_BOOL)
ask("stamped")
ask("rate")
ask("sailed")
ask("full(connection.Database.converters['BOOL'])")
ask("full(connection.Database.converters['DATE'])")
ask("full(connection.Database.converters['DATETIME'])")
show("Booleans, decimals and dates on their way out: the converter registered with the driver for the column's declared type, where there is one, then the operations object's")

run_part("use-tz-off")

# ---------------------------------------------------------------------------------------------
# Column types.


def named(field, name: str):
    """A field given a name, so that its column is known, as a model's class statement would give it."""
    field.set_attributes_from_name(name)
    return field


ASKING.update(named=named, timezone=timezone)
FIELDS = (
    "models.AutoField(primary_key=True)", "models.BigAutoField(primary_key=True)", "models.SmallAutoField(primary_key=True)",
    "models.BinaryField()", "models.BooleanField()", "models.CharField(max_length=60)", "models.CharField()", "models.DateField()",
    "models.DateTimeField()", "models.DecimalField(max_digits=8, decimal_places=2)", "models.DurationField()", "models.FileField()",
    "models.FilePathField(path='manifests')", "models.FloatField()", "models.IntegerField()", "models.BigIntegerField()",
    "models.SmallIntegerField()", "models.PositiveIntegerField()", "models.PositiveBigIntegerField()", "models.PositiveSmallIntegerField()",
    "models.IPAddressField()", "models.GenericIPAddressField()", "models.JSONField()", "models.SlugField()", "models.TextField()",
    "models.TimeField()", "models.UUIDField()",
)
ASKING["FIELDS"] = FIELDS
for field in FIELDS:
    ask(f"{field}.db_type(connection)")
for field in ("models.PositiveIntegerField()", "models.JSONField()", "models.AutoField(primary_key=True)", "models.CharField(max_length=60, db_collation='nocase')"):
    ask(f"named({field}, 'crates').db_parameters(connection)")
ask("Sailor._meta.get_field('ship').db_type(connection)")
ask("models.AutoField(primary_key=True).rel_db_type(connection)")
ask("models.PositiveIntegerField(primary_key=True).rel_db_type(connection)")
ask("models.CharField(max_length=60).cast_db_type(connection)")
ask("models.DateTimeField().cast_db_type(connection)")
ask("models.IntegerField().cast_db_type(connection)")
ask("sorted(set(connection.data_types) - {type(eval(field)).__name__ for field in FIELDS})")

show("Each field's column on SQLite: db_type for each field class with an entry in data_types, db_parameters where a check constraint or a collation is added, and the column of a foreign key")


def columns(field) -> Said:
    """The field's db_type on each of the four connections."""
    return Said(", ".join(f"{name} {field.db_type(conn)!r}" for name, conn in DIALECT_CONNECTIONS.items()))


DIALECT_CONNECTIONS = {"sqlite": connections["default"], "postgresql": DIALECTS["postgresql"], "mysql": DIALECTS["mysql"], "oracle": DIALECTS["oracle"]}
ASKING.update(columns=columns)
for field in FIELDS:
    ask(f"columns({field})")
ask("columns(models.PositiveIntegerField(primary_key=True)) == columns(models.PositiveIntegerField())")
for name in ("sqlite", "postgresql", "mysql", "oracle"):
    ask(f"models.PositiveIntegerField(primary_key=True).rel_db_type({name})")
show("The same fields' columns on four backends (PostgreSQL 17, MySQL 8.4 and Oracle 23 assumed; no server ran): columns(field) is db_type on each connection in turn")

# ---------------------------------------------------------------------------------------------
# The schema editor.

from django.apps.registry import Apps  # noqa: E402
from django.core.management.color import no_style  # noqa: E402
from django.db.backends.utils import names_digest, truncate_name  # noqa: E402

moorings = Apps()


class Buoy(models.Model):
    name = models.CharField(max_length=40)
    port = models.ForeignKey(Port, on_delete=models.CASCADE)

    class Meta:
        app_label = "moorings"
        apps = moorings
        indexes = [models.Index(fields=["name"], name="buoy_name_idx")]


ASKING.update(Buoy=Buoy, moorings=moorings, no_style=no_style, names_digest=names_digest, truncate_name=truncate_name, Apps=Apps)


def model_said(frame) -> str:
    return f"{short(frame.f_code.co_qualname)}({frame.f_locals['model'].__name__})" + on(frame)


def column_said(frame) -> str:
    return f"{short(frame.f_code.co_qualname)}({frame.f_locals['model'].__name__}, {brief(frame.f_locals['field'])})"


def executed(frame) -> str:
    sql = frame.f_locals["sql"]
    return f"BaseDatabaseSchemaEditor.execute({a(type(sql).__name__)}" + (f", params={frame.f_locals['params']!r})" if frame.f_locals["params"] not in ((), None) else ")")


EDITING = watch(S3S, "DatabaseSchemaEditor.__enter__", "DatabaseSchemaEditor.__exit__", label=bare) | watch(
    BS, "BaseDatabaseSchemaEditor.__enter__", "BaseDatabaseSchemaEditor.__exit__", label=bare,
) | watch(BS, "BaseDatabaseSchemaEditor.create_model", "BaseDatabaseSchemaEditor.table_sql", label=model_said) | watch(
    BS, "BaseDatabaseSchemaEditor.column_sql", label=column_said,
) | {(BS, "BaseDatabaseSchemaEditor.execute"): executed} | watch(
    S3, "DatabaseWrapper.disable_constraint_checking", "DatabaseWrapper.enable_constraint_checking", "DatabaseWrapper.check_constraints", label=bare,
) | {(TX, "Atomic.__enter__"): atomic_entered, (TX, "Atomic.__exit__"): atomic_left} | watch(B, "BaseDatabaseWrapper.commit", label=bare)
says(BS, "BaseDatabaseSchemaEditor.table_sql", how=lambda f, v: f"({v[0]!r}, {v[1]!r})")
says(BS, "BaseDatabaseSchemaEditor.column_sql", how=lambda f, v: f"({v[0]!r}, {v[1]!r})")
says(S3, "DatabaseWrapper.disable_constraint_checking")
step("the model of the script's own, in an Apps registry of its own, so that harbour's registry is untouched:")
code(Buoy)
quietly("editor = connection.schema_editor(collect_sql=True)")
with recorded(EDITING):
    do("editor.__enter__()")
    do("editor.create_model(Buoy)")
    ask("full([str(statement) for statement in editor.deferred_sql])")
    ask("type(editor.deferred_sql[0])")
    do("editor.__exit__(None, None, None)")
ask("full(editor.collected_sql)")
ask("'moorings_buoy' in connection.introspection.table_names()")
show("create_model, collected (collect_sql=True): the CREATE TABLE is collected at once and the indexes are deferred to the editor's exit; the editor still turns SQLite's foreign key checks off and on, and begins and commits a transaction")

PG_EDITING = watch(BS, "BaseDatabaseSchemaEditor.__enter__", "BaseDatabaseSchemaEditor.__exit__", label=bare) | watch(
    BS, "BaseDatabaseSchemaEditor.create_model", "BaseDatabaseSchemaEditor.table_sql", label=model_said,
) | {(BS, "BaseDatabaseSchemaEditor.execute"): executed}
quietly("editor = postgresql.schema_editor(collect_sql=True, atomic=False)")
with recorded(PG_EDITING):
    do("editor.__enter__()")
    do("editor.create_model(Buoy)")
    ask("full([str(statement) for statement in editor.deferred_sql])")
    do("editor.__exit__(None, None, None)")
ask("full(editor.collected_sql)")
show("create_model(Buoy) collected on PostgreSQL (PostgreSQL 17 assumed; no server ran; collect_sql=True, and atomic=False, so that no transaction is begun): the key is an identity column, and the foreign key is deferred to the exit as ALTER TABLE ... ADD CONSTRAINT, where SQLite writes it in the CREATE TABLE")


class Chart(models.Model):
    title = models.CharField(max_length=60, db_index=True)
    notes = models.TextField(db_index=True)
    port = models.ForeignKey(Port, on_delete=models.CASCADE)

    class Meta:
        app_label = "moorings"
        apps = moorings


PGS = "django.db.backends.postgresql.schema"
LIKE_INDEXES = watch(PGS, "DatabaseSchemaEditor._field_indexes_sql", "DatabaseSchemaEditor._create_like_index_sql", label=column_said)
says(PGS, "DatabaseSchemaEditor._create_like_index_sql", how=lambda f, v: "None" if v is None else f"a Statement, {str(v)!r}")
ASKING.update(Chart=Chart)
step("a second model of the script's own, in the registry of Buoy:")
code(Chart)
quietly("editor = postgresql.schema_editor(collect_sql=True, atomic=False)")
with recorded(LIKE_INDEXES):
    do("with editor: editor.create_model(Chart)")
ask("full(editor.collected_sql)")
show("A CharField and a TextField with db_index, collected on PostgreSQL (PostgreSQL 17 assumed; no server ran): each has its index and a second one, _like, with the operator class varchar_pattern_ops or text_pattern_ops, for LIKE; the foreign key's column, a bigint, has no second")

quietly("colour = named(models.CharField(max_length=10, null=True), 'colour'); colour.model = Buoy")
quietly("by_port = models.Index(fields=['port', 'name'], name='buoy_port_name_idx')")
quietly("has_name = models.CheckConstraint(condition=models.Q(name__gt=''), name='buoy_has_name')")
quietly("with connection.schema_editor() as editor: editor.create_model(Buoy)")
quietly("with connection.schema_editor() as editor: editor.add_field(Buoy, colour)")
quietly("with connection.schema_editor() as editor: editor.remove_field(Buoy, colour)")
quietly("Buoy._meta.indexes.append(by_port)  # as a migration's state of the model would hold it")
quietly("with connection.schema_editor() as editor: editor.add_index(Buoy, by_port)")
quietly("Buoy._meta.constraints.append(has_name)  # likewise")
quietly("with connection.schema_editor() as editor: editor.add_constraint(Buoy, has_name)")
show("The same, run, and then a column added and removed, an index added, and a check constraint added, which SQLite does by remaking the table")


def renamed_said(frame) -> str | None:
    if not frame.f_code.co_qualname.endswith("rename_table_references"):
        return None
    made, ran_ = type(frame.f_locals["self"]).__name__, short(frame.f_code.co_qualname)
    head = f"{made}.rename_table_references({frame.f_locals['old_table']!r}, {frame.f_locals['new_table']!r})"
    return head if ran_.startswith(made + ".") else f"{head}  ({ran_})"


step("Buoy's _meta still holds the index buoy_port_name_idx and the check constraint buoy_has_name that the block before appended to it")
quietly("editor = connection.schema_editor(collect_sql=True)")
quietly("editor.__enter__()")
quietly("editor.create_model(Buoy)")
ask("full([str(statement) for statement in editor.deferred_sql])")
with recorded(watch(BS, "BaseDatabaseSchemaEditor.alter_db_table", label=lambda f: f"BaseDatabaseSchemaEditor.alter_db_table(Buoy, {f.f_locals['old_db_table']!r}, {f.f_locals['new_db_table']!r})") | {(BS, "BaseDatabaseSchemaEditor.execute"): executed},
              modules={DDL: renamed_said}):
    do("editor.alter_db_table(Buoy, 'moorings_buoy', 'moorings_float')")
ask("full([str(statement) for statement in editor.deferred_sql])")
quietly("editor.__exit__(None, None, None)")
ask("full(editor.collected_sql)")
show("Deferred statements follow a renamed table: alter_db_table renames the table in each deferred Statement before the editor's exit writes it (collect_sql=True)")

step("Buoy's _meta holds the index and the check constraint of the block before it, as there; this time no statement is written before the rename")
quietly("editor = connection.schema_editor(collect_sql=True)")
quietly("editor.__enter__()")
quietly("editor.create_model(Buoy)")
with recorded(watch(BS, "BaseDatabaseSchemaEditor.alter_db_table", label=lambda f: f"BaseDatabaseSchemaEditor.alter_db_table(Buoy, {f.f_locals['old_db_table']!r}, {f.f_locals['new_db_table']!r})") | {(BS, "BaseDatabaseSchemaEditor.execute"): executed}):
    do("editor.alter_db_table(Buoy, 'moorings_buoy', 'moorings_float')")
ask("full([str(statement) for statement in editor.deferred_sql])")
quietly("editor.__exit__(None, None, None)")
ask("full(editor.collected_sql)")
show("The same rename with no question before it (collect_sql=True): the name of an index Django names itself is made the first time its statement is written, here after the rename, and so from the new table's name; the block before fixed the old one by asking")

quietly("editor = connection.schema_editor()")
ask("connection.ops.max_name_length()")
ask("editor._create_index_name('fleet_ship', ['home_id', 'tonnage'])")
ask("editor._create_index_name('fleet_ship', ['home_id', 'tonnage'], suffix='_fk')")
ask("names_digest('fleet_ship', 'home_id', 'tonnage', length=8)")
ask("Ship._meta.indexes[0].name")
quietly("long_table = 'office_' + 'manifest_' * 25")
ask("len(long_table)")
ask("editor._create_index_name(long_table, ['voyage_id'])")
ask("len(editor._create_index_name(long_table, ['voyage_id']))")
ask("postgresql.ops.max_name_length()")
ask("postgresql.SchemaEditorClass(postgresql)._create_index_name(long_table, ['voyage_id'])")
ask("truncate_name('office_manifest_voyage_index', oracle.ops.max_name_length())")
ask("truncate_name('office_manifest_voyage_index_for_the_long_haul', oracle.ops.max_name_length())")
ask("truncate_name('office_manifest_voyage_index_for_the_long_haul', connection.ops.max_name_length())")
show("Names of indexes and constraints: the table, the columns and a digest of them, within the backend's longest name (200 where it has none, as on SQLite; PostgreSQL's 63 and Oracle's 30, no server ran)")

FOREIGN_KEYS = watch(S3S, "DatabaseSchemaEditor.__enter__", "DatabaseSchemaEditor.__exit__", label=bare) | watch(
    S3, "DatabaseWrapper.disable_constraint_checking", "DatabaseWrapper.enable_constraint_checking", "DatabaseWrapper.check_constraints", label=bare,
) | {(TX, "Atomic.__enter__"): atomic_entered, (TX, "Atomic.__exit__"): atomic_left}
with recorded(FOREIGN_KEYS):
    do("with connection.schema_editor() as editor: pass")
    do("with transaction.atomic(): connection.schema_editor().__enter__()")
show("The schema editor on SQLite and foreign keys: it turns the checks off on entering, checks every table on leaving, and cannot be entered inside a transaction, where SQLite ignores the PRAGMA")

ALTERING = watch(BS, "BaseDatabaseSchemaEditor.alter_field", label=lambda f: f"BaseDatabaseSchemaEditor.alter_field(Buoy, {describe_field(f.f_locals['old_field'])}, {describe_field(f.f_locals['new_field'])})") | watch(
    BS, "BaseDatabaseSchemaEditor._field_should_be_altered", label=bare,
) | watch(S3S, "DatabaseSchemaEditor._alter_field", "DatabaseSchemaEditor._remake_table", label=bare)
says(BS, "BaseDatabaseSchemaEditor._field_should_be_altered")


def describe_field(field) -> str:
    return f"{type(field).__name__} {field.name!r}" + (f" max_length={field.max_length}" if field.max_length else "") + (f" verbose_name={field.verbose_name!r}" if field.verbose_name != field.name.replace("_", " ") else "")


quietly("old = Buoy._meta.get_field('name')")
quietly("longer = old.clone(); longer.max_length = 80; longer.set_attributes_from_name('name'); longer.model = Buoy")
with recorded(ALTERING):
    do("with connection.schema_editor() as editor: editor.alter_field(Buoy, old, longer)")
show("A column altered: SQLite remakes the table, copying the rows into a new one and renaming it, and makes the indexes again")

quietly("titled = longer.clone(); titled.set_attributes_from_name('title'); titled.model = Buoy")
quietly("labelled = titled.clone(); labelled.verbose_name = 'label'; labelled.set_attributes_from_name('title'); labelled.model = Buoy")
with recorded(ALTERING):
    do("with connection.schema_editor() as editor: editor.alter_field(Buoy, longer, titled)")
    do("with connection.schema_editor() as editor: editor.alter_field(Buoy, titled, labelled)")
show("A rename, and a change that alters nothing: a column renamed in place, and a verbose_name, which _field_should_be_altered does not count (the editor's own PRAGMAs are still sent)")

from django.db.migrations.state import AppConfigStub  # noqa: E402


def quays_models(code_length: int):
    """Pier and Mooring in an Apps registry of their own, with an app config for their label as a migration's state makes one, so that
    Pier's _meta knows the foreign key that points at it; a pier's code, its key, is code_length long."""
    quays = Apps([AppConfigStub("quays")])

    class Pier(models.Model):
        code = models.CharField(max_length=code_length, primary_key=True)
        keeper = models.CharField(max_length=20, null=True)

        class Meta:
            app_label = "quays"
            apps = quays

    class Mooring(models.Model):
        pier = models.ForeignKey(Pier, on_delete=models.CASCADE)

        class Meta:
            app_label = "quays"
            apps = quays

    return Pier, Mooring


def field_said(field) -> str:
    """A field by its class, its name, and the options the blocks on altering a column change."""
    said = [f"{type(field).__name__} {field.name!r}", f"max_length={field.max_length}"]
    said += ["primary_key=True"] if field.primary_key else []
    said += ["null=True"] if field.null else []
    said += [f"default={field.default!r}"] if field.has_default() else []
    return " ".join(said)


REMAKING = {
    (BS, "BaseDatabaseSchemaEditor.alter_field"): lambda f: f"BaseDatabaseSchemaEditor.alter_field({f.f_locals['model'].__name__}, {field_said(f.f_locals['old_field'])}, {field_said(f.f_locals['new_field'])})",
    (S3S, "DatabaseSchemaEditor._remake_table"): model_said,
} | watch(BS, "BaseDatabaseSchemaEditor._field_should_be_altered", label=bare) | watch(S3S, "DatabaseSchemaEditor._alter_field", label=bare)
ASKING.update(quays_models=quays_models)
step("the models of the three blocks on altering a column, made by a function of the script's own:")
code(quays_models)
quietly("Pier, Mooring = quays_models(4)")
quietly("with connection.schema_editor() as editor: editor.create_model(Pier); editor.create_model(Mooring)")
quietly("Pier.objects.create(code='N1'); Pier.objects.create(code='N2', keeper='Ada'); Mooring.objects.create(pier_id='N1')")
quietly("kept = Pier._meta.get_field('keeper')")
quietly("required = models.CharField(max_length=20, default='harbourmaster'); required.set_attributes_from_name('keeper'); required.model = Pier")
with recorded(REMAKING):
    do("with connection.schema_editor() as editor: editor.alter_field(Pier, kept, required)")
ask("list(Pier.objects.order_by('code').values_list('code', 'keeper'))")
show("A column that allowed NULL made NOT NULL with a default, on SQLite: the table is remade, and the copy into it fills each NULL with the default by coalesce")

quietly("purser = models.CharField(max_length=20, default='the purser'); purser.set_attributes_from_name('keeper'); purser.model = Pier")
with recorded(REMAKING):
    do("with connection.schema_editor() as editor: editor.alter_field(Pier, required, purser)")
show("Only a field's default changed, on SQLite: _field_should_be_altered counts a default, and SQLite's editor remakes the table, though the column it writes is the same")

quietly("LongPier, LongMooring = quays_models(8)  # the models as a migration's new state would have them")
with recorded(REMAKING):
    do("with connection.schema_editor() as editor: editor.alter_field(Pier, Pier._meta.get_field('code'), LongPier._meta.get_field('code'))")
ask("list(Mooring.objects.values_list('pier_id', flat=True))")
with connection.schema_editor() as cleaning:  # the tables of these three blocks are dropped, unwritten
    cleaning.delete_model(ASKING["Mooring"])
    cleaning.delete_model(ASKING["Pier"])
show("A primary key's type changed, on SQLite: the table is remade, and so is the table whose foreign key points at the key, to remake its column too (the models as a migration's states hold them, before and after)")

# ---------------------------------------------------------------------------------------------
# Introspection.

quietly("cursor = connection.cursor()")
ask("full(connection.introspection.table_names(cursor))")
quietly("description = connection.introspection.get_table_description(cursor, 'fleet_ship')")
for info in ASKING["description"]:
    note(f"  {info!r}")
ask("[connection.introspection.get_field_type(info.type_code, info) for info in description]")
ask("connection.introspection.get_relations(cursor, 'crew_sailor')")
ask("connection.introspection.get_primary_key_column(cursor, 'fleet_ship')")
ask("connection.introspection.get_primary_key_columns(cursor, 'office_berth')")
quietly("constraints = connection.introspection.get_constraints(cursor, 'fleet_ship')")
for name in sorted(ASKING["constraints"]):
    note(f"  {name}: {ASKING['constraints'][name]!r}")
ask("connection.introspection.get_sequences(cursor, 'fleet_ship')")
ask("full(connection.introspection.sequence_list())")
ask("full(sorted(connection.introspection.django_table_names(only_existing=True)))")
ask("sorted(set(connection.introspection.table_names()) - set(connection.introspection.django_table_names()))")
quietly("cursor.close()")
show("What introspection reads back from SQLite: the tables, a table's columns (a FieldInfo to a line), its relations, keys and constraints (a constraint to a line, sorted by name)")

quietly("archive_cursor = connections['archive'].cursor()")
quietly("relations = connections['archive'].introspection.get_relations(archive_cursor, 'office_logentry')")
ask("relations")
ask("relations['book_id'][2] is models.DB_CASCADE")
quietly("archive_cursor.close()")
ask("connection.ops.sequence_reset_sql(no_style(), [Port, Ship])")
show("A rule the database keeps, read back: get_relations on \"archive\"'s office_logentry, whose foreign key the database deletes with (LogEntry.book is DB_CASCADE), gives DB_CASCADE where crew_sailor's gave DO_NOTHING; and sequence_reset_sql, which on SQLite writes nothing")

FLUSHING = watch(BO, "BaseDatabaseOperations.execute_sql_flush", label=bare) | {(TX, "Atomic.__enter__"): atomic_entered, (TX, "Atomic.__exit__"): atomic_left} | watch(
    B, "BaseDatabaseWrapper.commit", "BaseDatabaseWrapper.savepoint", label=bare,
)
ask("full(connection.ops.sql_flush(no_style(), ['office_licence', 'office_berth'], reset_sequences=True))")
with recorded(FLUSHING):
    do("connection.ops.execute_sql_flush(connection.ops.sql_flush(no_style(), ['office_licence', 'office_berth'], reset_sequences=True))")
ask("Licence.objects.count()")
show("Flushing two tables: sql_flush writes a DELETE for each and resets their sequences, and execute_sql_flush runs them in one atomic block")

# ---------------------------------------------------------------------------------------------
# Test databases.

run_part("test-databases")

# ---------------------------------------------------------------------------------------------
# SQLite.

CALLED_BACK = watch(S3FN, "_sqlite_datetime_extract", label=generic) | watch(S3FN, "_sqlite_datetime_parse", label=generic)
says(S3FN, "_sqlite_datetime_extract", "_sqlite_datetime_parse")
step("crew_sailor holds five rows: the four the recording began with, Bram's signed_on changed by the block \"A datetime on its way in\" to 2026-03-14 17:30 UTC, and Fen, an Officer, added by the block \"Autocommit, the plain case\"")
with recorded(CALLED_BACK, sqlite=True, c=("sqlite3.Cursor.execute", "sqlite3.Cursor.fetchmany")):
    do("march = list(Sailor.objects.filter(signed_on__month=3))")
ask("march")
ask("Sailor.objects.count()")
show("SQLite calls back into Python: the SQL calls django_datetime_extract, and SQLite calls _sqlite_datetime_extract for it, once for each row it reads")

AGGREGATED = {("statistics", "pstdev"): lambda f: f"StdDevPop.finalize({list(f.f_locals['data'])!r})  (statistics.pstdev, called by SQLite)"}
says("statistics", "pstdev")
with recorded(AGGREGATED, sqlite=True, c=("sqlite3.Cursor.execute",)):
    do("spread = Ship.objects.aggregate(spread=models.StdDev('tonnage'))")
ask("spread")
show("An aggregate SQLite calls back for: STDDEV_POP is StdDevPop, a list, which register() gave SQLite; its step, list.append, is called from C for each row and is not written, and its finalize, statistics.pstdev, is called once, with the list")

CHECKING = {(TX, "Atomic.__enter__"): atomic_entered, (TX, "Atomic.__exit__"): atomic_left} | watch(
    S3, "DatabaseWrapper.check_constraints", label=bare,
) | watch(BI, "BaseDatabaseIntrospection.get_primary_key_column", label=bare) | watch(B, "BaseDatabaseWrapper.rollback", label=bare)
with recorded(CHECKING):
    do("with transaction.atomic(): Sailor.objects.create(name='Gale', ship_id=99); connection.check_constraints()")
ask("Sailor.objects.filter(name='Gale').exists()")
show("A foreign key with no row behind it, found by check_constraints: inside a transaction SQLite takes the row, its foreign keys being checked at the commit; check_constraints asks PRAGMA foreign_key_check, reads the key's columns, and raises IntegrityError, and the block rolls back")

DISABLING = {(TX, "Atomic.__enter__"): atomic_entered, (TX, "Atomic.__exit__"): atomic_left} | watch(
    B, "BaseDatabaseWrapper.constraint_checks_disabled", "BaseDatabaseWrapper.commit", label=bare,
) | watch(S3, "DatabaseWrapper.disable_constraint_checking", "DatabaseWrapper.enable_constraint_checking", label=bare)
with recorded(DISABLING):
    do("with transaction.atomic(), connection.constraint_checks_disabled(): Ship.objects.count()")
ask("connection.cursor().execute('PRAGMA foreign_keys').fetchone()")
show("constraint_checks_disabled() entered inside an atomic block, as loaddata enters it: SQLite ignores PRAGMA foreign_keys = OFF in a transaction, disable_constraint_checking reads the checks still on and returns False, and so nothing turns them back on")

ASKING.update(ConnectionHandler=ConnectionHandler)
quietly("connections.settings['memory'] = ConnectionHandler({'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}).settings['default']")
quietly("memory = connections['memory']")
quietly("memory.cursor().execute('CREATE TABLE tide (height real)')")
with recorded(watch(S3, "DatabaseWrapper.close", "DatabaseWrapper.is_in_memory_db", label=bare) | watch(B, "BaseDatabaseWrapper.close", label=bare)):
    do("memory.close()")
ask("memory.connection is None")
ask("memory.introspection.table_names()")
from django.db.backends.base.base import BaseDatabaseWrapper  # noqa: E402

ASKING.update(BaseDatabaseWrapper=BaseDatabaseWrapper)
quietly("BaseDatabaseWrapper.close(memory)  # the base class's close, which SQLite's skips for an in-memory database")
ask("memory.connection is None")
show("The in-memory database is not closed by SQLite's close(): on a connection of its own alias, \"memory\", close() leaves the driver's connection open, and its table with it")

quietly("connections.settings['immediate'] = ConnectionHandler({'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': connection.settings_dict['NAME'], 'OPTIONS': {'transaction_mode': 'IMMEDIATE', 'init_command': 'PRAGMA synchronous = NORMAL; PRAGMA cache_size = 2000'}}}).settings['default']")
OPTIONED = watch(S3, "DatabaseWrapper.get_connection_params", "DatabaseWrapper.get_new_connection", "DatabaseWrapper._start_transaction_under_autocommit", label=bare) | watch(
    B, "BaseDatabaseWrapper.init_connection_state", "BaseDatabaseWrapper.check_database_version_supported", label=bare,
) | {(TX, "Atomic.__enter__"): atomic_entered, (TX, "Atomic.__exit__"): atomic_left} | {("sqlite3", "connect"): bare}
says(S3, "DatabaseWrapper.get_connection_params")
with recorded(OPTIONED, sqlite=True, c=("sqlite3.Connection.execute", "sqlite3.Connection.commit")):
    do("Ship.objects.using('immediate').count()")
    ask("connections['immediate'].transaction_mode")
    ask("connections['immediate'].init_commands")
    do("with transaction.atomic(using='immediate'): Ship.objects.using('immediate').count()")
ask("sorted(base_module.RAN_DB_VERSION_CHECK)")
quietly("connections['immediate'].close()")
show("OPTIONS: transaction_mode and init_command, on a connection of its own alias, \"immediate\": the init commands run at opening, and an atomic block begins with BEGIN IMMEDIATE")

