"""A recording of querysets: what one holds, when it sends a statement and when it answers
from what it has, how rows become instances, dictionaries and tuples, how related objects are
fetched beside them, and what its methods that write do.

    python recordings/querysets.py > recordings/querysets.txt

Chapter 9 of the book (pages/querysets.md and the pages under it) is written against this
output. It needs only the pinned Django (the project's virtual environment has it) and the
small project beside it, `harbour/`, which chapter 8's recording uses too: a shipping line
in three applications, `fleet`, `crew` and `office`. The database is a SQLite file made for
the run. Run it again after a re-pin: where the output changes, the chapter has to.

In what follows a statement is always a statement of SQL, sent to the database; what the
script itself runs is called a line of Python.

The blocks are of three kinds, and a block may mix them. Where the order of calls is the
point, the lines are calls, nested as they were made: the calls a block is about and no
others, so everything between the lines ran and is left out. A line of Python (`named =
Sailor.objects.filter(ship=petrel).order_by('name')`) is what the script ran, as it ran it.
Under it stand the calls it set going, of those the block is about, and every statement it
sent: a line of Python with no `SQL` line under it sent none. Some lines of Python are run
with none of their calls written down, to make something a later line needs; the statements
they sent stand under them all the same. A method is written by the class that declares it,
whatever the class of the object. Its arguments follow, each parameter by its name, and of
those that have a default only the ones that were given another value; a function of one
parameter that has no default is written with the value alone. Three calls are written
otherwise: `Model.from_db` with every argument, and the class it was called on after it in
parentheses; `QuerySet._insert` with its instances, its fields, what it is to ask back and
its arguments about conflicts, whether or not they are at their defaults, and without the
alias it was passed; and `QuerySet._update` with each of its values as a field and a value,
where the code has a triple with a model, here always None, between the two. What a call returned follows `->`, put into words at the moment it
was returned; `raises` names an exception, once, at the innermost written-down call it
left, and again with its message under the line of Python it ended. A call with neither
after it returned something the recording does not describe, or is a generator, which
returns nothing until it is exhausted. A generator's line is written once, where its body
first runs. What it calls each time it is resumed is written one step deeper than whatever
resumed it, which for a loop the script runs puts those calls at the depth they would have
under the generator's own line, with the loop's lines between them.
`mark_for_rollback_on_error` is a context manager written as a generator: its line stands
where it was entered, and the lines that follow at its depth ran inside it.

Python's `list()` asks its argument for a length after it has taken an iterator from it.
So where Django's own code makes a list of a queryset, a line `QuerySet.__len__` follows
`QuerySet.__iter__` under the call that made the list, and that second line is Python's
doing; the script's own lines of Python loop over a queryset instead where calls are
written down.

Some calls are made so often that they are written down only under a condition.
`QuerySet._fetch_all` is called by iteration, `len()` and `bool()` of a queryset and by a
few of its methods. In the three blocks about evaluation every call of it is written, with
what it found; in the others it is written only where it has something to do, which is
where there is no result cache yet or there are prefetch lookups not yet followed.
`Query.get_compiler` is written in those three blocks only, and there only where a compiler
is asked for by a database's alias, not where a query inside another is given its compiler.
`get_related_populators` is written where there are related classes to populate.

A line that begins `SQL` is a statement as Django handed it to its own cursor, with its
parameters where it has any: the placeholders are Django's `%s`, which SQLite's backend
rewrites before the driver sees them. `BEGIN` and `SAVEPOINT` pass through that cursor on
SQLite and a commit does not, so a commit is the line `BaseDatabaseWrapper.commit`, which
is written among calls and not under a question or under a line of Python run without its
calls: there a `BEGIN` stands with nothing after it to close it. `Atomic.__enter__` says in
parentheses when its `Atomic` was made with `savepoint=False`; whether a transaction is
begun or a savepoint made is in the statement under it. A savepoint's name holds the number
of the thread that made it, which is written `(the thread)`. A line `the cursor's
fetchmany(100)  ->  4 rows` is a call of the driver's cursor through Django's wrapper. A
line that begins `the loop's body` is written by the loop the line of Python above it runs,
and a line that begins `the router is asked` by a router the script installs for one block,
which answers None to every question.

A second kind of block puts one question to a running Django on each line: the text before
`->` is the expression that was evaluated and what follows is the repr of its value, and a
statement the question sent stands under it, as does a warning it set off, on a line that
begins `warns`. Where a question raised, the exception's name
and message stand in place of a value; for three questions whose message is the driver's,
or long, the name alone. The third kind writes down what an object
holds, a thing to a line.

A queryset is written by its class, its model and its result cache: `a SailorQuerySet of
Sailor, no result cache`, `a QuerySet of Ship, a result cache of 2`. An instance is written
as its repr, `<Ship: Petrel>`, and the script stops if putting a call into words ever sends
a statement, so that no `SQL` line is this script's own doing. A list of more than six
things is written as its first two and how many more there are, and the instances handed to
`bulk_create` by their number and class, `[3 of LogEntry]`. In a question, `mode(...)` is
the fetch mode of each thing by its name and `deferred(queryset)` the queryset's
`query.deferred_loading` with its set of names sorted.

Nothing is written that differs between one run and the next on the same Python and the
same SQLite: no address in memory, no path on disk, no time read from the machine's clock
(`django.utils.timezone.now` is replaced by a function that returns 10 April 2026, 09:00
UTC). SQLite's limit on the parameters of one statement differs between builds, so no line
says it, but in the two blocks whose titles say so, where the script has lowered it to 10
for this connection with the driver's `setlimit`. A few messages are Python's own wording
(`cannot unpack non-iterable int object`, `object has no attribute 'delete'`), and the
script needs Python 3.14, where a frame knows its generator.

What ran is SQLite's part as well as Django's. These are this backend's, and another's
would differ: `INSERT OR IGNORE`, `ON CONFLICT`, `RETURNING`, and a database default
written out as its value among the rows of an insert, since SQLite has no `DEFAULT` there;
the absence of `FOR UPDATE`; the way `^` between two conditions is written; `LIKE ... ESCAPE`;
`EXPLAIN QUERY PLAN`; `django_date_trunc`, a function Django registers with SQLite; dates
and datetimes among the parameters as text; `0` and `1` for a comparison selected as a
column; the refusal of `DISTINCT ON`; the refusal of an ordering or a limit inside a
compound statement; `Case` with no `Cast` around it in `bulk_update`; the ordinary cursor
that `chunked_cursor` returns; the driver's messages (`UNIQUE constraint failed`) and
`OperationalError` for a statement that cannot be parsed; and the order of rows where a
statement has no `ORDER BY`, which is the choice of SQLite's planner.

In the last block the calls are made on two threads, and each line of a call says which:
the thread the event loop runs on, or another. A line is nested only under earlier lines of
its own thread, and a line of the other thread starts one step in from the line of Python
that is running. So the block shows which thread each call ran on and the order in which
the calls began; it does not show a call on one thread as made by a call on the other. A
coroutine's line is written where its body first runs, and what it returned is not written.

    RECORD_EVERYTHING=django.db.models.query python recordings/querysets.py    every call in the modules with that prefix
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# `harbour` imports from this directory, as it would from a project's. The directory goes last
# on the path and not first, where Python puts a script's own: `http.py` in it has the name of
# a package of the standard library, which Django imports.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != HERE] + [HERE]

import ast  # noqa: E402
import asyncio  # noqa: E402
import atexit  # noqa: E402
import copy  # noqa: E402
import datetime  # noqa: E402
import functools  # noqa: E402
import inspect  # noqa: E402
import json  # noqa: E402
import operator  # noqa: E402
import pickle  # noqa: E402
import shutil  # noqa: E402
import sqlite3  # noqa: E402
import tempfile  # noqa: E402
import re  # noqa: E402
import threading  # noqa: E402
import types  # noqa: E402
import warnings  # noqa: E402
import weakref  # noqa: E402

import django  # noqa: E402
from django.conf import settings  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # the same bytes on every machine
EVERYTHING = tuple(p for p in os.environ.get("RECORD_EVERYTHING", "").split(",") if p)

SCRATCH = tempfile.mkdtemp()
DATABASE = os.path.join(SCRATCH, "harbour.sqlite3")

settings.configure(
    DEBUG=False,
    SECRET_KEY="recording",
    INSTALLED_APPS=["harbour.fleet", "harbour.crew", "harbour.office"],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DATABASE}},
    DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    MEDIA_ROOT=os.path.join(SCRATCH, "media"),
    USE_TZ=True,
    TIME_ZONE="UTC",
)

LINES = []


class Stacks:
    """The watched frames open at this moment, which give the depth of the next line: one
    stack to a thread, so that a line is nested only under earlier lines of its own thread. A
    thread other than the script's starts one step in, under the line of Python that is running."""

    def __init__(self):
        self.by = {}
        self.first = threading.get_ident()

    def mine(self) -> list:
        return self.by.setdefault(threading.get_ident(), [])

    def append(self, frame) -> None:
        self.mine().append(frame)

    def pop(self):
        return self.mine().pop()

    def __getitem__(self, index):
        return self.mine()[index]

    def __len__(self) -> int:
        return len(self.mine()) + (0 if threading.get_ident() == self.first else 1)

    def __bool__(self) -> bool:
        return bool(self.mine())

    def clear(self) -> None:
        self.by.clear()


STACK = Stacks()
AT = {}  # where in LINES the line of each open watched call is, by the frame
SEEN = {}  # generator and coroutine frames already written down, each with its generator: such a frame is entered more than once
PENDING = []  # the watched call that has just returned: (frame, depth, its line, what is to be said of its value)
RAISED = []  # exceptions already written down, at the innermost watched call they left
RESUMABLE = 0x20 | 0x80 | 0x200  # a generator, a coroutine, an asynchronous generator


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


def show(title: str) -> None:
    flush()
    print(title)
    for line in LINES:
        print("    " + line)
    print()
    reset()


# ---------------------------------------------------------------------------------------------
# The recorder.

RULES = {}  # the set in force
LABELLING = False  # whether a call is being put into words at this moment: a statement sent to the database then is a fault of this script's
LISTENING = False  # whether a statement sent to the database is written down: inside a recorded block or a question
AFTER = {}  # (module, qualname) -> what to say of the value a call returned


def plain(frame) -> str:
    return short(frame.f_code.co_qualname)


def short(qualname: str) -> str:
    """A qualified name without the functions it is defined inside: RelatedManager.get_queryset."""
    return qualname.rsplit("<locals>.", 1)[-1]


def find(module: str, qualname: str):
    label = RULES.get((module, qualname))
    if label is not None:
        return label
    if EVERYTHING and module.startswith(EVERYTHING):
        return plain
    return None


def profile(frame, event, arg):
    code = frame.f_code
    if code is UNWINDING:
        return
    if event == "call":
        label = find(frame.f_globals.get("__name__", ""), code.co_qualname)
        if label is None:
            return
        if code.co_flags & RESUMABLE:  # every resumption is a call event
            # A frame's address is used again once its generator is gone, so the frame is known
            # by its generator, weakly held: a new generator at an old address is a new call.
            known = SEEN.get(id(frame))
            if known is not None and known() is frame.f_generator:
                STACK.append(frame)
                return
        flush()  # what the call before this one returned is said first
        global LABELLING
        LABELLING = True
        try:
            text = label(frame)
        except Exception:  # a fault of this script's: Python would drop the hook and carry on, and the recording would be short
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
            # The value is put into words now, as it is returned: an object its caller goes on to
            # change would otherwise be described as the caller left it.
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
                LINES[at] += f"  raises {type(exception).__name__}"
            else:
                LINES.append("  " * depth + f"raises {type(exception).__name__}")


UNWINDING = unwinding.__code__
MONITOR = sys.monitoring.PROFILER_ID
sys.monitoring.use_tool_id(MONITOR, "recordings/querysets.py")
sys.monitoring.register_callback(MONITOR, sys.monitoring.events.PY_UNWIND, unwinding)
sys.monitoring.set_events(MONITOR, sys.monitoring.events.PY_UNWIND)


class recorded:
    """`with recorded(RULES):` writes down, of what runs in the block, the calls those
    rules name."""

    def __init__(self, rules: dict):
        self.rules = rules

    def __enter__(self):
        global RULES, LISTENING
        RULES = self.rules
        LISTENING = True
        sys.setprofile(profile)

    def __exit__(self, *exc):
        global LISTENING
        sys.setprofile(None)
        LISTENING = False
        flush()


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
        raise SystemExit(f"recordings/querysets.py: this Python reports an exception leaving a function otherwise than expected: {LINES!r}")
    reset()
    RULES = {}


self_test()

ASKING = {}  # the names a statement or a question may use, and the names a statement binds


class Said(str):
    """An answer already put into words, to be written as it is and not as a string's repr."""

    __repr__ = str.__str__


def ask(expression: str, brief_: bool = False) -> None:
    """One question and its answer, on one line. The question is evaluated as it is written
    down, so the line cannot say one thing and the script do another. A brief answer names an
    exception and leaves out its message."""
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
            said = value if isinstance(value, Said) else repr(value)
        except Exception as raised:
            said = f"raises {type(raised).__name__}" + ("" if brief_ else f": {raised}")
    for warning in warned:  # a warning the question set off stands under it, like a statement it sent
        LINES.append("  " * len(STACK) + f"warns {warning.category.__name__}: {warning.message}")
    LISTENING = listening
    # A query made while the question was answered stands under the question, not above it.
    LINES[before:] = ["  " * len(STACK) + f"{expression}  ->  {said}", *("  " + line for line in LINES[before:])]
    sys.setprofile(watching)


