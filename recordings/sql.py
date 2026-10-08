"""A recording of the way from a queryset to a statement: what a Query holds, how a filter's
name becomes joins and a comparison, what an expression, a lookup and an aggregate write,
and how the compiler assembles and runs the statement.

    python recordings/sql.py > recordings/sql.txt

Chapter 10 of the book (pages/sql.md and the pages under it) is written against this
output. It needs only the pinned Django (the project's virtual environment has it) and the
small project beside it, `harbour/`, which chapters 8 and 9 record over too: a shipping line
in three applications, `fleet`, `crew` and `office`. The database is a SQLite file made for
the run. Run it again after a re-pin: where the output changes, the chapter has to.

In what follows a statement is always a statement of SQL, sent to the database; what the
script itself runs is called a line of Python.

The blocks are of three kinds, and a block may mix them. Where the order of calls is the
point, the lines are calls, nested as they were made: the calls a block is about and no
others, so everything between the lines ran and is left out. A line of Python (`q =
Sailor.objects.filter(ship__home__name='Bergen').query`) is what the script ran, as it ran
it. Under it stand the calls it set going, of those the block is about, and every statement
it sent: a line of Python with no `SQL` line under it sent none. Some lines of Python are
run with none of their calls written down, to make something a later line needs; the
statements they sent stand under them all the same. A method is written by the class that
declares it, whatever the class of the object. Its arguments follow, each parameter by its
name, and of those that have a default only the ones that were given another value; a
function of one parameter that has no default is written with the value alone. What a call
returned follows `->`, put into words at the moment it was returned; `raises` names an
exception, once, at the innermost written-down call it left, and again with its message
under the line of Python it ended. A call with neither after it returned something the
recording does not describe, or is a generator, which returns nothing until it is
exhausted. A generator's line is written once, where its body first runs.

A second kind of block puts one question to a running Django on each line: the text before
`->` is the expression that was evaluated and what follows is the repr of its value, and a
statement the question sent stands under it, as does a warning it set off, on a line that
begins `warns`. Where a question raised, the exception's name and message stand in place of
a value. The third kind writes down what an object holds, a thing to a line.

How things are put into words. A query is written by its class and model, `a Query of
Ship`; a queryset by its class, model and result cache. An expression is written as its
repr, which for most is the constructor that would make it: `F(name)`, `Col(fleet_ship,
fleet.Ship.name)`, `Value(480)`, `Lower(F(name))`, `Exact(Col(...), 480)`. A where tree is
written as its str, `(AND: ...)`, a path step of `names_to_path` as `PathInfo(from Model
to Model via Model.field, direct, many)`, an entry of the alias map as `Join(table, from
alias via Model.field, INNER JOIN, nullable)` or `BaseTable(table)`, a model's options as
`the options of Model`, and a field by its model and name, `Ship.home`. A statement's text
is the first value of what `SQLCompiler.as_sql` returned, and the second is its
parameters. A list of more than six things is written as its first two and how many more.

A line that begins `SQL` is a statement as Django handed it to its own cursor, with its
parameters where it has any: the placeholders are Django's `%s`, which SQLite's backend
rewrites before the driver sees them. The script stops if putting a call into words ever
sends a statement, so that no `SQL` line is this script's own doing.

A few helpers of the script's own stand in questions, so that a question can ask for a
statement without sending it. `sql_of(queryset)` is what the queryset's compiler's `as_sql`
returns, the statement and its parameters; `tail(queryset)` is the same from its FROM clause
on, with the select list, which is the model's columns, left out; `where_said(queryset)` is
the query's where tree; `entry(queryset)` is the first child of that tree, a lookup;
`said(thing)` is a thing put into words as this docstring describes; `aliases(query)` writes
the alias map, an entry to a line with its reference count; `converters_said(compiler)` and
`converter_names(expression)` name the converters by their functions, and the lambdas that
`BaseExpression.convert_value` returns by that method; and the lines `select[n]: ...`,
`annotation_col_map: ...` and `klass_info: ...` write down what a compiler holds after its
`as_sql`, in the order it holds it. Where a lookup, a where tree or a path is put into words,
a subquery inside it is written as `Exists(a Query of Sailor)` or `Subquery(...)`. A line
`SQLCompiler.as_sql  (as above)` stands for a call whose lines the block before it shows.

Three transforms of Django's that no field class registers at import, `Lower`, `Length` and
`Upper`, are registered on `CharField` early in the recording and stay registered; a block
says so where it is done. A transform of the script's own, `Shout`, is registered for one
block and taken off again. A few blocks switch a feature of the backend, or a constant, for
the block only, and their titles say so.

Nothing is written that differs between one run and the next on the same Python and the
same SQLite: no address in memory, no path on disk, no time read from the machine's clock
(`django.utils.timezone.now` is replaced by a function that returns 10 April 2026, 09:00
UTC), and a set is sorted before it is written. One block asks `explain()` of a query, and
what SQLite answers there is its planner's, the same for one build of SQLite.

What ran is SQLite's part as well as Django's. These are this backend's, and another's
would differ: `LIKE ... ESCAPE '\\'` for the pattern lookups and `REGEXP` for the regular
expressions; `django_datetime_extract`, `django_datetime_trunc` and their relatives,
functions Django registers with SQLite; `MAX` and `MIN` for `Greatest` and `Least`;
`RAND`; `STRFTIME(...)` for `Now`; `CAST(... AS NUMERIC)` around a decimal; the absence of
`FOR UPDATE`; the refusal of `DISTINCT ON`, and of an ordering or a limit inside a
compound statement; a compound statement nested as `SELECT * FROM (...)`; `INSERT OR
IGNORE`, `ON CONFLICT`, `RETURNING`, and a database default written out as its value;
`GROUP BY` listing every selected column; dates and datetimes among the parameters as
text; `0` and `1` for a comparison selected as a column; and the order of rows where a
statement has no `ORDER BY`, which is the choice of SQLite's planner.

    RECORD_EVERYTHING=django.db.models.sql python recordings/sql.py    every call in the modules with that prefix
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# `harbour` imports from this directory, as it would from a project's. The directory goes last
# on the path and not first, where Python puts a script's own: `http.py` in it has the name of
# a package of the standard library, which Django imports.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != HERE] + [HERE]

import atexit  # noqa: E402
import datetime  # noqa: E402
import decimal  # noqa: E402
import functools  # noqa: E402
import inspect  # noqa: E402
import json  # noqa: E402
import operator  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
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
    stack to a thread, so that a line is nested only under earlier lines of its own thread."""

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
SEEN = {}  # generator and coroutine frames already written down, each with its generator
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
LABELLING = False  # whether a call is being put into words at this moment: a statement sent then is a fault of this script's
LISTENING = False  # whether a statement sent to the database is written down
AFTER = {}  # (module, qualname) -> what to say of the value a call returned


def plain(frame) -> str:
    return short(frame.f_code.co_qualname)


def short(qualname: str) -> str:
    """A qualified name without the functions it is defined inside."""
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
            known = SEEN.get(id(frame))
            if known is not None and known() is frame.f_generator:
                STACK.append(frame)
                return
        flush()  # what the call before this one returned is said first
        global LABELLING
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
                LINES[at] += f"  raises {type(exception).__name__}"
            else:
                LINES.append("  " * depth + f"raises {type(exception).__name__}")


UNWINDING = unwinding.__code__
MONITOR = sys.monitoring.PROFILER_ID
sys.monitoring.use_tool_id(MONITOR, "recordings/sql.py")
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
        raise SystemExit(f"recordings/sql.py: this Python reports an exception leaving a function otherwise than expected: {LINES!r}")
    reset()
    RULES = {}


self_test()

ASKING = {}  # the names a statement or a question may use, and the names a statement binds


class Said(str):
    """An answer already put into words, to be written as it is and not as a string's repr."""

    __repr__ = str.__str__


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
            said = value if isinstance(value, Said) else repr(value)
        except Exception as raised:
            said = f"raises {type(raised).__name__}" + ("" if brief_ else f": {raised}")
    for warning in warned:
        LINES.append("  " * len(STACK) + f"warns {warning.category.__name__}: {warning.message}")
    LISTENING = listening
    LINES[before:] = ["  " * len(STACK) + f"{expression}  ->  {said}", *("  " + line for line in LINES[before:])]
    sys.setprofile(watching)


def do(statement: str) -> None:
    """A statement of Python, written down and then run, with what it sets going written
    under it. A name the statement binds can be used by the statements and questions after it."""
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
        LINES.append("  " * (len(STACK) - 1) + f"raises {type(raised).__name__}: {raised}")
    finally:
        flush()
        STACK.pop()
        LISTENING = listening
        sys.setprofile(watching)


def lines(statement: str) -> None:
    """A line of Python run with nothing written down but what it binds: for making a thing
    a block is about, out of the block."""
    exec(statement, ASKING)


# ---------------------------------------------------------------------------------------------
# Django is set up, the tables are made and the first rows put in them, none of it recorded.

django.setup()

from django.core.exceptions import EmptyResultSet, FieldError, FullResultSet  # noqa: E402
from django.db import connection, models  # noqa: E402
from django.db.models import (  # noqa: E402
    AnyValue, Avg, Case, Count, Exists, ExpressionWrapper, F, FilteredRelation, Func, Max, Min, OrderBy, OuterRef, Q, RowRange,
    StdDev, StringAgg, Subquery, Sum, Value, ValueRange, Variance, When, Window, WindowFrameExclusion,
)
from django.db.models.aggregates import Aggregate  # noqa: E402
from django.db.models.expressions import (  # noqa: E402
    BaseExpression, Col, ColPairs, CombinedExpression, DatabaseDefault, Expression, NegatedExpression, RawSQL, Ref, ResolvedOuterRef,
    Sliced, Star,
)
from django.db.models.fields import Field  # noqa: E402
from django.db.models.fields.related import ForeignObject  # noqa: E402
from django.db.models.fields.reverse_related import ForeignObjectRel  # noqa: E402
from django.db.models.functions import (  # noqa: E402
    Cast, Coalesce, Collate, Concat, DenseRank, Extract, NullIf, ExtractHour, ExtractYear, Greatest, Lag, Least, Length, Lower, Now, Ntile,
    Random, Rank, Round, RowNumber, Substr, Trunc, TruncDate, TruncMonth, Upper, UUID4, UUID7,
)
from django.db.models.lookups import Exact, In, IsNull, Lookup, Transform  # noqa: E402
from django.db.models.query_utils import PathInfo  # noqa: E402
from django.db.models.sql import Query  # noqa: E402
from django.db.models.sql.constants import CURSOR, MULTI, NO_RESULTS, ROW_COUNT, SINGLE  # noqa: E402
from django.db.models.sql.datastructures import BaseTable, Join  # noqa: E402
from django.db.models.sql.query import JoinInfo, JoinPromoter, RawQuery  # noqa: E402
from django.db.models.sql.subqueries import AggregateQuery, DeleteQuery, InsertQuery, UpdateQuery  # noqa: E402
from django.db.models.sql.where import WhereNode  # noqa: E402
from django.utils import timezone  # noqa: E402

from harbour.crew.models import Officer, Sailor, Veteran  # noqa: E402
from harbour.crew.models import Rank as CrewRank  # noqa: E402
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


def query_sent(execute, sql, params, many, context):
    if LABELLING:
        sys.stderr.write(f"recordings/sql.py: putting a call into words sent a statement to the database: {sql}\n")
        os._exit(1)
    if LISTENING:
        note(f"SQL {sql} with params {params!r}" if params else f"SQL {sql}")
    return execute(sql, params, many, context)


connection.execute_wrappers.append(query_sent)

with connection.schema_editor() as editor:
    for model in django.apps.apps.get_models():
        if not model._meta.proxy:
            editor.create_model(model)

bergen = Port.objects.create(name="Bergen", country="Norway")
leith = Port.objects.create(name="Leith", country="Scotland")
lisbon = Port.objects.create(name="Lisbon", country="Portugal")
petrel = Ship.objects.create(name="Petrel", tonnage=480, home=bergen)
gannet = Ship.objects.create(name="Gannet", tonnage=1200, home=leith)
ada = Sailor.objects.create(name="Ada", ship=petrel)
bram = Sailor.objects.create(name="Bram", ship=petrel)
cora = Officer.objects.create(name="Cora", ship=gannet, rank=CrewRank.MASTER)
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
Manifest.objects.create(voyage=spring, crates=40, kilos_each=25)

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
print("    Manifest: " + ", ".join(f"{m.serial} (voyage {m.voyage_id}, {m.crates} crates of {m.kilos_each} kg, {m.kilos} kg, stamped {m.stamped})" for m in Manifest.objects.order_by("serial")))
print()