def do(statement: str) -> None:
    """A statement of Python, written down and then run, with what it sets going written
    under it. The line is the text that runs, so it cannot say one thing and the script do
    another. A name the statement binds can be used by the statements and questions after it."""
    note(statement)
    STACK.append(None)
    try:
        exec(statement, ASKING)
    except Exception as raised:
        flush()
        LINES.append("  " * (len(STACK) - 1) + f"raises {type(raised).__name__}: {raised}")
    finally:
        flush()
        STACK.pop()


def quietly(statement: str) -> None:
    """A line of Python that is written down and run with none of its calls recorded: under it
    stand only the statements it sent to the database, so that a line of Python with no `SQL`
    line under it sent none."""
    global LISTENING
    watching, listening = sys.getprofile(), LISTENING
    sys.setprofile(None)
    note(statement)
    STACK.append(None)
    LISTENING = True
    try:
        exec(statement, ASKING)
    finally:
        flush()
        STACK.pop()
        LISTENING = listening
        sys.setprofile(watching)


# The calls that open and close a transaction, for every set of rules that writes statements down.
TRANSACTION = {
    # An Atomic made with savepoint=False says so; one made with the default does not. Whether a
    # savepoint is made at all is in the statement under the line: BEGIN where no transaction
    # was open, SAVEPOINT where one was.
    ("django.db.transaction", "Atomic.__enter__"): lambda f: "Atomic.__enter__" + ("" if f.f_locals["self"].savepoint else "  (an Atomic made with savepoint=False)"),
    ("django.db.transaction", "Atomic.__exit__"):
        lambda f: "Atomic.__exit__" + ("" if f.f_locals["exc_type"] is None else f"  (with {f.f_locals['exc_type'].__name__})"),
    ("django.db.transaction", "mark_for_rollback_on_error"): lambda f: "mark_for_rollback_on_error  (a context manager, entered here)",
    ("django.db.backends.base.base", "BaseDatabaseWrapper.commit"): plain,
    ("django.db.backends.base.base", "BaseDatabaseWrapper.rollback"): plain,
    ("django.db.backends.base.base", "BaseDatabaseWrapper.savepoint_commit"): plain,
    ("django.db.backends.base.base", "BaseDatabaseWrapper.savepoint_rollback"): plain,
}

# ---------------------------------------------------------------------------------------------
# Django is set up, the tables are made and the first rows put in them, none of it recorded.

django.setup()

from asgiref.sync import sync_to_async  # noqa: E402
from django.apps import apps  # noqa: E402
from django.db import connection, models, router, transaction  # noqa: E402
from django.db.models import Count, Exists, F, FilteredRelation, Max, Prefetch, Q, QuerySet, Sum, Value, prefetch_related_objects  # noqa: E402
from django.db.models.constants import OnConflict  # noqa: E402
from django.db.models.expressions import DatabaseDefault  # noqa: E402
from django.db.models.fetch_modes import FetchMode  # noqa: E402
from django.db.models.fields.reverse_related import ForeignObjectRel  # noqa: E402
from django.db.models.functions import Lower  # noqa: E402
from django.db.models.lookups import Lookup  # noqa: E402
from django.db.models.query import EmptyQuerySet, RawQuerySet  # noqa: E402
from django.db.models.sql import Query  # noqa: E402
from django.utils import timezone  # noqa: E402

from harbour.crew.models import Officer, Rank, Sailor, SailorQuerySet, Veteran  # noqa: E402
from harbour.fleet.models import Port, Ship, Voyage  # noqa: E402
from harbour.office.models import Berth, Licence, LogEntry, Logbook, Manifest  # noqa: E402

PIN = json.load(open(os.path.join(os.path.dirname(HERE), "pin.json"), encoding="utf-8"))["trees"]["django"]["commit"]
print(f"Django {django.VERSION[0]}.{django.VERSION[1]} in development, at the commit {PIN}, and the project harbour:\n"
      "INSTALLED_APPS = ['harbour.fleet', 'harbour.crew', 'harbour.office'], DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField',\n"
      "USE_TZ = True, TIME_ZONE = 'UTC', no DATABASE_ROUTERS, a SQLite database, and the clock at 2026-04-10 09:00 UTC\n")

NOW = datetime.datetime(2026, 4, 10, 9, 0, tzinfo=datetime.UTC)
timezone.now = lambda: NOW  # the recording's clock: see the docstring


def tidy() -> None:
    connection.close()
    shutil.rmtree(SCRATCH, ignore_errors=True)


atexit.register(tidy)


def query(execute, sql, params, many, context):
    if LABELLING:
        sys.stderr.write(f"recordings/querysets.py: putting a call into words sent a statement to the database: {sql}\n")
        os._exit(1)
    if LISTENING:
        # A savepoint's name holds the number of the thread it was made on: s12345_x1.
        said = re.sub(r'"s\d+_x(\d+)"', r'"s(the thread)_x\1"', sql)
        note(f"SQL {said} with params {params!r}" if params else f"SQL {said}")
    return execute(sql, params, many, context)


connection.execute_wrappers.append(query)

with connection.schema_editor() as editor:
    for model in apps.get_models():
        if not model._meta.proxy:
            editor.create_model(model)

bergen = Port.objects.create(name="Bergen", country="Norway")
leith = Port.objects.create(name="Leith", country="Scotland")
lisbon = Port.objects.create(name="Lisbon", country="Portugal")
petrel = Ship.objects.create(name="Petrel", tonnage=480, home=bergen)
gannet = Ship.objects.create(name="Gannet", tonnage=1200, home=leith)
ada = Sailor.objects.create(name="Ada", ship=petrel)
bram = Sailor.objects.create(name="Bram", ship=petrel)
cora = Officer.objects.create(name="Cora", ship=gannet, rank=Rank.MASTER)
dag = Sailor.objects.create(name="Dag", ship=gannet)
# auto_now_add gives every row the recording's moment; two sailors signed on long before it.
Sailor.objects.filter(name__in=["Ada", "Cora"]).update(signed_on=datetime.datetime(2011, 6, 1, 8, 0, tzinfo=datetime.UTC))
gannet.captain = cora
gannet.save()
spring = Voyage.objects.create(ship=petrel, sailed=datetime.date(2026, 3, 2))
spring.calls.add(leith, lisbon)
autumn = Voyage.objects.create(ship=gannet, sailed=datetime.date(2025, 10, 6))
autumn.calls.add(bergen)
Licence.objects.create(sailor=ada, port=bergen, granted=datetime.date(2019, 5, 1))
Berth.objects.create(port=bergen, number=1, metres=90)
Berth.objects.create(port=bergen, number=2, metres=140)
Logbook.objects.bulk_create([Logbook(title=f"Log {n}") for n in range(1, 26)])

print("The rows the recording begins with")
print("    Port: " + ", ".join(f"{p.pk} {p.name} ({p.country})" for p in Port.objects.order_by("pk")))
print("    Ship: " + ", ".join(f"{s.pk} {s.name} ({s.tonnage} tons, home {s.home.name}, captain {s.captain.name if s.captain else 'none'})" for s in Ship.objects.order_by("pk")))
print("    Sailor: " + ", ".join(f"{s.pk} {s.name} (ship {s.ship.name}, signed on {s.signed_on:%Y})" for s in Sailor.objects.order_by("pk")))
print("    Officer: " + ", ".join(f"{o.pk} {o.name} ({o.rank})" for o in Officer.objects.order_by("pk")))
print("    Voyage: " + ", ".join(f"{v.pk} (ship {v.ship.name}, sailed {v.sailed}, calls at {' and '.join(p.name for p in v.calls.order_by('pk'))})" for v in Voyage.objects.order_by("pk")))
print("    Licence: " + ", ".join(f"{x.pk} ({x.sailor.name} into {x.port.name})" for x in Licence.objects.order_by("pk")))
print("    Berth: " + ", ".join(f"{b.port.name} {b.number} ({b.metres} m)" for b in Berth.objects.order_by("port_id", "number")))
books = list(Logbook.objects.order_by("pk"))
print(f"    Logbook: {len(books)}, from {books[0].pk} {books[0].title} to {books[-1].pk} {books[-1].title}")
print()

ASKING.update(
    models=models, connection=connection, transaction=transaction, datetime=datetime, pickle=pickle, copy=copy,
    Q=Q, F=F, Count=Count, Sum=Sum, Max=Max, Lower=Lower, Prefetch=Prefetch, FilteredRelation=FilteredRelation, Exists=Exists, Value=Value,
    QuerySet=QuerySet, EmptyQuerySet=EmptyQuerySet, RawQuerySet=RawQuerySet, Query=Query, prefetch_related_objects=prefetch_related_objects,
    Port=Port, Ship=Ship, Voyage=Voyage, Sailor=Sailor, Officer=Officer, Veteran=Veteran, Rank=Rank, SailorQuerySet=SailorQuerySet,
    Licence=Licence, Manifest=Manifest, Berth=Berth, Logbook=Logbook, LogEntry=LogEntry,
    bergen=bergen, leith=leith, lisbon=lisbon, petrel=petrel, gannet=gannet, ada=ada, bram=bram, cora=cora, dag=dag, spring=spring, autumn=autumn,
)

# ---------------------------------------------------------------------------------------------
# How values and calls are said.


def a(name: str) -> str:
    """A thing by its class's name, with the article the name is read with."""
    return ("an " if name[0] in "AEIOU" and not name.startswith("One") else "a ") + name


def of_field(field) -> str:
    """A field by the class it is on and its name: Ship.home."""
    model = getattr(field, "model", None)
    return f"{model.__name__}.{field.name}" if inspect.isclass(model) else f"an unbound {type(field).__name__}"


def queryset_said(queryset) -> str:
    """A queryset by its class and its model, without sending its query: asking for its repr would."""
    fetched = queryset._result_cache
    return f"{a(type(queryset).__name__)} of {queryset.model.__name__}, " + ("no result cache" if fetched is None else f"a result cache of {len(fetched)}")


def instance_said(instance) -> str:
    """An instance as its repr, where writing that reads nothing from the database. Ship's,
    Port's and Sailor's __str__ read the name: an instance with that field deferred is written
    by its class and its key instead, so that no line of the recording is a query this script
    caused."""
    if hasattr(type(instance), "name") and "name" not in vars(instance):
        return f"<{type(instance).__name__}: pk={instance.pk!r}>"
    return repr(instance)


def prefetch_said(lookup) -> str:
    said = repr(lookup.prefetch_through)
    if lookup.queryset is not None:
        said += f", queryset={queryset_said(lookup.queryset)}"
    if lookup.to_attr:
        said += f", to_attr={lookup.to_attr!r}"
    return f"Prefetch({said})"


def brief(value) -> str:
    """A value in few words."""
    if isinstance(value, models.Model):
        return instance_said(value)
    if isinstance(value, (QuerySet, RawQuerySet)):
        return queryset_said(value)
    if isinstance(value, Query):
        return f"{a(type(value).__name__)} of {value.model.__name__}" if value.model else a(type(value).__name__)
    if isinstance(value, models.Field):
        return of_field(value)
    if isinstance(value, ForeignObjectRel):
        return f"the rel of {of_field(value.field)}"
    if isinstance(value, Prefetch):
        return prefetch_said(value)
    if isinstance(value, DatabaseDefault):
        return "a DatabaseDefault"
    if isinstance(value, FetchMode):
        return value.__reduce__()
    if isinstance(value, OnConflict):
        return str(value)
    if isinstance(value, (datetime.date, datetime.timedelta)):  # as its repr, said shortly: datetime(2026, 4, 10, 9, 0, tzinfo=UTC)
        return repr(value).replace("datetime.timezone.utc", "UTC").replace("datetime.", "")
    if inspect.isclass(value):
        return value.__name__
    if isinstance(value, types.MethodType):
        return f"the method {short(value.__qualname__)} of {brief(value.__self__)}"
    if isinstance(value, (types.FunctionType, types.BuiltinFunctionType)):
        return f"the function {short(value.__qualname__)}"
    if isinstance(value, functools.partial):
        return f"a partial of {brief(value.func)}"
    if isinstance(value, (operator.attrgetter, operator.itemgetter)):
        return repr(value).replace("operator.", "")
    if isinstance(value, list):
        return "[" + ", ".join(several(value)) + "]"
    if isinstance(value, tuple):
        return "(" + ", ".join(several(value)) + ("," if len(value) == 1 else "") + ")"
    if isinstance(value, (set, frozenset)):
        return "{" + ", ".join(sorted(brief(v) for v in value)) + "}" if value else "set()"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k!r}: {brief(v)}" for k, v in value.items()) + "}"
    if isinstance(value, (str, bytes, int, float, bool, type(None), Q, slice, range)):
        return repr(value)
    return a(type(value).__name__)


def counted(instances) -> str:
    """Instances that are too many, or too much alike, to write out: by their number and class."""
    kinds = sorted({type(i).__name__ for i in instances})
    return f"[{len(instances)} of {' and '.join(kinds)}]" if instances else "[]"


def mode(*things) -> Said:
    """The fetch mode of each thing, a queryset's or an instance's, by its name."""
    return Said("(" + ", ".join((t._state.fetch_mode if isinstance(t, models.Model) else t._fetch_mode).__reduce__() for t in things) + ")")


def several(values) -> list:
    """The things of a list in few words: all of them, or of more than six the first two and their number."""
    if len(values) > 6:
        return [brief(values[0]), brief(values[1]), f"and {len(values) - 2} more"]
    return [brief(v) for v in values]


SIGNATURES = {}


def defaults(frame) -> dict:
    """The defaults of the function a frame is running, by parameter."""
    code = frame.f_code
    if code not in SIGNATURES:
        found = {}
        try:
            thing = sys.modules[frame.f_globals["__name__"]]
            for part in code.co_qualname.split("."):
                thing = inspect.getattr_static(thing, part)
            thing = getattr(thing, "__func__", thing)
            found = {n: p.default for n, p in inspect.signature(thing).parameters.items() if p.default is not p.empty}
        except Exception:  # a function defined inside another: nothing is known of its defaults
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
    said += named([n for n in names if n not in positional])  # the keyword-only parameters
    if info.keywords:
        said += [f"{k}={brief(v)}" for k, v in frame.f_locals[info.keywords].items()]
    return ", ".join(said)


def generic(frame) -> str:
    said = given(frame)
    return f"{short(frame.f_code.co_qualname)}({said})" if said else short(frame.f_code.co_qualname)


def without(*leave_out):
    """The generic label, with the parameters named here passed over."""
    def said(frame) -> str:
        text = given(frame, *leave_out)
        return f"{short(frame.f_code.co_qualname)}({text})" if text else short(frame.f_code.co_qualname)
    return said


def watch(module: str, *qualnames, label=None) -> dict:
    return {(module, name): label or generic for name in qualnames}


def value_after(frame, value) -> str:
    return brief(value)


def says(module: str, *qualnames, how=value_after) -> None:
    for name in qualnames:
        AFTER[(module, name)] = how


QS = "django.db.models.query"
SQ = "django.db.models.sql.query"
CO = "django.db.models.sql.compiler"
MANAGER = "django.db.models.manager"
DESCRIPTORS = "django.db.models.fields.related_descriptors"
REVERSE = "create_reverse_many_to_one_manager.<locals>.RelatedManager."
MANY = "create_forward_many_to_many_manager.<locals>.ManyRelatedManager."


def chained(frame, value) -> str:
    return "the queryset itself" if value is frame.f_locals["self"] else f"a new {type(value).__name__}"


def from_db_called(frame) -> str:
    f = frame.f_locals
    mode = f", fetch_mode={brief(f['fetch_mode'])}" if f.get("fetch_mode") is not None else ""
    return f"Model.from_db({f['db']!r}, {list(f['field_names'])!r}, {brief(f['values'])}{mode})  ({f['cls'].__name__})"


def fetch_called(frame) -> str:
    f = frame.f_locals
    return f"the cursor's {f['func'].__name__}({', '.join(repr(v) for v in f['args'])})"


def fetch_returned(frame, value) -> str:
    if isinstance(value, list):
        return f"{len(value)} rows" if len(value) != 1 else "1 row"
    return "no row" if value is None else "a row"


def execute_called(frame) -> str:
    """SQLCompiler.execute_sql by the rule for every call: a parameter left at its default is passed over."""
    return generic(frame)


def manager_called(frame) -> str:
    return f"manager_method  (the method a base of the manager's class was given under the name {frame.f_locals['name']!r})"


MANAGERS = {
    (MANAGER, "BaseManager._get_queryset_methods.<locals>.create_method.<locals>.manager_method"): manager_called,
    (MANAGER, "BaseManager.get_queryset"): plain,
}
says(MANAGER, "BaseManager.get_queryset")

# What reads rows: the compiler's two calls, the driver's cursor, and the instance made of each.
ROWS = {
    (CO, "SQLCompiler.execute_sql"): execute_called,
    (CO, "SQLCompiler.results_iter"): plain,
    ("django.db.utils", "DatabaseErrorWrapper.__call__.<locals>.inner"): fetch_called,
    ("django.db.models.base", "Model.from_db"): from_db_called,
}
says("django.db.utils", "DatabaseErrorWrapper.__call__.<locals>.inner", how=fetch_returned)

says(QS, "QuerySet._chain", how=chained)
says(QS, "QuerySet.get", "QuerySet.count", "QuerySet.exists", "QuerySet.contains", "QuerySet.first", "QuerySet.last",
     "QuerySet.__len__", "QuerySet.__bool__", "QuerySet.__getitem__", "QuerySet.create", "QuerySet.update", "QuerySet._update",
     "QuerySet.delete", "QuerySet._raw_delete", "QuerySet.bulk_update", "QuerySet.in_bulk", "QuerySet.aggregate",
     "QuerySet.get_or_create", "QuerySet.update_or_create", "QuerySet._check_bulk_create_options", "QuerySet._insert",
     "QuerySet._extract_model_params", "QuerySet.iterator", "QuerySet.raw", "QuerySet.union", "QuerySet._combinator_query",
     "get_prefetcher", "Prefetch.get_current_querysets", "QuerySet.none")
says(SQ, "Query.get_count", "Query.has_results")


def fetching(frame):
    """QuerySet._fetch_all, written down only where it has something to do: there is no
    result cache yet, or there are prefetch lookups that have not been followed."""
    queryset = frame.f_locals["self"]
    if queryset._result_cache is None or (queryset._prefetch_related_lookups and not queryset._prefetch_done):
        return "QuerySet._fetch_all"
    return None


def fetching_always(frame) -> str:
    """QuerySet._fetch_all at every call, with what it finds."""
    return "QuerySet._fetch_all  (" + ("there is no result cache" if frame.f_locals["self"]._result_cache is None else "the result cache is filled") + ")"


FETCHING = {(QS, "QuerySet._fetch_all"): fetching}


def seen(thing) -> None:
    """What a loop the script runs calls with each thing the loop is given."""
    note(f"the loop's body runs with {brief(thing)}")


def deferred(queryset) -> tuple:
    """A queryset's query.deferred_loading, a set of names and a flag, with the names sorted: a set's own order differs from run to run."""
    names, defer = queryset.query.deferred_loading
    return sorted(names), defer


ASKING.update(seen=seen, mode=mode, deferred=deferred, asyncio=asyncio)

# ---------------------------------------------------------------------------------------------
# What a queryset holds, how one is built, and what a clone shares.

for name, value in vars(Ship.objects.all()).items():
    note(f"{name}: {brief(value)}")
show("What a new queryset holds: vars(Ship.objects.all()), an attribute to a line")

BUILDING = MANAGERS | watch(
    QS, "QuerySet.filter", "QuerySet.exclude", "QuerySet._filter_or_exclude", "QuerySet._filter_or_exclude_inplace",
    "QuerySet.order_by", "QuerySet.all", "QuerySet._chain", "QuerySet._clone",
) | watch(SQ, "Query.chain", "Query.clone", "Query.add_q", "Query.clear_ordering", "Query.add_ordering")

with recorded(BUILDING):
    do("named = Sailor.objects.filter(ship=petrel).order_by('name')")
ask("named._result_cache, named.ordered, named.db")
ask("str(named.query)")
show("A queryset is built: each method returns a clone, and no statement is sent")

quietly("again = named.all()")
ask("again is named, again.query is named.query, again.query.where is named.query.where, again.query.alias_map is named.query.alias_map")
ask("again.query.order_by is named.query.order_by, again.model is named.model, again._fetch_mode is named._fetch_mode")
ask("again._known_related_objects is named._known_related_objects")
ask("named._hints, again._hints is named._hints")
quietly("crew = petrel.crew.all()")
ask("crew._hints, crew.all()._hints is crew._hints")
quietly("list(named)")
ask("named._result_cache, named.all()._result_cache, named.filter(name='Ada')._result_cache")
show("What a clone shares with the queryset it was made from")

# ---------------------------------------------------------------------------------------------
# A related manager's queryset: one object changed in place, a filter that waits, and a sticky filter.

RELATED = watch(
    DESCRIPTORS, REVERSE + "get_queryset", REVERSE + "_apply_rel_filters", MANY + "get_queryset", MANY + "_apply_rel_filters",
) | MANAGERS | watch(
    QS, "QuerySet._avoid_cloning", "PreventQuerySetCloning.__enter__", "PreventQuerySetCloning.__exit__", "QuerySet._add_hints",
    "QuerySet.using", "QuerySet.filter", "QuerySet._filter_or_exclude", "QuerySet._filter_or_exclude_inplace", "QuerySet._chain",
    "QuerySet._clone", "QuerySet._next_is_sticky", "QuerySet.all",
) | watch(SQ, "Query.chain", "Query.add_q")
RELATED[(MANAGER, "BaseManager.get_queryset")] = lambda f: f"BaseManager.get_queryset  ({a(type(f.f_locals['self']).__name__)} for {brief(f.f_locals['self'].instance)})"

with recorded(RELATED):
    do("crew = petrel.crew.all()")
    ask("crew._deferred_filter, bool(crew._query.where), crew._hints, crew._known_related_objects")
    do("crew.query")
    ask("crew._deferred_filter, bool(crew._query.where)")
show("A related manager's queryset: one queryset changed in place, and a filter that waits until the query is read")

with recorded(RELATED):
    do("ports = spring.calls.all()")
    ask("ports._sticky_filter, ports._query.filter_is_sticky, ports._deferred_filter")
    do("in_scotland = ports.filter(country='Scotland')")
    ask("ports._query.filter_is_sticky, in_scotland.query.filter_is_sticky, sorted(in_scotland.query.used_aliases)")
show("A many-to-many manager's queryset: the next filter is sticky")

ask("list(spring.calls.filter(voyage__sailed__year=2026))")
ask("list(Port.objects.filter(voyage=spring).filter(voyage__sailed__year=2026))")
ask("list(Port.objects.filter(voyage=spring, voyage__sailed__year=2026))")
ask("list(spring.calls.order_by('name').filter(voyage__sailed__year=2026))")
show("What the sticky filter changes: the joins of four querysets that, from these rows, return the same ports")

quietly("autumn.calls.add(leith)")
ask("list(spring.calls.filter(voyage__sailed__year=2025))")
ask("list(Port.objects.filter(voyage=spring).filter(voyage__sailed__year=2025))")
ask("list(spring.calls.order_by('name').filter(voyage__sailed__year=2025))")
quietly("autumn.calls.remove(leith)")
show("With Leith put on the autumn voyage as well, which sailed in 2025: the querysets that join once and those that join twice answer differently")

# ---------------------------------------------------------------------------------------------
# Evaluation.

EVALUATING = ROWS | watch(
    QS, "QuerySet.__iter__", "QuerySet.__len__", "QuerySet.__bool__", "QuerySet.__getitem__", "QuerySet.count", "QuerySet.exists",
    "QuerySet.contains", "ModelIterable.__iter__", "QuerySet._prefetch_related_objects", "QuerySet.resolve_expression",
) | watch(SQ, "Query.get_count", "Query.has_results", "Query.set_limits") | {
    (QS, "QuerySet._fetch_all"): fetching_always,
    # Query.get_compiler where it is asked for a compiler by a database's alias: a query inside
    # another is given its compiler by the connection, further in, and that call is passed over.
    (SQ, "Query.get_compiler"): lambda f: generic(f) if f.f_locals["using"] is not None else None,
}
EVALUATING[(QS, "QuerySet.resolve_expression")] = plain

quietly("named = Sailor.objects.filter(ship=petrel).order_by('name')")
with recorded(EVALUATING):
    do("for sailor in named: seen(sailor)")
    do("len(named)")
    do("bool(named)")
    do("named[0]")
    do("named.count()")
    do("named.exists()")
    do("named.contains(dag)")
    do("for hand in named: seen(hand)")
show("The first use fetches every row, and each of these later uses reads the result cache")

quietly("fresh = Sailor.objects.filter(ship=petrel).order_by('name')")
with recorded(EVALUATING):
    do("fresh.count()")
    do("fresh.exists()")
    do("fresh.contains(dag)")
    do("fresh[0]")
    do("fresh[1:3]")
    do("fresh[0:4:2]")
ask("fresh._result_cache")
show("A queryset that has not been evaluated answers each of these but the plain slice with a statement of its own, and keeps nothing")

quietly("heavy = Ship.objects.filter(tonnage__gt=1000)")
with recorded(EVALUATING):
    do("on_heavy = Sailor.objects.filter(ship__in=heavy)")
    ask("heavy._result_cache, on_heavy._result_cache")
    do("for sailor in on_heavy: seen(sailor)")
    ask("heavy._result_cache")
show("A queryset given as a value to another's filter is not evaluated: its query goes into the other's statement")

ask("repr(Port.objects.all())")
ask("repr(Logbook.objects.order_by('id')).count('<Logbook'), repr(Logbook.objects.order_by('id'))[-45:]")
ask("len(pickle.loads(pickle.dumps(Port.objects.all()))._result_cache)")
ask("sorted(k for k in Port.objects.all().__getstate__() if not k.startswith('_')), [k for k in Port.objects.all().__getstate__() if 'version' in k]")
quietly("ports = Port.objects.all(); list(ports)")
ask("len(ports._result_cache), copy.deepcopy(ports)._result_cache, copy.copy(ports)._result_cache is ports._result_cache")
quietly("unread = Port.objects.all()")
ask("len(copy.copy(unread)._result_cache), len(unread._result_cache)")
ask("Port.objects.all() == Port.objects.all(), ports == ports")

show("Asked of repr, pickle and copy")

quietly("everyone = Sailor.objects.order_by('id')")
ask("everyone[1:3].query.low_mark, everyone[1:3].query.high_mark")
ask("everyone[5:].query.low_mark, everyone[5:].query.high_mark, everyone[5:][2:4].query.low_mark, everyone[5:][2:4].query.high_mark")
ask("everyone[:3][:10].query.high_mark, everyone[2:6][1:].query.low_mark")
ask("type(everyone[1:3]).__name__, type(everyone[0:4:2]).__name__")
ask("everyone[-1]")
ask("everyone[:-1]")
ask("everyone['id']")
ask("everyone[9]")
ask("isinstance(everyone[2:2], EmptyQuerySet), list(everyone[2:2])")
ask("everyone[1:3].filter(name='Bram')")
ask("everyone[1:3].order_by('name')")
ask("everyone[1:3].reverse()")
ask("everyone[1:3].distinct()")
ask("everyone[1:3].update(name='x')")
ask("everyone[1:3].delete()")
ask("everyone[1:3].in_bulk()")
ask("everyone[1:3].latest('signed_on')")
ask("list(everyone[1:3].values_list('name', flat=True)), everyone[1:3].count(), everyone[1:3].exists()")
show("Slices: one question to a line")