ASKING.update(
    models=models, connection=connection, datetime=datetime, decimal=decimal, Decimal=decimal.Decimal,
    Q=Q, F=F, Value=Value, Count=Count, Sum=Sum, Max=Max, Min=Min, Avg=Avg, StdDev=StdDev, Variance=Variance, AnyValue=AnyValue,
    StringAgg=StringAgg, Exists=Exists, Subquery=Subquery, OuterRef=OuterRef, Case=Case, When=When, ExpressionWrapper=ExpressionWrapper,
    Func=Func, Window=Window, RowRange=RowRange, ValueRange=ValueRange, WindowFrameExclusion=WindowFrameExclusion, OrderBy=OrderBy,
    FilteredRelation=FilteredRelation, Aggregate=Aggregate, BaseExpression=BaseExpression, Expression=Expression, Col=Col, ColPairs=ColPairs,
    CombinedExpression=CombinedExpression, DatabaseDefault=DatabaseDefault, NegatedExpression=NegatedExpression, RawSQL=RawSQL, Ref=Ref,
    ResolvedOuterRef=ResolvedOuterRef, Sliced=Sliced, Star=Star, Field=Field, ForeignObject=ForeignObject,
    Cast=Cast, Coalesce=Coalesce, Collate=Collate, NullIf=NullIf, Concat=Concat, DenseRank=DenseRank, Extract=Extract, ExtractHour=ExtractHour, ExtractYear=ExtractYear,
    Greatest=Greatest, Lag=Lag, Least=Least, Length=Length, Lower=Lower, Now=Now, Ntile=Ntile, Random=Random, Rank=Rank, Round=Round,
    RowNumber=RowNumber, Substr=Substr, Trunc=Trunc, TruncDate=TruncDate, TruncMonth=TruncMonth, Upper=Upper, UUID4=UUID4, UUID7=UUID7,
    Exact=Exact, In=In, IsNull=IsNull, Lookup=Lookup, Transform=Transform, PathInfo=PathInfo, Query=Query, RawQuery=RawQuery,
    JoinInfo=JoinInfo, JoinPromoter=JoinPromoter, BaseTable=BaseTable, Join=Join, WhereNode=WhereNode,
    AggregateQuery=AggregateQuery, DeleteQuery=DeleteQuery, InsertQuery=InsertQuery, UpdateQuery=UpdateQuery,
    CURSOR=CURSOR, MULTI=MULTI, NO_RESULTS=NO_RESULTS, ROW_COUNT=ROW_COUNT, SINGLE=SINGLE,
    EmptyResultSet=EmptyResultSet, FullResultSet=FullResultSet, FieldError=FieldError,
    Port=Port, Ship=Ship, Voyage=Voyage, Sailor=Sailor, Officer=Officer, Veteran=Veteran,
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
    if isinstance(field, ForeignObjectRel):
        return f"the rel of {of_field(field.field)}"
    return f"{model.__name__}.{field.name}" if inspect.isclass(model) else f"an unbound {type(field).__name__}"


def queryset_said(queryset) -> str:
    fetched = queryset._result_cache
    return f"{a(type(queryset).__name__)} of {queryset.model.__name__}, " + ("no result cache" if fetched is None else f"a result cache of {len(fetched)}")


def path_said(info) -> str:
    return (f"PathInfo(from {info.from_opts.model.__name__} to {info.to_opts.model.__name__} via {of_field(info.join_field)}, "
            + ("direct" if info.direct else "reverse") + (", many" if info.m2m else ", one")
            + (f", filtered as {info.filtered_relation.alias!r}" if info.filtered_relation else "") + ")")


def join_said(entry) -> str:
    if isinstance(entry, Join):
        return (f"Join({entry.table_name}, from {entry.parent_alias} via {of_field(entry.join_field)}, {entry.join_type}, "
                + ("nullable" if entry.nullable else "not nullable") + (", filtered" if entry.filtered_relation else "") + ")")
    return f"BaseTable({entry.table_name})"


def instance_said(instance) -> str:
    if hasattr(type(instance), "name") and "name" not in vars(instance):
        return f"<{type(instance).__name__}: pk={instance.pk!r}>"
    return repr(instance)


def brief(value) -> str:
    """A value in few words."""
    if isinstance(value, models.Model):
        return instance_said(value)
    if isinstance(value, models.QuerySet):
        return queryset_said(value)
    if isinstance(value, Query):
        return f"{a(type(value).__name__)} of {value.model.__name__}" if value.model else a(type(value).__name__)
    if isinstance(value, models.Field):
        return of_field(value)
    if isinstance(value, ForeignObjectRel):
        return of_field(value)
    if isinstance(value, models.options.Options):
        return f"the options of {value.model.__name__}"
    if isinstance(value, PathInfo):
        return path_said(value)
    if isinstance(value, (Join, BaseTable)):
        return join_said(value)
    if isinstance(value, JoinInfo):
        return (f"JoinInfo(final_field={of_field(value.final_field)}, targets={brief(value.targets)}, opts={brief(value.opts)}, "
                f"joins={value.joins!r}, path={brief(value.path)}" + (", with transforms" if getattr(value.transform_function, "has_transforms", False) else "") + ")")
    if isinstance(value, WhereNode):
        return tree_said(value)
    if isinstance(value, Subquery):
        return f"{type(value).__name__}({brief(value.query)})"
    if type(value).__name__ in ("NothingNode", "ExtraWhere"):
        return a(type(value).__name__)
    if isinstance(value, DatabaseDefault):
        return f"DatabaseDefault({brief(value.expression)})"
    if isinstance(value, Lookup):
        return f"{type(value).__name__}({brief(value.lhs)}, {brief(value.rhs)})"
    if isinstance(value, (BaseExpression, Q, FilteredRelation, F)):
        return repr(value)
    if isinstance(value, (datetime.date, datetime.timedelta)):
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
    if isinstance(value, (str, bytes, int, float, bool, type(None), slice, range, decimal.Decimal)):
        return repr(value)
    return a(type(value).__name__)


def tree_said(node) -> str:
    """A where tree as its str, with each leaf put into words."""
    template = "(NOT (%s: %s))" if node.negated else "(%s: %s)"
    return template % (node.connector, ", ".join(tree_said(c) if isinstance(c, WhereNode) else brief(c) for c in node.children))


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


def generic(frame) -> str:
    said = given(frame)
    return f"{short(frame.f_code.co_qualname)}({said})" if said else short(frame.f_code.co_qualname)


def without(*leave_out):
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
WH = "django.db.models.sql.where"
DS = "django.db.models.sql.datastructures"
SUB = "django.db.models.sql.subqueries"
EX = "django.db.models.expressions"
LK = "django.db.models.lookups"
AG = "django.db.models.aggregates"
FN_DT = "django.db.models.functions.datetime"
FN_CMP = "django.db.models.functions.comparison"
FN_TXT = "django.db.models.functions.text"
QU = "django.db.models.query_utils"
RL = "django.db.models.fields.related_lookups"
TL = "django.db.models.fields.tuple_lookups"


def as_sql_said(frame, value) -> str:
    """What an as_sql returned: the SQL and its parameters, as (sql, params)."""
    sql, params = value
    return f"({sql!r}, {brief(tuple(params))})"


def sql_only(frame, value) -> str:
    return repr(value[0])


def aliases(query) -> None:
    """The alias map of a query, an entry to a line, with the reference count of each."""
    for alias, entry in query.alias_map.items():
        note(f"alias_map[{alias!r}]: {join_said(entry)}, referenced {query.alias_refcount[alias]}")


def select_said(compiler) -> None:
    for position, (column, (sql, params), alias) in enumerate(compiler.select):
        note(f"select[{position}]: {sql}" + (f"  as {alias}" if alias else "") + f"  ({brief(column)})")
    note(f"annotation_col_map: {compiler.annotation_col_map!r}")


def klass_said(info, depth: int = 0) -> None:
    if info is None:
        note("klass_info: None")
        return
    reached = ""
    if "field" in info:
        reached = f", reached by {of_field(info['field'])}, reverse={info['reverse']}, from_parent={info['from_parent']}"
    note("  " * depth + f"klass_info: model {info['model'].__name__}{reached}, select_fields {info['select_fields']}")
    for related in info.get("related_klass_infos", []):
        klass_said(related, depth + 1)


def converter_name(function) -> str:
    """A converter by its qualified name; the lambdas BaseExpression.convert_value returns by that method's."""
    return "BaseExpression.convert_value's lambda" if "<lambda>" in function.__qualname__ else short(function.__qualname__)


def converters_said(compiler) -> Said:
    found = compiler.get_converters([s[0] for s in compiler.select[: compiler.col_count]])
    return Said("{" + ", ".join(f"{pos}: [{', '.join(converter_name(c) for c in convs)}]" for pos, (convs, _) in found.items()) + "}")


def converter_names(expression) -> list:
    return [converter_name(c) for c in expression.get_db_converters(connection)]


def where_said(queryset) -> Said:
    return Said(tree_said(queryset.query.where))


def sql_of(queryset) -> tuple:
    """A queryset's statement and parameters from its compiler, as as_sql returns them."""
    sql, params = queryset.query.get_compiler("default").as_sql()
    return sql, tuple(params)


def tail(queryset) -> Said:
    """The same from its FROM clause on: the select list, which is the model's columns, left out."""
    sql, params = sql_of(queryset)
    at = sql.find(" FROM ")
    return Said(repr((sql[at + 1:] if at >= 0 else sql, params)))


def entry(queryset, position: int = 0):
    """A child of a queryset's where tree, the first unless another is asked for."""
    return queryset.query.where.children[position]


def said(value) -> Said:
    return Said(brief(value))


ASKING.update(said=said, tail=tail, aliases=aliases, converters_said=converters_said, converter_names=converter_names, where_said=where_said, sql_of=sql_of, entry=entry, brief=brief, Said=Said)

# ---------------------------------------------------------------------------------------------
# What a Query holds.

for name, value in vars(Query(Sailor)).items():
    note(f"{name}: {brief(value)}")
show("What a new Query holds: vars(Query(Sailor)), an attribute to a line")

for name, value in vars(Query).items():
    if not name.startswith("__") and not callable(value) and not isinstance(value, (property, functools.cached_property, classmethod, staticmethod)):
        note(f"{name}: {brief(value)}")
show("The class attributes a Query falls back on until something sets one on the instance: vars(Query), an attribute to a line")

lines("q = Sailor.objects.filter(ship__home__name='Bergen', signed_on__year__lt=2020).order_by('-signed_on').query")
ask("brief(q.model), q.default_cols, q.select, q.order_by, q.default_ordering, q.standard_ordering, q.low_mark, q.high_mark")
ask("where_said(Sailor.objects.filter(ship__home__name='Bergen', signed_on__year__lt=2020))")
ask("list(q.alias_map), q.alias_refcount, q.table_map, sorted(q.used_aliases)")
aliases(ASKING["q"])
ask("q.annotations, q.annotation_select, q.deferred_loading, q.group_by, q.combinator, q.subquery")
ask("str(q)")
ask("q.sql_with_params()")
show("The query of Sailor.objects.filter(ship__home__name='Bergen', signed_on__year__lt=2020).order_by('-signed_on'): what the two methods left on it")

lines("c = q.clone()")
ask("c is q, type(c) is type(q), c.model is q.model")
ask("c.where is q.where, c.where.children[0] is q.where.children[0], c.where.children[1].lhs is q.where.children[1].lhs")
ask("c.alias_map is q.alias_map, c.alias_map['fleet_ship'] is q.alias_map['fleet_ship'], c.alias_refcount is q.alias_refcount, c.table_map is q.table_map")
ask("c.order_by is q.order_by, c.select is q.select, c.deferred_loading is q.deferred_loading, c.annotations is q.annotations, c.used_aliases is q.used_aliases")
ask("sorted(vars(c)) == sorted(vars(q))")
lines("d = Ship.objects.select_related('home').annotate(hands=Count('crew')).query")
lines("e = d.clone()")
ask("e.select_related is d.select_related, e.select_related, e.annotations is d.annotations, e.annotations['hands'] is d.annotations['hands']")
ask("e.annotation_select_mask is d.annotation_select_mask, e._annotation_select_cache, d._annotation_select_cache is not None")
show("Query.clone: the containers are copied, and what they hold is shared")

lines("sticky = Sailor.objects.filter(ship__home__name='Bergen').query")
ask("sorted(sticky.used_aliases), sorted(sticky.chain().used_aliases)")
lines("sticky.filter_is_sticky = True")
ask("sorted(sticky.chain().used_aliases), sticky.chain().filter_is_sticky")
lines("u = Ship.objects.filter(tonnage__gt=500).query.chain(klass=UpdateQuery)")
ask("type(u).__name__, u.compiler, u.values, u.related_updates, u.related_ids, where_said(Ship.objects.filter(tonnage__gt=500))")
ask("type(Ship.objects.all().query.chain()).__name__, type(u.chain()).__name__, type(u.chain(klass=Query)).__name__")
show("Query.chain: a clone ready for the next method, with used_aliases emptied unless the filter is sticky, and perhaps of another class")

lines("raw = RawQuery('SELECT id, name FROM crew_sailor WHERE ship_id = %s', 'default', params=[1])")
ask("sorted(vars(raw)), raw.params_type.__name__, str(raw)")
ask("[row for row in raw]")
ask("raw.get_columns()")
ask("isinstance(raw, Query), raw.low_mark, raw.high_mark, raw.extra_select, raw.annotation_select")
show("A RawQuery: a statement and its parameters, with a few attributes of a Query mirrored for the compiler that reads its rows")

# ---------------------------------------------------------------------------------------------
# One filter, from the keyword argument to the where tree, and its query compiled and run.

BUILDING = watch(
    QS, "QuerySet.filter", "QuerySet._filter_or_exclude_inplace",
) | watch(
    SQ, "Query.add_q", "Query._add_q", "Query.build_filter", "Query.solve_lookup_type", "Query.names_to_path", "Query.resolve_lookup_value",
    "Query.setup_joins", "Query.join", "Query.table_alias", "Query.trim_joins", "Query.build_lookup", "Query.try_transform",
    "Query.check_related_objects", "Query.demote_joins", "Query.promote_joins", "JoinPromoter.__init__", "JoinPromoter.add_votes",
    "JoinPromoter.update_join_types",
) | watch(LK, "Lookup.__init__", "Lookup.get_prep_lookup") | watch(WH, "WhereNode.add", label=lambda f: f"WhereNode.add({brief(f.f_locals['data'])}, {f.f_locals['conn_type']!r})")
BUILDING[(SQ, "Query.names_to_path")] = without("opts")
BUILDING[(SQ, "Query.setup_joins")] = without("opts")
BUILDING[(SQ, "Query._add_q")] = lambda f: f"Query._add_q({brief(f.f_locals['q_object'])}, used_aliases={brief(f.f_locals['used_aliases'])})"
BUILDING[(SQ, "Query.build_filter")] = lambda f: f"Query.build_filter({brief(f.f_locals['filter_expr'])}" + (f", can_reuse={brief(f.f_locals['can_reuse'])}" if f.f_locals["can_reuse"] is not None else "") + (", branch_negated=True" if f.f_locals["branch_negated"] else "") + (", current_negated=True" if f.f_locals["current_negated"] else "") + ")"
BUILDING[(LK, "Lookup.__init__")] = lambda f: f"{type(f.f_locals['self']).__name__}.__init__(lhs={brief(f.f_locals['lhs'])}, rhs={brief(f.f_locals['rhs'])})  (Lookup.__init__)"
BUILDING[(LK, "Lookup.get_prep_lookup")] = lambda f: f"{type(f.f_locals['self']).__name__}.get_prep_lookup  (Lookup.get_prep_lookup)"
says(SQ, "Query.solve_lookup_type", "Query.names_to_path", "Query.setup_joins", "Query.trim_joins", "Query.build_lookup", "Query.try_transform",
     "Query.join", "Query.table_alias", "Query.resolve_lookup_value", "JoinPromoter.update_join_types", "Query.resolve_ref")
says(SQ, "Query.build_filter", how=lambda f, v: f"({brief(v[0])}, {brief(v[1])})")
says(SQ, "Query._add_q", how=lambda f, v: f"({brief(v[0])}, {brief(v[1])})")
says(LK, "Lookup.get_prep_lookup")
says(QS, "QuerySet.filter", how=lambda f, v: queryset_said(v))

with recorded(BUILDING):
    do("bergen_veterans = Sailor.objects.filter(ship__home__name='Bergen', signed_on__year__lt=2020)")
ask("where_said(bergen_veterans)")
show("One filter, from the keyword arguments to the where tree")

COMPILING = watch(
    CO, "SQLCompiler.as_sql", "SQLCompiler.pre_sql_setup", "SQLCompiler.setup_query", "SQLCompiler.get_select", "SQLCompiler.get_default_columns",
    "SQLCompiler.get_order_by", "SQLCompiler._order_by_pairs", "SQLCompiler.find_ordering_name", "SQLCompiler.get_extra_select", "SQLCompiler.get_group_by",
    "SQLCompiler.get_distinct", "SQLCompiler.get_from_clause", "SQLCompiler.get_combinator_sql", "SQLCompiler.get_qualify_sql",
    "SQLCompiler.execute_sql", "SQLCompiler.results_iter", "SQLCompiler.get_converters", "SQLCompiler.apply_converters",
) | watch(
    SQ, "Query.get_compiler", "Query.setup_joins", "Query.trim_joins", "Query.reset_refcounts",
) | watch(WH, "WhereNode.split_having_qualify", "WhereNode.as_sql") | watch(DS, "Join.as_sql", "BaseTable.as_sql") | watch(
    LK, "BuiltinLookup.as_sql", "Lookup.process_lhs", "Lookup.process_rhs", "YearLookup.as_sql", "BuiltinLookup.process_lhs",
) | watch(EX, "Col.as_sql", "OrderBy.as_sql", "Func.as_sql") | {
    (CO, "SQLCompiler.compile"): lambda f: f"SQLCompiler.compile({brief(f.f_locals['node'])})",
    ("django.db.backends.base.operations", "BaseDatabaseOperations.limit_offset_sql"): generic,
    ("django.db.backends.utils", "CursorWrapper.execute"): lambda f: "CursorWrapper.execute",
}
COMPILING[(SQ, "Query.setup_joins")] = without("opts")
COMPILING[(LK, "Lookup.process_lhs")] = lambda f: f"{type(f.f_locals['self']).__name__}.process_lhs  (Lookup.process_lhs)"
COMPILING[(LK, "Lookup.process_rhs")] = lambda f: f"{type(f.f_locals['self']).__name__}.process_rhs  (Lookup.process_rhs)"
COMPILING[(LK, "BuiltinLookup.as_sql")] = lambda f: f"{type(f.f_locals['self']).__name__}.as_sql  (BuiltinLookup.as_sql)"
COMPILING[(LK, "BuiltinLookup.process_lhs")] = lambda f: f"{type(f.f_locals['self']).__name__}.process_lhs  (BuiltinLookup.process_lhs)"
COMPILING[(LK, "YearLookup.as_sql")] = lambda f: f"{type(f.f_locals['self']).__name__}.as_sql  (YearLookup.as_sql)"
COMPILING[(EX, "Func.as_sql")] = lambda f: f"{type(f.f_locals['self']).__name__}.as_sql  (Func.as_sql)"
COMPILING[(CO, "SQLCompiler.get_select")] = without("with_col_aliases")
COMPILING[(CO, "SQLCompiler.as_sql")] = without("with_limits")
COMPILING[(CO, "SQLCompiler.pre_sql_setup")] = plain
COMPILING[(CO, "SQLCompiler.setup_query")] = plain
COMPILING[(CO, "SQLCompiler.get_default_columns")] = without("select_mask")
COMPILING[(CO, "SQLCompiler.get_order_by")] = plain
COMPILING[(CO, "SQLCompiler._order_by_pairs")] = plain
COMPILING[(CO, "SQLCompiler.find_ordering_name")] = without("opts", "alias", "already_seen")
COMPILING[(CO, "SQLCompiler.get_extra_select")] = plain
COMPILING[(CO, "SQLCompiler.get_group_by")] = plain
COMPILING[(CO, "SQLCompiler.get_distinct")] = plain
COMPILING[(CO, "SQLCompiler.get_from_clause")] = plain
COMPILING[(CO, "SQLCompiler.get_converters")] = plain
COMPILING[(CO, "SQLCompiler.apply_converters")] = plain
COMPILING[(CO, "SQLCompiler.results_iter")] = plain
COMPILING[(CO, "SQLCompiler.execute_sql")] = generic
COMPILING[(WH, "WhereNode.split_having_qualify")] = plain
COMPILING[(WH, "WhereNode.as_sql")] = plain
COMPILING[(DS, "Join.as_sql")] = plain
COMPILING[(DS, "BaseTable.as_sql")] = plain
COMPILING[(EX, "Col.as_sql")] = lambda f: f"Col.as_sql  ({brief(f.f_locals['self'])})"
COMPILING[(EX, "OrderBy.as_sql")] = plain
says(CO, "SQLCompiler.as_sql", "SQLCompiler.compile", "SQLCompiler.get_from_clause", how=as_sql_said)
says(CO, "SQLCompiler.get_select", how=lambda f, v: f"({len(v[0])} columns, klass_info for {v[1]['model'].__name__ if v[1] else None}, {v[2]!r})")
says(CO, "SQLCompiler.get_order_by", how=lambda f, v: "[" + ", ".join(repr(sql) for _, (sql, _, _) in v) + "]")
says(CO, "SQLCompiler.get_group_by", how=lambda f, v: "[" + ", ".join(repr(sql) for sql, _ in v) + "]")
says(CO, "SQLCompiler.get_distinct", how=lambda f, v: f"({v[0]!r}, {v[1]!r})")
says(CO, "SQLCompiler.get_extra_select", how=lambda f, v: f"[{len(v)} extra]" if v else "[]")
says(CO, "SQLCompiler.pre_sql_setup", how=lambda f, v: f"(extra_select of {len(v[0])}, order_by of {len(v[1])}, group_by of {len(v[2])})")
says(CO, "SQLCompiler.get_default_columns", how=lambda f, v: brief(v))
says(CO, "SQLCompiler.find_ordering_name", how=lambda f, v: brief([expr for expr, _ in v]))
says(CO, "SQLCompiler._order_by_pairs", how=None)
says(WH, "WhereNode.split_having_qualify", how=lambda f, v: f"({brief(v[0])}, {brief(v[1])}, {brief(v[2])})")
says(WH, "WhereNode.as_sql", how=as_sql_said)
says(DS, "Join.as_sql", "BaseTable.as_sql", how=as_sql_said)
says(LK, "BuiltinLookup.as_sql", "YearLookup.as_sql", "Lookup.process_lhs", "Lookup.process_rhs", "BuiltinLookup.process_lhs", how=as_sql_said)
says(EX, "Col.as_sql", "OrderBy.as_sql", "Func.as_sql", how=as_sql_said)
says("django.db.backends.base.operations", "BaseDatabaseOperations.limit_offset_sql")
says(SQ, "Query.get_compiler", how=lambda f, v: a(type(v).__name__))
says(CO, "SQLCompiler.get_converters", how=lambda f, v: "{" + ", ".join(f"{pos}: [{', '.join(converter_name(c) for c in convs)}]" for pos, (convs, _) in v.items()) + "}")

lines("by_date = Sailor.objects.filter(ship__home__name='Bergen', signed_on__year__lt=2020).order_by('-signed_on')[:5]")
with recorded(COMPILING):
    do("compiler = by_date.query.get_compiler('default')")
    do("compiler.as_sql()")
show("The same query compiled: the clauses in the order the compiler makes them, and the statement they are assembled into")

RUNNING = {k: v for k, v in COMPILING.items() if k[1] in ("SQLCompiler.execute_sql", "SQLCompiler.results_iter", "SQLCompiler.get_converters", "SQLCompiler.apply_converters", "CursorWrapper.execute")}
RUNNING[(CO, "SQLCompiler.as_sql")] = lambda f: "SQLCompiler.as_sql  (as above)"
with recorded(RUNNING):
    do("rows = list(compiler.results_iter())")
ask("rows")
show("The compiled query run: execute_sql sends the statement, and results_iter hands the rows on with their converters applied")

# ---------------------------------------------------------------------------------------------
# Expressions.

lines("q = Ship.objects.all().query")
ask("F('tonnage').resolve_expression(q)")
ask("F('home').resolve_expression(q), list(q.alias_map)")
ask("F('home__name').resolve_expression(q), list(q.alias_map)")
ask("F('name__lower').resolve_expression(q)")
ask("F('cargo').resolve_expression(q)")
ask("F('crew').resolve_expression(q), list(q.alias_map)")
lines("annotated = Ship.objects.annotate(hands=Count('crew')).query")
ask("F('hands').resolve_expression(annotated)")
show("F resolved against a query: resolve_ref returns a Col, joining tables as it goes, or the annotation the name refers to")

ask("[type(Value(v).output_field).__name__ for v in ('x', True, 1, 1.5, datetime.date(2026, 4, 10), datetime.datetime(2026, 4, 10, 9), datetime.timedelta(days=1), Decimal('1.5'), b'x')]")
ask("Value(None).output_field")
ask("Value(None)._output_field_or_none, Value([1, 2])._output_field_or_none")
ask("Value(480).as_sql(None, connection), Value(None).as_sql(None, connection), Value('Ada', output_field=models.CharField()).as_sql(None, connection)")
ask("Value(480).resolve_expression(q).for_save, Value(480).resolve_expression(q, for_save=True).for_save, Value(480).for_save")
ask("Value(Decimal('1.5')).as_sqlite(None, connection), Value(1.5, output_field=models.DecimalField()).as_sqlite(None, connection)")
ask("Value(480).get_group_by_cols(), Value(480).empty_result_set_value, Value(480).allowed_default")
show("Value: the output field it infers from its value, and the placeholder it writes")

lines("plus = F('tonnage') + 1")
ask("type(plus).__name__, plus.lhs, plus.connector, plus.rhs, plus.get_source_expressions()")
ask("type(plus.resolve_expression(q).output_field).__name__, type((F('tonnage') * F('tonnage')).resolve_expression(q).output_field).__name__, type((F('tonnage') + 1.5).resolve_expression(q).output_field).__name__")
ask("type((F('tonnage') - 1).resolve_expression(q).output_field).__name__")
ask("(F('name') + 1).resolve_expression(q).output_field")
ask("(F('name') + 1).resolve_expression(q)")
ask("type((F('sailed') - F('sailed')).resolve_expression(Voyage.objects.all().query)).__name__, type((F('sailed') - F('sailed')).resolve_expression(Voyage.objects.all().query).output_field).__name__")
ask("type((F('sailed') + datetime.timedelta(days=7)).resolve_expression(Voyage.objects.all().query)).__name__, type((F('sailed') + datetime.timedelta(days=7)).resolve_expression(Voyage.objects.all().query).output_field).__name__")
ask("(F('tonnage') + 1).resolve_expression(q).as_sql(q.get_compiler('default'), connection)")
ask("(F('tonnage') ** 2).resolve_expression(q).as_sql(q.get_compiler('default'), connection), (F('tonnage') % 7).resolve_expression(q).as_sql(q.get_compiler('default'), connection)")
ask("(F('tonnage').bitand(4)).resolve_expression(q).as_sql(q.get_compiler('default'), connection), (-F('tonnage')).resolve_expression(q).as_sql(q.get_compiler('default'), connection)")
ask("F('tonnage') & F('home')")
ask("type(Q(tonnage__gt=1) & Exists(Sailor.objects.all())).__name__, type(Exists(Sailor.objects.all()) & Exists(Voyage.objects.all())).__name__, type(~Exists(Sailor.objects.all())).__name__")
ask("1 + F('tonnage'), (1 + F('tonnage')).lhs, F('tonnage')[2:4], F('name')[0]")
show("Combinable and CombinedExpression: what the operators make, and the output field of an arithmetic expression")

ask("F('name') == F('name'), F('name') == F('tonnage'), Value(1) == Value(1), Value(1) == Value('1'), Lower('name') == Lower('name'), Lower('name') == Upper('name')")
ask("Count('crew') == Count('crew'), Count('crew') == Count('crew', distinct=True), Count('crew').identity")
ask("Exact(Col('fleet_ship', Ship._meta.get_field('name')), 'x') == Exact(Col('fleet_ship', Ship._meta.get_field('name')), 'x'), Exact(Col('fleet_ship', Ship._meta.get_field('name')), 'x').identity")
ask("len({F('name'), F('name'), Lower('name'), Lower('name'), Value(1)})")
show("Identity: two expressions made the same way are equal, and hash alike")

lines("low = Lower('name')")
lines("resolved = low.resolve_expression(q)")
ask("resolved is low, low.source_expressions, resolved.source_expressions, resolved.is_summary")
ask("low.get_source_expressions(), resolved.output_field, type(resolved.output_field).__name__")
ask("Coalesce('tonnage', 0).resolve_expression(q).get_source_expressions()")
ask("Case(When(tonnage__gt=1000, then=Value('big')), default=Value('small')).resolve_expression(q)")
ask("Case(When(tonnage__gt=1000, then=Value('big')), default=Value('small')).resolve_expression(q).cases[0].condition")
ask("list(Case(When(tonnage__gt=1000, then=Value('big')), default=Value('small')).resolve_expression(q).flatten())")
ask("resolved.contains_aggregate, resolved.contains_over_clause, resolved.contains_column_references, resolved.conditional, resolved.filterable, resolved.window_compatible")
ask("Count('crew').contains_aggregate, Window(RowNumber()).contains_over_clause, Window(RowNumber()).contains_aggregate, Value(1).contains_column_references, Q(tonnage__gt=1).conditional, Exists(Sailor.objects.all()).conditional")
ask("resolved.relabeled_clone({'fleet_ship': 'T9'}), resolved.replace_expressions({F('name'): Value('x')}), low.replace_expressions({F('name'): Value('x')})")
show("resolve_expression: a copy whose sources are resolved, and what the copy can tell about itself")

lines("compiler = q.get_compiler('default')")
ask("compiler.compile(Greatest('tonnage', 1000).resolve_expression(q)), compiler.compile(Least('tonnage', 1000).resolve_expression(q))")
ask("compiler.compile(Cast('tonnage', models.FloatField()).resolve_expression(q)), compiler.compile(Cast('name', models.DateField()).resolve_expression(q))")
ask("compiler.compile(Func(F('name'), function='UPPER').resolve_expression(q))")
ask("compiler.compile(Func(F('name'), Value('!'), function='CONCAT', arg_joiner=' || ', template='(%(expressions)s)').resolve_expression(q))")
ask("compiler.compile(ExpressionWrapper(F('tonnage') * 2, output_field=models.DecimalField()).resolve_expression(q))")
ask("compiler.compile(ExpressionWrapper(F('tonnage') * 2, output_field=models.IntegerField()).resolve_expression(q))")
ask("compiler.compile(NegatedExpression(Q(tonnage__gt=1000)).resolve_expression(q))")
ask("NegatedExpression(F('tonnage')).resolve_expression(q)")
ask("compiler.compile(Case(When(tonnage__gt=1000, then=Value('big')), default=Value('small')).resolve_expression(q))")
ask("compiler.compile(Case(When(tonnage__gt=1000, then=Value('big')), output_field=models.CharField()).resolve_expression(q))")
ask("compiler.compile(Case(When(Q(pk__in=[]), then=Value('never')), default=Value('always')).resolve_expression(q))")
ask("compiler.compile(Case(When(Q(), then=Value('x')), default=Value('y')).resolve_expression(q))")
ask("When(tonnage__gt=1)")
ask("When(F('tonnage'), then=1)")
ask("Case(Value(1))")
ask("compiler.compile(RawSQL('tonnage * %s', (2,)))")
ask("compiler.compile(Ref('hands', Count('crew'))), compiler.compile(Star())")
ask("compiler.compile(DatabaseDefault(Value(False)).resolve_expression(q, for_save=True)), DatabaseDefault(Value(False)).resolve_expression(q)")
ask("compiler.compile(Sliced(F('name'), slice(0, 3)).resolve_expression(q)), compiler.compile(F('name')[1].resolve_expression(q))")
ask("Sliced(F('name'), -1)")
show("as_sql through the compiler: what a Func, a Cast, a Case, an ExpressionWrapper, a NegatedExpression and the other small expressions write on SQLite")

ask("Length('name').output_field, Coalesce('tonnage', 0).resolve_expression(q).output_field, type(Coalesce('tonnage', 0).resolve_expression(q).output_field).__name__")
ask("Coalesce('name', 0).resolve_expression(q).output_field")
ask("type(Func(F('name'), function='X').resolve_expression(q).output_field).__name__, type(Avg('tonnage').resolve_expression(q).output_field).__name__, type(Sum('tonnage').resolve_expression(q).output_field).__name__")
ask("Func(Value(None), function='X').output_field")
ask("Func(Value(None), function='X')._output_field_or_none")
ask("Func(Value(None), function='X').conditional")
ask("ExpressionWrapper(F('tonnage') * 1.5, output_field=models.FloatField()).resolve_expression(q).convert_value(2.0, None, connection), Sum('tonnage').resolve_expression(q).convert_value is BaseExpression._convert_value_noop")
ask("[(brief(e), converter_names(e)) for e in (Lower('name').resolve_expression(q), Cast('tonnage', models.FloatField()).resolve_expression(q), Cast('name', models.DateField()).resolve_expression(q), Count('crew').resolve_expression(q))]")
show("The output field of an expression: declared on the class, given at construction, inferred from the sources, or missing")

# ---------------------------------------------------------------------------------------------
# From a name to a column.

ask("said(Sailor.objects.all().query.names_to_path(['name'], Sailor._meta))")
ask("said(Sailor.objects.all().query.names_to_path(['pk'], Sailor._meta))")
ask("said(Sailor.objects.all().query.names_to_path(['ship'], Sailor._meta))")
ask("said(Sailor.objects.all().query.names_to_path(['ship', 'home', 'name'], Sailor._meta))")
ask("said(Sailor.objects.all().query.names_to_path(['ship', 'home', 'name', 'lower', 'exact'], Sailor._meta))")
ask("said(Ship.objects.all().query.names_to_path(['crew', 'name'], Ship._meta))")
ask("said(Voyage.objects.all().query.names_to_path(['calls', 'country'], Voyage._meta))")
ask("said(Sailor.objects.all().query.names_to_path(['pilots_into', 'country'], Sailor._meta))")
ask("said(Officer.objects.all().query.names_to_path(['name'], Officer._meta))")
ask("said(Sailor.objects.all().query.names_to_path(['officer', 'rank'], Sailor._meta))")
ask("said(Ship.objects.all().query.names_to_path(['captain', 'officer', 'rank'], Ship._meta))")
ask("said(Berth.objects.all().query.names_to_path(['pk'], Berth._meta))")
ask("said(Ship.objects.annotate(hands=Count('crew')).query.names_to_path(['hands', 'gt'], Ship._meta))")
show("names_to_path, name by name: the path of joins, the final field, the target fields, and the names left over")

ask("said(Ship.objects.all().query.names_to_path(['crew', 'name'], Ship._meta, allow_many=False))", brief_=True)
ask("said(Voyage.objects.all().query.names_to_path(['ship', 'name'], Voyage._meta, allow_many=False))")
ask("said(Sailor.objects.all().query.names_to_path(['cargo'], Sailor._meta))")
ask("said(Sailor.objects.all().query.names_to_path(['ship', 'cargo'], Sailor._meta))")
ask("said(Sailor.objects.all().query.names_to_path(['name', 'ship'], Sailor._meta))")
ask("said(Sailor.objects.all().query.names_to_path(['name', 'ship'], Sailor._meta, fail_on_missing=True))")
show("names_to_path refusing: a multi-valued relation where none is allowed, a name that is no field, and a name after a field that is no relation")

ask("Sailor.objects.all().query.solve_lookup_type('name')")
ask("Sailor.objects.all().query.solve_lookup_type('ship__home__name__lower__startswith')")
ask("Sailor.objects.all().query.solve_lookup_type('signed_on__year__lt')")
ask("Ship.objects.annotate(hands=Count('crew')).query.solve_lookup_type('hands__gt')")
ask("Ship.objects.annotate(hands=Count('crew')).query.solve_lookup_type('hands__gt', summarize=True)")
ask("Ship.objects.annotate(crew__count=Count('crew')).query.solve_lookup_type('crew__count__gt')")
ask("Sailor.objects.all().query.solve_lookup_type('name__lower__upper__exact__gt')")
show("solve_lookup_type: the lookups, the field parts, and an annotation where the name refers to one")

SEARCHING = watch(SQ, "Query.setup_joins", "Query.names_to_path", "Query.try_transform", "Query.resolve_ref") | watch(EX, "F.resolve_expression")
SEARCHING[(SQ, "Query.setup_joins")] = without("opts")
SEARCHING[(SQ, "Query.names_to_path")] = without("opts")
SEARCHING[(EX, "F.resolve_expression")] = lambda f: f"F.resolve_expression  ({brief(f.f_locals['self'])})"
says(EX, "F.resolve_expression")

with recorded(SEARCHING):
    do("Sailor.objects.annotate(year=F('signed_on__year')).query.annotations['year']")
    do("Sailor.objects.annotate(port=F('ship__home__name__upper')).query.annotations['port']")
show("setup_joins on a name with transforms: names_to_path is tried on shorter and shorter prefixes until one is all fields")

ask("sql_of(Sailor.objects.filter(ship=petrel))")
ask("sql_of(Sailor.objects.filter(ship__home=bergen))")
ask("sql_of(Sailor.objects.filter(ship__home__name='Bergen'))")
ask("sql_of(Sailor.objects.filter(ship__id=1)), sql_of(Sailor.objects.filter(ship__pk=1))")
ask("sql_of(Ship.objects.filter(crew=ada))")
ask("sql_of(Voyage.objects.filter(calls=leith))")
ask("sql_of(Sailor.objects.filter(ship__crew=ada))")
show("trim_joins: a join whose only use is the key the previous table already holds is taken away again")

JOINING = watch(SQ, "Query.setup_joins", "Query.join", "Query.table_alias", "Query.trim_joins", "Query.unref_alias", "Query.ref_alias")
JOINING[(SQ, "Query.setup_joins")] = without("opts")
JOINING[(SQ, "Query.names_to_path")] = without("opts")

with recorded(JOINING):
    do("to_bergen = Sailor.objects.filter(ship__home=bergen)")
aliases(ASKING["to_bergen"].query)
show("setup_joins and trim_joins for ship__home=bergen: two joins made, one taken back")

ask("models.CharField.get_lookups().get('lower'), models.CharField.get_lookups().get('length')")
quietly("models.CharField.register_lookup(Lower); models.CharField.register_lookup(Length); models.CharField.register_lookup(Upper)")
ask("models.CharField.get_lookups().get('lower').__name__")
show("Lower, Length and Upper registered on CharField for the rest of the recording: the text functions are transforms, but none is registered on a field class at import")

ask("sql_of(Sailor.objects.filter(signed_on__year=2011))")
ask("sql_of(Sailor.objects.filter(name__lower='ada'))")
ask("sql_of(Sailor.objects.filter(name__lower__startswith='a'))")
ask("sql_of(Sailor.objects.filter(name__upper__lower__length__gt=2))")
ask("Sailor.objects.filter(name__shouted='ada')")
ask("Sailor.objects.filter(name__lower__shouted='ada')")
ask("Sailor.objects.filter(name__exact__exact='ada')")
ask("Sailor.objects.filter(signed_on__yaer=2011)")
ask("Sailor.objects.filter(ship__contains=1)")
ask("Sailor.objects.filter(name__ship='Ada')")
show("build_lookup and try_transform: every word but the last is a transform, the last is a lookup or, failing that, a transform and exact")

ask("sql_of(Ship.objects.filter(captain=None)), entry(Ship.objects.filter(captain=None))")
ask("tail(Ship.objects.filter(captain__exact=None)), tail(Ship.objects.filter(name__iexact=None))")
ask("Ship.objects.filter(captain__gt=None)")
ask("sql_of(Ship.objects.filter(captain__in=[None, 1]))")
ask("sql_of(Ship.objects.filter(name=''))")
ask("connection.features.interprets_empty_strings_as_nulls")
show("build_lookup with None: exact and iexact become isnull, the other lookups refuse it")

ask("Sailor.objects.all().query.resolve_ref('name')")
ask("Sailor.objects.all().query.resolve_ref('ship'), Sailor.objects.all().query.resolve_ref('ship__name')")
ask("Sailor.objects.all().query.resolve_ref('name__lower'), Sailor.objects.all().query.resolve_ref('name__lower__length')")
ask("Sailor.objects.annotate(hands=Count('pk')).query.resolve_ref('hands')")
ask("Sailor.objects.annotate(hands=Count('pk')).query.resolve_ref('hands', summarize=True)")
ask("Sailor.objects.alias(hands=Count('pk')).query.resolve_ref('hands', summarize=True)")
ask("Sailor.objects.all().query.resolve_ref('ship__name', allow_joins=False)")
ask("Berth.objects.all().query.resolve_ref('pk')")
ask("Sailor.objects.all().query.resolve_ref('pilots_into')")
show("resolve_ref: what an F finds under a name")

ask("sql_of(Officer.objects.filter(rank='master'))")
ask("sql_of(Officer.objects.filter(name='Cora'))")
ask("sql_of(Sailor.objects.filter(officer__rank='master'))")
ask("sql_of(Veteran.objects.filter(name='Ada'))")
ask("Officer.objects.all().query.get_meta() is Officer._meta, said(Officer._meta.get_path_to_parent(Sailor)), Officer._meta.get_base_chain(Sailor), Veteran._meta.get_path_to_parent(Sailor)")
show("A field the parent holds: names_to_path adds the path to the parent, and join_parent_model joins its table")

# ---------------------------------------------------------------------------------------------
# Tables, aliases and joins.

lines("once = Voyage.objects.filter(calls__name='Leith', calls__country='Scotland')")
aliases(ASKING["once"].query)
ask("tail(once)")
lines("twice = Voyage.objects.filter(calls__name='Leith').filter(calls__country='Scotland')")
aliases(ASKING["twice"].query)
ask("twice.query.table_map, sorted(twice.query.used_aliases)")
ask("tail(twice)")
lines("direct = Sailor.objects.filter(ship__name='Petrel').filter(ship__tonnage__lt=500)")
aliases(ASKING["direct"].query)
show("The alias map after one filter with two conditions on a many-to-many relation, after two filters, and after two filters across a foreign key")

lines("j = twice.query.alias_map['T4']")
ask("j.table_name, j.parent_alias, j.table_alias, j.join_type, j.join_cols, j.nullable, j.filtered_relation, brief(j.join_field)")
ask("j.identity == twice.query.alias_map['fleet_voyage_calls'].identity, j == twice.query.alias_map['fleet_voyage_calls'], j.relabeled_clone({'T4': 'T9'}).table_alias, j.promote().join_type, j.demote().join_type")
ask("twice.query.alias_map['fleet_voyage'].identity, twice.query.alias_map['fleet_voyage'].join_type, twice.query.alias_map['fleet_voyage'].parent_alias")
ask("twice.query.base_table, twice.query.get_initial_alias(), twice.query.alias_refcount['fleet_voyage']")
ask("twice.query.count_active_tables()")
show("A Join and a BaseTable: what each holds, and what makes two joins equal")

ask("tail(Ship.objects.filter(captain__name='Cora'))")
ask("tail(Ship.objects.annotate(master=F('captain__name')))")
ask("tail(Ship.objects.filter(Q(captain__name='Cora') | Q(tonnage__lt=500)))")
ask("tail(Ship.objects.filter(Q(captain__name='Cora') | Q(captain__name='Dag')))")
ask("tail(Ship.objects.filter(Q(captain__name='Cora') | Q(tonnage__lt=500)).filter(captain__signed_on__year=2011))")
ask("tail(Sailor.objects.filter(Q(ship__home__name='Bergen') | Q(name='Dag')))")
ask("tail(Ship.objects.filter(Q(captain__ship__name='Petrel') | Q(name='Gannet')))")
ask("tail(Ship.objects.filter(crew__name='Ada'))")
ask("tail(Ship.objects.filter(~Q(captain__name='Cora') & ~Q(captain__name='Dag')))")
show("Join types: a nullable foreign key and a reverse relation are joined LEFT OUTER, an AND demotes to INNER, an OR keeps the outer join, and a non-nullable key is never promoted")

PROMOTING = watch(SQ, "Query.add_q", "Query._add_q", "Query.join", "Query.promote_joins", "Query.demote_joins", "JoinPromoter.__init__", "JoinPromoter.add_votes", "JoinPromoter.update_join_types")
PROMOTING[(SQ, "Query._add_q")] = lambda f: f"Query._add_q({brief(f.f_locals['q_object'])}" + (", branch_negated=True" if f.f_locals["branch_negated"] else "") + (", current_negated=True" if f.f_locals["current_negated"] else "") + ")"
PROMOTING[(SQ, "Query.join")] = lambda f: f"Query.join({brief(f.f_locals['join'])})"
says(SQ, "Query.join", "JoinPromoter.update_join_types")

with recorded(PROMOTING):
    do("either = Ship.objects.filter(Q(captain__name='Cora') | Q(tonnage__lt=500))")
aliases(ASKING["either"].query)
with recorded(PROMOTING):
    do("narrowed = either.filter(captain__signed_on__year=2011)")
aliases(ASKING["narrowed"].query)
with recorded(PROMOTING):
    do("neither = Ship.objects.filter(~(Q(captain__name='Cora') | Q(captain__name='Dag')))")
aliases(ASKING["neither"].query)
show("JoinPromoter: the votes of an OR promote a join, a later AND demotes it, and a negated OR is treated as an AND")

lines("left = Voyage.objects.filter(calls__name='Leith').query")
lines("right = Voyage.objects.filter(calls__name='Lisbon').query")
ask("list(left.alias_map), list(right.alias_map), right.alias_prefix, sorted(right.subq_aliases)")
lines("bumped = right.clone(); bumped.bump_prefix(left, exclude={'fleet_voyage'})")
ask("list(bumped.alias_map), bumped.alias_prefix, sorted(bumped.subq_aliases), sorted(left.subq_aliases)")
ask("bumped.table_map, bumped.alias_refcount, said(bumped.where)")
ask("list(right.relabeled_clone({'fleet_voyage_calls': 'C1', 'fleet_port': 'C2'}).alias_map), str(right.relabeled_clone({'fleet_voyage_calls': 'C1', 'fleet_port': 'C2'}).where)")
show("bump_prefix and change_aliases: the aliases of a query that is to stand inside another are renamed to a prefix the outer query does not use")

ask("sql_of(Sailor.objects.extra(tables=['fleet_ship'], where=['fleet_ship.id = crew_sailor.ship_id']))")
ask("tail(Ship.objects.filter(crew__name='Ada').annotate(hands=Count('crew')))")
show("get_from_clause: every entry of the alias map that is still referenced, and the extra tables after them")

# ---------------------------------------------------------------------------------------------
# The where clause.

with recorded(BUILDING):
    do("mixed = Ship.objects.filter(Q(home__name='Bergen') | Q(tonnage__gt=1000), ~Q(name='Skua'))")
ask("where_said(mixed)")
ask("sql_of(mixed)")
show("add_q with OR inside AND and a negation: each Q becomes a WhereNode, nested as the Q was")

ask("tail(Ship.objects.exclude(tonnage=480))")
ask("tail(Ship.objects.exclude(captain=None))")
ask("tail(Ship.objects.exclude(captain__name='Cora'))")
ask("tail(Ship.objects.exclude(captain__name__in=['Cora', None]))")
ask("tail(Sailor.objects.exclude(ship__captain=None))")
ask("tail(Ship.objects.exclude(tonnage=F('home__id')))")
ask("tail(Ship.objects.exclude(captain=F('home')))")
show("build_filter under a negation: an IS NOT NULL is added for a nullable column, so that NOT behaves as Python's not")

EXCLUDING = BUILDING | watch(SQ, "Query.split_exclude", "Query.trim_start", "Query.add_filter", "Query.bump_prefix") | {(SQ, "Query.names_to_path"): None}
del EXCLUDING[(SQ, "Query.names_to_path")]
EXCLUDING[(SQ, "Query.split_exclude")] = lambda f: f"Query.split_exclude(filter_expr={brief(f.f_locals['filter_expr'])}, can_reuse={brief(f.f_locals['can_reuse'])}, names_with_path={brief([(n, p) for n, p in f.f_locals['names_with_path']])})"
EXCLUDING[(SQ, "Query.trim_start")] = lambda f: "Query.trim_start"
EXCLUDING[(SQ, "Query.bump_prefix")] = lambda f: f"Query.bump_prefix({brief(f.f_locals['other_query'])})"
for key in [k for k in EXCLUDING if k[1] in ("Query.table_alias", "Query.join", "Query.resolve_lookup_value", "Query.check_related_objects", "Query.trim_joins", "JoinPromoter.__init__", "JoinPromoter.add_votes", "JoinPromoter.update_join_types", "Query.demote_joins", "Query.promote_joins", "Lookup.__init__", "Lookup.get_prep_lookup", "WhereNode.add")]:
    del EXCLUDING[key]
says(SQ, "Query.trim_start", "Query.split_exclude")
says(SQ, "Query.split_exclude", how=lambda f, v: f"({brief(v[0])}, {brief(v[1])})")

with recorded(EXCLUDING):
    do("no_ada = Ship.objects.exclude(crew__name='Ada')")
ask("sql_of(no_ada)")
show("exclude across a multi-valued relation: setup_joins raises MultiJoin, and split_exclude builds a subquery under NOT EXISTS")

ask("tail(Port.objects.exclude(voyage__sailed__year=2026))")
ask("tail(Ship.objects.exclude(captain__pilots_into__name='Bergen'))")
ask("tail(Ship.objects.filter(~Q(crew__name='Ada') | Q(tonnage__gt=1000)))")
ask("tail(Ship.objects.exclude(crew__name='Ada', crew__signed_on__year=2011))")
ask("tail(Ship.objects.exclude(crew__name='Ada').exclude(crew__name='Bram'))")
ask("tail(Ship.objects.filter(crew__name='Ada').exclude(crew__name='Bram'))")
show("What split_exclude writes: a subquery for each excluded condition, OR IS NULL where an outer join precedes the relation, and a filter beside an exclude")

ask("sql_of(Ship.objects.filter(pk__in=[]))")
ask("list(Ship.objects.filter(pk__in=[]))")
ask("tail(Ship.objects.filter(Q(pk__in=[]) | Q(name='Petrel')))")
ask("sql_of(Ship.objects.filter(Q(pk__in=[]) & Q(name='Petrel')))")
ask("sql_of(Ship.objects.exclude(pk__in=[]))")
ask("sql_of(Ship.objects.filter(~Q(pk__in=[]) | Q(name='Petrel')))")
ask("tail(Ship.objects.filter(Q())), tail(Ship.objects.filter(Q() | Q(name='Petrel')))")
ask("sql_of(Ship.objects.none())")
ask("where_said(Ship.objects.none()), Ship.objects.none().query.is_empty(), where_said(Ship.objects.filter(pk__in=[])), Ship.objects.filter(pk__in=[]).query.is_empty()")
ask("Ship.objects.none().query.where.as_sql(Ship.objects.all().query.get_compiler('default'), connection)")
ask("Ship.objects.filter(pk__in=[]).query.where.as_sql(Ship.objects.all().query.get_compiler('default'), connection)")
ask("Ship.objects.exclude(pk__in=[]).query.where.as_sql(Ship.objects.all().query.get_compiler('default'), connection)")
ask("WhereNode().as_sql(None, connection)")
show("WhereNode.as_sql: a child that matches nothing or everything is counted, and the node itself may match nothing or everything")

ask("tail(Ship.objects.filter(Q(name='Petrel') ^ Q(tonnage__gt=1000)))")
ask("tail(Ship.objects.filter(Q(name='Petrel') ^ Q(tonnage__gt=1000) ^ Q(home__name='Leith')))")
ask("connection.features.supports_logical_xor")
show("XOR on SQLite, which has no XOR of its own: an OR beside a count of the true operands")

ask("tail(Ship.objects.filter(Exists(Sailor.objects.filter(ship=OuterRef('pk'), name='Ada'))))")
ask("tail(Ship.objects.filter(Q(tonnage__gt=1) & Exists(Sailor.objects.filter(ship=OuterRef('pk')))))")
ask("tail(Ship.objects.filter(~Exists(Sailor.objects.filter(ship=OuterRef('pk')))))")
ask("tail(Ship.objects.filter(Value(True)))")
ask("tail(Ship.objects.filter(Q(name='Petrel') & Value(True)))")
ask("Ship.objects.filter(F('tonnage'))")
ask("Ship.objects.filter(Lower('name'))")
ask("tail(Ship.objects.filter(ExpressionWrapper(Q(tonnage__gt=1000), output_field=models.BooleanField())))")
ask("where_said(Ship.objects.filter(Exists(Sailor.objects.filter(ship=OuterRef('pk')))))")
show("A conditional expression as a filter: resolved and, where it is not a lookup already, compared with True")

ask("Sailor.objects.filter(ship=bergen)")
ask("Sailor.objects.filter(ship__in=[petrel, bergen])")
ask("Sailor.objects.filter(ship__in=Port.objects.all())")
ask("tail(Sailor.objects.filter(ship__in=Port.objects.values('id')))")
ask("tail(Sailor.objects.filter(ship=Veteran.objects.get(pk=1).ship))")
ask("tail(Ship.objects.filter(captain=Veteran(pk=1)))")
ask("tail(Sailor.objects.filter(officer=cora)), tail(Officer.objects.filter(sailor_ptr=ada))")
ask("Sailor.objects.filter(ship=Ship.objects.filter(name='Petrel'))")
ask("tail(Sailor.objects.filter(ship=Ship.objects.filter(name='Petrel')[:1]))")
show("check_related_objects: what a filter on a relation accepts as its value")

ask("tail(Ship.objects.extra(where=['tonnage > %s', 'home_id = 1'], params=[500]))")
ask("where_said(Ship.objects.extra(where=['tonnage > %s'], params=[500]))")
ask("Ship.objects.extra(where=['tonnage > %s'], params=[500]).query.where.children[0].as_sql()")
ask("sql_of(Ship.objects.filter(name='Petrel').extra(where=['tonnage > 0']).filter(pk__in=[]))")
show("ExtraWhere: SQL a program wrote, taken as it is")

lines("veterans = Ship.objects.annotate(veterans=FilteredRelation('crew', condition=Q(crew__signed_on__year__lt=2020)))")
ask("veterans.query._filtered_relations['veterans'].relation_name, veterans.query._filtered_relations['veterans'].alias, veterans.query._filtered_relations['veterans'].condition, veterans.query._filtered_relations['veterans'].resolved_condition")
ask("list(veterans.query.alias_map), tail(veterans)")
lines("named_veterans = veterans.filter(veterans__name='Ada')")
aliases(ASKING["named_veterans"].query)
ask("said(named_veterans.query.alias_map['veterans'].filtered_relation.resolved_condition)")
ask("tail(named_veterans)")
ask("tail(veterans.values('name', 'veterans__name'))")
ask("said(Ship.objects.all().query.names_to_path(['veterans', 'name'], Ship._meta))")
ask("said(named_veterans.query.names_to_path(['veterans', 'name'], Ship._meta))")
ask("Ship.objects.annotate(v=FilteredRelation('crew', condition=Q(crew__ship__name='Petrel')))")
ask("tail(Ship.objects.annotate(v=FilteredRelation('crew__pilots_into', condition=Q(crew__name='Ada'))).filter(v__name='Bergen'))")
ask("Ship.objects.annotate(v=FilteredRelation('crew__name')).filter(v='Ada')")
show("FilteredRelation on the query's side: the join carries the condition, and a name that starts with the alias walks through it")

# ---------------------------------------------------------------------------------------------
# Lookups.

quietly("list(Sailor.objects.filter(name__exact='Ada'))")
quietly("list(Sailor.objects.filter(name__iexact='ada'))")
quietly("list(Sailor.objects.filter(name__contains='d'))")
quietly("list(Sailor.objects.filter(name__icontains='D'))")
quietly("list(Sailor.objects.filter(name__startswith='A'))")
quietly("list(Sailor.objects.filter(name__istartswith='a'))")
quietly("list(Sailor.objects.filter(name__endswith='a'))")
quietly("list(Sailor.objects.filter(name__iendswith='A'))")
quietly("list(Sailor.objects.filter(name__contains='100%_a'))")
quietly("list(Ship.objects.filter(tonnage__gt=500))")
quietly("list(Ship.objects.filter(tonnage__gte=500))")
quietly("list(Ship.objects.filter(tonnage__lt=500))")
quietly("list(Ship.objects.filter(tonnage__lte=500))")
quietly("list(Ship.objects.filter(tonnage__range=(400, 600)))")
quietly("list(Ship.objects.filter(tonnage__in=[480, 1200]))")
quietly("list(Ship.objects.filter(captain__isnull=True))")
quietly("list(Ship.objects.filter(captain__isnull=False))")
quietly("list(Sailor.objects.filter(name__regex='^A'))")
quietly("list(Sailor.objects.filter(name__iregex='^a'))")
quietly("list(Voyage.objects.filter(sailed__year=2026))")
quietly("list(Voyage.objects.filter(sailed__year__gte=2026))")
quietly("list(Voyage.objects.filter(sailed__month=3))")
quietly("list(Voyage.objects.filter(sailed__week_day=2))")
quietly("list(Sailor.objects.filter(signed_on__date=datetime.date(2011, 6, 1)))")
quietly("list(Sailor.objects.filter(signed_on__hour=8))")
quietly("list(Manifest.objects.filter(stamped=True))")
quietly("list(Manifest.objects.filter(stamped__exact=False))")
show("The statement each standard lookup writes on SQLite, one line of Python and its statement each")

lines("compiler = Ship.objects.all().query.get_compiler('default')")
lines("tonnage = Ship._meta.get_field('tonnage').get_col('fleet_ship')")
ask("Exact(tonnage, '480').rhs, Exact(tonnage, '480').lhs, Exact(tonnage, 480).rhs_is_direct_value(), Exact(tonnage, F('id')).rhs_is_direct_value()")
ask("Exact(tonnage, 'x')")
ask("Exact(480, 480), Exact(480, 480).lhs")
ask("type(Exact(tonnage, 480).output_field).__name__, Exact(tonnage, 480).conditional, Exact(tonnage, 480).lookup_name, Exact.prepare_rhs, IsNull.prepare_rhs, Exact.can_use_none_as_rhs")
ask("Exact(tonnage, 480).get_source_expressions(), Exact(tonnage, F('id')).resolve_expression(Ship.objects.all().query).get_source_expressions()")
ask("Exact(tonnage, 480).process_lhs(compiler, connection), Exact(tonnage, 480).process_rhs(compiler, connection), Exact(tonnage, 480).get_rhs_op(connection, '%s')")
ask("Exact(tonnage, 480).as_sql(compiler, connection), Exact(tonnage, F('id')).resolve_expression(Ship.objects.all().query).as_sql(compiler, connection)")
ask("Exact(tonnage, Ship.objects.filter(pk=1).values('tonnage')[:1].query).resolve_expression(Ship.objects.all().query).as_sql(compiler, connection)")
ask("connection.operators['exact'], connection.operators['icontains'], connection.ops.lookup_cast('icontains', 'CharField'), connection.ops.lookup_cast('exact', 'CharField')")
ask("Exact(tonnage, 480) == Exact(tonnage, 480), Exact(tonnage, 480).identity, hash(Exact(tonnage, 480)) == hash(Exact(tonnage, 480))")
ask("Exact(tonnage, 480).get_db_prep_lookup(480, connection), In(tonnage, [480, 1200]).get_db_prep_lookup([480, 1200], connection)")
show("A Lookup taken apart: the right side prepared by the left side's field, and the two halves compiled by process_lhs and process_rhs")

ask("tail(Ship.objects.filter(tonnage__in=[480, 480, 1200]))")
ask("tail(Ship.objects.filter(tonnage__in=[480, None]))")
ask("sql_of(Ship.objects.filter(tonnage__in=[None]))")
ask("tail(Ship.objects.filter(tonnage__in=iter([480])))")
ask("tail(Ship.objects.filter(tonnage__in=[F('id'), 480]))")
ask("tail(Ship.objects.filter(tonnage__in=Ship.objects.values('tonnage').order_by('name')))")
ask("Ship.objects.filter(tonnage__in=Ship.objects.values('tonnage', 'name'))")
ask("connection.ops.max_in_list_size()")
show("In: duplicates and None are dropped, an empty list matches nothing, and a queryset becomes a subquery with its ordering cleared")

ask("tail(Sailor.objects.filter(name__startswith='A%')), tail(Sailor.objects.filter(name__startswith='A_'))")
ask("tail(Sailor.objects.filter(name__startswith=F('name')))")
ask("tail(Sailor.objects.filter(name__icontains=Lower('name')))")
ask("tail(Sailor.objects.filter(name__iexact=F('name')))")
ask("connection.ops.prep_for_like_query('100%_a'), connection.pattern_esc, connection.pattern_ops['startswith'], connection.features.pattern_lookup_needs_param_pattern")
show("PatternLookup: a plain value is escaped and wrapped in Python, an expression is wrapped by SQL from pattern_ops")

ask("tail(Voyage.objects.filter(sailed__year=2026)), tail(Voyage.objects.filter(sailed__year__lt=2026)), tail(Voyage.objects.filter(sailed__year__gt=2026))")
ask("tail(Voyage.objects.filter(sailed__year__gte=2026)), tail(Voyage.objects.filter(sailed__year__lte=2026))")
ask("tail(Sailor.objects.filter(signed_on__year=2011))")
ask("tail(Voyage.objects.filter(sailed__iso_year=2026))")
ask("tail(Voyage.objects.filter(sailed__year=F('id')))")
ask("tail(Voyage.objects.filter(sailed__year__in=[2025, 2026]))")
ask("connection.ops.year_lookup_bounds_for_date_field(2026), connection.ops.year_lookup_bounds_for_datetime_field(2026)")
show("YearLookup: a plain year is compared as bounds on the column itself, so that an index on the column can serve")

ask("tail(Ship.objects.annotate(v=Value(None, output_field=models.CharField())).filter(v__isnull=True))")
ask("sql_of(Ship.objects.annotate(v=Value(None, output_field=models.CharField())).filter(v__isnull=False))")
ask("sql_of(Ship.objects.annotate(v=Value('x')).filter(v__isnull=True))")
ask("Ship.objects.filter(captain__isnull='yes')")
ask("tail(Ship.objects.filter(captain__isnull=1))")
show("IsNull: on a Value the answer is known before any SQL is written")

ask("sql_of(Ship.objects.filter(tonnage__gt=2 ** 70))")
ask("tail(Ship.objects.filter(tonnage__lt=2 ** 70))")
ask("sql_of(Ship.objects.filter(tonnage=2 ** 70))")
ask("tail(Ship.objects.filter(tonnage__gte=-2 ** 70))")
ask("sql_of(Ship.objects.filter(tonnage__lte=-2 ** 70))")
ask("connection.ops.integer_field_range('PositiveIntegerField'), connection.ops.integer_field_range('BigIntegerField')")
ask("tail(Ship.objects.filter(tonnage__lt=1.5)), tail(Ship.objects.filter(tonnage__gte=1.5)), tail(Ship.objects.filter(tonnage__gt=1.5))")
ask("Ship.objects.filter(tonnage='x')")
ask("tail(Ship.objects.filter(tonnage='480'))")
show("The lookups IntegerField registers over Field's: a value past the column's range is decided without the database, and a float is rounded")

ask("tail(Manifest.objects.filter(stamped=True)), tail(Manifest.objects.filter(stamped=False))")
ask("tail(Manifest.objects.filter(stamped=1))")
ask("tail(Ship.objects.annotate(big=Q(tonnage__gt=1000)).filter(big=True))")
ask("tail(Ship.objects.annotate(big=Q(tonnage__gt=1000)).filter(big=False))")
ask("connection.ops.conditional_expression_supported_in_where_clause(Manifest._meta.get_field('stamped').get_col('office_manifest'))")
show("Exact with a boolean: a conditional column stands alone in the WHERE, or under NOT")

ask("Ship.objects.filter(pk=Ship.objects.filter(name='Petrel'))")
ask("Ship.objects.filter(pk=Ship.objects.values('id', 'name')[:1])")
ask("tail(Ship.objects.filter(pk=Ship.objects.filter(name='Petrel')[:1]))")
ask("tail(Ship.objects.filter(name=Ship.objects.filter(name='Petrel').values('name')[:1]))")
ask("tail(Ship.objects.filter(tonnage__gt=Ship.objects.filter(name='Petrel').values('tonnage')[:1]))")
ask("tail(Ship.objects.filter(tonnage__gt=Ship.objects.filter(name='Petrel').values('tonnage')))")
show("Exact with a queryset: limited to one row and one column, or refused")

ask("Sailor.objects.filter(name__regex='^A').query.where.children[0].as_sql(compiler, connection), 'regex' in connection.operators, connection.operators['regex']")
ask("Sailor.objects.filter(signed_on__year=2011).query.where.children[0].lhs, Sailor.objects.filter(signed_on__year=2011).query.where.children[0].lhs.lhs, Sailor.objects.filter(signed_on__year=2011).query.where.children[0].rhs")
show("Asked of a few lookups")

# ---------------------------------------------------------------------------------------------
# Lookups on relations and on a composite primary key.

ask("{name: cls.__name__ for name, cls in sorted(vars(ForeignObject)['class_lookups'].items())}")
ask("entry(Sailor.objects.filter(ship=petrel)), entry(Sailor.objects.filter(ship=1)), entry(Sailor.objects.filter(ship='1'))")
ask("entry(Sailor.objects.filter(ship=petrel)).rhs, entry(Sailor.objects.filter(ship='1')).rhs, type(entry(Sailor.objects.filter(ship='1')).rhs).__name__")
ask("Sailor.objects.filter(ship='x')")
ask("Sailor.objects.filter(ship=Ship(name='Skua'))")
ask("entry(Sailor.objects.filter(ship__in=[petrel, 2, '2'])).rhs")
ask("entry(Sailor.objects.filter(ship__in=Ship.objects.filter(tonnage__gt=1000))).rhs.values_select, entry(Sailor.objects.filter(ship__in=Ship.objects.filter(tonnage__gt=1000))).rhs.has_select_fields")
ask("tail(Sailor.objects.filter(ship__in=Ship.objects.filter(tonnage__gt=1000)))")
ask("tail(Sailor.objects.filter(ship__in=Ship.objects.values('home')))")
ask("tail(Sailor.objects.filter(ship__gt=1)), tail(Sailor.objects.filter(ship__isnull=False))")
ask("tail(Ship.objects.filter(captain=cora)), tail(Ship.objects.filter(captain=ada.pk))")
ask("entry(Sailor.objects.filter(officer=cora)), tail(Sailor.objects.filter(officer=cora))")
ask("entry(Sailor.objects.filter(ship__home=bergen)), entry(Ship.objects.filter(crew=ada))")
show("The lookups registered on ForeignObject: an instance, a key or a queryset on the right of a relation")

ask("entry(Berth.objects.filter(pk=(1, 2))), tail(Berth.objects.filter(pk=(1, 2)))")
ask("tail(Berth.objects.filter(pk__in=[(1, 1), (1, 2)]))")
ask("tail(Berth.objects.filter(pk__gt=(1, 1))), tail(Berth.objects.filter(pk__lte=(1, 1)))")
ask("tail(Berth.objects.filter(pk__isnull=False)), tail(Berth.objects.filter(pk__isnull=True))")
ask("tail(Berth.objects.filter(pk__in=Berth.objects.filter(metres__gt=100)))")
ask("sql_of(Berth.objects.filter(pk__in=[]))")
ask("sql_of(Berth.objects.filter(pk__in=[(1, None)]))")
ask("Berth.objects.filter(pk=1)")
ask("Berth.objects.filter(pk=(1,))")
ask("Berth.objects.filter(pk__in=[(1, 2, 3)])")
ask("Berth.objects.filter(pk__in=[1, 2])")
ask("Berth.objects.filter(pk=F('pk'))")
ask("tail(Berth.objects.filter(pk=Berth.objects.values('pk')[:1]))")
ask("tail(Berth.objects.filter(pk__gt=Berth.objects.values('pk')[:1]))")
ask("connection.features.supports_tuple_lookups, connection.features.supports_tuple_comparison_against_subquery")
show("A composite primary key compared as a tuple: TupleExact, TupleIn and their relatives, registered on CompositePrimaryKey")

connection.features.supports_tuple_lookups = False
ask("connection.features.supports_tuple_lookups")
ask("tail(Berth.objects.filter(pk=(1, 2)))")
ask("tail(Berth.objects.filter(pk__in=[(1, 1), (1, 2)]))")
ask("tail(Berth.objects.filter(pk__gt=(1, 1)))")
ask("tail(Berth.objects.filter(pk__gte=(1, 1)))")
ask("tail(Berth.objects.filter(pk__in=Berth.objects.filter(metres__gt=100)))")
del connection.features.__dict__["supports_tuple_lookups"]
show("With supports_tuple_lookups switched off for this block: the fallback SQL of the tuple lookups, written as ANDs and ORs of one-column comparisons")

# ---------------------------------------------------------------------------------------------
# Transforms and database functions.

ask("list(Ship.objects.annotate(x=Lower('name')).values_list('x', flat=True))")
ask("list(Ship.objects.annotate(x=Length('name')).values_list('x', flat=True))")
ask("list(Ship.objects.annotate(x=Concat('name', Value(' of '), 'home__name')).values_list('x', flat=True))")
ask("list(Ship.objects.annotate(x=Substr('name', 2, 3)).values_list('x', flat=True))")
ask("list(Ship.objects.annotate(x=Coalesce('captain__name', Value('nobody'))).values_list('x', flat=True))")
ask("list(Ship.objects.annotate(x=Cast('tonnage', models.FloatField()) / 1000).values_list('x', flat=True))")
ask("list(Ship.objects.annotate(x=Round(Cast('tonnage', models.FloatField()) / 7, 2)).values_list('x', flat=True))")
ask("list(Ship.objects.annotate(x=Greatest('tonnage', 1000)).values_list('x', flat=True))")
ask("[type(v).__name__ for v in Ship.objects.annotate(x=Now()).values_list('x', flat=True)]")
ask("[type(v).__name__ for v in Ship.objects.annotate(x=Random()).values_list('x', flat=True)]")
ask("[type(v).__name__ for v in Ship.objects.annotate(x=UUID4()).values_list('x', flat=True)]")
ask("list(Ship.objects.annotate(x=UUID7()).values_list('x', flat=True))[0].version")
show("Database functions in an annotation: what each writes on SQLite, and what comes back")

ask("list(Voyage.objects.annotate(x=ExtractYear('sailed')).values_list('x', flat=True))")
ask("list(Voyage.objects.annotate(x=Extract('sailed', 'month')).values_list('x', flat=True))")
ask("list(Sailor.objects.annotate(x=ExtractHour('signed_on')).values_list('x', flat=True))")
ask("list(Sailor.objects.annotate(x=ExtractHour('signed_on', tzinfo=datetime.timezone(datetime.timedelta(hours=2)))).values_list('x', flat=True))")
ask("list(Voyage.objects.annotate(x=TruncMonth('sailed')).values_list('x', flat=True))")
ask("list(Sailor.objects.annotate(x=TruncMonth('signed_on')).values_list('x', flat=True))")
ask("list(Sailor.objects.annotate(x=TruncDate('signed_on')).values_list('x', flat=True))")
ask("list(Sailor.objects.annotate(x=Trunc('signed_on', 'year', output_field=models.DateField())).values_list('x', flat=True))")
ask("Voyage.objects.annotate(x=Extract('sailed', 'hour'))")
ask("Voyage.objects.annotate(x=Trunc('sailed', 'hour'))")
ask("Voyage.objects.annotate(x=ExtractYear('ship'))")
ask("Voyage.objects.annotate(x=ExtractYear('sailed', tzinfo=datetime.UTC))")
ask("type(TruncMonth('sailed').resolve_expression(Voyage.objects.all().query).output_field).__name__, type(TruncMonth('signed_on').resolve_expression(Sailor.objects.all().query).output_field).__name__, type(ExtractYear('sailed').output_field).__name__")
ask("ExtractYear('signed_on').get_tzname(), ExtractYear('signed_on', tzinfo=datetime.timezone(datetime.timedelta(hours=2))).get_tzname()")
show("Extract and Trunc: the backend writes the SQL, a datetime is converted to the current time zone first, and the output field decides which function is asked for")

class Shout(Transform):
    lookup_name = "shout"
    function = "UPPER"
    bilateral = True


ASKING["Shout"] = Shout
quietly("models.CharField.register_lookup(Shout)")
ask("Shout.get_lookups(), Length.get_lookups(), Length('name').resolve_expression(Sailor.objects.all().query).get_lookup('gt').__name__, Shout('name').resolve_expression(Sailor.objects.all().query).get_lookup('exact').__name__")
ask("tail(Sailor.objects.filter(name__upper='ADA'))")
ask("tail(Sailor.objects.filter(name__shout='ada'))")
ask("tail(Sailor.objects.filter(name__shout__in=['ada', 'bram']))")
ask("tail(Sailor.objects.filter(name__shout__startswith='a'))")
ask("tail(Sailor.objects.filter(name__lower__shout__exact='ada'))")
ask("Sailor.objects.filter(name__shout__in=Sailor.objects.values('name'))")
ask("entry(Sailor.objects.filter(name__shout='ada')).bilateral_transforms, entry(Sailor.objects.filter(name__shout='ada')).lhs.get_bilateral_transforms(), entry(Sailor.objects.filter(name__upper='ADA')).bilateral_transforms")
ask("tail(Sailor.objects.filter(name__length=3)), tail(Sailor.objects.filter(name__length__gt=3))")
ask("tail(Sailor.objects.annotate(n=Length('name')).filter(n__gt=3)), tail(Sailor.objects.filter(name__length__gt=F('ship__tonnage')))")
quietly("models.CharField._unregister_lookup(Shout)")
show("A Transform as a lookup's left side: a transform registered on CharField for this block, with bilateral=True so that the right side is transformed too")

FUNCTIONS = watch(EX, "Func.as_sql", "Func.__init__", "Value.as_sql") | {
    (CO, "SQLCompiler.compile"): lambda f: f"SQLCompiler.compile({brief(f.f_locals['node'])})",
    (FN_CMP, "Greatest.as_sqlite"): lambda f: "Greatest.as_sqlite",
    (FN_CMP, "Cast.as_sqlite"): lambda f: "Cast.as_sqlite",
    (FN_CMP, "Cast.as_sql"): lambda f: "Cast.as_sql",
    (EX, "SQLiteNumericMixin.as_sqlite"): lambda f: f"{type(f.f_locals['self']).__name__}.as_sqlite  (SQLiteNumericMixin.as_sqlite)",
    (EX, "Value.as_sqlite"): lambda f: "Value.as_sqlite",
    (FN_TXT, "ConcatPair.pipes_concat_sql"): lambda f: "ConcatPair.as_sqlite  (pipes_concat_sql)",
    (FN_TXT, "ConcatPair.coalesce"): lambda f: "ConcatPair.coalesce",
    ("django.db.backends.sqlite3.operations", "DatabaseOperations.check_expression_support"): lambda f: f"DatabaseOperations.check_expression_support({brief(f.f_locals['expression'])})  (sqlite3)",
}
FUNCTIONS[(EX, "Func.as_sql")] = lambda f: f"{type(f.f_locals['self']).__name__}.as_sql  (Func.as_sql" + "".join(f", {k}={v!r}" for k, v in (("function", f.f_locals["function"]), ("template", f.f_locals["template"]), ("arg_joiner", f.f_locals["arg_joiner"])) if v is not None) + ")"
FUNCTIONS[(EX, "Func.__init__")] = lambda f: f"{type(f.f_locals['self']).__name__}.__init__({brief(f.f_locals['expressions'])}" + (f", output_field={brief(f.f_locals['output_field'])}" if f.f_locals["output_field"] is not None else "") + (f", {brief(f.f_locals['extra'])[1:-1]}" if f.f_locals["extra"] else "") + ")  (Func.__init__)"
FUNCTIONS[(EX, "Value.as_sql")] = lambda f: f"Value.as_sql  ({brief(f.f_locals['self'])})"
says(EX, "Func.as_sql", "Value.as_sql", "SQLiteNumericMixin.as_sqlite", "Value.as_sqlite", how=as_sql_said)
says(FN_CMP, "Greatest.as_sqlite", "Cast.as_sqlite", "Cast.as_sql", how=as_sql_said)
says(FN_TXT, "ConcatPair.pipes_concat_sql", how=as_sql_said)
says(CO, "SQLCompiler.compile", how=as_sql_said)

lines("compiler = Ship.objects.all().query.get_compiler('default')")
with recorded(FUNCTIONS):
    do("biggest = Greatest('tonnage', 1000)")
    do("compiler.compile(biggest.resolve_expression(Ship.objects.all().query))")
    do("compiler.compile(Lower('name').resolve_expression(Ship.objects.all().query))")
show("compile: a vendor method is preferred to as_sql, and Func.as_sql fills a template from the compiled sources")

ask("Func.template, Func.arg_joiner, Func.arity, Lower.function, Lower.lookup_name, Transform.arity, Transform.bilateral")
ask("Lower('name', 'tonnage')")
ask("Round('tonnage', 2), Round.arity")
ask("Concat('name')")
ask("Func('name', function='UPPER').resolve_expression(Ship.objects.all().query).get_source_expressions(), Func('name', 'tonnage', function='X').extra")
ask("Func(F('name'), function='X', template='%(function)s[%(expressions)s]').resolve_expression(Ship.objects.all().query).as_sql(compiler, connection)")
ask("Func(F('name'), function='X').resolve_expression(Ship.objects.all().query).as_sql(compiler, connection, function='Y', template='%(function)s<%(expressions)s>')")
ask("Lower('name').resolve_expression(Ship.objects.all().query).lhs")
ask("Coalesce('tonnage')")
ask("Ship.objects.annotate(x=Collate('name', 'nocase')).values_list('x', flat=True)[:1]")
ask("list(Ship.objects.annotate(x=NullIf('tonnage', 480)).values_list('x', flat=True))")
show("Func's template, arity and extra: what a function class declares and what a call may override")

# ---------------------------------------------------------------------------------------------
# Aggregates.

ask("Count('crew'), Count('*'), Count('*').resolve_expression(Ship.objects.all().query).get_source_expressions()")
ask("Count('*', filter=Q(tonnage__gt=1))")
ask("Aggregate.template, Count.function, Count.allow_distinct, Max.allow_distinct, StringAgg.allow_order_by, Count.empty_result_set_value, Sum.empty_result_set_value, Aggregate.contains_aggregate, Aggregate.window_compatible")
ask("Max('tonnage', distinct=True)")
ask("Count('crew', order_by='name')")
ask("Count('crew', default=0)")
ask("Count('crew').default_alias, Sum('tonnage').default_alias")
ask("Sum(F('tonnage') * 2).default_alias")
ask("Count('crew').get_source_expressions(), Count('crew', filter=Q(crew__name='Ada'), distinct=True).get_source_expressions()")
ask("type(Sum('tonnage', default=0).resolve_expression(Ship.objects.all().query)).__name__, Sum('tonnage', default=0).resolve_expression(Ship.objects.all().query).get_source_expressions()")
ask("Sum('tonnage', default=0).resolve_expression(Ship.objects.all().query).is_summary, Sum('tonnage', default=0).resolve_expression(Ship.objects.all().query, summarize=True).is_summary")
ask("Count('crew').get_group_by_cols(), Count('crew').resolve_expression(Ship.objects.all().query).contains_aggregate")
show("An Aggregate: a Func with distinct, filter, order_by and default, and the checks on each")

ask("Ship.objects.aggregate(Count('crew'))")
ask("Ship.objects.aggregate(n=Count('crew', distinct=True))")
ask("Ship.objects.aggregate(n=Count('crew', filter=Q(crew__signed_on__year__lt=2020)))")
ask("Ship.objects.aggregate(t=Sum('tonnage'), a=Avg('tonnage'), m=Max('tonnage'), s=StdDev('tonnage'), v=Variance('tonnage', sample=True))")
ask("Sailor.objects.aggregate(names=StringAgg('name', Value(', '), order_by='-name'))")
ask("Sailor.objects.aggregate(names=StringAgg('name', Value(','), distinct=True))")
ask("Ship.objects.aggregate(n=AnyValue('name'))")
ask("Ship.objects.aggregate(Sum('tonnage', default=0), Min('tonnage'))")
ask("Ship.objects.aggregate(n=Count('crew'), m=Count('crew') * 2)")
ask("Berth.objects.aggregate(n=Count('pk'))")
ask("Berth.objects.aggregate(n=Count('pk', distinct=True))")
ask("connection.features.supports_aggregate_filter_clause, connection.features.supports_aggregate_order_by_clause, connection.features.supports_any_value, connection.features.supports_aggregate_distinct_multiple_argument")
show("What the aggregates write on SQLite: FILTER, DISTINCT, ORDER BY inside the function, and a default as COALESCE")

ask("Ship.objects.annotate(n=Count('crew')).annotate(m=Sum('n'))")
ask("Ship.objects.annotate(m=Sum(Count('crew')))")
ask("Ship.objects.annotate(n=Count('crew')).aggregate(m=Sum('n'))")
ask("Ship.objects.annotate(n=Count('crew')).aggregate(m=Sum('n'), o=Max('m'))")
ask("Ship.objects.aggregate(m=Sum('n'))")
ask("Ship.objects.alias(n=Count('crew')).aggregate(m=Sum('n'))")
ask("Ship.objects.aggregate(Sum('home__name'))")
show("Aggregate.resolve_expression: an aggregate of an aggregate is refused, unless the inner one is an annotation and the outer one summarises a subquery")

AGGREGATING = watch(SQ, "Query.get_aggregation", "Query.get_count", "Query.exists", "Query.has_results", "Query.set_annotation_mask", "Query.append_annotation_mask", "Query.add_annotation", "Query.clear_ordering", "Query.clear_limits") | watch(
    AG, "Aggregate.resolve_expression") | watch(SUB, "AggregateQuery.__init__") | {
    (CO, "SQLCompiler.execute_sql"): generic, (CO, "SQLAggregateCompiler.as_sql"): plain, (CO, "SQLCompiler.as_sql"): without("with_limits"),
    (CO, "SQLCompiler.get_converters"): plain, (CO, "SQLCompiler.apply_converters"): plain, (CO, "SQLCompiler.has_results"): plain, (QS, "QuerySet.aggregate"): generic,
    (QS, "QuerySet.count"): plain, (QS, "QuerySet.exists"): plain,
}
AGGREGATING[(SQ, "Query.get_aggregation")] = lambda f: f"Query.get_aggregation(using={f.f_locals['using']!r}, aggregate_exprs={brief(f.f_locals['aggregate_exprs'])})"
AGGREGATING[(AG, "Aggregate.resolve_expression")] = lambda f: f"{type(f.f_locals['self']).__name__}.resolve_expression(summarize={f.f_locals['summarize']!r})  (Aggregate.resolve_expression, of {brief(f.f_locals['self'])})"
AGGREGATING[(SUB, "AggregateQuery.__init__")] = lambda f: f"AggregateQuery.__init__(model={f.f_locals['model'].__name__}, inner_query={brief(f.f_locals['inner_query'])})"
AGGREGATING[(SQ, "Query.set_annotation_mask")] = lambda f: f"Query.set_annotation_mask({brief(sorted(f.f_locals['names']) if f.f_locals['names'] is not None else None)})"
AGGREGATING[(SQ, "Query.append_annotation_mask")] = lambda f: f"Query.append_annotation_mask({brief(sorted(f.f_locals['names']))})"
says(SQ, "Query.get_aggregation", "Query.get_count", "Query.exists", "Query.has_results")
says(AG, "Aggregate.resolve_expression")
says(CO, "SQLCompiler.execute_sql", "SQLCompiler.has_results")
says(CO, "SQLCompiler.as_sql", "SQLAggregateCompiler.as_sql", how=as_sql_said)
says(QS, "QuerySet.aggregate", "QuerySet.count", "QuerySet.exists")

with recorded(AGGREGATING):
    do("Ship.objects.aggregate(total=Sum('tonnage'), ships=Count('id'))")
show("get_aggregation, the plain case: the aggregates become the query's only annotations, and one statement answers")

with recorded(AGGREGATING):
    do("Ship.objects.order_by('name')[:1].aggregate(total=Sum('tonnage'))")
show("get_aggregation with a slice: the query is wrapped as the inner query of an AggregateQuery")

with recorded(AGGREGATING):
    do("Ship.objects.annotate(hands=Count('crew')).aggregate(most=Max('hands'))")
show("get_aggregation over an annotation that aggregates: the grouped query goes inside, and the outer aggregate refers to its column")

with recorded(AGGREGATING):
    do("Ship.objects.annotate(hands=Count('crew')).count()")
    do("Ship.objects.filter(tonnage__gt=1000).count()")
show("get_count: a count is an aggregation of Count('*'), inside a subquery where the query groups")

with recorded(AGGREGATING):
    do("Ship.objects.filter(tonnage__gt=1000).exists()")
    do("Ship.objects.annotate(hands=Count('crew')).filter(hands__gt=1).exists()")
lines("e = Ship.objects.filter(tonnage__gt=1000).query.exists()")
ask("e.select, e.default_cols, e.annotation_select, e.high_mark, e.order_by, e.default_ordering, str(e)")
show("Query.exists: the select list cleared, a constant selected under the alias 'a', the ordering dropped and one row asked for")

ask("Ship.objects.filter(pk__in=[]).aggregate(n=Count('id'), s=Sum('tonnage'), m=Max('tonnage'), c=Coalesce(Sum('tonnage'), 0), d=Sum('tonnage', default=5))")
ask("Ship.objects.filter(pk__in=[]).aggregate(s=Sum('tonnage') + 1)")
ask("Ship.objects.filter(pk__in=[]).count()")
ask("Count.empty_result_set_value, Sum.empty_result_set_value, Coalesce(Sum('tonnage'), 0).empty_result_set_value, (Sum('tonnage') + 1).empty_result_set_value")
show("Aggregating over a query that matches nothing: each aggregate's empty_result_set_value is the answer, unless one has none, and then the statement is sent with a false predicate")

# ---------------------------------------------------------------------------------------------
# Subqueries.

lines("first_hand = Sailor.objects.filter(ship=OuterRef('pk')).order_by('name').values('name')[:1]")
ask("sql_of(Ship.objects.annotate(first=Subquery(first_hand)))")
ask("list(Ship.objects.annotate(first=Subquery(first_hand)).values_list('name', 'first'))")
lines("sub = Subquery(first_hand)")
ask("sub.query is first_hand.query, sub.query.subquery, first_hand.query.subquery, said(sub.get_source_expressions())")
lines("outer = Ship.objects.all().query")
lines("resolved = sub.resolve_expression(outer)")
ask("type(resolved).__name__, resolved.subquery, resolved.alias_prefix, list(resolved.alias_map), resolved.external_aliases, sorted(outer.subq_aliases)")
ask("said(resolved.where)")
ask("type(Subquery(first_hand, output_field=models.CharField()).resolve_expression(outer)).__name__, type(Subquery(first_hand, output_field=models.IntegerField()).resolve_expression(outer)).__name__")
ask("type(Subquery(first_hand).resolve_expression(outer).output_field).__name__")
ask("Subquery(Sailor.objects.filter(ship=OuterRef('pk')).values('name', 'id')[:1]).resolve_expression(outer).output_field")
ask("resolved.get_external_cols(), resolved.get_group_by_cols(), resolved.contains_subquery, Ship.objects.annotate(first=Subquery(first_hand)).query.annotations['first'].contains_subquery")
show("Subquery and OuterRef: the inner query is resolved against the outer, keeps aliases of its own, and takes the outer's as external")

RESOLVING = watch(SQ, "Query.resolve_expression", "Query.bump_prefix", "Query.change_aliases", "Query.resolve_ref", "Query.as_sql") | watch(
    EX, "Subquery.resolve_expression", "OuterRef.resolve_expression", "ResolvedOuterRef.resolve_expression", "F.resolve_expression", "Subquery.as_sql") | watch(WH, "WhereNode.resolve_expression")
RESOLVING[(SQ, "Query.resolve_expression")] = lambda f: f"Query.resolve_expression(query={brief(f.f_locals['query'])})  (of {brief(f.f_locals['self'])})"
RESOLVING[(SQ, "Query.bump_prefix")] = lambda f: f"Query.bump_prefix({brief(f.f_locals['other_query'])})"
RESOLVING[(SQ, "Query.as_sql")] = lambda f: f"Query.as_sql  (of {brief(f.f_locals['self'])})"
RESOLVING[(EX, "Subquery.resolve_expression")] = lambda f: f"{type(f.f_locals['self']).__name__}.resolve_expression  (Subquery.resolve_expression)"
RESOLVING[(EX, "OuterRef.resolve_expression")] = lambda f: f"OuterRef.resolve_expression  ({brief(f.f_locals['self'])})"
RESOLVING[(EX, "ResolvedOuterRef.resolve_expression")] = lambda f: f"ResolvedOuterRef.resolve_expression  ({brief(f.f_locals['self'])})"
RESOLVING[(EX, "F.resolve_expression")] = lambda f: f"F.resolve_expression  ({brief(f.f_locals['self'])})"
RESOLVING[(EX, "Subquery.as_sql")] = lambda f: f"{type(f.f_locals['self']).__name__}.as_sql  (Subquery.as_sql)"
RESOLVING[(WH, "WhereNode.resolve_expression")] = plain
says(SQ, "Query.resolve_expression", "Query.resolve_ref")
says(SQ, "Query.as_sql", how=as_sql_said)
says(EX, "Subquery.resolve_expression", "OuterRef.resolve_expression", "ResolvedOuterRef.resolve_expression", "F.resolve_expression")
says(EX, "Subquery.as_sql", how=as_sql_said)

with recorded(RESOLVING):
    do("with_first = Ship.objects.annotate(first=Subquery(first_hand))")
    do("tail(with_first)")
show("A subquery resolved and compiled: OuterRef becomes ResolvedOuterRef when the inner query is resolved, and a Col of the outer table when the where tree is")

ask("tail(Ship.objects.filter(Exists(Sailor.objects.filter(ship=OuterRef('pk'), name='Ada'))))")
ask("sql_of(Ship.objects.annotate(has_ada=Exists(Sailor.objects.filter(ship=OuterRef('pk'), name='Ada'))))[0][:160]")
ask("list(Ship.objects.annotate(has_ada=Exists(Sailor.objects.filter(ship=OuterRef('pk'), name='Ada'))).values_list('name', 'has_ada'))")
ask("tail(Ship.objects.filter(Exists(Sailor.objects.none())))")
ask("sql_of(Ship.objects.annotate(x=Exists(Sailor.objects.none())))[0][:120]")
ask("Exists(Sailor.objects.all()).query.select, Exists(Sailor.objects.all()).query.high_mark, Exists(Sailor.objects.all()).output_field, Exists(Sailor.objects.all()).empty_result_set_value, Subquery(Sailor.objects.all()).empty_result_set_value")
ask("tail(Ship.objects.filter(Exists(Sailor.objects.filter(ship=OuterRef('pk')).values('name'))))")
show("Exists: a Subquery whose query is the inner query's exists(), and whose SQL is known when the inner query can match nothing")

ask("sql_of(Port.objects.annotate(x=Subquery(Ship.objects.filter(home=OuterRef('pk')).annotate(y=Subquery(Sailor.objects.filter(ship=OuterRef(OuterRef('pk'))).values('name')[:1])).values('y')[:1])).values('name', 'x'))")
ask("OuterRef('pk').resolve_expression(), OuterRef(OuterRef('pk')).resolve_expression(), OuterRef(OuterRef('pk')).resolve_expression().resolve_expression()")
ask("Sailor.objects.filter(ship=OuterRef('pk'))")
ask("list(Sailor.objects.filter(ship=OuterRef('pk')))")
show("OuterRef inside OuterRef: each level of nesting takes one off")

ask("tail(Sailor.objects.filter(ship__in=Ship.objects.filter(tonnage__gt=1000).order_by('name')))")
ask("tail(Sailor.objects.filter(ship=Ship.objects.order_by('name')[:1]))")
ask("sql_of(Ship.objects.annotate(x=Subquery(Sailor.objects.filter(ship=OuterRef('pk')).order_by('-name').values('name')[:1])).values('x'))")
ask("connection.features.ignores_unnecessary_order_by_in_subqueries")
ask("sql_of(Ship.objects.annotate(x=Subquery(Sailor.objects.filter(ship=OuterRef('pk')).distinct().order_by('signed_on').values('name')[:1])).values('x'))")
show("The ordering of a query inside another: cleared by In, kept under a slice, and the extra columns of distinct with order_by wrapped away")

ask("tail(Ship.objects.filter(tonnage__gt=Subquery(Ship.objects.filter(name='Petrel').values('tonnage')[:1])))")
ask("sql_of(Ship.objects.annotate(biggest=Subquery(Ship.objects.order_by('-tonnage').values('tonnage')[:1])).filter(tonnage=F('biggest')).values('name'))")
ask("tail(Ship.objects.filter(tonnage=Subquery(Ship.objects.order_by('-tonnage').values('tonnage')[:1]) - 720))")
ask("tail(Ship.objects.filter(pk__in=Sailor.objects.filter(name='Ada').values('ship')))")
ask("tail(Ship.objects.filter(pk__in=Sailor.objects.filter(name='Ada').values_list('ship', flat=True)))")
ask("tail(Ship.objects.filter(pk__in=Subquery(Sailor.objects.filter(name='Ada').values('ship'))))")
show("A subquery as a value: in a comparison, in arithmetic, and the three ways of writing an IN")

# ---------------------------------------------------------------------------------------------
# Window expressions.

ask("sql_of(Sailor.objects.annotate(n=Window(RowNumber(), partition_by=F('ship'), order_by='name')))[0][:200]")
ask("list(Sailor.objects.annotate(n=Window(RowNumber(), partition_by=F('ship'), order_by='name')).values_list('name', 'n'))")
ask("sql_of(Sailor.objects.annotate(n=Window(Rank(), order_by=F('signed_on').desc())))[0][:160]")
ask("sql_of(Sailor.objects.annotate(n=Window(Sum('id'), order_by='id', frame=RowRange(start=-1, end=0))))[0][:200]")
ask("sql_of(Sailor.objects.annotate(n=Window(Sum('id'), order_by='id', frame=ValueRange(start=None, end=0, exclusion=WindowFrameExclusion.CURRENT_ROW))))[0][:230]")
ask("sql_of(Sailor.objects.annotate(n=Window(Lag('name', offset=1, default=Value('-')), order_by='id')))[0][:160]")
ask("sql_of(Sailor.objects.annotate(n=Window(Ntile(2), order_by='id')))[0][:120]")
ask("sql_of(Sailor.objects.annotate(n=Window(DenseRank(), partition_by=['ship', 'signed_on__year'], order_by=['-name', 'id'])))[0][:260]")
ask("Window(F('name'))")
ask("Window(RowNumber(), order_by=5)")
ask("RowRange(start=1, exclusion='ties')")
ask("str(RowRange(start=-1, end=0)), str(ValueRange()), ValueRange().as_sql(compiler, connection)")
ask("Window(RowNumber()).get_source_expressions(), Window(RowNumber(), partition_by='ship', order_by='name').get_source_expressions()")
ask("Window(RowNumber(), partition_by='ship', order_by='name').resolve_expression(Sailor.objects.all().query).get_group_by_cols(), Window(Sum('id')).contains_aggregate, Window(Sum('id')).contains_over_clause")
ask("connection.features.supports_over_clause, connection.features.supports_frame_exclusion")
show("Window: the expression, PARTITION BY, ORDER BY and a frame, and what the window functions write")

QUALIFYING = {k: v for k, v in COMPILING.items() if k[1] in ("SQLCompiler.as_sql", "SQLCompiler.pre_sql_setup", "SQLCompiler.get_qualify_sql", "WhereNode.split_having_qualify", "SQLCompiler.get_select", "SQLCompiler.get_order_by")}
QUALIFYING[(CO, "SQLCompiler.get_qualify_sql")] = plain
QUALIFYING[(SQ, "Query.add_annotation")] = generic
says(CO, "SQLCompiler.get_qualify_sql", how=lambda f, v: f"({' '.join(v[0])!r}, {brief(tuple(v[1]))})")

lines("numbered = Sailor.objects.annotate(n=Window(RowNumber(), partition_by='ship', order_by='name'))")
with recorded(QUALIFYING):
    do("sql_of(numbered.filter(n=1))")
ask("list(numbered.filter(n=1).values_list('name', flat=True))")
show("Filtering on a window: split_having_qualify puts the condition aside, and get_qualify_sql wraps the statement in a subquery")

ask("sql_of(numbered.filter(n=1).values('name'))[0][:330]")
ask("sql_of(numbered.filter(Q(n=1) | Q(name='Dag')))[0][120:]")
ask("sql_of(numbered.filter(n=1, name__startswith='A'))[0][120:]")
ask("sql_of(numbered.filter(n=1).order_by('-name'))[0][120:]")
ask("sql_of(Sailor.objects.annotate(n=Window(Count('id'), partition_by='ship')).filter(n__gt=1))[0][120:]")
ask("numbered.filter(n=1).query.where.split_having_qualify()")
ask("numbered.annotate(hands=Count('id')).filter(Q(n=1) | Q(hands__gt=1))")
ask("numbered.aggregate(m=Max('n'))")
show("Asked of a filter on a window")

# ---------------------------------------------------------------------------------------------
# The compiler.

ask("type(Ship.objects.all().query.get_compiler('default')).__name__, connection.ops.compiler_module, Query.compiler, UpdateQuery.compiler, InsertQuery.compiler, DeleteQuery.compiler, AggregateQuery.compiler")
ask("type(Ship.objects.all().query.get_compiler(connection=connection)).__name__, Ship.objects.all().query.get_compiler('default').using, Ship.objects.all().query.get_compiler(connection=connection).using")
ask("Ship.objects.all().query.get_compiler()")
ask("connection.ops.compiler('SQLCompiler').__module__, connection.ops.compiler('SQLInsertCompiler').__name__")
lines("compiler = Ship.objects.filter(tonnage__gt=100).query.get_compiler('default')")
ask("compiler.query is Ship.objects.filter(tonnage__gt=100).query, compiler.elide_empty, compiler.select, compiler.klass_info, compiler.annotation_col_map, compiler.quote_cache")
ask("compiler.quote_name('name'), compiler.quote_name('*'), compiler.quote_name('name') is compiler.quote_name('name'), compiler.quote_cache")
ask("compiler.quote_name_unless_alias('name')")
ask("repr(compiler)[:40]")
show("get_compiler: the backend's operations supply the compiler class by the name the query carries")

ask("compiler.execute_sql()")
ask("compiler.execute_sql(SINGLE)")
ask("compiler.execute_sql(NO_RESULTS)")
ask("compiler.execute_sql(ROW_COUNT)")
ask("type(compiler.execute_sql(CURSOR)).__name__")
ask("type(compiler.execute_sql(MULTI, chunked_fetch=True)).__name__, connection.features.can_use_chunked_reads")
ask("compiler.execute_sql(result_type=None)")
ask("list(Ship.objects.filter(pk__in=[]).query.get_compiler('default').execute_sql()), Ship.objects.filter(pk__in=[]).query.get_compiler('default').execute_sql(SINGLE)")
ask("Ship.objects.filter(pk__in=[]).query.get_compiler('default', elide_empty=False).execute_sql(SINGLE)")
ask("compiler.has_results(), Ship.objects.filter(pk__in=[]).query.get_compiler('default').has_results()")
show("execute_sql: one statement, and five kinds of result, with nothing sent where the query can match nothing")

ask("compiler.as_sql()")
ask("compiler.as_sql(with_col_aliases=True)")
ask("compiler.as_sql(with_limits=False), Ship.objects.all()[:1].query.get_compiler('default').as_sql(with_limits=False)")
ask("compiler.select[0], compiler.col_count, compiler.klass_info, compiler.annotation_col_map, compiler.has_extra_select")
ask("compiler.query.alias_refcount")
ask("compiler.query.used_aliases, compiler.query.alias_map['fleet_ship'].table_alias")
show("as_sql: the statement and its parameters, with every column aliased on request, and the reference counts put back afterwards")

lines("typed = Manifest.objects.annotate(kilos_each_f=Cast('kilos_each', models.FloatField()), half=F('crates') / 2.0, when=Value(datetime.datetime(2026, 4, 10, 9, 0, tzinfo=datetime.UTC), output_field=models.DateTimeField())).query.get_compiler('default')")
ask("typed.as_sql()[0]")
ask("[(brief(expr), sql) for expr, (sql, _), _ in typed.select]")
ask("converters_said(typed)")
ask("[row for row in typed.results_iter()]")
ask("[type(v).__name__ for v in next(iter(typed.results_iter()))]")
ask("[type(v).__name__ for v in next(iter(typed.execute_sql()))[0]]")
show("results_iter and the converters: each column's converters, the backend's then the field's or the expression's, turn what the driver returned into what the program gets")

ask("[len(chunk) for chunk in Logbook.objects.all().query.get_compiler('default').execute_sql(chunked_fetch=True)]")
ask("[len(chunk) for chunk in Logbook.objects.all().query.get_compiler('default').execute_sql(chunked_fetch=True, chunk_size=10)]")
ask("[len(chunk) for chunk in Logbook.objects.all().query.get_compiler('default').execute_sql()]")
ask("len(list(Logbook.objects.all().query.get_compiler('default').results_iter(chunked_fetch=True, chunk_size=10)))")
ask("connection.features.empty_fetchmany_value, connection.ops.compiler_module")
show("Rows a chunk at a time: cursor_iter asks the cursor for chunk_size rows until none come back")

ask("Ship.objects.filter(name='Petrel').explain()")
ask("Ship.objects.filter(name='Petrel').query.explain('default')")
ask("Ship.objects.filter(name='Petrel').explain(format='json')")
ask("Ship.objects.filter(name='Petrel').explain(**{'bad option': True})")
ask("Ship.objects.filter(name='Petrel').query.explain_info, Ship.objects.filter(name='Petrel').query.clone().explain_info")
show("explain: a prefix the backend writes, and the rows that come back joined into text")

# ---------------------------------------------------------------------------------------------
# The SELECT clause.


def selection(queryset) -> None:
    compiler = queryset.query.get_compiler("default")
    compiler.as_sql()
    select_said(compiler)
    klass_said(compiler.klass_info)


selection(Ship.objects.all())
show("get_select for Ship.objects.all(): every concrete field as a Col, no alias, the klass_info of the model, and no annotations")

selection(Ship.objects.values("name", "home__country"))
ask("Ship.objects.values('name', 'home__country').query.selected, Ship.objects.values('name', 'home__country').query.values_select, Ship.objects.values('name', 'home__country').query.select, Ship.objects.values('name', 'home__country').query.default_cols")
show("get_select after values: the named columns from Query.selected, each under its name, and no klass_info")

selection(Ship.objects.annotate(hands=Count("crew"), low=Lower("name")))
ask("Ship.objects.annotate(hands=Count('crew'), low=Lower('name')).query.annotation_select_mask, Ship.objects.annotate(hands=Count('crew')).alias(low=Lower('name')).query.annotation_select_mask, list(Ship.objects.annotate(hands=Count('crew')).alias(low=Lower('name')).query.annotation_select)")
show("get_select with annotations: the model's columns, then each selected annotation under its alias, and annotation_col_map says where")

selection(Ship.objects.values("name").annotate(hands=Count("crew")).values("hands", "name"))
ask("Ship.objects.values('name').annotate(hands=Count('crew')).values('hands', 'name').query.selected")
ask("Ship.objects.values('name', low=Lower('name')).query.selected, Ship.objects.values('name', low=Lower('name')).query.annotations, Ship.objects.values('name', low=Lower('name')).query.values_select")
ask("Ship.objects.values_list('name', Lower('name')).query.selected")
ask("Ship.objects.extra(select={'heavy': 'tonnage > 1000'}).values('name', 'heavy').query.selected, Ship.objects.extra(select={'heavy': 'tonnage > 1000'}).values('name', 'heavy').query.extra_select_mask")
ask("Ship.objects.values('cargo')")
ask("Ship.objects.alias(low=Lower('name')).values('low')")
ask("Ship.objects.annotate(low=Lower('name')).values('name').values('low')")
show("Query.selected after values: the order given, each name with a column's index, an annotation's name or a RawSQL")

selection(Ship.objects.only("name"))
selection(Sailor.objects.defer("name", "ship"))
ask("Sailor.objects.only('name').query.deferred_loading, said(Sailor.objects.only('name').query.get_select_mask())")
ask("said(Sailor.objects.defer('name').query.get_select_mask())")
ask("said(Sailor.objects.only('ship__name').query.get_select_mask())")
ask("said(Sailor.objects.select_related('ship').only('name', 'ship__name').query.get_select_mask())")
ask("said(Sailor.objects.select_related('ship').defer('ship__tonnage').query.get_select_mask())")
ask("said(Sailor.objects.defer('pilots_into').query.get_select_mask()), tail(Sailor.objects.defer('pilots_into'))")
ask("Sailor.objects.only('name__x').query.get_select_mask()")
ask("Sailor.objects.defer('cargo').query.get_select_mask()")
ask("said(Officer.objects.only('rank').query.get_select_mask())")
show("get_select_mask: deferred_loading turned into the fields that will be loaded, model by model, with the primary key always among them")

selection(Officer.objects.all())
aliases(Officer.objects.all().query)
ask("tail(Officer.objects.all())")
ask("said(Officer.objects.all().query.get_compiler('default').get_default_columns({}))")
ask("said(Sailor.objects.all().query.get_compiler('default').get_default_columns({}, start_alias='T9'))")
show("get_default_columns for a child model: the parent's columns come through the join to its table, which join_parent_model makes")

selection(Sailor.objects.select_related("ship__home", "officer"))
show("get_select with select_related: the related models' columns follow the model's, and klass_info becomes a tree")

selection(Ship.objects.select_related())
ask("Ship.objects.select_related().query.select_related")
ask("Ship.objects.select_related('crew')")
ask("Ship.objects.select_related('name')")
ask("Sailor.objects.select_related('ship').only('name')")
ask("Sailor.objects.select_related('ship').defer('ship')")
ask("[len(Ship.objects.select_related(*names).query.get_compiler('default').get_select()[0]) for names in (('home',), ('home', 'captain'), ('captain__ship__home',))]")
show("get_related_selections: with no names, every non-null forward relation is followed to a depth of max_depth; with names, those and no others")

lines("c = Ship.objects.annotate(big=Q(tonnage__gt=1000), has_ada=Exists(Sailor.objects.filter(ship=OuterRef('pk'), name='Ada')), nothing=Q(pk__in=[]), nobody=Exists(Sailor.objects.none()), all=~Q(pk__in=[])).query.get_compiler('default')")
ask("c.as_sql()")
ask("list(Ship.objects.annotate(big=Q(tonnage__gt=1000), nothing=Q(pk__in=[]), nobody=Exists(Sailor.objects.none())).values_list('name', 'big', 'nothing', 'nobody'))")
ask("connection.features.supports_boolean_expr_in_select_clause")
show("A condition as a column: select_format on SQLite leaves it as it is, and a condition that can match nothing or everything is written as a constant")

ask("Ship.objects.annotate(**{'bad name': F('tonnage')})")
ask("Ship.objects.annotate(**{'pct%': F('tonnage')}).query.annotations")
ask("Ship.objects.values(**{'a-b': F('tonnage')}).query.selected, Ship.objects.extra(select={'x y': '1'})")
show("check_alias: what an alias may not contain, and the percent sign that is deprecated")

# ---------------------------------------------------------------------------------------------
# ORDER BY and DISTINCT.

ask("tail(Ship.objects.all()), Ship._meta.ordering, Ship.objects.all().query.order_by, Ship.objects.all().query.default_ordering")
ask("tail(Ship.objects.order_by('tonnage')), Ship.objects.order_by('tonnage').query.order_by")
ask("tail(Ship.objects.order_by()), Ship.objects.order_by().query.order_by, Ship.objects.order_by().query.default_ordering")
ask("tail(Ship.objects.order_by('-name', 'home__country'))")
ask("tail(Ship.objects.order_by('?'))")
ask("tail(Ship.objects.order_by(Lower('name'))), tail(Ship.objects.order_by('name__lower'))")
ask("tail(Ship.objects.order_by(F('tonnage').desc(nulls_last=True))), tail(Ship.objects.order_by(F('captain').asc(nulls_first=True)))")
ask("tail(Ship.objects.annotate(hands=Count('crew')).order_by('-hands')), tail(Ship.objects.alias(hands=Count('crew')).order_by('hands'))")
ask("tail(Ship.objects.order_by(Value('x')))")
ask("tail(Ship.objects.reverse()), Ship.objects.reverse().query.standard_ordering, tail(Ship.objects.order_by('-tonnage', 'name').reverse())")
ask("tail(Ship.objects.extra(order_by=['tonnage']).order_by('name')), Ship.objects.extra(order_by=['tonnage']).query.extra_order_by")
ask("tail(Ship.objects.order_by('name', '-name', 'tonnage', 'tonnage'))")
ask("Ship.objects.order_by('cargo')")
ask("Ship.objects.order_by(Count('crew'))")
ask("Ship.objects.order_by(5)")
ask("tail(Ship.objects.order_by('pk')), tail(Ship.objects.order_by('home_id')), tail(Ship.objects.order_by('home__pk'))")
show("Where the ordering comes from, in order of precedence: extra, order_by, the model's Meta.ordering; and what each form of name is turned into")

ask("tail(Sailor.objects.order_by('ship'))")
ask("tail(Sailor.objects.order_by('-ship'))")
ask("tail(Sailor.objects.order_by('ship_id')), tail(Sailor.objects.order_by('ship__pk'))")
ask("tail(Voyage.objects.order_by('ship__home'))")
ask("tail(Sailor.objects.order_by('ship__name__lower'))")
ask("tail(Ship.objects.order_by('captain'))")
ask("tail(Licence.objects.order_by('port', 'sailor'))")
show("find_ordering_name: an ordering by a relation becomes the related model's Meta.ordering, prefixed with the relation's name")

ORDERING = {k: v for k, v in COMPILING.items() if k[1] in ("SQLCompiler.get_order_by", "SQLCompiler._order_by_pairs", "SQLCompiler.find_ordering_name", "Query.setup_joins", "Query.trim_joins", "SQLCompiler.compile")}
ORDERING[(CO, "SQLCompiler._order_by_pairs")] = plain
ORDERING[(CO, "SQLCompiler.find_ordering_name")] = lambda f: f"SQLCompiler.find_ordering_name(name={f.f_locals['name']!r}, opts={brief(f.f_locals['opts'])}" + (f", alias={f.f_locals['alias']!r}" if f.f_locals["alias"] else "") + (f", default_order={f.f_locals['default_order']!r}" if f.f_locals["default_order"] != "ASC" else "") + ")"
says(CO, "SQLCompiler.compile", how=as_sql_said)

lines("compiler = Sailor.objects.order_by('-ship', 'name').query.get_compiler('default')")
with recorded(ORDERING):
    do("compiler.pre_sql_setup()")
show("get_order_by for Sailor.objects.order_by('-ship', 'name'): find_ordering_name follows the relation and comes back with the ship's own ordering")

lines("sliced = Ship.objects.order_by('tonnage')[:1].query")
lines("sliced.clear_ordering()")
ask("sliced.order_by, sliced.default_ordering")
lines("sliced.clear_ordering(force=True)")
ask("sliced.order_by, sliced.default_ordering, tail(Ship.objects.order_by('tonnage')[:1])")
lines("kept = Ship.objects.order_by('tonnage').query")
lines("kept.clear_ordering(clear_default=False)")
ask("kept.order_by, kept.default_ordering")
show("clear_ordering: refused without force where the query is sliced, has distinct fields or a lock; and clear_default decides whether Meta.ordering comes back")

ask("tail(Ship.objects.distinct()), Ship.objects.distinct().query.distinct, Ship.objects.distinct().query.distinct_fields")
ask("tail(Ship.objects.distinct().order_by('home__country'))")
ask("tail(Ship.objects.distinct().order_by('name'))")
ask("tail(Ship.objects.values('tonnage').distinct().order_by('name'))")
ask("Ship.objects.distinct('name').query.distinct_fields, tail(Ship.objects.distinct('name'))")
ask("tail(Ship.objects.distinct().annotate(hands=Count('crew')).order_by('hands'))")
ask("Ship.objects.distinct().order_by('home__country').query.get_compiler('default').pre_sql_setup()[0]")
show("DISTINCT: an ordering by a column that is not selected adds the column, and DISTINCT ON is refused by SQLite's distinct_sql")

ask("sql_of(Sailor.objects.order_by('signed_on').values_list('name'))")
ask("sql_of(Sailor.objects.values_list('name').order_by('signed_on'))")
ask("sql_of(Sailor.objects.values_list('name', 'signed_on').order_by('signed_on'))")
ask("sql_of(Sailor.objects.values_list('name').annotate(low=Lower('name')).order_by('low'))")
ask("sql_of(Sailor.objects.values_list('name').annotate(low=Lower('name')).order_by(Lower('name')))")
ask("sql_of(Ship.objects.values('home').annotate(hands=Count('crew')).order_by('home'))")
ask("connection.features.allows_group_by_select_index, connection.features.supports_order_by_nulls_modifier, connection.features.order_by_nulls_first")
show("Ordering by position: a selected expression is referred to by its place in the select list")

ask("Ship.objects.all().query.orderby_issubset_groupby, Ship.objects.values('home').annotate(n=Count('crew')).order_by('home').query.orderby_issubset_groupby, Ship.objects.values('home').annotate(n=Count('crew')).order_by('name').query.orderby_issubset_groupby")
ask("Ship.objects.values('home').annotate(n=Count('crew')).order_by('?').query.orderby_issubset_groupby, Ship.objects.extra(order_by=['x']).values('home').annotate(n=Count('crew')).query.orderby_issubset_groupby")
show("orderby_issubset_groupby: whether an ordering can be dropped from the inner query of an aggregation")

# ---------------------------------------------------------------------------------------------
# GROUP BY and HAVING.

ask("Ship.objects.all().query.group_by, Ship.objects.annotate(hands=Count('crew')).query.group_by, Ship.objects.annotate(low=Lower('name')).query.group_by")
ask("Ship.objects.values('home').annotate(hands=Count('crew')).query.group_by")
ask("Ship.objects.values('home', 'name').annotate(hands=Count('crew')).query.group_by")
ask("Ship.objects.annotate(hands=Count('crew')).values('home').query.group_by")
ask("Ship.objects.values(low=Lower('name')).annotate(hands=Count('crew')).query.group_by, Ship.objects.values(low=Lower('name')).annotate(hands=Count('crew')).query.annotations")
ask("Ship.objects.alias(hands=Count('crew')).query.group_by")
show("Query.group_by: None where nothing aggregates, True after an annotation that does, and a tuple after values and then annotate")

ask("tail(Ship.objects.annotate(hands=Count('crew')))")
ask("tail(Ship.objects.values('home').annotate(hands=Count('crew')))")
ask("tail(Ship.objects.values('home').annotate(hands=Count('crew')).order_by('name'))")
ask("tail(Ship.objects.values('home').annotate(hands=Count('crew')).filter(hands__gt=1))")
ask("tail(Ship.objects.values('home').annotate(hands=Count('crew')).filter(Q(hands__gt=1) | Q(name='Petrel')))")
ask("tail(Ship.objects.values('home').annotate(hands=Count('crew')).filter(hands__gt=1, name='Petrel'))")
ask("tail(Ship.objects.annotate(hands=Count('crew')).values('name', 'hands'))")
ask("tail(Ship.objects.annotate(hands=Count('crew')).values('hands'))")
ask("tail(Ship.objects.values('home__country').annotate(hands=Count('crew')))")
ask("tail(Ship.objects.values(low=Lower('name')).annotate(hands=Count('crew')))")
ask("tail(Ship.objects.annotate(hands=Count('crew')).annotate(low=Lower('name')))")
ask("tail(Ship.objects.annotate(hands=Count('crew'), fleet=Window(Count('id'))))")
show("What get_group_by writes: the minimal set from the query, then every selected column, then what the ordering and the HAVING refer to, and Meta.ordering dropped")

GROUPING = {k: v for k, v in COMPILING.items() if k[1] in ("SQLCompiler.as_sql", "SQLCompiler.pre_sql_setup", "SQLCompiler.get_group_by", "SQLCompiler.get_order_by", "WhereNode.split_having_qualify", "SQLCompiler.get_select")}
GROUPING[(CO, "SQLCompiler.collapse_group_by")] = lambda f: f"SQLCompiler.collapse_group_by(expressions={brief(f.f_locals['expressions'])}, having={brief(f.f_locals['having'])})"
GROUPING[(SQ, "Query.set_group_by")] = generic
GROUPING[(SQ, "Query.set_values")] = generic
GROUPING[(SQ, "Query.add_annotation")] = generic
says(CO, "SQLCompiler.collapse_group_by")

with recorded(GROUPING):
    do("grouped = Ship.objects.values('home').annotate(hands=Count('crew')).filter(Q(hands__gt=1) | Q(name='Petrel')).order_by('name')")
    do("sql_of(grouped)")
show("GROUP BY and HAVING assembled: set_values and set_group_by on the query, then split_having_qualify and get_group_by in the compiler")

connection.features.allows_group_by_selected_pks = True
ask("connection.features.allows_group_by_selected_pks, connection.features.allows_group_by_selected_pks_on_model(Ship)")
ask("tail(Ship.objects.annotate(hands=Count('crew')))")
ask("tail(Ship.objects.annotate(hands=Count('crew')).order_by('home__country'))")
ask("tail(Ship.objects.values('home').annotate(hands=Count('crew')))")
del connection.features.__dict__["allows_group_by_selected_pks"]
show("With allows_group_by_selected_pks switched on for this block: collapse_group_by keeps a table's primary key and drops its other columns")

connection.features.allows_group_by_select_index = False
ask("tail(Ship.objects.values('home').annotate(hands=Count('crew')).order_by('home'))")
ask("tail(Ship.objects.values(low=Lower('name')).annotate(hands=Count('crew')))")
del connection.features.__dict__["allows_group_by_select_index"]
show("With allows_group_by_select_index switched off for this block: the expressions are written out where a position stood")

ask("tail(Ship.objects.annotate(hands=Count('crew')).filter(hands__gt=1).filter(name='Petrel'))")
ask("tail(Ship.objects.annotate(hands=Count('crew')).filter(~Q(hands__gt=1)))")
ask("tail(Ship.objects.annotate(hands=Count('crew')).filter(~(Q(hands__gt=1) & Q(name='Petrel'))))")
ask("tail(Ship.objects.annotate(hands=Count('crew')).filter(Q(hands__gt=1) ^ Q(name='Petrel')))")
ask("tail(Ship.objects.annotate(hands=Count('crew')).exclude(crew__name='Ada'))")
ask("said(Ship.objects.annotate(hands=Count('crew')).filter(Q(hands__gt=1) | Q(name='Petrel')).query.where.split_having_qualify())")
ask("said(Ship.objects.annotate(hands=Count('crew')).filter(hands__gt=1, name='Petrel').query.where.split_having_qualify())")
ask("Ship.objects.annotate(hands=Count('crew')).filter(hands__gt=1).query.where.contains_aggregate, Ship.objects.annotate(hands=Count('crew')).filter(name='Petrel').query.where.contains_aggregate")
show("split_having_qualify: an AND is split between WHERE and HAVING, and an OR or a negated AND that mixes the two goes whole to HAVING")

# ---------------------------------------------------------------------------------------------
# Two queries into one, and compound statements.

MERGING = watch(SQ, "Query.combine", "Query.bump_prefix", "Query.join", "JoinPromoter.__init__", "JoinPromoter.add_votes", "JoinPromoter.update_join_types", "Query.unref_alias") | watch(WH, "WhereNode.add", label=lambda f: f"WhereNode.add({brief(f.f_locals['data'])}, {f.f_locals['conn_type']!r})") | watch(WH, "WhereNode.relabel_aliases")
MERGING[(SQ, "Query.combine")] = lambda f: f"Query.combine(rhs={brief(f.f_locals['rhs'])}, connector={f.f_locals['connector']!r})  (of {brief(f.f_locals['self'])})"
MERGING[(SQ, "Query.bump_prefix")] = lambda f: f"Query.bump_prefix({brief(f.f_locals['other_query'])}, exclude={brief(f.f_locals['exclude'])})"
MERGING[(SQ, "Query.join")] = lambda f: f"Query.join({brief(f.f_locals['join'])}, reuse={brief(f.f_locals['reuse'])})"
MERGING[(WH, "WhereNode.relabel_aliases")] = lambda f: f"WhereNode.relabel_aliases({brief(f.f_locals['change_map'])})"
says(SQ, "Query.join", "JoinPromoter.update_join_types")

lines("to_leith = Voyage.objects.filter(calls__name='Leith'); to_lisbon = Voyage.objects.filter(calls__name='Lisbon')")
with recorded(MERGING):
    do("both = to_leith & to_lisbon")
aliases(ASKING["both"].query)
ask("tail(both), list(both)")
with recorded(MERGING):
    do("either = to_leith | to_lisbon")
aliases(ASKING["either"].query)
ask("tail(either), list(either)")
show("Query.combine: for an AND the right side's joins are made afresh, for an OR they are reused, and the right side's where tree is relabelled and added")

ask("tail(Ship.objects.order_by('tonnage') | Ship.objects.order_by('name')), tail(Ship.objects.order_by('tonnage') & Ship.objects.all())")
ask("tail(Ship.objects.filter(Q(captain__name='Cora') | Q(tonnage__lt=500)) & Ship.objects.filter(captain__signed_on__year=2011))")
ask("tail(Ship.objects.filter(captain__name='Cora') | Ship.objects.filter(tonnage__lt=500))")
ask("tail(Ship.objects.filter(name='Petrel').extra(select={'a': '1'}) | Ship.objects.filter(name='Gannet'))")
ask("Ship.objects.extra(select={'a': '1'}) | Ship.objects.extra(select={'b': '2'})")
ask("tail(Ship.objects.extra(select={'a': '1'}) & Ship.objects.extra(select={'b': '2'}))")
ask("Ship.objects.all().query.combine(Sailor.objects.all().query, 'AND')")
ask("Ship.objects.all()[:1].query.combine(Ship.objects.all().query, 'AND')")
ask("Ship.objects.distinct().query.combine(Ship.objects.all().query, 'AND')")
show("What combine takes from the right side: its ordering where it has one, its select, its extra, and the join promotion of the two where trees")

lines("old = Sailor.objects.filter(signed_on__year__lt=2020); on_petrel = Sailor.objects.filter(ship=petrel); dag = Sailor.objects.filter(name='Dag')")
ask("sql_of(old.union(on_petrel))")
ask("sql_of(old.union(on_petrel, all=True))")
ask("sql_of(old.intersection(on_petrel))")
ask("sql_of(old.difference(on_petrel))")
ask("sql_of(old.union(on_petrel).union(dag))")
ask("sql_of(old.union(on_petrel, dag))")
ask("sql_of(old.union(on_petrel).values('name'))")
ask("sql_of(old.values('name').union(on_petrel.values('name')))")
ask("sql_of(old.union(on_petrel).order_by('name'))")
ask("sql_of(old.union(on_petrel).order_by('-signed_on', 'name'))")
ask("sql_of(old.values('name').union(on_petrel.values('name')).order_by('name'))")
ask("old.values('name').union(on_petrel.values('name')).order_by('id')")
ask("sql_of(old.union(on_petrel)[:2])")
ask("sql_of(old.union(Sailor.objects.none()))")
ask("sql_of(Sailor.objects.none().union(old))")
ask("sql_of(Sailor.objects.none().difference(old))")
ask("sql_of(old.difference(Sailor.objects.none()))")
ask("sql_of(old.union(on_petrel.filter(pk__in=[]))[:1])")
ask("sql_of(Sailor.objects.filter(pk__in=old.union(on_petrel).values('pk')))")
ask("str(old.union(on_petrel).query.exists())")
ask("old.order_by('name').union(on_petrel)")
ask("old[:1].union(on_petrel)")
ask("connection.ops.set_operators, connection.features.supports_select_union, connection.features.supports_select_intersection, connection.features.supports_select_difference, connection.features.supports_slicing_ordering_in_compound, connection.features.supports_parentheses_in_compound, connection.features.requires_compound_order_by_subquery")
show("get_combinator_sql on SQLite: the parts joined by the operator, a nested compound wrapped as a subquery, an empty part left out, and ORDER BY by position")

COMBINING = {k: v for k, v in COMPILING.items() if k[1] in ("SQLCompiler.as_sql", "SQLCompiler.get_combinator_sql", "SQLCompiler.get_order_by", "SQLCompiler.pre_sql_setup")}
COMBINING[(CO, "SQLCompiler.get_combinator_sql")] = generic
COMBINING[(CO, "SQLCompiler._get_combinator_part_sql")] = lambda f: f"SQLCompiler._get_combinator_part_sql(compiler for {brief(f.f_locals['compiler'].query)})"
COMBINING[(SQ, "Query.set_values")] = generic
COMBINING[(SQ, "Query.add_annotation")] = generic
COMBINING[(SQ, "Query.add_select_col")] = generic
says(CO, "SQLCompiler.get_combinator_sql", how=lambda f, v: f"({' '.join(v[0])!r}, {brief(tuple(v[1]))})")
says(CO, "SQLCompiler._get_combinator_part_sql", how=as_sql_said)

with recorded(COMBINING):
    do("sql_of(old.union(on_petrel).values('name').order_by('signed_on'))")
show("A compound statement compiled: each part compiled by a compiler of its own with the outer query's selection, and an ORDER BY column the parts did not select added to each")

# ---------------------------------------------------------------------------------------------
# INSERT, UPDATE and DELETE.

INSERTING = watch(
    CO, "SQLInsertCompiler.as_sql", "SQLInsertCompiler.execute_sql", "SQLInsertCompiler.prepare_value", "SQLInsertCompiler.pre_save_val",
    "SQLInsertCompiler.field_as_sql", "SQLInsertCompiler.assemble_as_sql",
) | watch(SUB, "InsertQuery.insert_values") | watch(
    "django.db.backends.base.operations", "BaseDatabaseOperations.insert_statement", "BaseDatabaseOperations.bulk_insert_sql", "BaseDatabaseOperations.returning_columns",
    "BaseDatabaseOperations.fetch_returned_rows", "BaseDatabaseOperations.on_conflict_suffix_sql",
) | watch("django.db.backends.sqlite3.operations", "DatabaseOperations.insert_statement", "DatabaseOperations.on_conflict_suffix_sql")
INSERTING[(CO, "SQLInsertCompiler.as_sql")] = plain
INSERTING[(CO, "SQLInsertCompiler.execute_sql")] = lambda f: f"SQLInsertCompiler.execute_sql(returning_fields={brief(f.f_locals['returning_fields'])})"
INSERTING[(CO, "SQLInsertCompiler.prepare_value")] = lambda f: f"SQLInsertCompiler.prepare_value({of_field(f.f_locals['field'])}, {brief(f.f_locals['value'])})"
INSERTING[(CO, "SQLInsertCompiler.pre_save_val")] = lambda f: f"SQLInsertCompiler.pre_save_val({of_field(f.f_locals['field'])}, {brief(f.f_locals['obj'])})"
INSERTING[(CO, "SQLInsertCompiler.field_as_sql")] = lambda f: f"SQLInsertCompiler.field_as_sql({of_field(f.f_locals['field']) if f.f_locals['field'] is not None else None}, {brief(f.f_locals['val'])})"
INSERTING[(CO, "SQLInsertCompiler.assemble_as_sql")] = lambda f: f"SQLInsertCompiler.assemble_as_sql(fields={brief(f.f_locals['fields'])}, value_rows={brief(f.f_locals['value_rows'])})"
INSERTING[(SUB, "InsertQuery.insert_values")] = lambda f: f"InsertQuery.insert_values(fields={brief(f.f_locals['fields'])}, objs={brief(f.f_locals['objs'])}" + (", raw=True" if f.f_locals["raw"] else "") + ")"
INSERTING[("django.db.backends.sqlite3.operations", "DatabaseOperations.insert_statement")] = lambda f: f"DatabaseOperations.insert_statement(on_conflict={brief(f.f_locals['on_conflict'])})  (sqlite3)"
INSERTING[("django.db.backends.sqlite3.operations", "DatabaseOperations.on_conflict_suffix_sql")] = lambda f: f"DatabaseOperations.on_conflict_suffix_sql(on_conflict={brief(f.f_locals['on_conflict'])})  (sqlite3)"
INSERTING[("django.db.backends.base.operations", "BaseDatabaseOperations.bulk_insert_sql")] = lambda f: f"BaseDatabaseOperations.bulk_insert_sql(fields={brief(f.f_locals['fields'])}, placeholder_rows={brief([list(r) for r in f.f_locals['placeholder_rows']])})"
INSERTING[("django.db.backends.base.operations", "BaseDatabaseOperations.returning_columns")] = lambda f: f"BaseDatabaseOperations.returning_columns({brief(f.f_locals['fields'])})"
INSERTING[("django.db.backends.base.operations", "BaseDatabaseOperations.fetch_returned_rows")] = lambda f: "BaseDatabaseOperations.fetch_returned_rows"
says(CO, "SQLInsertCompiler.prepare_value", "SQLInsertCompiler.pre_save_val", "SQLInsertCompiler.execute_sql")
says(CO, "SQLInsertCompiler.field_as_sql", how=as_sql_said)
says(CO, "SQLInsertCompiler.assemble_as_sql", how=lambda f, v: f"({brief([list(r) for r in v[0]])}, {brief(v[1])})")
says(CO, "SQLInsertCompiler.as_sql", how=lambda f, v: "[" + ", ".join(f"({sql!r}, {brief(tuple(params))})" for sql, params in v) + "]")
says("django.db.backends.sqlite3.operations", "DatabaseOperations.insert_statement", "DatabaseOperations.on_conflict_suffix_sql")
says("django.db.backends.base.operations", "BaseDatabaseOperations.bulk_insert_sql", "BaseDatabaseOperations.returning_columns", "BaseDatabaseOperations.fetch_returned_rows")

with recorded(INSERTING):
    do("oban = Port.objects.create(name='Oban', country='Scotland')")
    ask("oban.pk")
show("SQLInsertCompiler for one row: each field's value through pre_save and prepare_value, one placeholder each, and RETURNING for the key")

with recorded(INSERTING):
    do("Port.objects.bulk_create([Port(name='Mull', country='Scotland'), Port(name='Skagen', country='Denmark')])")
show("SQLInsertCompiler for two rows: bulk_insert_sql writes one VALUES list for both, and SQLite returns both keys")

with recorded(INSERTING):
    do("Manifest.objects.create(voyage=spring, crates=12, kilos_each=80)")
show("An insert with a database default and a generated column on SQLite: the default is written out as a value, and the generated column is asked back")

with recorded(INSERTING):
    do("Logbook.objects.bulk_create([Logbook(pk=1, title='Log 1, again')], ignore_conflicts=True)")
    do("Logbook.objects.bulk_create([Logbook(pk=1, title='Log 1, fair copy')], update_conflicts=True, update_fields=['title'], unique_fields=['pk'])")
quietly("Logbook.objects.filter(pk=1).update(title='Log 1')")
show("An insert with a conflict clause: insert_statement and on_conflict_suffix_sql are the backend's")

ask("Port.objects.create(name=Lower(Value('TOBERMORY')), country=Concat(Value('Scot'), Value('land'))).name")
quietly("Port.objects.filter(name='tobermory').delete()")
ask("Port.objects.create(name=F('country'), country='x')")
ask("Port.objects.create(name=Count('ships'), country='x')")
ask("Port.objects.create(name=Window(RowNumber()), country='x')")
ask("said(Manifest(voyage=spring, crates=1, kilos_each=1).stamped)")
ask("Manifest(voyage=spring, crates=1, kilos_each=1, stamped=True).stamped")
show("prepare_value: an expression is resolved for a save, and a column, an aggregate or a window may not stand in an insert")

UPDATING = watch(
    CO, "SQLUpdateCompiler.as_sql", "SQLUpdateCompiler.execute_sql", "SQLUpdateCompiler.pre_sql_setup", "SQLUpdateCompiler.execute_returning_sql",
    "SQLCompiler.execute_sql",
) | watch(SUB, "UpdateQuery.add_update_values", "UpdateQuery.add_update_fields", "UpdateQuery.add_related_update", "UpdateQuery.get_related_updates") | watch(
    SQ, "Query.chain", "Query.add_fields", "Query.clear_where", "Query.add_filter", "Query.count_active_tables", "Query.reset_refcounts")
UPDATING[(CO, "SQLUpdateCompiler.as_sql")] = plain
UPDATING[(CO, "SQLUpdateCompiler.pre_sql_setup")] = plain
UPDATING[(CO, "SQLUpdateCompiler.execute_sql")] = generic
UPDATING[(CO, "SQLCompiler.execute_sql")] = generic
UPDATING[(SUB, "UpdateQuery.add_update_values")] = lambda f: f"UpdateQuery.add_update_values({brief(f.f_locals['values'])})"
UPDATING[(SUB, "UpdateQuery.add_update_fields")] = lambda f: "UpdateQuery.add_update_fields([" + ", ".join(f"({of_field(fd)}, {brief(v)})" for fd, _, v in f.f_locals["values_seq"]) + "])"
UPDATING[(SUB, "UpdateQuery.add_related_update")] = lambda f: f"UpdateQuery.add_related_update(model={f.f_locals['model'].__name__}, field={of_field(f.f_locals['field'])}, value={brief(f.f_locals['value'])})"
UPDATING[(SQ, "Query.add_filter")] = lambda f: f"Query.add_filter({f.f_locals['filter_lhs']!r}, {brief(f.f_locals['filter_rhs'])})"
UPDATING[(SQ, "Query.chain")] = lambda f: f"Query.chain(klass={brief(f.f_locals['klass'])})" if f.f_locals["klass"] else "Query.chain"
says(CO, "SQLUpdateCompiler.as_sql", how=as_sql_said)
says(CO, "SQLUpdateCompiler.execute_sql", "SQLCompiler.execute_sql", "SQLUpdateCompiler.execute_returning_sql")
says(SQ, "Query.count_active_tables", "Query.chain")
says(SUB, "UpdateQuery.get_related_updates")

with recorded(UPDATING):
    do("Ship.objects.filter(pk=1).update(tonnage=F('tonnage') + 10, home=leith)")
quietly("Ship.objects.filter(pk=1).update(tonnage=480, home=bergen)")
show("SQLUpdateCompiler for a filter on the table itself: each value prepared or compiled, and one statement")

with recorded(UPDATING):
    do("Sailor.objects.filter(ship__name='Petrel').update(name=Upper('name'))")
quietly("Sailor.objects.filter(pk__in=[1, 2]).update(name=Concat(Substr('name', 1, 1), Lower(Substr('name', 2))))")
show("pre_sql_setup where the filter joins another table: the joins go into a subquery on the primary key, and the update keeps one table")

connection.features.update_can_self_select = False
with recorded(UPDATING):
    do("Sailor.objects.filter(ship__name='Petrel').update(signed_on=F('signed_on'))")
del connection.features.__dict__["update_can_self_select"]
show("With update_can_self_select switched off for this block: the keys are fetched first and the update names them")

with recorded(UPDATING):
    do("Officer.objects.filter(rank='master').update(name='Cora C.', rank='master')")
quietly("Officer.objects.filter(rank='master').update(name='Cora')")
show("An update of a child whose values belong to two tables: the parent's go to a related update, and the keys are fetched first for both")

ask("Sailor.objects.filter(pk=1).update(ship=petrel), Sailor.objects.filter(pk=1).update(ship=1)")
ask("Sailor.objects.filter(pk=1).update(name=petrel)")
ask("Ship.objects.filter(pk=1).update(tonnage=Count('crew'))")
ask("Ship.objects.filter(pk=1).update(tonnage=Window(RowNumber()))")
ask("Ship.objects.filter(pk=1).update(crew=1)")
ask("Manifest.objects.filter(serial='M-0001').update(kilos=1)")
ask("Manifest.objects.filter(serial='M-0001').update(crates=41), Manifest.objects.get(serial='M-0001').kilos")
quietly("Manifest.objects.filter(serial='M-0001').update(crates=40)")
ask("Berth.objects.filter(number=1).update(pk=(1, 9))")
ask("Ship.objects.filter(pk=1).update(tonnage=F('home__id'))")
ask("UpdateQuery(Ship).update_batch([1, 2], {'tonnage': F('tonnage')}, 'default')")
show("Asked of an update: a model instance, an aggregate, a window, a relation, a generated column and a composite key as values")

lines("compiler = Manifest.objects.filter(serial='M-0001').query.chain(klass=UpdateQuery).get_compiler('default')")
lines("compiler.query.add_update_values({'crates': 40})")
with recorded(UPDATING):
    do("compiler.execute_returning_sql([Manifest._meta.get_field('kilos')])")
ask("connection.features.can_return_rows_from_update")
show("execute_returning_sql: an update that asks for columns back, which Model.save uses for a generated column")

DELETING = watch(CO, "SQLDeleteCompiler.as_sql", "SQLDeleteCompiler._as_sql", "SQLCompiler.execute_sql") | watch(SUB, "DeleteQuery.do_query", "DeleteQuery.delete_batch") | watch(SQ, "Query.add_filter", "Query.clear_where", "Query.clear_select_clause")
DELETING[(CO, "SQLDeleteCompiler.as_sql")] = plain
DELETING[(CO, "SQLDeleteCompiler._as_sql")] = lambda f: f"SQLDeleteCompiler._as_sql({brief(f.f_locals['query'])})"
DELETING[(CO, "SQLCompiler.execute_sql")] = generic
DELETING[(SUB, "DeleteQuery.do_query")] = lambda f: f"DeleteQuery.do_query(table={f.f_locals['table']!r}, where=a WhereNode of {len(f.f_locals['where'].children[0].rhs)} keys, using={f.f_locals['using']!r})"
DELETING[(SUB, "DeleteQuery.delete_batch")] = lambda f: f"DeleteQuery.delete_batch(pk_list={brief(f.f_locals['pk_list'])}, using={f.f_locals['using']!r})"
DELETING[(SQ, "Query.add_filter")] = lambda f: f"Query.add_filter({f.f_locals['filter_lhs']!r}, {brief(f.f_locals['filter_rhs'])})"
says(CO, "SQLDeleteCompiler.as_sql", "SQLDeleteCompiler._as_sql", how=as_sql_said)
says(CO, "SQLCompiler.execute_sql")
says(SUB, "DeleteQuery.do_query", "DeleteQuery.delete_batch")

with recorded(DELETING):
    do("Port.objects.filter(name__in=['Oban', 'Mull', 'Skagen'])._raw_delete('default')")
    do("Sailor.objects.filter(ship__name='Nobody')._raw_delete('default')")
    do("Sailor.objects.filter(pk__in=Sailor.objects.filter(name='Nobody'))._raw_delete('default')")
show("SQLDeleteCompiler: a plain DELETE where the query has one table, and a subquery on the primary key where it has joins or refers to its own table")

connection.features.delete_can_self_reference_subquery = False
with recorded(DELETING):
    do("Sailor.objects.filter(pk__in=Sailor.objects.filter(name='Nobody'))._raw_delete('default')")
del connection.features.__dict__["delete_can_self_reference_subquery"]
show("With delete_can_self_reference_subquery switched off for this block: the subquery is moved under a second select")

import django.db.models.sql.subqueries as subqueries_module  # noqa: E402

subqueries_module.GET_ITERATOR_CHUNK_SIZE = 5
with recorded(DELETING):
    do("DeleteQuery(Logbook).delete_batch(list(range(100, 112)), 'default')")
subqueries_module.GET_ITERATOR_CHUNK_SIZE = 100
ask("Logbook.objects.count()")
show("With GET_ITERATOR_CHUNK_SIZE lowered to 5 for this block: delete_batch sends the keys in chunks of that size, one statement each")

ask("Sailor.objects.filter(pk__in=[])._raw_delete('default')")
ask("LogEntry.objects.exclude(pk__in=[])._raw_delete('default')")
show("A delete that can match nothing sends nothing, and one that matches everything has no WHERE")