ITERATING = ROWS | watch(QS, "QuerySet.iterator", "QuerySet._iterator", "ModelIterable.__iter__", "QuerySet.__iter__") | watch(
    "django.db.backends.base.base", "BaseDatabaseWrapper.chunked_cursor", "BaseDatabaseWrapper.cursor") | FETCHING

quietly("everyone = Sailor.objects.order_by('id')")
with recorded(ITERATING):
    do("for sailor in everyone.iterator(chunk_size=3): seen(sailor)")
    ask("everyone._result_cache")
show("iterator: rows are read from the cursor a chunk at a time, and each becomes an instance as the loop asks for it")

with recorded(ITERATING):
    do("for sailor in everyone: seen(sailor)")
    ask("len(everyone._result_cache)")
show("The same loop over the queryset itself: every row is read and every instance made before the loop sees the first")

ask("next(everyone.iterator(chunk_size=0))")
ask("connection.settings_dict.get('DISABLE_SERVER_SIDE_CURSORS'), connection.features.can_use_chunked_reads")
show("Asked of iterator")

# ---------------------------------------------------------------------------------------------
# The methods that run a statement at once.

GETTING = ROWS | watch(
    QS, "QuerySet.get", "QuerySet.filter", "QuerySet.order_by", "QuerySet.__len__", "QuerySet._fetch_all", "ModelIterable.__iter__",
    "QuerySet.first", "QuerySet.last", "QuerySet.earliest", "QuerySet.latest", "QuerySet._earliest", "QuerySet.reverse",
    "QuerySet.__getitem__", "QuerySet.__iter__",
) | watch(SQ, "Query.set_limits", "Query.clear_ordering", "Query.add_ordering") | FETCHING

with recorded(GETTING):
    do("Ship.objects.get(name='Petrel')")
show("get: the ordering is dropped, at most twenty-one rows are asked for, and the clone is evaluated")

ask("Ship.objects.get(name='Skua')")
ask("Sailor.objects.get(ship=petrel)")
ask("Logbook.objects.get(title__startswith='Log')")
ask("Logbook.objects.get()")
ask("Sailor.objects.order_by('name')[:1].get().name")
ask("Sailor.objects.order_by('name')[:2].get()")
ask("Sailor.objects.distinct().get(name='Ada').name")
show("Asked of get")

with recorded(GETTING):
    do("Sailor.objects.first()")
    do("Ship.objects.first()")
    do("Ship.objects.last()")
    do("Sailor.objects.latest('signed_on', 'name')")
show("first, last and latest")

ask("Sailor.objects.filter(name='Nobody').first(), Sailor.objects.none().last()")
ask("Sailor.objects.order_by('-name').first().name, Sailor.objects.order_by('-name').last().name")
ask("Sailor.objects.earliest()")
ask("Ship._meta.get_latest_by, Sailor.objects.all().ordered, Ship.objects.all().ordered, Ship.objects.order_by().ordered")
ask("Sailor.objects.values('ship').annotate(n=Count('id')).first()")
ask("Sailor.objects.values('ship').annotate(n=Count('id')).order_by('ship').first()")
ask("Ship.objects.all().totally_ordered, Ship.objects.order_by('tonnage').totally_ordered, Ship.objects.order_by('tonnage', 'pk').totally_ordered, Ship.objects.order_by('name', 'home').totally_ordered")
ask("Ship.objects.order_by('name', 'home_id').totally_ordered")
ask("Ship.objects.order_by().first().name, Ship.objects.order_by().last().name")
ask("Sailor.objects.filter(name='Nobody').earliest('signed_on')")
quietly("by_name = Sailor.objects.order_by('name'); list(by_name)")
ask("by_name.first()")
ask("by_name.last()")
show("Asked of first, last, earliest, ordered and totally_ordered")

ask("Ship.objects.aggregate(Sum('tonnage'))")
ask("Ship.objects.aggregate(total=Sum('tonnage'), ships=Count('id'))")
ask("Ship.objects.aggregate(Sum('tonnage') + 1)")
ask("Ship.objects.aggregate('tonnage')")
ask("Ship.objects.count()")
ask("Ship.objects.filter(tonnage__gt=1000).exists()")
ask("Ship.objects.contains(petrel)")
ask("Ship.objects.contains(ada)")
ask("type(cora).__name__, Sailor.objects.contains(cora), Officer.objects.contains(cora)")
ask("Ship.objects.contains('Petrel')")
ask("Ship.objects.contains(Ship(name='Skua'))")
ask("isinstance(Ship.objects.filter(name='Petrel').explain(), str)")
ask("Veteran.objects.contains(ada), Sailor.objects.contains(Veteran.objects.get(pk=1))")
show("aggregate, count, exists, contains and explain: an answer, and no queryset")

ask("Sailor.objects.in_bulk([1, 2])")
ask("Sailor.objects.in_bulk([])")
ask("Port.objects.in_bulk()")
ask("Sailor.objects.in_bulk(['Ada'], field_name='name')")
ask("Manifest.objects.in_bulk(['M-0001'], field_name='serial')")
ask("Sailor.objects.distinct('name').in_bulk(['Ada'], field_name='name')")
ask("Sailor.objects.values('name').in_bulk([1, 2])")
ask("Sailor.objects.values('id', 'name').in_bulk([1, 2])")
ask("Sailor.objects.values_list('name').in_bulk([1, 2])")
ask("Sailor.objects.values_list('name', flat=True).in_bulk([1, 2])")
ask("Sailor.objects.values_list('id', flat=True).in_bulk([1, 2])")
ask("Sailor.objects.values_list('name', named=True).in_bulk([1])")
show("in_bulk: after values or values_list, the field the rows are known by is added to what is selected, and taken out again but from a named tuple")

# ---------------------------------------------------------------------------------------------
# values and values_list; annotate and alias.

VALUES = watch(
    QS, "QuerySet.values", "QuerySet.values_list", "QuerySet._values", "QuerySet._fetch_all", "ValuesIterable.__iter__",
    "ValuesListIterable.__iter__", "NamedValuesListIterable.__iter__", "FlatValuesListIterable.__iter__",
) | watch(SQ, "Query.set_values") | {(CO, "SQLCompiler.results_iter"): generic, (CO, "SQLCompiler.execute_sql"): execute_called} | FETCHING

with recorded(VALUES):
    do("rows = list(Ship.objects.values('name', 'tonnage'))")
    ask("rows")
    do("pairs = list(Ship.objects.values_list('name', 'tonnage'))")
    ask("pairs")
show("values and values_list: the same rows, and another iterable class to make something of them")

ask("[q._iterable_class.__name__ for q in (Ship.objects.all(), Ship.objects.values('name'), Ship.objects.values_list('name'), Ship.objects.values_list('name', flat=True), Ship.objects.values_list('name', named=True))]")
ask("Ship.objects.all()._fields, Ship.objects.values()._fields, Ship.objects.values('name', 'home__country')._fields")
ask("list(Ship.objects.values())")
ask("list(Ship.objects.values_list('name', flat=True))")
ask("list(Ship.objects.values_list('name', 'tonnage', named=True))")
ask("list(Ship.objects.values('name', country=F('home__country')))")
ask("Ship.objects.values_list(Lower('name'), 'name', 'name')._fields")
ask("list(Ship.objects.values_list(Lower('name'), 'name', 'name'))")
ask("Ship.objects.values_list('name', 'tonnage', flat=True)")
ask("Ship.objects.values_list('name', flat=True, named=True)")
ask("Ship.objects.values('name').select_related('home')")
ask("Ship.objects.values('name').defer('tonnage')")
ask("list(Voyage.objects.dates('sailed', 'year'))")
ask("[(len(row), row._fields) for row in Ship.objects.values_list('name', named=True).annotate(hands=Count('crew')).order_by('name')]")
quietly("blank = Ship.objects.all(); blank.query = Ship.objects.values_list('name').query")
ask("blank._iterable_class.__name__, blank._fields, list(blank)")
show("Asked of values and values_list")

ask("[(ship.name, ship.hands) for ship in Ship.objects.annotate(hands=Count('crew')).order_by('name')]")
ask("Ship.objects.annotate(hands=Count('crew')).query.group_by, Ship.objects.values('home').annotate(hands=Count('crew')).query.group_by")
ask("list(Ship.objects.values('home').annotate(hands=Count('crew')).order_by('home'))")
ask("[(ship.name, hasattr(ship, 'hands')) for ship in Ship.objects.alias(hands=Count('crew')).filter(hands__gt=1)]")
ask("Ship.objects.annotate(Count('crew'))[0].crew__count")
ask("Ship.objects.annotate(tonnage=Count('crew'))")
ask("Ship.objects.annotate(Count('crew') + 1)")
ask("Ship.objects.annotate(crew__count=Sum('tonnage'), *[Count('crew')])")
ask("Ship.objects.annotate(hands='crew')")
show("annotate and alias")

# ---------------------------------------------------------------------------------------------
# Rows into instances: select_related, known related objects, deferred fields and fetch modes.


def select_said(compiler) -> None:
    for position, (column, _, alias) in enumerate(compiler.select):
        note(f"select[{position}]: {column.alias}.{column.target.column}" + (f"  as {alias}" if alias else ""))


def klass_said(info, depth: int = 0) -> None:
    reached = ""
    if "field" in info:
        reached = f", reached by {of_field(info['field'])}, reverse={info['reverse']}, from_parent={info['from_parent']}"
    note("  " * depth + f"klass_info: model {info['model'].__name__}{reached}, select_fields {info['select_fields']}")
    for related in info.get("related_klass_infos", []):
        klass_said(related, depth + 1)


def populator_made(frame) -> str:
    info = frame.f_locals["klass_info"]
    return f"RelatedPopulator.__init__  (for {info['model'].__name__}, reached by {of_field(info['field'])})"


def populate_called(frame) -> str:
    f = frame.f_locals
    return f"RelatedPopulator.populate  (the populator for {f['self'].model_cls.__name__}, from_obj={brief(f['from_obj'])})"


SELECTING = {k: v for k, v in ROWS.items() if k[1] != "Query.get_compiler"} | watch(
    QS, "QuerySet._fetch_all", "ModelIterable.__iter__", "get_related_populators",
) | {(QS, "RelatedPopulator.__init__"): populator_made, (QS, "RelatedPopulator.populate"): populate_called} | FETCHING
SELECTING[(QS, "get_related_populators")] = lambda f: "get_related_populators" if f.f_locals["klass_info"].get("related_klass_infos") else None

quietly("joined = Sailor.objects.select_related('ship__home').order_by('id')[:2]")
quietly("compiler = joined.query.get_compiler('default'); compiler.as_sql()")
select_said(ASKING["compiler"])
klass_said(ASKING["compiler"].klass_info)
show("What the compiler hands the iterable for Sailor.objects.select_related('ship__home'): the columns, and which of them are whose")

with recorded(SELECTING):
    do("pair = list(joined)")
ask("pair[0].ship is pair[1].ship, pair[0].ship == pair[1].ship, pair[0].ship.home is pair[1].ship.home")
ask("Sailor.ship.is_cached(pair[0]), Ship.home.is_cached(pair[0].ship), 'crew' in pair[0].ship._state.fields_cache")
show("select_related: one row becomes three instances")

with recorded(SELECTING):
    do("ships = list(Ship.objects.select_related('captain'))")
    ask("[ship.name for ship in ships], [Ship.captain.is_cached(ship) for ship in ships], ships[1]._state.fields_cache")
    ask("[(ship.name, ship.captain) for ship in ships]")
    ask("Ship.captain.is_cached(Ship.objects.get(name='Petrel'))")
    ask("ships[0].captain.command is ships[0]")
show("select_related across a relation that is null in a row: no instance is made, and None is what is cached")

quietly("down = Sailor.objects.select_related('officer').order_by('id')[2:3]")
quietly("compiler = down.query.get_compiler('default'); compiler.as_sql()")
select_said(ASKING["compiler"])
klass_said(ASKING["compiler"].klass_info)
with recorded(SELECTING):
    do("cora_row = list(down)")
    ask("type(cora_row[0]).__name__, type(cora_row[0].officer).__name__, cora_row[0].officer.sailor_ptr is cora_row[0]")
show("select_related from a parent down to its child: the child's instance is made from the parent's columns and its own")

ask("list(Sailor.objects.select_related('ship').only('name'))")
ask("[s.name for s in Sailor.objects.select_related('ship').only('name', 'ship__name').order_by('id')][:1]")
ask("list(Sailor.objects.select_related('pilots_into'))")
ask("Sailor.objects.select_related('ship').query.select_related, Sailor.objects.select_related('ship__home', 'ship__captain').query.select_related")
ask("Sailor.objects.select_related('ship').select_related(None).query.select_related")
# The instance is held in a name: a ModelState empties its fields cache as it is finalized, so
# the cache of an instance that is dropped in the middle of the question would read as empty.
quietly("no_officer = Sailor.objects.select_related('officer').get(pk=1)")
ask("no_officer._state.fields_cache, Sailor.officer.is_cached(no_officer)")
ask("no_officer.officer")
ask("Sailor.objects.select_related().query.select_related")
ask("len(Sailor.objects.select_related())")
show("Asked of select_related")

with recorded(ROWS | watch(QS, "ModelIterable.__iter__") | FETCHING):
    do("crew = list(petrel.crew.all())")
    ask("crew[0].ship is petrel, crew[1].ship is petrel")
ask("petrel.crew.select_related('ship')[0].ship is petrel")
ask("Sailor.ship.is_cached(petrel.crew.only('name')[0])")
show("Known related objects: the instance a related manager was made for is given to each instance it fetches")

DEFERRING = ROWS | watch(
    QS, "QuerySet.only", "QuerySet.defer", "QuerySet._fetch_all", "ModelIterable.__iter__", "QuerySet.in_bulk", "QuerySet.values_list",
    "FlatValuesListIterable.__iter__", "ValuesListIterable.__iter__",
) | watch(SQ, "Query.add_immediate_loading", "Query.add_deferred_loading", "Query.clear_deferred_loading") | watch(
    "django.db.models.query_utils", "DeferredAttribute.fetch_one", "DeferredAttribute.fetch_many",
) | watch("django.db.models.fetch_modes", "FetchOne.fetch", "FetchPeers.fetch", "FetchRaise.fetch") | watch(
    "django.db.models.base", "Model.refresh_from_db") | FETCHING

DEFERRING[("django.db.models.query_utils", "DeferredAttribute.fetch_one")] = lambda f: f"DeferredAttribute.fetch_one({brief(f.f_locals['instance'])})  ({of_field(f.f_locals['self'].field)})"
DEFERRING[("django.db.models.query_utils", "DeferredAttribute.fetch_many")] = lambda f: f"DeferredAttribute.fetch_many({brief(f.f_locals['instances'])})  ({of_field(f.f_locals['self'].field)})"
for kind in ("FetchOne", "FetchPeers", "FetchRaise"):
    DEFERRING[("django.db.models.fetch_modes", f"{kind}.fetch")] = (
        lambda f, kind=kind: f"{kind}.fetch(a {type(f.f_locals['fetcher']).__name__} for {of_field(f.f_locals['fetcher'].field)}, {brief(f.f_locals['instance'])})")
DEFERRING[("django.db.models.base", "Model.refresh_from_db")] = lambda f: f"Model.refresh_from_db(fields={f.f_locals['fields']!r})  ({brief(f.f_locals['self'])})"

with recorded(DEFERRING):
    do("slim = list(Sailor.objects.only('name').order_by('id')[:2])")
    do("slim[0].signed_on")
show("only: the columns left out are not selected, and a read of one fetches it for that instance")

ask("deferred(Sailor.objects.all())")
ask("deferred(Sailor.objects.defer('name')), deferred(Sailor.objects.defer('name').defer('signed_on'))")
ask("deferred(Sailor.objects.only('name')), deferred(Sailor.objects.only('name').only('signed_on'))")
ask("deferred(Sailor.objects.only('name', 'signed_on').defer('name')), deferred(Sailor.objects.defer('name').only('name', 'signed_on'))")
ask("deferred(Sailor.objects.defer('name').defer(None))")
ask("Sailor.objects.only(None)")
ask("sorted(Sailor.objects.only('name').get(pk=1).get_deferred_fields()), sorted(Sailor.objects.defer('id').get(pk=1).get_deferred_fields())")
ask("deferred(Sailor.objects.only('name').defer('name')), deferred(Sailor.objects.only('pk'))")
ask("list(Sailor.objects.only('cargo'))")
ask("Officer.objects.only('rank').get(pk=3).id")
ask("Officer.objects.fetch_mode(models.FETCH_RAISE).only('rank').get(pk=3).id")
quietly("unkeyed = Sailor.objects.only('name').get(pk=1); unkeyed.pk = None")
ask("unkeyed.signed_on")
show("Asked of defer and only: what each leaves on the query")

with recorded(DEFERRING):
    do("peers = list(Sailor.objects.fetch_mode(models.FETCH_PEERS).only('name').order_by('id'))")
    do("peers[0].signed_on")
    ask("['signed_on' in vars(sailor) for sailor in peers], len(peers[0]._state.peers)")
show("A deferred field read under FETCH_PEERS: one statement fetches it for every instance the query made")

ask("mode(Sailor.objects.all(), Sailor.objects.fetch_mode(models.FETCH_RAISE), Sailor.objects.fetch_mode(models.FETCH_RAISE).filter(pk=1).order_by('name'))")
ask("mode(ada, Sailor.objects.fetch_mode(models.FETCH_PEERS).get(pk=1), Sailor.objects.fetch_mode(models.FETCH_PEERS).get(pk=1).ship)")
ask("mode(Sailor.objects.fetch_mode(models.FETCH_PEERS).raw('SELECT * FROM crew_sailor'), Sailor.objects.fetch_mode(models.FETCH_PEERS).create(name='Eve', ship=petrel))")
quietly("Sailor.objects.filter(name='Eve').delete()")
ask("mode(petrel.crew.all(), Ship.objects.fetch_mode(models.FETCH_RAISE).get(pk=1).crew.all())")
ask("Sailor.objects.fetch_mode(models.FETCH_RAISE).only('name').get(pk=1).signed_on")
ask("[len(s.ship._state.peers) for s in Sailor.objects.fetch_mode(models.FETCH_PEERS).select_related('ship')]")
ask("[type(row).__name__ for row in Sailor.objects.fetch_mode(models.FETCH_PEERS).values('name')[:1]]")
ask("pickle.loads(pickle.dumps(models.FETCH_PEERS)) is models.FETCH_PEERS, models.FETCH_ONE.__reduce__()")
ask("mode(Sailor.objects.fetch_mode(models.FETCH_PEERS).raw('SELECT * FROM crew_sailor').prefetch_related('ship'))")
ask("mode(Sailor.objects.fetch_mode(models.FETCH_PEERS).prefetch_related('ship')[0].ship)")
ask("mode(Ship.objects.fetch_mode(models.FETCH_PEERS).prefetch_related('crew')[0].crew.all()[0])")
quietly("peers = list(Sailor.objects.fetch_mode(models.FETCH_PEERS).only('name').order_by('id')); peers[1].signed_on = None")
ask("peers[0].signed_on.year, peers[1].signed_on.year")
quietly("eve = Sailor.objects.create(name='Eve', ship=petrel); peers = list(Sailor.objects.fetch_mode(models.FETCH_PEERS).only('name').order_by('id')); Sailor.objects.filter(name='Eve').delete()")
ask("peers[0].signed_on")
show("Asked of fetch modes")

with recorded(DEFERRING | watch(QS, "QuerySet.iterator", "QuerySet._iterator")):
    do("for sailor in Sailor.objects.fetch_mode(models.FETCH_PEERS).only('name').order_by('id').iterator(): seen(sailor.signed_on.year)")
show("iterator under FETCH_PEERS, with a deferred field read in the loop: each instance is alone by the time it is read")

# ---------------------------------------------------------------------------------------------
# prefetch_related.


def one_level_called(frame) -> str:
    f = frame.f_locals
    return f"prefetch_one_level(instances={brief(f['instances'])}, prefetcher={prefetcher_said(f['prefetcher'])}, lookup={brief(f['lookup'])}, level={f['level']})"


def prefetcher_said(prefetcher) -> str:
    if prefetcher is None:
        return "None"
    instance = getattr(prefetcher, "instance", None)
    if isinstance(instance, models.Model):
        return f"{a(type(prefetcher).__name__)} for {brief(instance)}"
    field = getattr(prefetcher, "field", None) or getattr(getattr(prefetcher, "related", None), "field", None)
    return f"{a(type(prefetcher).__name__)} for {of_field(field)}" if field is not None else a(type(prefetcher).__name__)


def prefetcher_returned(frame, value) -> str:
    prefetcher, descriptor, found, is_fetched = value
    return f"({prefetcher_said(prefetcher)}, {a(type(descriptor).__name__) if descriptor is not None else None}, {found}, {brief(is_fetched)})"


def querysets_called(frame) -> str:
    f = frame.f_locals
    given_querysets = "" if f["querysets"] is None else f", querysets={brief(f['querysets'])}"
    return f"{short(frame.f_code.co_qualname)}(instances={brief(f['instances'])}{given_querysets})"


def querysets_returned(frame, value) -> str:
    queryset, rel_obj_attr, instance_attr, single, cache_name, is_descriptor = value
    return f"({brief(queryset)}, {brief(rel_obj_attr)}, {brief(instance_attr)}, {single}, {cache_name!r}, {is_descriptor})"


def one_level_returned(frame, value) -> str:
    objects, lookups = value
    return f"({brief(objects)}, {brief(lookups)})"


PREFETCHING = watch(
    QS, "QuerySet._fetch_all", "ModelIterable.__iter__", "QuerySet._prefetch_related_objects", "prefetch_related_objects",
    "get_prefetcher", "QuerySet.prefetch_related", "QuerySet.iterator", "QuerySet._iterator", "normalize_prefetch_lookups",
) | {
    (QS, "prefetch_one_level"): one_level_called,
    (DESCRIPTORS, REVERSE + "get_prefetch_querysets"): querysets_called,
    (DESCRIPTORS, MANY + "get_prefetch_querysets"): querysets_called,
    (DESCRIPTORS, "ForwardManyToOneDescriptor.get_prefetch_querysets"): querysets_called,
    (DESCRIPTORS, "ReverseOneToOneDescriptor.get_prefetch_querysets"): querysets_called,
} | FETCHING
del PREFETCHING[(QS, "normalize_prefetch_lookups")]
says(QS, "get_prefetcher", how=prefetcher_returned)
says(QS, "prefetch_one_level", how=one_level_returned)
says(DESCRIPTORS, REVERSE + "get_prefetch_querysets", MANY + "get_prefetch_querysets", "ForwardManyToOneDescriptor.get_prefetch_querysets",
     "ReverseOneToOneDescriptor.get_prefetch_querysets", how=querysets_returned)

with recorded(PREFETCHING):
    do("ships = list(Ship.objects.prefetch_related('crew'))")
show("prefetch_related: the queryset's own statement, and then one for the crews of all its ships")

ask("ships[0]._prefetched_objects_cache")
ask("list(ships[0].crew.all()), ships[0].crew.all() is ships[0].crew.all()")
ask("ships[0].crew.all()[0].ship is ships[0]")
ask("ships[0].crew.count(), ships[0].crew.exists()")
ask("list(ships[0].crew.filter(name='Cora'))")
ask("list(ships[0].crew.order_by('name'))")
ask("Ship.objects.prefetch_related('crew')._prefetch_related_lookups, Ship.objects.prefetch_related('crew').prefetch_related('home')._prefetch_related_lookups, Ship.objects.prefetch_related('crew').prefetch_related(None)._prefetch_related_lookups")
ask("Ship.objects.prefetch_related('crew')._prefetch_done, Ship.objects.prefetch_related('crew').filter(tonnage__gt=1)._prefetch_related_lookups")
show("Asked of the ships and their prefetched crews")

with recorded(PREFETCHING):
    do("ports = list(Port.objects.prefetch_related('ships__crew'))")
show("A prefetch lookup of two parts: one level at a time, each level's objects the next level's instances")

with recorded(PREFETCHING):
    do("sailors = list(Sailor.objects.order_by('id').prefetch_related('ship'))")
    ask("sailors[0].ship is sailors[1].ship, Sailor.ship.is_cached(sailors[0]), hasattr(sailors[0], '_prefetched_objects_cache'), sailors[0]._prefetched_objects_cache")
show("A prefetch across a foreign key: the descriptor is the prefetcher, and the objects go to the field's cache")

with recorded(PREFETCHING):
    do("voyages = list(Voyage.objects.order_by('id').prefetch_related('calls'))")
    ask("[[port.name for port in voyage.calls.all()] for voyage in voyages]")
show("A prefetch across a many-to-many relation: the statement selects, beside each port, the voyage it is to be matched to")

with recorded(PREFETCHING):
    do("ships = list(Ship.objects.prefetch_related(Prefetch('crew', queryset=Sailor.objects.filter(signed_on__year__lt=2020), to_attr='veterans')))")
    ask("[(ship.name, ship.veterans) for ship in ships], hasattr(ships[0], '_prefetched_objects_cache'), ships[0]._prefetched_objects_cache")
show("A Prefetch with a queryset and to_attr: the list is set as an attribute")

with recorded(PREFETCHING):
    do("sailors = list(Sailor.objects.order_by('id').prefetch_related(Prefetch('ship', queryset=Ship.objects.prefetch_related('crew'))))")
show("A Prefetch whose queryset has prefetch lookups of its own: they are taken off it before it runs, and followed afterwards as lookups of the first queryset")

with recorded(PREFETCHING):
    do("ports = list(Port.objects.prefetch_related(Prefetch('ships', queryset=Ship.objects.prefetch_related('crew'))))")
show("The same through a reverse relation: the manager evaluates the queryset itself, lookups and all, and the lookups taken off it find their work done")

quietly("hands = list(Sailor.objects.order_by('id'))")
with recorded(PREFETCHING):
    do("hands[0].ship")
    do("prefetch_related_objects(hands, 'ship__home')")
    ask("Sailor.ship.is_cached(hands[3]), hands[1].ship is hands[0].ship, hands[2].ship is hands[3].ship")
    ask("Ship.home.is_cached(hands[0].ship), Ship.home.is_cached(hands[1].ship)")
    do("prefetch_related_objects(hands, 'ship__home')")
show("prefetch_related_objects, called twice with instances a program already has, one of which has read its ship")

with recorded(PREFETCHING):
    do("for ship in Ship.objects.prefetch_related('crew').iterator(chunk_size=1): seen(ship)")
show("iterator with prefetch lookups: a prefetch for each chunk")

ask("list(Ship.objects.prefetch_related('crew').iterator())")
ask("list(Ship.objects.prefetch_related('name'))")
ask("list(Ship.objects.prefetch_related('cargo'))")
ask("list(Ship.objects.prefetch_related('home__name'))")
ask("list(Ship.objects.prefetch_related('crew', Prefetch('crew', queryset=Sailor.objects.all())))")
ask("list(Ship.objects.prefetch_related(Prefetch('crew', queryset=Sailor.objects.all(), to_attr='tonnage')))")
ask("Prefetch('crew', queryset=Sailor.objects.values('name'))")
ask("Prefetch('ships__crew', to_attr='hands').prefetch_through, Prefetch('ships__crew', to_attr='hands').prefetch_to")
ask("Prefetch('crew') == Prefetch('crew', queryset=Sailor.objects.all()), Prefetch('crew') == Prefetch('crew', to_attr='hands')")
ask("list(Ship.objects.values('name').prefetch_related('crew'))")
ask("[len(s.crew.all()) for s in Ship.objects.raw('SELECT * FROM fleet_ship ORDER BY id').prefetch_related('crew')]")
ask("list(Ship.objects.prefetch_related(Prefetch('crew', queryset=Sailor.objects.all(), to_attr='crew')))")
ask("[(ship.name, ship.first_hand) for ship in Ship.objects.prefetch_related(Prefetch('crew', queryset=Sailor.objects.order_by('name')[:1], to_attr='first_hand'))]")
ask("list(Ship.objects.prefetch_related(Prefetch('crew', queryset=Sailor.objects.order_by('name')[:1])))")
ask("len(Port.objects.prefetch_related('ships', 'ships__crew'))")
ask("len(Ship.objects.prefetch_related(Prefetch('crew', queryset=Sailor.objects.all()), 'crew'))")
ask("pickle.loads(pickle.dumps(Ship.objects.prefetch_related(Prefetch('crew', queryset=Sailor.objects.filter(name='Ada')))))._prefetch_related_lookups[0].queryset._result_cache")
quietly("ships = Ship.objects.prefetch_related('crew'); list(ships); ships.update(tonnage=F('tonnage'))")
ask("ships._result_cache, ships._prefetch_done")
ask("[hasattr(ship, '_prefetched_objects_cache') for ship in ships]")
ask("[hasattr(found, '_prefetched_objects_cache') for found in (Ship.objects.prefetch_related('crew').get(pk=1), Ship.objects.prefetch_related('crew').first(), Ship.objects.prefetch_related('crew')[0])]")
show("Asked of prefetch_related")

# ---------------------------------------------------------------------------------------------
# Combining querysets.

COMBINING = watch(
    QS, "QuerySet.__and__", "QuerySet.__or__", "QuerySet.__xor__", "QuerySet._merge_sanity_check", "QuerySet._merge_known_related_objects",
    "QuerySet._check_operator_queryset", "QuerySet.union", "QuerySet.intersection", "QuerySet.difference", "QuerySet._combinator_query",
    "QuerySet._clear_ordering_in_combined_queries", "QuerySet._chain", "QuerySet._not_support_combined_queries",
) | watch(SQ, "Query.combine", "Query.clear_ordering", "Query.clear_limits", "Query.can_filter")

quietly("old = Sailor.objects.filter(signed_on__year__lt=2020); on_petrel = Sailor.objects.filter(ship=petrel)")
with recorded(COMBINING):
    do("both = old & on_petrel")
    do("either = old | on_petrel")
    ask("list(both)")
    ask("list(either)")
    ask("list(old ^ on_petrel)")
show("The operators: two queries become one, and its conditions are joined with AND, OR or XOR")

quietly("two = Sailor.objects.order_by('id')[:2]; dag_only = Sailor.objects.filter(name='Dag')")
with recorded(COMBINING):
    do("first_two = two | dag_only")
    ask("list(first_two)")
    ask("two & dag_only")
    ask("list(dag_only & two)")
    ask("mode(Sailor.objects.fetch_mode(models.FETCH_PEERS).prefetch_related('ship')[:2] | dag_only), (Sailor.objects.fetch_mode(models.FETCH_PEERS).prefetch_related('ship')[:2] | dag_only)._prefetch_related_lookups")
show("A sliced queryset on the left of | becomes a condition on the primary key; on the left of & it is refused, and on the right its limits are dropped")

quietly("named_dag = Sailor.objects.filter(name='Dag')")
with recorded(COMBINING):
    do("names = old.union(on_petrel, named_dag)")
    ask("names.query.combinator, names.query.combinator_all, len(names.query.combined_queries), bool(names.query.where)")
    ask("names.query.combined_queries[0] is old.query, names.query.combined_queries[1] is on_petrel.query")
    ask("list(names)")
    ask("list(names.order_by('-name')[:2])")
show("union: the queries are kept side by side, and compiled as one statement")

ask("list(old.order_by('name').union(on_petrel))")
ask("list(old.union(on_petrel.order_by('name')))")
ask("list(old[:1].union(on_petrel))")
quietly("heavy = Ship.objects.filter(tonnage__gt=1000); light = Ship.objects.filter(tonnage__lt=1000)")
ask("Ship._meta.ordering, Sailor._meta.ordering")
ask("list(heavy.union(light))")
ask("list(heavy.union(light).order_by())")
ask("list(heavy.order_by().union(light))")
ask("list(heavy.order_by().union(light.order_by()))")
ask("heavy.union(light).query.default_ordering, heavy.union(light).query.combined_queries[0].default_ordering, heavy.union(light).query.combined_queries[1].default_ordering")
ask("connection.features.supports_slicing_ordering_in_compound")
show("union and the ordering of its parts, on SQLite")

ask("list(old.intersection(on_petrel))")
ask("list(on_petrel.difference(old))")
ask("list(old.union(on_petrel, all=True).values_list('name', flat=True).order_by('name'))")
ask("old.union(on_petrel).filter(name='Ada')")
ask("old.union(on_petrel).annotate(n=Count('id'))")
ask("old.union(on_petrel).get(name='Ada')")
ask("old.union(on_petrel).order_by('name')[:1].get().name")
ask("old.union(on_petrel).count()")
ask("old.union(on_petrel).exists()")
ask("old.union(on_petrel) | old")
ask("old.union(on_petrel).delete()")
ask("old.union(on_petrel).update(name='x')")
ask("old.union() is old, old.union(Sailor.objects.none()).query.combinator")
ask("Sailor.objects.none().union(old) is old, Sailor.objects.none().intersection(old).query.is_empty(), old.intersection(Sailor.objects.none()).query.is_empty()")
ask("list(old.union(on_petrel).complex_filter({'name': 'Ada'}))")
ask("heavy.union(light).count(), heavy.union(light).exists()")
show("Asked of union, intersection and difference")

ask("isinstance(Sailor.objects.none(), EmptyQuerySet), isinstance(Sailor.objects.all(), EmptyQuerySet), type(Sailor.objects.none()).__name__")
ask("list(Sailor.objects.none()), Sailor.objects.none().count(), Sailor.objects.none().exists()")
ask("list(Sailor.objects.filter(pk__in=[]))")
ask("isinstance(Sailor.objects.filter(pk__in=[]), EmptyQuerySet)")
ask("(Sailor.objects.none() | old) is old, (old & Sailor.objects.none()).query.is_empty()")
ask("Sailor.objects.none().ordered, Sailor.objects.none().filter(name='Ada').query.is_empty()")
ask("EmptyQuerySet()")
ask("Sailor.objects.values('name') | Sailor.objects.values('id')")
ask("type(Sailor.objects.all() | Sailor.objects.values('id')).__name__, (Sailor.objects.all() | Sailor.objects.values('id'))._fields")
ask("Sailor.objects.all() | Ship.objects.all()")
quietly("of_petrel = petrel.crew.all(); of_gannet = gannet.crew.all()")
ask("{field.name: sorted(known) for field, known in of_petrel._known_related_objects.items()}")
quietly("of_petrel | of_gannet")
ask("{field.name: sorted(known) for field, known in of_petrel._known_related_objects.items()}")
show("none and EmptyQuerySet, and what the operators refuse")

ask("Ship.objects.reverse().query.standard_ordering, Ship.objects.reverse().reverse().query.standard_ordering")
ask("Ship.objects.order_by('tonnage', '-name').query.order_by, Ship.objects.order_by('tonnage').order_by().query.order_by, Ship.objects.order_by().query.default_ordering")
ask("Ship.objects.distinct().query.distinct, Ship.objects.distinct('name').query.distinct_fields")
ask("list(Ship.objects.distinct('name'))")
ask("Ship.objects.select_for_update().query.select_for_update, Ship.objects.select_for_update(skip_locked=True, of=('self',)).query.select_for_update_of")
ask("Ship.objects.select_for_update(nowait=True, skip_locked=True)")
ask("Ship.objects.using('replica')._db, Ship.objects.using('replica').filter(pk=1)._db")
ask("list(Ship.objects.extra(select={'heavy': 'tonnage > 1000'}, order_by=['tonnage']).values_list('name', 'heavy'))")
ask("bool(Sailor.objects.all()._has_filters()), bool(Sailor.objects.filter(pk=1)._has_filters()), bool(Sailor.objects.all()[1:]._has_filters())")
ask("[ship.name for ship in Ship.objects.select_for_update()]")
show("What some other methods leave on the query")

ask("sorted(name for name, method in vars(QuerySet).items() if getattr(method, 'alters_data', False))")
ask("sorted(name for name, method in vars(QuerySet).items() if getattr(method, 'queryset_only', None) is True), sorted(name for name, method in vars(QuerySet).items() if getattr(method, 'queryset_only', None) is False)")
ask("type('Quiet', (QuerySet,), {'delete': lambda self: 0}).delete.alters_data, type('Quiet', (QuerySet,), {'purge': lambda self: 0}).purge.__dict__")
ask("QuerySet[Port] is QuerySet")
ask("sorted(vars(SailorQuerySet).keys() - {'__module__', '__qualname__', '__doc__', '__firstlineno__', '__static_attributes__'})")
show("The marks on the methods: alters_data and queryset_only")

# ---------------------------------------------------------------------------------------------
# Which database.


class Listening:
    """A router that writes down what it is asked and answers None, which leaves the choice
    to Django's default."""

    def db_for_read(self, model, **hints):
        if LISTENING:
            note(f"the router is asked db_for_read({model.__name__}" + "".join(f", {k}={brief(v)}" for k, v in hints.items()) + ")")

    def db_for_write(self, model, **hints):
        if LISTENING:
            note(f"the router is asked db_for_write({model.__name__}" + "".join(f", {k}={brief(v)}" for k, v in hints.items()) + ")")


router.routers = [Listening()]
ask("Ship.objects.all().db")
ask("Ship.objects.using('default').db")
ask("Ship.objects.all()._db, Ship.objects.using('default')._db")
ask("petrel.crew.all().db")
ask("Ship.objects.select_for_update().db")
ask("Ship.objects.all()._for_write, Ship.objects.select_for_update()._for_write, Ship.objects.select_for_update().filter(pk=1)._for_write")
ask("[ship.name for ship in Ship.objects.all()]")
ask("Ship.objects.count()")
ask("Ship.objects.get_or_create(name='Petrel', home=bergen, defaults={'tonnage': 1})")
ask("Ship.objects.filter(pk=0).update(tonnage=1)")
ask("Port.objects.create(name='Mull', country='Scotland').name")
quietly("Port.objects.filter(name='Mull').delete()")
ask("len(Logbook.objects.bulk_create([Logbook(title='Spare log')]))")
quietly("Logbook.objects.filter(title='Spare log').delete()")
del router.__dict__["routers"]
show("Which database: the router is asked each time an alias is needed, for reading or for writing")

# ---------------------------------------------------------------------------------------------
# Writing: create, get_or_create, update_or_create, update, delete.

WRITING = TRANSACTION | watch(
    QS, "QuerySet.create", "QuerySet.get_or_create", "QuerySet.update_or_create", "QuerySet.get", "QuerySet._extract_model_params",
    "QuerySet.select_for_update", "QuerySet.update", "QuerySet._update", "QuerySet.delete", "QuerySet._raw_delete", "QuerySet._insert",
) | watch(
    "django.db.models.base", "Model.save", label=lambda f: "Model.save(" + ", ".join(
        f"{n}={brief(f.f_locals[n])}" for n in ("force_insert", "force_update", "using", "update_fields") if differs(f.f_locals[n], {"force_insert": False, "force_update": False}.get(n))
    ) + f")  ({a(type(f.f_locals['self']).__name__)})",
) | watch("django.db.models.deletion", "Collector.collect", "Collector.delete", label=plain) | watch(
    "django.db.models.sql.subqueries", "UpdateQuery.add_update_values", "UpdateQuery.add_update_fields", label=plain) | watch(
    "django.db.models.utils", "resolve_callables", label=plain)
WRITING[(QS, "QuerySet._insert")] = lambda f: (
    f"QuerySet._insert(objs={brief(f.f_locals['objs'])}, fields={brief(f.f_locals['fields'])}, returning_fields={brief(f.f_locals['returning_fields'])}"
    + "".join(f", {n}={brief(f.f_locals[n])}" for n in ("on_conflict", "update_fields", "unique_fields") if f.f_locals[n] is not None) + ")")
WRITING[(QS, "QuerySet._update")] = lambda f: (
    "QuerySet._update(values=[" + ", ".join(f"({of_field(field)}, {brief(value)})" for field, _, value in f.f_locals["values"])
    + f"], returning_fields={brief(f.f_locals['returning_fields'])})")
says("django.db.models.deletion", "Collector.delete")

with recorded(WRITING):
    do("oban = Port.objects.create(name='Oban', country='Scotland')")
    ask("oban.pk, oban._state.adding, oban._state.db")
show("create: an instance is made and saved with force_insert")

with recorded(WRITING):
    do("Port.objects.get_or_create(name='Oban', defaults={'country': 'Alba'})")
    do("Port.objects.get_or_create(name='Skagen', defaults={'country': lambda: 'Denmark'})")
show("get_or_create: a get, and only when it finds nothing a create inside an atomic block")

with recorded(WRITING):
    do("Ship.objects.get_or_create(name='Petrel', home=bergen, tonnage=900)")
show("get_or_create where the insert breaks a unique constraint: the get is tried once more, and the error is raised again")

ask("Port.objects.get_or_create(name__iexact='oban', defaults={'name': 'Oban', 'country': 'Scotland'})[1]")
ask("Port.objects.get_or_create(name='Mull', defaults={'county': 'Argyll'})")
ask("Sailor.objects.create(name='Eve', ship=petrel, command=gannet)")
ask("Port.objects.get_or_create(name='Bergen', defaults={'county': 'Hordaland'})")
ask("sorted(Sailor._meta._reverse_one_to_one_field_names)")
show("Asked of get_or_create and create")

with recorded(WRITING):
    do("Port.objects.update_or_create(name='Skagen', defaults={'country': 'Danmark'})")
    do("Port.objects.update_or_create(name='Tromso', defaults={'country': 'Norge'}, create_defaults={'country': 'Norway'})")
show("update_or_create: a transaction, a get_or_create under select_for_update, and a save of the fields in defaults")

with recorded(WRITING):
    do("Sailor.objects.update_or_create(name='Ada', defaults={'ship': petrel})")
show("update_or_create on a model with a field that has a pre_save of its own: the field is added to update_fields")

ask("Port.objects.update_or_create(name='Bergen')")
ask("Officer.objects.update_or_create(name='Cora', defaults={'rank': 'master'})")
show("Asked of update_or_create")

quietly("aboard = Sailor.objects.filter(ship=gannet); list(aboard)")
with recorded(WRITING | watch(SQ, "Query.chain")):
    ask("len(aboard._result_cache)")
    do("aboard.update(ship=gannet)")
    ask("aboard._result_cache")
show("update: a copy of the query is made an UpdateQuery, one statement is sent, and the result cache is dropped")

ask("Sailor.objects.filter(ship=gannet).update(name=Lower('name'))")
ask("Sailor.objects.filter(ship=gannet).update(name=F('name'), ship__name='x')")
ask("Sailor.objects.filter(name='dag').order_by('name').update(name='Dag'), Sailor.objects.filter(name='cora').update(name='Cora')")
ask("Sailor.objects.annotate(short=Lower('name')).order_by('short').filter(pk=0).update(name='x')")
ask("Sailor.objects.update()")
ask("Ship.objects.filter(crew__name='Ada').update(tonnage=480)")
ask("Ship.objects.annotate(hands=Count('crew')).order_by('hands').update(tonnage=1)")
show("Asked of update")

quietly("skagen = Port.objects.filter(name__in=['Skagen', 'Tromso']); list(skagen)")
# Of the clones made while a queryset is deleted, the one QuerySet.delete makes itself.
with recorded(WRITING | watch(SQ, "Query.clear_ordering") | {
        (QS, "QuerySet._chain"): lambda f: "QuerySet._chain" if f.f_back.f_code.co_qualname == "QuerySet.delete" else None}):
    do("skagen.delete()")
    ask("skagen._result_cache")
show("delete: a clone with its ordering cleared is handed to a Collector")

ask("Port.objects.filter(name='Oban').delete()")
ask("Port.objects.filter(name='Bergen').delete()", brief_=True)
ask("Sailor.objects.delete()")
ask("Sailor.objects.values('name').delete()")
ask("Sailor.objects.distinct('name').delete()")
ask("Sailor.objects.select_related('ship').order_by('name').filter(pk=0).delete()")
show("Asked of delete")

# ---------------------------------------------------------------------------------------------
# bulk_create and bulk_update.

BULK = TRANSACTION | watch(
    QS, "QuerySet.bulk_create", "QuerySet._check_bulk_create_options", "QuerySet._prepare_for_bulk_create", "QuerySet._batched_insert",
    "QuerySet.bulk_update", "QuerySet.filter", "QuerySet.update",
)


def conflict_said(frame) -> str:
    return "".join(f", {n}={brief(frame.f_locals[n])}" for n in ("on_conflict", "update_fields", "unique_fields") if frame.f_locals[n] is not None)


def bulk_create_called(frame) -> str:
    f = frame.f_locals
    said = "".join(f", {n}={f[n]!r}" for n, default in (
        ("batch_size", None), ("ignore_conflicts", False), ("update_conflicts", False), ("update_fields", None), ("unique_fields", None),
    ) if f[n] is not default)
    return f"QuerySet.bulk_create(objs={counted(list(f['objs']))}{said})"


BULK[(QS, "QuerySet.bulk_create")] = bulk_create_called
BULK[(QS, "QuerySet._prepare_for_bulk_create")] = lambda f: f"QuerySet._prepare_for_bulk_create({counted(f.f_locals['objs'])})"
BULK[(QS, "QuerySet._batched_insert")] = lambda f: (
    f"QuerySet._batched_insert(objs={counted(f.f_locals['objs'])}, fields={brief(f.f_locals['fields'])}, batch_size={f.f_locals['batch_size']!r}{conflict_said(f)})")
BULK[(QS, "QuerySet._insert")] = lambda f: (
    f"QuerySet._insert(objs={counted(f.f_locals['objs'])}, fields={brief(f.f_locals['fields'])}, returning_fields={brief(f.f_locals['returning_fields'])}{conflict_said(f)})")
BULK[(QS, "QuerySet.bulk_update")] = lambda f: (
    f"QuerySet.bulk_update(objs={brief(list(f.f_locals['objs']))}, fields={f.f_locals['fields']!r}" + (f", batch_size={f.f_locals['batch_size']!r}" if f.f_locals["batch_size"] is not None else "") + ")")
BULK[(QS, "QuerySet.update")] = lambda f: "QuerySet.update(" + ", ".join(f"{k}={a(type(v).__name__)}" for k, v in f.f_locals["kwargs"].items()) + ")"
says(QS, "QuerySet._prepare_for_bulk_create", how=lambda f, v: f"({len(v[0])} with a primary key, {len(v[1])} without)")
says(QS, "QuerySet.bulk_create", how=lambda f, v: counted(v) + (", with the primary keys " + brief([o.pk for o in v]) if v else ""))
LIMITED = BULK | {("django.db.backends.base.operations", "BaseDatabaseOperations.bulk_batch_size"):
                  lambda f: f"BaseDatabaseOperations.bulk_batch_size(fields={brief(f.f_locals['fields'])}, objs={counted(f.f_locals['objs'])})"}
says("django.db.backends.base.operations", "BaseDatabaseOperations.bulk_batch_size")

quietly("log = Logbook.objects.get(pk=1)")
with recorded(BULK):
    do("lines = LogEntry.objects.bulk_create([LogEntry(book=log, line='Cast off'), LogEntry(book=log, line='Cleared the mole'), LogEntry(book=log, line='Full ahead')])")
    ask("[(entry.pk, entry._state.adding, entry._state.db) for entry in lines]")
show("bulk_create: one INSERT for the three, and the primary keys the database gave them are set on the instances")

with recorded(BULK):
    do("LogEntry.objects.bulk_create([LogEntry(book=log, line=f'Sounding {n}') for n in range(1, 6)], batch_size=2)")
show("bulk_create with batch_size=2: three statements, in a transaction")

with recorded(BULK):
    do("mixed = Logbook.objects.bulk_create([Logbook(pk=40, title='Rough log'), Logbook(title='Fair log')])")
    ask("[(book.pk, book.title) for book in mixed]")
show("bulk_create of instances with a primary key and without: two statements with different columns, in a transaction")

with recorded(BULK):
    do("again = Logbook.objects.bulk_create([Logbook(pk=40, title='Rough log, again'), Logbook(pk=41, title='Deck log')], ignore_conflicts=True)")
    ask("[(book.pk, book._state.adding) for book in again], list(Logbook.objects.filter(pk__in=[40, 41]).values_list('pk', 'title'))")
show("bulk_create with ignore_conflicts: nothing is asked back")

with recorded(BULK):
    do("Logbook.objects.bulk_create([Logbook(pk=40, title='Rough log, fair copy')], update_conflicts=True, update_fields=['title'], unique_fields=['pk'])")
    ask("Logbook.objects.get(pk=40).title")
show("bulk_create with update_conflicts: the conflict's target and the columns to update go into the statement")

with recorded(BULK):
    do("cargo = Manifest.objects.bulk_create([Manifest(voyage=spring, crates=40, kilos_each=25), Manifest(voyage=spring, crates=12, kilos_each=80, stamped=True)])")
    ask("[(m.serial, m.kilos, m.stamped) for m in cargo]")
show("bulk_create of a model with a generated column and a database default")

ask("Officer.objects.bulk_create([])")
ask("Veteran.objects.bulk_create([])")
ask("Logbook.objects.bulk_create([Logbook(title='x')], batch_size=0)")
ask("Logbook.objects.bulk_create([Logbook(title='x')], ignore_conflicts=True, update_conflicts=True)")
ask("Logbook.objects.bulk_create([Logbook(title='x')], update_conflicts=True)")
ask("Logbook.objects.bulk_create([Logbook(title='x')], update_conflicts=True, update_fields=['title'])")
ask("Logbook.objects.bulk_create([Logbook(title='x')], update_conflicts=True, update_fields=['id'], unique_fields=['title'])")
ask("LogEntry.objects.bulk_create([LogEntry(book=Logbook(title='unsaved'), line='x')])")
ask("connection.features.supports_ignore_conflicts, connection.features.supports_update_conflicts, connection.features.supports_update_conflicts_with_target, connection.features.can_return_rows_from_bulk_insert")
ask("[(book.pk, book._state.adding, book._state.db) for book in Logbook.objects.bulk_create([Logbook(title='Unkeyed log')], ignore_conflicts=True)]")
show("Asked of bulk_create")

quietly("ada.name, bram.name = 'Ada L.', 'Bram S.'")
with recorded(BULK):
    do("Sailor.objects.bulk_update([ada, bram], ['name'])")
show("bulk_update: one UPDATE whose value for each column is a CASE over the primary keys")

quietly("ada.name, bram.name = 'Ada', 'Bram'")
with recorded(BULK):
    do("Sailor.objects.bulk_update([ada, bram], ['name'], batch_size=1)")
show("bulk_update with batch_size=1: a statement for each batch")

ask("Sailor.objects.bulk_update([], ['name'])")
ask("Sailor.objects.bulk_update([ada], [])")
ask("Sailor.objects.bulk_update([Sailor(name='Eve')], ['name'])")
ask("Sailor.objects.bulk_update([ada], ['id'])")
ask("Sailor.objects.bulk_update([ada], ['pilots_into'])")
ask("Officer.objects.bulk_update([Officer.objects.get(pk=3)], ['name'])")
show("Asked of bulk_update")

connection.ensure_connection()
connection.connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 10)
connection.features.__dict__.pop("max_query_params", None)
with recorded(LIMITED):
    ask("connection.features.max_query_params")
    quietly("log = Logbook.objects.get(pk=2)")
    do("LogEntry.objects.bulk_create([LogEntry(book=log, line=f'Bell {n}') for n in range(1, 13)])")
ask("Sailor.objects.bulk_update([ada, bram], ['name'])")
ask("Sailor.objects.bulk_update([ada, bram], ['name', 'ship', 'signed_on'])")
show("With SQLite's limit on the parameters of a statement lowered to 10: the backend's limit makes the batches of bulk_create")

ask("len(Logbook.objects.in_bulk(range(1, 26)))")
show("With the same limit: in_bulk fetches the rows for the values it was given in batches")

quietly("log = Logbook.objects.get(pk=3)")
ask("mode(*LogEntry.objects.fetch_mode(models.FETCH_PEERS).bulk_create([LogEntry(book=log, line='Anchored')]))")
ask("mode(LogEntry.objects.fetch_mode(models.FETCH_PEERS).create(book=log, line='Weighed'))")
show("bulk_create and the queryset's fetch mode")
connection.close()  # the next statement opens a connection with the driver's own limit again
connection.features.__dict__.pop("max_query_params", None)

# ---------------------------------------------------------------------------------------------
# Q, exclude, FilteredRelation.

ask("Q(name='Ada', ship=1)")
ask("Q(ship=1, name='Ada') == Q(name='Ada', ship=1), hash(Q(ship=1, name='Ada')) == hash(Q(name='Ada', ship=1))")
ask("Q(name='Ada') | Q(name='Dag')")
ask("Q(name='Ada') & Q(ship=1) & Q(pk__gt=0)")
ask("(Q(name='Ada') | Q(name='Dag')) & Q(ship=1)")
ask("~Q(name='Ada')")
ask("~(Q(name='Ada') | Q(name='Dag'))")
ask("Q(name='Ada') ^ Q(name='Dag')")
ask("Q() & Q(name='Ada'), Q(name='Ada') | Q(), bool(Q()), len(Q(name='Ada', ship=1))")
ask("Q(Q(name='Ada') | Q(name='Dag'), ship=1).children")
ask("Q(name='Ada') & 5")
ask("Q(name='Ada') & F('name')")
ask("Q(name='Ada', _connector='OR', _negated=True)")
ask("Q(name='Ada', _connector='NAND')")
ask("Q(name='Ada').deconstruct(), (~Q(name='Ada') | Q(ship=1)).deconstruct()")
ask("Q(Q(name='Ada') | Q(name='Dag'), ship=1).identity")
ask("list(Q(Q(name='Ada') | Q(name='Dag'), ship=F('captain')).flatten())")
ask("sorted(Q(Q(name='Ada') | Q(ship__home__name='Leith'), tonnage__gt=F('captain__id')).referenced_base_fields)")
ask("Q.default, Q.conditional, Q.connectors")
quietly("ada_q = Q(name='Ada')")
ask("(~ada_q).children is ada_q.children, (~ada_q).children[0] is ada_q, ada_q.negated, (~ada_q).negated")
ask("type(Q() & Exists(Sailor.objects.all())).__name__")
ask("Q(name='Ada') & Q(ship=1) == Q(ship=1) & Q(name='Ada'), Q(name='Ada', ship=1) == Q(ship=1, name='Ada')")
ask("Q(tonnage__gt=0).replace_expressions({F('tonnage'): Value(480)}).children")
show("Q objects: one question to a line")

FILTERING = watch(QS, "QuerySet.filter", "QuerySet.exclude", "QuerySet._filter_or_exclude", "QuerySet._filter_or_exclude_inplace", "QuerySet.complex_filter") | watch(
    SQ, "Query.add_q") | watch("django.db.models.query_utils", "Q.resolve_expression", label=lambda f: f"Q.resolve_expression  ({f.f_locals['self']!r})")

with recorded(FILTERING):
    do("others = Sailor.objects.exclude(name='Ada', ship=petrel)")
    ask("list(others)")
    do("leith_or_big = Ship.objects.filter(Q(home__name='Leith') | Q(tonnage__gt=1000), name__startswith='G')")
    ask("list(leith_or_big)")
    do("marked = Sailor.objects.annotate(veteran=Q(signed_on__year__lt=2020))")
    ask("[(sailor.name, sailor.veteran) for sailor in marked]")
show("filter and exclude make a Q of their arguments; a Q given as an annotation is resolved as an expression")

ask("Sailor.objects.filter(name='Ada', _connector='OR')")
ask("Sailor.objects.filter(Q(name='Ada'), 5)")
ask("Sailor.objects.filter().query.where, Sailor.objects.exclude().query.where")
ask("list(Sailor.objects.complex_filter({'name': 'Ada'})), list(Sailor.objects.complex_filter(Q(name='Dag')))")
ask("list(Sailor.objects.filter(~Q(ship=petrel) & Q(signed_on__year=2026)))")
ask("list(Sailor.objects.order_by('id')[:2].complex_filter(Q(name='Dag')))")
ask("[(ship.name, ship.cora) for ship in Ship.objects.annotate(cora=Q(captain__name='Cora')).order_by('name')]")
ask("[ship.name for ship in Ship.objects.filter(captain__name='Cora')]")
show("Asked of filter and exclude")

ask("Q(tonnage__gt=0).check({'tonnage': 480})")
ask("Q(tonnage__gt=0).check({'tonnage': 0})")
ask("Q(tonnage__gt=F('crates')).check({'tonnage': 480, 'crates': 40})")
ask("Q(tonnage__gt=0).check({})")
quietly("with transaction.atomic(): checked = Q(tonnage__gt=0).check({'tonnage': 480})")
ask("checked")
show("Q.check: the condition is put to the database, with values in place of columns")

ask("list(Ship.objects.annotate(veterans=FilteredRelation('crew', condition=Q(crew__signed_on__year__lt=2020))).values_list('name', 'veterans__name'))")
ask("Ship.objects.annotate(veterans=FilteredRelation('crew', condition=Q(crew__signed_on__year__lt=2020))).prefetch_related('veterans')")
ask("Ship.objects.annotate(veterans=FilteredRelation('crew', condition=Q(crew__signed_on__year__lt=2020))).only('veterans__name')")
ask("FilteredRelation('crew', condition={'crew__name': 'Ada'})")
ask("FilteredRelation('')")
ask("FilteredRelation('crew') == FilteredRelation('crew'), FilteredRelation('crew').condition")
quietly("with_veterans = Ship.objects.annotate(veterans=FilteredRelation('crew', condition=Q(crew__signed_on__year__lt=2020)))")
ask("list(with_veterans.query._filtered_relations), with_veterans.query._filtered_relations['veterans'].alias, with_veterans.query._filtered_relations['veterans'].condition, sorted(with_veterans.query.alias_map)")
ask("[ship.name for ship in with_veterans.filter(veterans__name='Ada')]")
show("FilteredRelation: a condition in the join")

# ---------------------------------------------------------------------------------------------
# The lookup registry.


class Shouted(Lookup):
    lookup_name = "shouted"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        return f"UPPER({lhs}) = UPPER({rhs})", (*lhs_params, *rhs_params)


ASKING.update(Shouted=Shouted, name_field=Sailor._meta.get_field("name"), title_field=Logbook._meta.get_field("title"))
ask("sorted(models.Field.get_lookups())")
ask("sorted(set(models.DateField.get_lookups()) - set(models.Field.get_lookups()))")
ask("sorted(set(models.CharField.get_lookups()) - set(models.Field.get_lookups())), 'class_lookups' in vars(models.CharField), 'class_lookups' in vars(models.Field)")
ask("sorted(models.ForeignKey.get_lookups()), sorted(vars(models.ForeignObject)['class_lookups'])")
ask("name_field.get_lookup('exact').__name__, name_field.get_lookup('year'), name_field.get_transform('year')")
ask("Sailor._meta.get_field('signed_on').get_lookup('year'), Sailor._meta.get_field('signed_on').get_transform('year').__name__")
ask("Sailor._meta.get_field('signed_on').get_transform('year').get_lookups is models.Field.get_lookups, Sailor._meta.get_field('signed_on').get_transform('year')(F('signed_on')).get_lookup('gt').__name__")
ask("name_field.get_lookups() is models.CharField.get_lookups(), models.CharField.get_lookups() is models.CharField.get_lookups(), models.CharField.get_lookups() is models.Field.get_lookups()")
quietly("name_field.register_lookup(Shouted)")
ask("name_field.instance_lookups, name_field.get_lookup('shouted').__name__, title_field.get_lookup('shouted'), models.CharField.get_lookups().get('shouted')")
ask("list(Sailor.objects.filter(name__shouted='ada'))")
ask("Logbook.objects.filter(title__shouted='log 1')")
quietly("name_field._unregister_lookup(Shouted)")
quietly("models.CharField.register_lookup(Shouted)")
ask("vars(models.CharField)['class_lookups'], title_field.get_lookup('shouted').__name__, models.TextField.get_lookups().get('shouted'), models.EmailField.get_lookups().get('shouted').__name__")
ask("Logbook.objects.filter(title__shouted='log 1').count()")
quietly("models.CharField._unregister_lookup(Shouted)")
ask("vars(models.CharField)['class_lookups'], title_field.get_lookup('shouted')")
ask("sorted(Sailor._meta.get_field('ship').get_lookups()), sorted(models.ForeignKey.get_class_lookups())")
ask("Sailor.objects.filter(ship__contains=1)")
show("The lookups a field answers to: registered on a class or on one field")

# ---------------------------------------------------------------------------------------------
# Raw querysets.

RAW = {k: v for k, v in ROWS.items() if k[0] != SQ} | watch(
    QS, "QuerySet.raw", "RawQuerySet.__iter__", "RawQuerySet._fetch_all", "RawQuerySet.iterator", "RawModelIterable.__iter__",
    "RawQuerySet.resolve_model_init_order", "RawQuerySet.__getitem__", "RawQuerySet.__len__",
) | watch(SQ, "RawQuery._execute_query", "RawQuery.get_columns", "RawQuery.__iter__", label=plain)
RAW[(QS, "QuerySet.raw")] = lambda f: f"QuerySet.raw({f.f_locals['raw_query']!r}" + (f", params={f.f_locals['params']!r}" if f.f_locals["params"] else "") + ")"
says(QS, "RawQuerySet.resolve_model_init_order", "RawQuerySet.__getitem__", "RawQuerySet.__len__")
says(SQ, "RawQuery.get_columns")

with recorded(RAW):
    do("hands = Sailor.objects.raw('SELECT id, name, upper(name) AS shout FROM crew_sailor WHERE ship_id = %s ORDER BY id', [1])")
    ask("type(hands).__name__, isinstance(hands, QuerySet), hands._result_cache, repr(hands)")
    do("for sailor in hands: seen(sailor)")
    ask("hands.columns, sorted(hands.model_fields), hands[0].shout, sorted(hands[0].get_deferred_fields())")
    do("hands[1]")
    do("len(hands)")
show("raw: nothing is sent until the RawQuerySet is iterated, and then each row becomes an instance of the model")

ask("[sailor.name for sailor in Sailor.objects.raw('SELECT id, name AS label FROM crew_sailor ORDER BY id LIMIT 2', translations={'label': 'name'})]")
ask("list(Sailor.objects.raw('SELECT name FROM crew_sailor'))")
ask("Sailor.objects.raw('SELEKT nothing')")
ask("list(Sailor.objects.raw('SELEKT nothing'))", brief_=True)
ask("[type(ship).__name__ for ship in Sailor.objects.raw('SELECT * FROM fleet_ship')]")
ask("Sailor.objects.raw('SELECT * FROM crew_sailor').filter(name='Ada')", brief_=True)
ask("Sailor.objects.raw('SELECT * FROM crew_sailor').using('default').db, hasattr(RawQuerySet, 'count'), hasattr(RawQuerySet, 'prefetch_related')")
ask("[(berth.port_id, berth.number, berth.pk) for berth in Berth.objects.raw('SELECT * FROM office_berth ORDER BY number')]")
ask("list(Berth.objects.raw('SELECT port_id, metres FROM office_berth'))")
quietly("names = Sailor.objects.raw('SELECT id, name FROM crew_sailor WHERE name = %s', ['Ada'])")
ask("names.columns")
ask("len(names), repr(names)")
ask("names[-1].name, names[0].signed_on.year")
ask("len(list(names.iterator())), len(names._result_cache)")
quietly("unkept = Sailor.objects.raw('SELECT id, name FROM crew_sailor')")
ask("len(list(unkept.iterator())), unkept._result_cache")
ask("len(Veteran.objects.raw('SELECT * FROM crew_sailor')), len(Sailor.objects.filter(name='Ada').raw('SELECT * FROM crew_sailor'))")
ask("mode(Sailor.objects.fetch_mode(models.FETCH_PEERS).raw('SELECT * FROM crew_sailor'), Sailor.objects.fetch_mode(models.FETCH_PEERS).raw('SELECT * FROM crew_sailor').prefetch_related('ship'), Sailor.objects.fetch_mode(models.FETCH_PEERS).raw('SELECT * FROM crew_sailor').using('default'))")
ask("Sailor.objects.raw('SELECT * FROM crew_sailor').prefetch_related('ship').using('default')._prefetch_related_lookups")
show("Asked of raw")

# ---------------------------------------------------------------------------------------------
# The asynchronous methods.

LOOP = None  # the thread the event loop runs on


def where() -> str:
    return "the event loop's thread" if threading.get_ident() == LOOP else "another thread"


def handed(function) -> str:
    """The function that sync_to_async was given, by its name."""
    return short(function.__qualname__)


def on_thread(label):
    def said(frame):
        text = label(frame)
        return None if text is None else f"{text}  [{where()}]"
    return said


ASYNC = {key: on_thread(label) for key, label in (watch(
    QS, "QuerySet.aget", "QuerySet.get", "QuerySet.acount", "QuerySet.count", "QuerySet.__aiter__", "QuerySet.aiterator",
    "BaseIterable.__aiter__", "BaseIterable._async_generator", "ModelIterable.__iter__",
    "aprefetch_related_objects", "prefetch_related_objects", "ValuesListIterable.__iter__",
) | {
    (CO, "SQLCompiler.execute_sql"): execute_called,
    (QS, "BaseIterable._async_generator.<locals>.next_slice"): lambda f: "next_slice  (the function BaseIterable._async_generator hands to sync_to_async)",
    (QS, "QuerySet.__aiter__.<locals>.generator"): lambda f: "generator  (the asynchronous generator QuerySet.__aiter__ returned)",
    # The hand-over: asgiref's coroutine, with the function it was made for.
    ("asgiref.sync", "SyncToAsync.__call__"): lambda f: f"SyncToAsync.__call__  (made by sync_to_async for {handed(f.f_locals['self'].func)})",
} | FETCHING).items()}
says(QS, "BaseIterable._async_generator.<locals>.next_slice", how=lambda f, v: f"a list of {len(v)}")


async def ado(statement: str) -> None:
    """`do` for a statement that awaits."""
    note(statement)
    STACK.append(None)
    try:
        result = eval(compile(statement, "<statement>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT), ASKING)
        if inspect.iscoroutine(result):
            await result
    except Exception as raised:
        flush()
        LINES.append("  " * (len(STACK) - 1) + f"raises {type(raised).__name__}: {raised}")
    finally:
        flush()
        STACK.pop()


def other_thread_begins() -> None:
    connection.execute_wrappers.append(query)  # this thread's connection: Django keeps one to a thread
    sys.setprofile(profile)


def other_thread_ends() -> None:
    sys.setprofile(None)
    connection.close()


async def asynchronous() -> None:
    global LOOP
    LOOP = threading.get_ident()
    await sync_to_async(other_thread_begins)()
    sys.setprofile(profile)
    await ado("ada = await Sailor.objects.aget(name='Ada')")
    await ado("await Sailor.objects.filter(ship=petrel).acount()")
    await ado("async for sailor in Sailor.objects.filter(ship=petrel).order_by('id'): seen(sailor)")
    await ado("async for sailor in Sailor.objects.order_by('id').aiterator(chunk_size=3): seen(sailor)")
    await ado("async for ship in Ship.objects.prefetch_related('crew').aiterator(chunk_size=1): seen(ship)")
    await ado("kept = Sailor.objects.filter(ship=petrel).order_by('id')")
    await ado("async for sailor in kept: seen(sailor)")
    await ado("async for sailor in kept: seen(sailor)")
    await ado("await asyncio.gather(Sailor.objects.acount(), Ship.objects.acount())")
    await ado("async for row in Sailor.objects.values_list('name').aiterator(): seen(row)")
    await ado("async for sailor in Sailor.objects: seen(sailor)")
    await ado("Sailor.objects.get(name='Ada')")
    sys.setprofile(None)
    await sync_to_async(other_thread_ends)()


RULES = ASYNC
LISTENING = True
asyncio.run(asynchronous())
LISTENING = False
show("The asynchronous methods: the work is done by synchronous code on another thread")
