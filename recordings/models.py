"""A recording of models: how a class statement becomes a model class, what the class and
its options then hold, and what an instance does when it is made, read, saved, validated
and deleted.

    python recordings/models.py > recordings/models.txt

Chapter 8 of the book (pages/models.md and the pages under it) is written against this
output. It needs only the pinned Django (the project's virtual environment has it) and the
small project beside it, `harbour/`: a shipping line in three applications, `fleet`, `crew`
and `office`, entered in INSTALLED_APPS in that order. The database is a SQLite file made
for the run, and the files a FileField stores go to a directory made for the run. Run it
again after a re-pin: where the output changes, the chapter has to.

The blocks are of three kinds, and a block may mix them. Where the order of calls is the
point, the lines are calls, nested as they were made: the calls a block is about and no
others, so everything between the lines ran and is left out. A method is written by the
class that declares it, whatever the class of the object; what the object is, or what it
belongs to, follows in parentheses where it tells. `(Ship.home)` is that field, or a
descriptor the field set on its own class. `(the rel of Ship.home)` is the object that
field carries as `remote_field`, its ForeignObjectRel, or a descriptor made for that
object on the class the relation points at. `(a Ship)` is an instance, and `(of <Ship:
Petrel>)` a related manager made for that instance. Where a descriptor's class is not the
class that declares the method, it follows: `(Voyage.calls, a ManyToManyDescriptor)`. A
method of a related manager is written `RelatedManager.add` or `ManyRelatedManager.add`,
without the name of the function its class is made in. What a call returned follows `->`,
put into words at the moment it was returned; `raises` names an exception, once, at the
innermost written-down call it left. A call with neither after it returned something the
recording does not describe, or was left by an exception already named further in. A
function behind `cached_property` is written down only when its body runs.

A line that begins `SQL` is a statement as Django handed it to its own cursor, with its
parameters where it has any: the placeholders are Django's `%s`, which SQLite's backend
rewrites before the driver sees them. `BEGIN` passes through that cursor on SQLite and a
commit does not, so a commit is the line `BaseDatabaseWrapper.commit`. A line that begins
`signal` is written by a receiver the script connects to that signal for the block. A line
that is words and not a call (`bram.ship is read`) is the script's own statement, with what
it set going written under it.

Some calls are made so often, or outside what a block is about, that they are written down
only under a condition, which the docstring of the function that labels them gives:
`Options.setup_pk` only for a field that says it is the primary key;
`DeferredAttribute.__get__` only for an instance that has no value under the field's
attname; `Model._save_parents` only for a class that has parents;
`Model._assign_returned_values` only where it was handed fields to assign;
`Field.__deepcopy__` and `OneToOneField.__init__` only while a class statement is being
dealt with; a descriptor's `__get__` only for a read on an instance, not on the class; and
a function that shares the name of a watched method without being a method is passed over.

A second kind of block puts one question to a running Django on each line: the text before
`->` is the expression that was evaluated and what follows is the repr of its value, and a
statement the question sent to the database stands under it. The third kind writes down
what an object holds, or what a call returned, a thing to a line.

Nothing is written that differs between machines or runs: no address in memory, no path on
disk, no time read from the machine's clock. The clock is the recording's own:
`django.utils.timezone.now` is replaced by a function that returns 10 April 2026, 09:00 UTC.
In a line of calls a date is written as its repr without the module's name, `date(2026, 3,
2)`. An instance is written as its repr, `<Ship: Petrel>`; where it has no name loaded for
its `__str__` to read it is written `<Ship: pk=1>`, and the script stops if putting a call
into words ever sends a statement to the database, so that no `SQL` line is this script's
own doing. A file's name within its storage is written with a forward slash throughout:
between `FileField.generate_filename` and `Storage.get_available_name` it has the machine's
own separator, which on Windows is a backslash.

What ran is SQLite's part as well as Django's: the column types, the form a value is given
for a query, `INSERT OR IGNORE`, `RETURNING`, a table made again to add a constraint, and
the order of rows where a statement has no `ORDER BY` are this backend's.

    RECORD_EVERYTHING=django.db.models.base python recordings/models.py    every call in the modules with that prefix, but in the blocks of checks
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
import inspect  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402

import django  # noqa: E402
from django.conf import settings  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # the same bytes on every machine
EVERYTHING = tuple(p for p in os.environ.get("RECORD_EVERYTHING", "").split(",") if p)

SCRATCH = tempfile.mkdtemp()
DATABASE = os.path.join(SCRATCH, "harbour.sqlite3")
MEDIA = os.path.join(SCRATCH, "media")

settings.configure(
    DEBUG=False,
    SECRET_KEY="recording",
    INSTALLED_APPS=["harbour.fleet", "harbour.crew", "harbour.office"],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DATABASE}},
    DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    MEDIA_ROOT=MEDIA,
    USE_TZ=True,
    TIME_ZONE="UTC",
)

LINES = []
STACK = []  # the watched frames open at this moment: the depth of the next line
AT = {}  # where in LINES the line of each open watched call is, by the frame
SEEN = set()  # generator and coroutine frames already written down: such a frame is entered more than once
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
# How things are said.

def a(name: str) -> str:
    """A thing by its class's name, with the article the name is read with."""
    return ("an " if name[0] in "AEIOU" and not name.startswith("One") else "a ") + name


def thing(value) -> str:
    """A value by what it is: a class by its name, anything else by its class's."""
    if inspect.isclass(value):
        return f"the class {value.__qualname__}"
    return a(type(value).__name__)


def named(model) -> str:
    """A model where a class or a string may stand: the class by its name, the string as written."""
    return model.__name__ if inspect.isclass(model) else repr(model)


def of_field(field) -> str:
    """A field by the class it is on and its name: Ship.home."""
    model = getattr(field, "model", None)
    return f"{model.__name__}.{field.name}" if inspect.isclass(model) else f"an unbound {type(field).__name__}"


def plain(frame) -> str:
    return frame.f_code.co_qualname


def declared_and_actual(frame, said: str) -> str:
    """A call of a method, with the class of the object where it is not the declaring class."""
    declaring = frame.f_code.co_qualname.split(".")[0]
    actual = type(frame.f_locals["self"]).__name__
    return said if actual == declaring else f"{said}  ({a(actual)})"


RULES = {}  # the set in force
LABELLING = False  # whether a call is being put into words at this moment: a statement sent to the database then is a fault of this script's

# (module, qualname) -> what to say of the value a call returned.
AFTER = {}


def find(module: str, qualname: str, name: str):
    label = RULES.get((module, qualname))
    if label is not None:
        return label
    by_name = RULES.get("named")
    if by_name and name in by_name and module.startswith(RULES.get("named_in", "django.db.models")):
        return by_name[name]
    if EVERYTHING and module.startswith(EVERYTHING):
        return plain
    return None


def profile(frame, event, arg):
    code = frame.f_code
    if code is UNWINDING:
        return
    if event == "call":
        label = find(frame.f_globals.get("__name__", ""), code.co_qualname, code.co_name)
        if label is None:
            return
        if code.co_flags & RESUMABLE and id(frame) in SEEN:  # every resumption is a call event
            STACK.append(frame)
            return
        flush()  # what the call before this one returned is said first: a label may depend on it
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
            SEEN.add(id(frame))
        note(text)
        AT[id(frame)] = len(LINES) - 1
        STACK.append(frame)
    elif event == "return":
        if STACK and STACK[-1] is frame:
            flush()
            after = None if code.co_flags & RESUMABLE else AFTER.get((frame.f_globals.get("__name__", ""), code.co_qualname))
            if after is None and not code.co_flags & RESUMABLE:
                after = (RULES.get("named_after") or {}).get(code.co_name)
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
        if not any(e is exception for e in RAISED) and not isinstance(exception, (StopIteration, GeneratorExit)):
            RAISED.append(exception)
            if at == len(LINES) - 1:
                LINES[at] += f"  raises {type(exception).__name__}"
            else:
                LINES.append("  " * depth + f"raises {type(exception).__name__}")


UNWINDING = unwinding.__code__
MONITOR = sys.monitoring.PROFILER_ID
sys.monitoring.use_tool_id(MONITOR, "recordings/models.py")
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
        raise SystemExit(f"recordings/models.py: this Python reports an exception leaving a function otherwise than expected: {LINES!r}")
    reset()
    RULES = {}


self_test()

ASKING = {}  # the names an asked expression may use
LISTENING = False  # whether a statement sent to the database is written down: inside a recorded block or a question


class Said(str):
    """An answer already put into words, to be written as it is and not as a string's repr,
    alone or among other answers."""

    __repr__ = str.__str__


def ask(expression: str, brief_: bool = False, show_as: str = "") -> None:
    """One question and its answer, on one line. The question is evaluated as it is written
    down, so the line cannot say one thing and the script do another. A brief answer names an
    exception and leaves out its message."""
    global LISTENING
    watching, listening = sys.getprofile(), LISTENING
    sys.setprofile(None)  # a question is its answer and nothing else: no calls are written down under it
    flush()
    before = len(LINES)
    LISTENING = True
    try:
        value = eval(expression, ASKING)
        said = value if isinstance(value, Said) else answered(value)
    except Exception as raised:
        said = f"raises {type(raised).__name__}" + ("" if brief_ else f": {raised}")
    LISTENING = listening
    # A query made while the question was answered stands under the question, not above it.
    LINES[before:] = ["  " * len(STACK) + f"{show_as or expression}  ->  {said}", *("  " + line for line in LINES[before:])]
    sys.setprofile(watching)


def answered(value) -> str:
    return repr(value)


def names(things) -> Said:
    """The names of a list of fields, managers or classes, in the list's order."""
    return Said("[" + ", ".join(t.__name__ if inspect.isclass(t) else getattr(t, "name", None) or repr(t) for t in things) + "]")


ASKING["names"] = names


import contextlib  # noqa: E402


@contextlib.contextmanager
def step(text: str):
    """A line of words, and what runs in the block written down under it."""
    note(text)
    STACK.append(None)
    try:
        yield
    finally:
        flush()
        STACK.pop()


# The calls that open and close a transaction, for every set of rules that writes statements down.
TRANSACTION = {
    ("django.db.transaction", "Atomic.__enter__"): lambda f: f"Atomic.__enter__  (savepoint={f.f_locals['self'].savepoint})",
    ("django.db.transaction", "Atomic.__exit__"):
        lambda f: "Atomic.__exit__" + ("" if f.f_locals["exc_type"] is None else f"  (with {f.f_locals['exc_type'].__name__})"),
    ("django.db.transaction", "mark_for_rollback_on_error"): plain,
    ("django.db.backends.base.base", "BaseDatabaseWrapper.commit"): plain,
    ("django.db.backends.base.base", "BaseDatabaseWrapper.rollback"): plain,
    ("django.db.backends.base.base", "BaseDatabaseWrapper.savepoint"): plain,
    ("django.db.backends.base.base", "BaseDatabaseWrapper.savepoint_commit"): plain,
    ("django.db.backends.base.base", "BaseDatabaseWrapper.savepoint_rollback"): plain,
}

# ---------------------------------------------------------------------------------------------
# The class statements: what ModelBase.__new__ does with each.

def new_called(frame) -> str:
    bases = frame.f_locals["bases"]
    said = ", ".join(b.__name__ for b in bases) + ("," if len(bases) == 1 else "")
    return f"ModelBase.__new__({frame.f_locals['name']!r}, ({said}))"


def add_to_class_called(frame) -> str:
    return f"ModelBase.add_to_class({frame.f_locals['cls'].__name__}, {frame.f_locals['name']!r}, {thing(frame.f_locals['value'])})"


def contribute_called(frame) -> str:
    given = frame.f_locals
    cls, name = (given["cls"], given["name"]) if "cls" in given else given["args"][:2]  # GeneratedField's takes *args
    return declared_and_actual(frame, f"{frame.f_code.co_qualname}({cls.__name__}, {name!r})")


def contribute_related_called(frame) -> str:
    rel = frame.f_locals["related"]
    return f"{frame.f_code.co_qualname}({frame.f_locals['cls'].__name__}, the rel of {of_field(rel.field)})"


def add_field_called(frame) -> str:
    field = frame.f_locals["field"]
    return f"Options.add_field({of_field(field)}{', private=True' if frame.f_locals['private'] else ''})"


def setup_pk_called(frame):
    """Options.setup_pk is called for every field that goes into local_fields. Only a call for a
    field that says it is the primary key is written down."""
    field = frame.f_locals["field"]
    return f"Options.setup_pk({of_field(field)})" if field.primary_key else None


def setup_pk_returned(frame, value) -> str:
    opts = frame.f_locals["self"]
    return f"Options.pk is {of_field(opts.pk)}"


def expire_called(frame) -> str:
    opts = frame.f_locals["self"]
    return f"Options._expire_cache(forward={frame.f_locals['forward']}, reverse={frame.f_locals['reverse']})  (of {opts.object_name})"


def lazy_related_called(frame) -> str:
    related = ", ".join(named(m) for m in frame.f_locals["related_models"])
    return f"lazy_related_operation({frame.f_locals['function'].__name__}, {frame.f_locals['model'].__name__}, {related})"


def waiting_said(frame, value) -> str:
    """What the registry holds back once a lazy operation has been handed over: read from the
    registry itself as the call returns."""
    from django.apps import apps
    pending = {key: len(waiting) for key, waiting in sorted(apps._pending_operations.items()) if waiting}
    if not pending:
        return "nothing waits in Apps._pending_operations"
    return "Apps._pending_operations holds " + ", ".join(f"{count} under {key!r}" for key, count in pending.items())


def lazy_model_called(frame) -> str:
    keys = ", ".join(repr(k) for k in frame.f_locals["model_keys"])
    return f"Apps.lazy_model_operation(function{', ' + keys if keys else ''})"


def resolve_related_called(frame) -> str:
    return (f"resolve_related_class({frame.f_locals['model'].__name__}, {frame.f_locals['related'].__name__}, "
            f"field={of_field(frame.f_locals['field'])})")


def descriptor_made(what):
    def said(frame) -> str:
        return declared_and_actual(frame, f"{frame.f_code.co_qualname}({what(frame)})")
    return said


def parent_link_made(frame):
    """A OneToOneField made while a class is being put together and not in a class body: the
    link to a parent that ModelBase.__new__ makes."""
    if not STACK:
        return None
    kwargs = frame.f_locals["kwargs"]
    said = ", ".join(f"{k}={v!r}" for k, v in kwargs.items() if k in ("name", "auto_created", "parent_link"))
    return f"OneToOneField.__init__({named(frame.f_locals['to'])}, on_delete={frame.f_locals['on_delete'].__name__}, {said})"


def exception_made(frame) -> str:
    bases = frame.f_locals["bases"]
    said = ", ".join(b.__qualname__ for b in bases) + ("," if len(bases) == 1 else "")
    return f"subclass_exception({frame.f_locals['name']!r}, ({said}))"


def deepcopied(frame):
    if not STACK:
        return None
    return f"Field.__deepcopy__  (a copy of {of_field(frame.f_locals['self'])})"


def intermediary_called(frame) -> str:
    return f"create_many_to_many_intermediary_model({of_field(frame.f_locals['field'])}, {frame.f_locals['klass'].__name__})"


def index_named(frame, value) -> str:
    return f"the index is named {frame.f_locals['self'].name!r}"


CLASSES = {
    ("django.db.models.base", "ModelBase.__new__"): new_called,
    ("django.db.models.base", "ModelBase.add_to_class"): add_to_class_called,
    ("django.db.models.base", "ModelBase._prepare"): lambda f: f"ModelBase._prepare({f.f_locals['cls'].__name__})",
    ("django.db.models.base", "subclass_exception"): exception_made,
    ("django.db.models.options", "Options.add_field"): add_field_called,
    ("django.db.models.options", "Options.setup_pk"): setup_pk_called,
    ("django.db.models.options", "Options.setup_proxy"): lambda f: f"Options.setup_proxy({f.f_locals['target'].__name__})",
    ("django.db.models.options", "Options._prepare"): lambda f: f"Options._prepare({f.f_locals['model'].__name__})",
    ("django.db.models.options", "Options._get_default_pk_class"): plain,
    ("django.db.models.options", "Options.add_manager"): lambda f: f"Options.add_manager({a(type(f.f_locals['manager']).__name__)})",
    ("django.db.models.fields", "Field.__deepcopy__"): deepcopied,
    ("django.db.models.fields.related", "OneToOneField.__init__"): parent_link_made,
    ("django.db.models.fields.related", "lazy_related_operation"): lazy_related_called,
    ("django.db.models.fields.related", "RelatedField.contribute_to_class.<locals>.resolve_related_class"): resolve_related_called,
    ("django.db.models.fields.related", "ManyToManyField.contribute_to_class.<locals>.resolve_through_model"):
        lambda f: f"resolve_through_model({f.f_locals['_'].__name__}, {f.f_locals['model'].__name__}, field={of_field(f.f_locals['field'])})",
    ("django.db.models.fields.related", "create_many_to_many_intermediary_model"): intermediary_called,
    ("django.db.models.query_utils", "DeferredAttribute.__init__"): descriptor_made(lambda f: of_field(f.f_locals["field"])),
    ("django.db.models.fields.related_descriptors", "ForwardManyToOneDescriptor.__init__"):
        descriptor_made(lambda f: of_field(f.f_locals["field_with_rel"])),
    ("django.db.models.fields.related_descriptors", "ReverseOneToOneDescriptor.__init__"):
        descriptor_made(lambda f: f"the rel of {of_field(f.f_locals['related'].field)}"),
    ("django.db.models.fields.related_descriptors", "ReverseManyToOneDescriptor.__init__"):
        descriptor_made(lambda f: f"the rel of {of_field(f.f_locals['rel'].field)}"),
    ("django.db.models.fields.related_descriptors", "ManyToManyDescriptor.__init__"):
        descriptor_made(lambda f: f"the rel of {of_field(f.f_locals['rel'].field)}, reverse={f.f_locals['reverse']}"),
    ("django.db.models.manager", "ManagerDescriptor.__init__"): descriptor_made(lambda f: a(type(f.f_locals["manager"]).__name__)),
    ("django.db.models.indexes", "Index.set_name_with_model"): lambda f: f"Index.set_name_with_model({f.f_locals['model'].__name__})",
    ("django.apps.registry", "Apps.register_model"): lambda f: f"Apps.register_model({f.f_locals['app_label']!r}, {f.f_locals['model'].__name__})",
    ("django.apps.registry", "Apps.do_pending_operations"): lambda f: f"Apps.do_pending_operations({f.f_locals['model'].__name__})",
    ("django.apps.registry", "Apps.lazy_model_operation"): lazy_model_called,
    ("django.apps.registry", "Apps.clear_cache"): plain,
    "named": {
        "contribute_to_class": contribute_called,
        "contribute_to_related_class": contribute_related_called,
    },
}

AFTER.update({
    ("django.db.models.options", "Options.setup_pk"): setup_pk_returned,
    ("django.db.models.options", "Options._get_default_pk_class"): lambda f, v: f"the class {v.__name__}",
    ("django.db.models.fields.related", "lazy_related_operation"): waiting_said,
    ("django.apps.registry", "Apps.do_pending_operations"): waiting_said,
    ("django.db.models.indexes", "Index.set_name_with_model"): index_named,
})


def class_prepared_heard(sender, **kwargs):
    note(f"signal class_prepared, sender {sender.__name__}")


from django.db.models.signals import class_prepared  # noqa: E402

class_prepared.connect(class_prepared_heard)

import json  # noqa: E402

# The commit comes from the book's pin and not from django.get_version(), which for a
# development version asks git for a timestamp and so depends on the machine.
PIN = json.load(open(os.path.join(os.path.dirname(HERE), "pin.json"), encoding="utf-8"))["trees"]["django"]["commit"]
print(f"Django {django.VERSION[0]}.{django.VERSION[1]} in development, at the commit {PIN}, and the project harbour:\n"
      "INSTALLED_APPS = ['harbour.fleet', 'harbour.crew', 'harbour.office'], DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField',\n"
      "USE_TZ = True, TIME_ZONE = 'UTC', MEDIA_URL not set, a SQLite database, and the clock at 2026-04-10 09:00 UTC\n")

with recorded(CLASSES):
    django.setup()

class_prepared.disconnect(class_prepared_heard)

# One block to a class statement: the lines from each ModelBase.__new__ at the left margin to the next.
flush()
STATEMENTS = []
for line in LINES:
    if line.startswith("ModelBase.__new__"):
        STATEMENTS.append([line])
    elif STATEMENTS and line.startswith(" "):
        STATEMENTS[-1].append(line)
reset()

print("django.setup(): the model classes, in the order their class statements ran")
for statement in STATEMENTS:
    print("    " + statement[0])
    for line in statement[1:]:
        if "Apps.register_model" in line or "ModelBase.__new__" in line:
            print("    " + line)
print()

for statement in STATEMENTS:
    name = statement[0].split("'")[1]
    print(f"The class statement of {name}")
    for line in statement:
        print("    " + line)
    print()

from django.apps import apps  # noqa: E402
from django.db import connection, models, transaction  # noqa: E402
from django.db.models.options import Options  # noqa: E402
from django.utils import timezone  # noqa: E402

from harbour.crew.models import Officer, Rank, Sailor, SailorQuerySet, Veteran, VeteranManager  # noqa: E402
from harbour.fleet.models import Named, Port, Ship, Voyage  # noqa: E402
from harbour.office.models import Berth, Licence, LogEntry, Logbook, Manifest  # noqa: E402

ASKING.update(
    apps=apps, connection=connection, models=models, transaction=transaction, datetime=datetime, Options=Options,
    Named=Named, Port=Port, Ship=Ship, Voyage=Voyage, Sailor=Sailor, Officer=Officer, Veteran=Veteran, Rank=Rank,
    SailorQuerySet=SailorQuerySet, VeteranManager=VeteranManager,
    Licence=Licence, Manifest=Manifest, Berth=Berth, Logbook=Logbook, LogEntry=LogEntry,
)

# ---------------------------------------------------------------------------------------------
# What the classes hold, asked before any table is made and before any query has run.

EVERY_CLASS_HAS = ("__module__", "__qualname__", "__firstlineno__", "__static_attributes__", "__dict__", "__weakref__")


def holds(cls, title: str) -> None:
    """Each name in a class's own __dict__ with what its value is, in the order the names were
    set, but for the names every class has."""
    for name, value in vars(cls).items():
        if name not in EVERY_CLASS_HAS:
            note(f"{name}: {repr(value) if name == '__doc__' else thing(value)}")
    show(title)


def cached(model) -> Said:
    """What a model's options have cached at this moment: which of the names that
    Options._expire_cache deletes are in the object's __dict__, and how many answers
    Options._get_fields_cache holds."""
    caches = Options.FORWARD_PROPERTIES | Options.REVERSE_PROPERTIES
    present = ", ".join(sorted(n for n in vars(model._meta) if n in caches))
    return Said(f"[{present}] and {len(model._meta._get_fields_cache)} in _get_fields_cache")


ASKING["cached"] = cached

# Asked first of all, while nothing has yet read a list of fields from these two models' options.
ask("sorted(Options.FORWARD_PROPERTIES)")
ask("sorted(Options.REVERSE_PROPERTIES)")
ask("cached(Logbook)")
ask("cached(LogEntry)")
ask("names(Logbook._meta.fields)")
ask("cached(Logbook)")
ask("names(Logbook._meta.related_objects)")
ask("cached(Logbook)")
ask("cached(LogEntry)")
ask("Logbook._meta._expire_cache(forward=False)")
ask("cached(Logbook)")
ask("cached(LogEntry)")
ask("Logbook._meta.get_field('logentry')")
ask("cached(Logbook)")
show("What the options of two models have cached, as lists of fields are asked of one of them")

holds(Named, "What the class Named holds in its own __dict__, in the order the names were set")
holds(Ship, "What the class Ship holds in its own __dict__, in the order the names were set")
holds(Port, "What the class Port holds in its own __dict__, in the order the names were set")
holds(Sailor, "What the class Sailor holds in its own __dict__, in the order the names were set")
holds(Officer, "What the class Officer holds in its own __dict__, in the order the names were set")
holds(Veteran, "What the class Veteran holds in its own __dict__, in the order the names were set")


def declare(name: str, **meta):
    """Run a class statement for a model of the fleet whose Meta has these attributes."""
    return type(name, (models.Model,), {"__module__": "harbour.fleet.models", "Meta": type("Meta", (), meta)})


ASKING["declare"] = declare

ask("type(Ship)")
ask("Ship.__doc__")
ask("[m.__name__ for m in apps.get_models()]")
ask("[m.__name__ for m in apps.get_models(include_auto_created=True)]")
ask("[c.__name__ for c in Ship.DoesNotExist.__mro__]")
ask("Ship.DoesNotExist.__module__, Ship.DoesNotExist.__qualname__")
ask("[c.__name__ for c in Ship.NotUpdated.__mro__]")
ask("Officer.DoesNotExist.__bases__ == (Sailor.DoesNotExist,)")
ask("hasattr(Named, 'DoesNotExist'), hasattr(Named, 'objects'), hasattr(Named, '_meta')")
ask("Named.Meta.abstract, Named._meta.abstract")
ask("Port.Meta is Named.Meta")
ask("declare('Wherry', colour='red')")
ask("type('Tug', (models.Model,), {'__module__': 'elsewhere'})")
ask("type('Tug', (models.Model,), {'__module__': 'elsewhere', 'Meta': type('Meta', (), {'abstract': True})}).__name__")
show("Asked of the classes the metaclass made")

ask("Ship._meta")
ask("Ship._meta.app_label, Ship._meta.object_name, Ship._meta.model_name")
ask("Ship._meta.label, Ship._meta.label_lower, Ship._meta.db_table")
ask("Ship._meta.verbose_name, str(Ship._meta.verbose_name_plural)")
ask("Named._meta.ordering, Port._meta.ordering, Ship._meta.ordering, Voyage._meta.ordering")
ask("sorted(Ship._meta.original_attrs)")
ask("sorted(Port._meta.original_attrs)")
ask("[c.name for c in Ship._meta.constraints]")
ask("[i.name for i in Ship._meta.indexes]")
ask("Ship._meta.pk, Ship._meta.auto_field")
ask("Ship._meta.abstract, Ship._meta.proxy, Ship._meta.managed, Ship._meta.swapped")
ask("Ship._meta.apps is apps, Ship._meta.app_config")
ask("Ship._meta.concrete_model.__name__, Veteran._meta.concrete_model.__name__, Veteran._meta.proxy_for_model.__name__")
ask("Veteran._meta.db_table, Veteran._meta.pk is Sailor._meta.pk")
ask("Officer._meta.parents")
ask("Officer._meta.pk")
ask("Voyage.calls.through._meta.auto_created, Voyage.calls.through._meta.db_table")
ask("Berth._meta.pk, names(Berth._meta.pk_fields), Berth._meta.is_composite_pk")
ask("names(Manifest._meta.db_returning_fields)")
ask("Manifest._meta.auto_field, Berth._meta.auto_field, Officer._meta.auto_field")
show("Asked of Options, the object a model class keeps as _meta")

ask("names(Ship._meta.local_fields)")
ask("names(Ship._meta.local_many_to_many), names(Ship._meta.private_fields)")
ask("names(Ship._meta.fields)")
ask("names(Ship._meta.concrete_fields)")
ask("names(Ship._meta.related_objects)")
ask("names(Ship._meta.get_fields())")
ask("names(Ship._meta.get_fields(include_hidden=True))")
ask("names(Voyage._meta.fields), names(Voyage._meta.many_to_many)")
ask("names(Voyage._meta.get_fields())")
ask("names(Port._meta.get_fields())")
ask("names(Port._meta.get_fields(include_hidden=True))")
ask("names(Sailor._meta.get_fields())")
ask("names(Officer._meta.local_fields)")
ask("names(Officer._meta.fields)")
ask("names(Officer._meta.get_fields(include_parents=False))")
ask("names(Veteran._meta.local_fields), names(Veteran._meta.fields)")
ask("names(Manifest._meta.concrete_fields), names(Manifest._meta.local_concrete_fields)")
ask("names(Berth._meta.fields), names(Berth._meta.concrete_fields)")
ask("Ship._meta.get_field('home')")
ask("Ship._meta.get_field('home_id') is Ship._meta.get_field('home')")
ask("Ship._meta.get_field('crew')")
ask("Port._meta.get_field('ships')")
ask("Ship._meta.get_field('mast')")
ask("Port._meta.get_field('Voyage_calls+')")
ask("names(Port._meta.related_objects)")
ask("names(Officer._meta.get_fields())")
ask("names(Veteran._meta.get_fields(include_parents=False))")
show("The lists of fields that Options gives")



ask("[(f.name, f.creation_counter) for f in Ship._meta.local_fields]")
ask("Named._meta.get_field('name').creation_counter == Port._meta.get_field('name').creation_counter == Ship._meta.get_field('name').creation_counter")
ask("Port._meta.get_field('name') is Ship._meta.get_field('name'), Port._meta.get_field('name') == Ship._meta.get_field('name')")
ask("Named._meta.get_field('name').model, Port._meta.get_field('name').model, Ship._meta.get_field('name').model")
ask("Officer._meta.get_field('name') is Sailor._meta.get_field('name'), Officer._meta.get_field('name').model")
ask("[(f.name, f.attname, f.column) for f in Ship._meta.fields]")
ask("[(f.name, f.attname, f.column) for f in Voyage._meta.get_fields() if not f.auto_created]")
ask("type(Ship.tonnage).__name__, Ship.tonnage.field")
ask("type(Ship.home_id).__name__, type(Ship.home).__name__")
ask("Ship._meta.get_field('tonnage').deconstruct()")
ask("Ship._meta.get_field('name').deconstruct()")
ask("sorted(Ship._meta.get_field('home').deconstruct()[3])")
ask("Ship._meta.get_field('home').deconstruct()[3]['to'], Ship._meta.get_field('home').deconstruct()[3]['related_name']")
ask("Ship._meta.get_field('tonnage').clone() == Ship._meta.get_field('tonnage')")
ask("Ship._meta.get_field('tonnage').clone().deconstruct()[1:] == Ship._meta.get_field('tonnage').deconstruct()[1:]")
ask("Ship._meta.get_field('tonnage').clone().name, hasattr(Ship._meta.get_field('tonnage').clone(), 'model')")
ask("Ship._meta.get_field('tonnage').get_internal_type(), Ship._meta.get_field('tonnage').db_type(connection)")
ask("Ship._meta.get_field('tonnage').db_parameters(connection)")
ask("Ship._meta.pk.db_type(connection), Ship._meta.pk.rel_db_type(connection), Ship._meta.get_field('home').db_type(connection)")
ask("[(type(v).__name__, v.limit_value) for v in Ship._meta.get_field('tonnage').validators]")
ask("[(type(v).__name__, v.limit_value) for v in Ship._meta.get_field('name').validators]")
ask("Ship._meta.get_field('tonnage').get_default(), Ship._meta.get_field('name').get_default(), Ship._meta.get_field('captain').get_default()")
ask("Manifest._meta.get_field('stamped').has_default(), Manifest._meta.get_field('stamped').has_db_default()")
ask("type(Manifest._meta.get_field('stamped').get_default()).__name__")
ask("Manifest._meta.get_field('stamped').db_returning, Manifest._meta.get_field('kilos').db_returning, Manifest._meta.get_field('kilos').generated")
import pickle  # noqa: E402

ASKING.update(pickle=pickle)
ask("pickle.loads(pickle.dumps(Ship._meta.get_field('tonnage'))) is Ship._meta.get_field('tonnage')")
ask("Ship._meta.get_field('tonnage').__reduce__()[0].__name__, Ship._meta.get_field('tonnage').__reduce__()[1]")
ask("hash(Port._meta.get_field('name')) == hash(Ship._meta.get_field('name'))")
show("Asked of the fields of Ship and of a few others")

ask("type(Rank), [c.__name__ for c in Rank.__mro__]")
ask("Rank.choices")
ask("Rank.values, Rank.labels, Rank.names")
ask("Rank.MATE, Rank.MATE.value, Rank.MATE.label, Rank.ENGINEER.label")
ask("Rank.MATE == 'mate', str(Rank.MATE), 'mate' in Rank, Rank('mate') is Rank.MATE")
ask("Officer._meta.get_field('rank').choices")
ask("Officer._meta.get_field('rank').flatchoices")
ask("Officer(rank='mate').get_rank_display(), Officer(rank='bosun').get_rank_display()")
ask("type(vars(Officer)['get_rank_display']).__name__")
ask("list(Officer._meta.get_field('rank').get_choices())")
ask("Officer._meta.get_field('rank').get_choices(include_blank=False)")
show("Choices: an enumeration, and what a field makes of it")


def column(field) -> Said:
    """What a field calls itself, and the column SQLite's backend gives it. A field that is
    on no class has no column name for its check to be written with, so one is given the
    name `n`, as contribute_to_class would give it the name of its attribute."""
    if field.name is None:
        field.set_attributes_from_name("n")
    made = field.db_parameters(connection)
    return Said(f"internal type {field.get_internal_type()!r}, column {made['type']!r}" + (f", check {made['check']!r}" if made["check"] else ""))


ASKING["column"] = column

for made in (
    "models.AutoField(primary_key=True)", "models.BigAutoField(primary_key=True)", "models.SmallAutoField(primary_key=True)",
    "models.BooleanField()", "models.CharField(max_length=60)", "models.CharField()", "models.TextField()", "models.SlugField()",
    "models.EmailField()", "models.URLField()", "models.FilePathField()", "models.GenericIPAddressField()",
    "models.SmallIntegerField()", "models.IntegerField()", "models.BigIntegerField()",
    "models.PositiveSmallIntegerField()", "models.PositiveIntegerField()", "models.PositiveBigIntegerField()",
    "models.FloatField()", "models.DecimalField(max_digits=8, decimal_places=2)",
    "models.DateField()", "models.TimeField()", "models.DateTimeField()", "models.DurationField()",
    "models.BinaryField()", "models.UUIDField()", "models.JSONField()",
    "models.FileField()", "models.ImageField()",
):
    ask(f"column({made})")
ask("column(Ship._meta.get_field('home'))")
ask("column(Officer._meta.get_field('sailor_ptr'))")
ask("column(Manifest._meta.get_field('kilos'))")
ask("Voyage._meta.get_field('calls').db_type(connection), Berth._meta.pk.db_type(connection)")
show("The field classes: what each calls itself, and the column SQLite's backend gives it")

ask("isinstance(models.BigAutoField(primary_key=True), models.AutoField)")
ask("issubclass(models.SmallAutoField, models.AutoField), issubclass(models.IntegerField, models.AutoField)")
ask("[c.__name__ for c in models.BigAutoField.__mro__]")
ask("[c.__name__ for c in models.AutoField.__mro__]")
ask("type(models.AutoField).__name__, type(models.BigAutoField).__name__")
ask("models.IntegerField().to_python('7'), models.IntegerField().to_python(None)")
ask("models.IntegerField().to_python('seven')")
ask("models.BooleanField().to_python('t'), models.BooleanField().to_python('0')")
ask("models.DecimalField(max_digits=8, decimal_places=2).to_python('12.50')")
ask("models.DecimalField(max_digits=8, decimal_places=2).to_python(12.5)")
ask("models.DateField().to_python('2026-03-02'), models.DateField().to_python(datetime.datetime(2026, 3, 2, 14, 0))")
ask("models.DurationField().to_python('1 02:30:00')")
ask("models.UUIDField().to_python('c0ffee00-0000-4000-8000-000000000001')")
ask("models.CharField(max_length=3).to_python(480), models.CharField(max_length=3).to_python(None)")
ask("models.IntegerField().get_prep_value('7'), models.CharField().get_prep_value(480)")
ask("models.DateField().get_prep_value('2026-03-02')")
ask("models.JSONField().get_db_prep_value({'crates': 12}, connection)")
ask("models.UUIDField().get_db_prep_value(models.UUIDField().to_python('c0ffee00-0000-4000-8000-000000000001'), connection)")
ask("models.DecimalField(max_digits=8, decimal_places=2).get_db_prep_value(models.DecimalField(max_digits=8, decimal_places=2).to_python('12.5'), connection)")
ask("models.DateTimeField().get_db_prep_value(datetime.datetime(2026, 4, 10, 9, 0, tzinfo=datetime.UTC), connection)")
ask("models.DecimalField(max_digits=4, decimal_places=2).to_python(1.1), models.DecimalField(max_digits=4, decimal_places=2).to_python('1.1')")
ask("models.FloatField().to_python('1.1'), models.TextField().to_python(1.1)")
show("Asked of the field classes: the automatic keys, to_python, and the values prepared for a query on SQLite")

from django.db.models.fields.related import resolve_relation  # noqa: E402

ASKING.update(
    home=Ship._meta.get_field("home"), captain=Ship._meta.get_field("captain"), ship=Voyage._meta.get_field("ship"),
    calls=Voyage._meta.get_field("calls"), pilots_into=Sailor._meta.get_field("pilots_into"), resolve_relation=resolve_relation,
)


def hops(paths) -> Said:
    """A list of PathInfo, each as: from which model to which, its join_field (a field, or a
    rel written by its field), and its flags direct and m2m."""
    def joined_by(field) -> str:
        return of_field(field) if isinstance(field, models.Field) else f"the rel of {of_field(field.field)}"

    return Said("[" + "; ".join(
        f"{p.from_opts.object_name} to {p.to_opts.object_name}, join_field {joined_by(p.join_field)}, direct={p.direct}, m2m={p.m2m}"
        for p in paths) + "]")


ASKING["hops"] = hops

ask("home is Ship._meta.get_field('home'), captain is Ship._meta.get_field('captain'), ship is Voyage._meta.get_field('ship')")
ask("home.remote_field")
ask("type(home.remote_field).__name__, home.remote_field.field is home")
ask("home.remote_field.model, home.related_model, home.remote_field.related_model")
ask("home.many_to_one, home.remote_field.one_to_many, home.remote_field.multiple")
ask("home.remote_field.related_name, home.remote_field.get_accessor_name(), home.related_query_name()")
ask("ship.remote_field.related_name, ship.remote_field.get_accessor_name(), ship.related_query_name()")
ask("home.name, home.attname, home.column, home.target_field")
ask("home.remote_field.on_delete.__name__, captain.remote_field.on_delete.__name__, home.db_constraint")
ask("Port._meta.get_field('ships') is home.remote_field, home.remote_field.name, home.remote_field.hidden")
ask("type(captain.remote_field).__name__, captain.unique, captain.one_to_one, captain.remote_field.multiple")
ask("captain.remote_field.get_accessor_name(), Sailor._meta.get_field('command') is captain.remote_field")
ask("calls is Voyage._meta.get_field('calls'), pilots_into is Sailor._meta.get_field('pilots_into')")
ask("type(calls.remote_field).__name__, calls.remote_field.through, calls.remote_field.through._meta.auto_created")
ask("calls.column, calls.concrete, calls.many_to_many")
ask("calls.m2m_db_table(), calls.m2m_column_name(), calls.m2m_reverse_name()")
ask("[(f.name, f.remote_field.related_name, f.remote_field.hidden) for f in calls.remote_field.through._meta.fields if f.is_relation]")
ask("calls.remote_field.through._meta.unique_together")
ask("pilots_into.remote_field.through, pilots_into.remote_field.through._meta.auto_created, pilots_into.remote_field.get_accessor_name()")
ask("hops(home.path_infos)")
ask("hops(home.reverse_path_infos)")
ask("hops(calls.path_infos)")
ask("hops(Officer._meta.get_path_to_parent(Sailor))")
ask("resolve_relation(Ship, 'self'), resolve_relation(Ship, 'Voyage'), resolve_relation(Ship, 'crew.Sailor'), resolve_relation(Ship, Port)")
show("Asked of the relations: a field, its rel, and the names each side goes by")

from django.db.models.manager import BaseManager  # noqa: E402

ASKING.update(BaseManager=BaseManager)

ask("[c.__name__ for c in models.Manager.__mro__]")
ask("models.Manager.__mro__[1]._queryset_class")
ask("'filter' in vars(models.Manager.__mro__[1]), 'filter' in vars(BaseManager), 'filter' in vars(models.Manager)")
ask("models.Manager.filter.__qualname__")
ask("hasattr(models.Manager, 'delete'), hasattr(models.Manager, 'as_manager'), hasattr(models.Manager, '_insert'), hasattr(models.Manager, '_clone')")
ask("models.QuerySet.delete.queryset_only, models.QuerySet._insert.queryset_only, models.QuerySet.as_manager.queryset_only")
ask("[c.__name__ for c in type(Sailor.objects).__mro__]")
ask("hasattr(Sailor.objects, 'aboard'), hasattr(Ship.objects, 'aboard')")
ask("type(vars(Sailor)['objects']).__name__, Sailor.objects is Sailor.objects")
ask("Sailor._meta.local_managers[0] is Sailor.objects, Sailor._meta.local_managers[0] == Sailor.objects")
ask("names(Sailor._meta.managers), names(Officer._meta.local_managers), names(Officer._meta.managers)")
ask("Officer.objects.model, Officer.objects is Sailor.objects, type(Officer.objects) is type(Sailor.objects)")
ask("type(Sailor._default_manager).__name__, type(Sailor._base_manager).__name__, Sailor._base_manager.name")
ask("type(Veteran._default_manager).__name__, type(Veteran._base_manager).__name__")
ask("Ship.objects.auto_created, Sailor.objects.auto_created, Ship.objects.name, Ship.objects.model")
ask("Ship(name='Heron').objects")
ask("Named.objects")
ask("str(Ship.objects)")
ask("Sailor.objects.deconstruct()[:3]")
show("Asked of the managers")


# ---------------------------------------------------------------------------------------------
# The database, and the rows the recording begins with.

NOW = datetime.datetime(2026, 4, 10, 9, 0, tzinfo=datetime.UTC)
timezone.now = lambda: NOW  # the recording's clock: see the docstring


def tidy() -> None:
    connection.close()
    shutil.rmtree(SCRATCH, ignore_errors=True)


atexit.register(tidy)


def query(execute, sql, params, many, context):
    if LABELLING:
        sys.stderr.write(f"recordings/models.py: putting a call into words sent a statement to the database: {sql}\n")
        os._exit(1)
    if LISTENING:
        note(f"SQL {sql} with params {params!r}" if params else f"SQL {sql}")
    return execute(sql, params, many, context)


connection.execute_wrappers.append(query)

with recorded(TRANSACTION):
    note("a schema editor is entered")
    with connection.schema_editor() as editor:
        for model in apps.get_models():
            if model._meta.proxy:  # Veteran: it has no table of its own
                continue
            with step(f"editor.create_model({model.__name__})"):
                editor.create_model(model)
        note("the editor is left")
show("The tables: the schema editor is given each model the registry holds that is not a proxy, in the registry's order")

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
# The rows of its calls are made on the table between, and not with spring.calls.add: reading
# spring.calls here would make the related manager's class, which a later block is to show being made.
Voyage.calls.through.objects.create(voyage=spring, port=leith)
Voyage.calls.through.objects.create(voyage=spring, port=lisbon)
Licence.objects.create(sailor=ada, port=bergen, granted=datetime.date(2019, 5, 1))
Berth.objects.create(port=bergen, number=1, metres=90)
Berth.objects.create(port=bergen, number=2, metres=140)

ASKING.update(bergen=bergen, leith=leith, lisbon=lisbon, petrel=petrel, gannet=gannet, ada=ada, bram=bram, cora=cora, dag=dag, spring=spring)

# ---------------------------------------------------------------------------------------------
# How values, instances and calls are said in the blocks that follow.

import contextlib  # noqa: E402
import pickle  # noqa: E402

from django.core.exceptions import ValidationError  # noqa: E402
from django.core.files.base import ContentFile  # noqa: E402
from django.db.models import F, QuerySet, signals  # noqa: E402
from django.db.models.expressions import DatabaseDefault  # noqa: E402
from django.db.models.fetch_modes import FetchMode  # noqa: E402
from django.db.models.fields.reverse_related import ForeignObjectRel  # noqa: E402

LOCALS = ("create_reverse_many_to_one_manager.<locals>.", "create_forward_many_to_many_manager.<locals>.")


def q(frame) -> str:
    """A function's qualified name, without the name of the function a related manager's class is made in."""
    name = frame.f_code.co_qualname
    for prefix in LOCALS:
        name = name.removeprefix(prefix)
    return name


def queryset_said(queryset) -> str:
    """A queryset by its class and its model, without sending its query: asking for its repr would."""
    fetched = queryset._result_cache
    return f"{a(type(queryset).__name__)} of {queryset.model.__name__}, " + ("not yet fetched" if fetched is None else f"fetched, {len(fetched)} rows")


def instance_said(instance) -> str:
    """An instance as its repr, where writing that reads nothing from the database. Ship's and
    Sailor's __str__ read the name: an instance with a deferred field is written by its class
    and its key instead, so that no line of the recording is a query this script caused."""
    if hasattr(type(instance), "name") and "name" not in vars(instance):
        return f"<{type(instance).__name__}: pk={instance.pk!r}>"
    return repr(instance)


def brief(value) -> str:
    """A value in few words."""
    if isinstance(value, models.Model):
        return instance_said(value)
    if isinstance(value, QuerySet):
        return queryset_said(value)
    if isinstance(value, models.Field):
        return of_field(value)
    if isinstance(value, ForeignObjectRel):
        return f"the rel of {of_field(value.field)}"
    if isinstance(value, DatabaseDefault):
        return "a DatabaseDefault"
    if isinstance(value, FetchMode):
        return value.__reduce__()
    if isinstance(value, ContentFile):
        return f"a ContentFile named {value.name!r}"
    if isinstance(value, (datetime.date, datetime.timedelta)):  # as its repr, said shortly: datetime(2026, 4, 10, 9, 0, tzinfo=UTC)
        return repr(value).replace("datetime.timezone.utc", "UTC").replace("datetime.", "")
    if inspect.isclass(value):
        return value.__name__
    if isinstance(value, list):
        return "[" + ", ".join(brief(v) for v in value) + "]"
    if isinstance(value, tuple):
        return "(" + ", ".join(brief(v) for v in value) + ("," if len(value) == 1 else "") + ")"
    if isinstance(value, (set, frozenset)):
        return "{" + ", ".join(sorted(brief(v) for v in value)) + "}" if value else "set()"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k!r}: {brief(v)}" for k, v in value.items()) + "}"
    return repr(value)


def field_names(fields) -> str:
    return "[" + ", ".join(f.name for f in fields) + "]"


def whose(obj) -> str:
    """What an object that is not written out belongs to: a field by its class and name; a
    rel (the ForeignObjectRel a relation field carries as remote_field) by that field, and so
    a descriptor made for the rel on the class the relation points at; a constraint by its
    name; an instance by its class. The descriptor a many-to-many field sets on its own class
    holds the rel too, with reverse=False, and is written by the field."""
    if isinstance(obj, models.Model):
        return a(type(obj).__name__)
    if isinstance(obj, models.Field):
        return of_field(obj)
    if isinstance(obj, ForeignObjectRel):
        return f"the rel of {of_field(obj.field)}"
    if getattr(obj, "reverse", None) is False and isinstance(getattr(obj, "rel", None), ForeignObjectRel):
        return of_field(obj.rel.field)
    for attribute in ("related", "rel"):
        rel = getattr(obj, attribute, None)
        if isinstance(rel, ForeignObjectRel):
            return f"the rel of {of_field(rel.field)}"
    if isinstance(getattr(obj, "instance", None), models.Model):  # a related manager
        return f"of {instance_said(obj.instance)}"
    if isinstance(getattr(obj, "field", None), models.Field):
        return of_field(obj.field)
    if isinstance(obj, (models.BaseConstraint, models.Index)):
        return obj.name
    return a(type(obj).__name__)


def differs(value, default) -> bool:
    return value is not default if default is None or isinstance(default, bool) else value != default


def call(*positional, **defaults):
    """A label: the function's name, the arguments named here as they would be written (a
    name that begins `=` with its name before it), and of the others any that does not have
    the default given here."""
    def said(frame) -> str:
        given = [f"{n[1:]}={brief(frame.f_locals[n[1:]])}" if n.startswith("=") else brief(frame.f_locals[n]) for n in positional]
        given += [f"{n}={brief(frame.f_locals[n])}" for n, default in defaults.items() if differs(frame.f_locals[n], default)]
        return f"{q(frame)}({', '.join(given)})"
    return said


def method(*positional, **defaults):
    """The same for a method, with what the object is, or belongs to, in parentheses."""
    inner = call(*positional, **defaults)

    def said(frame) -> str:
        return f"{inner(frame)}  ({whose(frame.f_locals['self'])})"
    return said


def value_after(frame, value) -> str:
    return brief(value)


@contextlib.contextmanager
def heard(*wanted):
    """Connect, for the block, a receiver to each (signal, its name, a sender, what to say of
    what it was sent). The receiver writes one line."""
    connected = []
    for signal, name, sender, say in wanted:
        def receiver(sender, name=name, say=say, **sent):
            said = say(sent)
            note(f"signal {name}, sender {sender.__name__}" + (f", {said}" if said else ""))
        signal.connect(receiver, sender=sender, weak=False)
        connected.append((signal, receiver, sender))
    try:
        yield
    finally:
        for signal, receiver, sender in connected:
            signal.disconnect(receiver, sender=sender)


# ---------------------------------------------------------------------------------------------
# An instance: made from keyword arguments, made from a row, and with a field left out.

def init_called(frame) -> str:
    said = [brief(v) for v in frame.f_locals["args"]] + [f"{k}={brief(v)}" for k, v in frame.f_locals["kwargs"].items()]
    return f"Model.__init__({', '.join(said)})  (a new {type(frame.f_locals['self']).__name__})"


def from_db_called(frame) -> str:
    given = frame.f_locals
    mode = "" if given["fetch_mode"] is None else f", fetch_mode={brief(given['fetch_mode'])}"
    return f"Model.from_db({given['db']!r}, {given['field_names']!r}, {brief(tuple(given['values']))}{mode})  ({given['cls'].__name__})"


def deferred_read(frame):
    """DeferredAttribute.__get__ is written down only where it is called for an instance that
    has no value under the field's attname: a ForeignKeyDeferredAttribute, having a __set__,
    is called for every read of its attribute."""
    instance = frame.f_locals["instance"]
    field = frame.f_locals["self"].field
    if instance is None or field.attname in instance.__dict__:
        return None
    return f"DeferredAttribute.__get__({a(type(instance).__name__)})  ({of_field(field)})"


def descriptor_get(frame):
    """A descriptor read on an instance: a read on the class, which gives the descriptor itself, is not written down."""
    instance = frame.f_locals["instance"]
    if instance is None:
        return None
    return f"{q(frame)}({brief(instance)})  ({whose_and_class(frame)})"


def whose_and_class(frame) -> str:
    """What a descriptor belongs to, and its class where that is not the class that declares the method."""
    obj = frame.f_locals["self"]
    declaring, actual = frame.f_code.co_qualname.split(".")[0], type(obj).__name__
    return whose(obj) if actual == declaring else f"{whose(obj)}, {a(actual)}"


def descriptor_set(frame) -> str:
    return f"{q(frame)}({brief(frame.f_locals['instance'])}, {brief(frame.f_locals['value'])})  ({whose_and_class(frame)})"


def default_called(frame):
    return f"{q(frame)}()  ({whose(frame.f_locals['self'])})"


def fetch_called(frame) -> str:
    fetcher = frame.f_locals["fetcher"]
    return f"{q(frame)}({a(type(fetcher).__name__)} for {whose(fetcher)}, {brief(frame.f_locals['instance'])})"


FETCHING = {
    ("django.db.models.fetch_modes", "FetchOne.fetch"): fetch_called,
    ("django.db.models.fetch_modes", "FetchPeers.fetch"): fetch_called,
    ("django.db.models.fetch_modes", "FetchRaise.fetch"): fetch_called,
}

INSTANCE = {
    **FETCHING,
    ("django.db.models.base", "Model.__init__"): init_called,
    ("django.db.models.base", "Model.from_db"): from_db_called,
    ("django.db.models.base", "Model.refresh_from_db"): method(using=None, fields=None, from_queryset=None),
    ("django.db.models.query_utils", "DeferredAttribute.__get__"): deferred_read,
    ("django.db.models.query_utils", "DeferredAttribute._check_parent_chain"): lambda f: "DeferredAttribute._check_parent_chain",
    ("django.db.models.query_utils", "DeferredAttribute.fetch_one"): lambda f: f"DeferredAttribute.fetch_one({a(type(f.f_locals['instance']).__name__)})",
    ("django.db.models.fields.related_descriptors", "ForwardManyToOneDescriptor.__set__"): descriptor_set,
    ("django.db.models.fields.related_descriptors", "ForeignKeyDeferredAttribute.__set__"): descriptor_set,
    "named": {"get_default": default_called},
    "named_after": {"get_default": value_after},
    "named_in": "django.db.models.fields",
}
AFTER.update({
    ("django.db.models.query_utils", "DeferredAttribute.__get__"): value_after,
    ("django.db.models.query_utils", "DeferredAttribute._check_parent_chain"): value_after,
})

INIT_SIGNALS = (
    (signals.pre_init, "pre_init", Ship, lambda sent: f"args={brief(sent['args'])}, kwargs with the keys {sorted(sent['kwargs'])}"),
    (signals.post_init, "post_init", Ship, lambda sent: ""),
)

with heard(*INIT_SIGNALS), recorded(INSTANCE):
    heron = Ship(name="Heron", tonnage=300, home=bergen)
show("Ship(name='Heron', tonnage=300, home=bergen): an instance is made from keyword arguments")


def instance_holds(instance, title: str) -> None:
    for name, value in vars(instance).items():
        note(f"{name}: {'a ModelState' if name == '_state' else brief(value)}")
    state = instance._state
    note(f"and its _state: adding={state.adding}, db={state.db!r}, fields_cache={brief(dict(vars(state).get('fields_cache', {})))}")
    show(title)


instance_holds(heron, "What the new Ship holds in its __dict__")

with heard(*INIT_SIGNALS), recorded(INSTANCE):
    loaded = Ship.objects.get(name="Petrel")
show("Ship.objects.get(name='Petrel'): a row becomes an instance")

instance_holds(loaded, "What the Ship made from a row holds in its __dict__")

with recorded(INSTANCE):
    slim = Ship.objects.only("name").get(name="Petrel")
show("Ship.objects.only('name').get(name='Petrel'): a row with two of the model's five columns")

instance_holds(slim, "What the Ship made from two columns holds in its __dict__")
ASKING.update(heron=heron, loaded=loaded, slim=slim, pickle=pickle)

ask("sorted(slim.get_deferred_fields())")
with recorded(INSTANCE):
    note("slim.tonnage is read")
    STACK.append(None)
    slim.tonnage
    STACK.pop()
    note("slim.tonnage is read again")
    STACK.append(None)
    slim.tonnage
    STACK.pop()
ask("sorted(slim.get_deferred_fields())")
with recorded(INSTANCE):
    note("slim.refresh_from_db() is called")
    STACK.append(None)
    slim.refresh_from_db()
    STACK.pop()
ask("sorted(slim.get_deferred_fields())")
show("A deferred field is read, and the instance is then refreshed")

ask("heron.pk, heron.id, heron._state.adding, heron._state.db")
ask("Ship(name='Heron', tonnage=300)._state.db")
ask("loaded.pk, loaded._state.adding, loaded._state.db")
ask("loaded == Ship.objects.get(name='Petrel'), loaded is Ship.objects.get(name='Petrel')")
ask("hash(loaded) == hash(loaded.pk)")
ask("heron == Ship(name='Heron', tonnage=300, home=bergen), heron == heron")
ask("hash(heron)")
ask("Veteran.objects.get(name='Ada') == Sailor.objects.get(name='Ada')")
ask("Officer.objects.get(name='Cora') == Sailor.objects.get(name='Cora')")
ask("Officer.objects.get(name='Cora').pk == Sailor.objects.get(name='Cora').pk")
ask("loaded.__reduce__()[0].__name__, loaded.__reduce__()[1]")
ask("sorted(loaded.__reduce__()[2])")
ask("pickle.loads(pickle.dumps(loaded)) == loaded, pickle.loads(pickle.dumps(loaded)).name")
ask("Named(name='Nowhere')")
ask("Ship(1, 'Petrel', 480, 1, None, 6)")
ask("Ship(1, 'Petrel', name='Gull')")
ask("Ship(name='Heron', mast=2)")
ask("loaded.serializable_value('home'), loaded.serializable_value('name')")
show("Asked of instances")

# ---------------------------------------------------------------------------------------------
# What a field does to a value on the way into a row and out of one.

def value_called(frame) -> str:
    prepared = ", prepared=True" if frame.f_locals.get("prepared") else ""
    return f"{q(frame)}({brief(frame.f_locals['value'])}{prepared})  ({whose(frame.f_locals['self'])})"


def pre_save_called(frame) -> str:
    return f"{q(frame)}(add={frame.f_locals['add']})  ({whose(frame.f_locals['self'])})"


def converter_called(frame) -> str:
    return f"{q(frame)}({brief(frame.f_locals['value'])})"


def converters_called(frame) -> str:
    """The backend is asked which converters a selected column needs. The column is written by
    the field it is a column of, with the field its values are of where that is another."""
    expression = frame.f_locals["expression"]
    target, output = getattr(expression, "target", expression.output_field), expression.output_field
    said = f"the column of {of_field(target)}" + ("" if target is output else f", whose values are those of {of_field(output)}")
    return f"DatabaseOperations.get_db_converters({said})"


VALUES = {
    ("django.db.models.base", "Model.save"): method(force_insert=False, force_update=False, update_fields=None),
    ("django.db.models.base", "Model.from_db"): from_db_called,
    ("django.db.models.sql.compiler", "SQLInsertCompiler.pre_save_val"): lambda f: f"SQLInsertCompiler.pre_save_val({of_field(f.f_locals['field'])})",
    ("django.db.models.sql.compiler", "SQLInsertCompiler.prepare_value"):
        lambda f: f"SQLInsertCompiler.prepare_value({of_field(f.f_locals['field'])}, {brief(f.f_locals['value'])})",
    ("django.db.backends.sqlite3.operations", "DatabaseOperations.adapt_datetimefield_value"): converter_called,
    ("django.db.backends.sqlite3.operations", "DatabaseOperations.convert_datetimefield_value"): converter_called,
    ("django.db.backends.sqlite3.operations", "DatabaseOperations.get_db_converters"): converters_called,
    "named": {
        "pre_save": pre_save_called, "get_db_prep_save": value_called, "get_db_prep_value": value_called,
        "get_prep_value": value_called, "to_python": value_called,
    },
    "named_after": {name: value_after for name in ("pre_save", "get_db_prep_save", "get_db_prep_value", "get_prep_value", "to_python")},
    "named_in": "django.db.models.fields",
}
AFTER.update({
    ("django.db.models.sql.compiler", "SQLInsertCompiler.pre_save_val"): value_after,
    ("django.db.models.sql.compiler", "SQLInsertCompiler.prepare_value"): value_after,
    ("django.db.backends.sqlite3.operations", "DatabaseOperations.adapt_datetimefield_value"): value_after,
    ("django.db.backends.sqlite3.operations", "DatabaseOperations.convert_datetimefield_value"): value_after,
    ("django.db.backends.sqlite3.operations", "DatabaseOperations.get_db_converters"): lambda f, v: "[" + ", ".join(c.__name__ for c in v) + "]",
})

with recorded(VALUES):
    Sailor(name="Edda", ship=petrel).save()
show("Sailor(name='Edda', ship=petrel).save(): what each field does to its value on the way into the row")

with recorded(VALUES):
    edda = Sailor.objects.get(name="Edda")
show("Sailor.objects.get(name='Edda'): the value looked for on its way in, and the row's values on their way out")
ASKING.update(edda=edda)

with recorded({**VALUES, ("django.db.models.sql.compiler", "SQLUpdateCompiler.as_sql"): plain}):
    edda.save()
show("edda.save(), for the Sailor just fetched: the same fields on the way into an update")

ask("Sailor._meta.get_field('signed_on').get_db_converters(connection), hasattr(models.DateTimeField, 'from_db_value')")
ask("models.JSONField().get_db_converters(connection)[0].__qualname__, hasattr(models.JSONField, 'from_db_value')")
ask("Sailor._meta.get_field('signed_on').to_python('2026-04-10 09:00:00+00:00')")
ask("Sailor._meta.get_field('signed_on').value_to_string(edda), Sailor._meta.get_field('ship').value_to_string(edda)")
ask("Sailor._meta.get_field('ship').value_from_object(edda), Sailor._meta.get_field('ship').get_attname()")
ask("Sailor._meta.get_field('signed_on').auto_now_add, Sailor._meta.get_field('signed_on').editable, Sailor._meta.get_field('signed_on').blank")
show("Asked of a field about values")

# ---------------------------------------------------------------------------------------------
# A save.

def save_table_called(frame) -> str:
    given = frame.f_locals
    said = [f"cls={given['cls'].__name__}"]
    said += [f"{n}={brief(given[n])}" for n, default in (("raw", False), ("force_insert", False), ("force_update", False), ("update_fields", None))
             if differs(given[n], default)]
    return f"Model._save_table({', '.join(said)})"


def do_update_called(frame) -> str:
    given = frame.f_locals
    said = [f"pk_val={given['pk_val']!r}", f"values for {field_names(v[0] for v in given['values'])}"]
    if given["forced_update"]:
        said.append("forced_update")
    if given["returning_fields"]:
        said.append(f"returning_fields={field_names(given['returning_fields'])}")
    return f"Model._do_update({', '.join(said)})"


def do_insert_called(frame) -> str:
    given = frame.f_locals
    return f"Model._do_insert(fields={field_names(given['fields'])}, returning_fields={field_names(given['returning_fields'])})"


def assigned_called(frame):
    """Model._assign_returned_values is called after every statement of a save. It is written
    down where it was handed fields to assign."""
    given = frame.f_locals
    if not given["returning_fields"]:
        return None
    return f"Model._assign_returned_values({brief(given['returned_values'])}, {field_names(given['returning_fields'])})"


def save_parents_called(frame):
    """Model._save_parents is called in every save that is not raw. It is written down for a
    class that has parents."""
    cls = frame.f_locals["cls"]
    return f"Model._save_parents(cls={cls.__name__})" if cls._meta.parents else None


SAVE = {
    **TRANSACTION,
    ("django.db.models.base", "Model.save"): method(force_insert=False, force_update=False, update_fields=None),
    ("django.db.models.base", "Model.save_base"): call(raw=False, force_insert=False, force_update=False, update_fields=None),
    ("django.db.models.base", "Model._prepare_related_fields_for_save"): plain,
    ("django.db.models.base", "Model._save_parents"): save_parents_called,
    ("django.db.models.base", "Model._save_table"): save_table_called,
    ("django.db.models.base", "Model._do_update"): do_update_called,
    ("django.db.models.base", "Model._do_insert"): do_insert_called,
    ("django.db.models.base", "Model._assign_returned_values"): assigned_called,
    ("django.db.models.fields", "Field.get_pk_value_on_save"): lambda f: f"Field.get_pk_value_on_save()  ({of_field(f.f_locals['self'])})",
}
# The same, with each call of a field's pre_save and the compiler's call that makes the second.
SAVE_WITH_FIELDS = {
    **SAVE,
    ("django.db.models.sql.compiler", "SQLInsertCompiler.pre_save_val"): lambda f: f"SQLInsertCompiler.pre_save_val({of_field(f.f_locals['field'])})",
    "named": {"pre_save": pre_save_called},
    "named_after": {"pre_save": value_after},
    "named_in": "django.db.models.fields",
}
AFTER.update({
    ("django.db.models.base", "Model._save_parents"): lambda f, v: f"inserted: {v}",
    ("django.db.models.base", "Model._save_table"): lambda f, v: f"updated: {v}",
    ("django.db.models.base", "Model._do_update"): value_after,
    ("django.db.models.base", "Model._do_insert"): value_after,
    ("django.db.models.fields", "Field.get_pk_value_on_save"): value_after,
})


def save_signals(model):
    return (
        (signals.pre_save, "pre_save", model, lambda sent: f"raw={sent['raw']}, update_fields={brief(sent['update_fields'])}"),
        (signals.post_save, "post_save", model, lambda sent: f"created={sent['created']}, update_fields={brief(sent['update_fields'])}"),
    )


with heard(*save_signals(Ship)), recorded(SAVE):
    heron.save()
show("heron.save(): a new Ship, whose primary key is not set")

with recorded(SAVE_WITH_FIELDS):
    Port(name="Oban", country="Scotland").save()
show("Port(name='Oban', country='Scotland').save(): the same kind of save, with each call of a field's pre_save")

ask("heron.pk, heron._state.adding, heron._state.db")
show("Asked of the Ship once saved")

with heard(*save_signals(Ship)), recorded(SAVE):
    heron.tonnage = 320
    heron.save()
show("heron.save() again, with its tonnage changed")

with heard(*save_signals(Ship)), recorded(SAVE):
    Ship(id=40, name="Skua", tonnage=90, home=leith).save()
show("Ship(id=40, name='Skua', tonnage=90, home=leith).save(): a primary key set by hand, and no such row")

with recorded(SAVE_WITH_FIELDS):
    first = Manifest(voyage=spring, crates=12, kilos_each=40)
    note(f"a Manifest is made: its serial is {first.serial!r}, its stamped is {brief(first.stamped)}, and it has {'a' if 'kilos' in vars(first) else 'no'} value under kilos")
    first.save()
show("Manifest(voyage=spring, crates=12, kilos_each=40).save(): a primary key with a default, a default of the database's, a generated column")
ASKING.update(first=first)

ask("first.serial, first.kilos, first.stamped")
ask("Manifest._meta.pk.has_default(), Ship._meta.pk.has_default()")
show("Asked of the Manifest once saved")

with recorded(SAVE):
    first.crates = 20
    first.save()
ask("first.crates, first.kilos")
show("first.crates = 20, and first.save(): a generated column that depends on what was written")

with heard(*save_signals(Ship)), recorded(SAVE):
    heron.tonnage = 330
    heron.name = "Heron II"
    heron.save(update_fields=["tonnage"])
show("heron.save(update_fields=['tonnage']), with its tonnage and its name changed")

ask("Ship.objects.get(pk=heron.pk).name, Ship.objects.get(pk=heron.pk).tonnage")
show("Asked of the row afterwards")

with recorded(SAVE):
    try:
        Ship(id=99, name="Auk", tonnage=70, home=leith).save(update_fields=["tonnage"])
    except Ship.NotUpdated as raised:
        note(f"the caller catches Ship.NotUpdated: {raised}")
show("Ship(id=99, name='Auk', tonnage=70, home=leith).save(update_fields=['tonnage']): no such row")

with recorded(SAVE):
    slim = Ship.objects.only("name").get(name="Skua")
    slim.name = "Skua II"
    slim.save()
show("A Ship fetched with only('name') is renamed and saved")

with recorded(SAVE):
    try:
        Ship(id=40, name="Skua", tonnage=90, home=leith).save(force_insert=True)
    except Exception as raised:
        note(f"the caller catches {type(raised).__name__}: {raised}")
show("Ship(id=40, name='Skua', tonnage=90, home=leith).save(force_insert=True): the row is there")

with recorded(SAVE_WITH_FIELDS):
    heron.tonnage = F("tonnage") + 20
    heron.save()
show("heron.tonnage = F('tonnage') + 20, and heron.save(): the value is an expression")

ask("heron.tonnage")
show("Asked of the Ship after the expression was saved")

with heard(*save_signals(Officer), *save_signals(Sailor)), recorded(SAVE):
    finn = Officer(name="Finn", ship=gannet, rank=Rank.MATE)
    finn.save()
show("Officer(name='Finn', ship=gannet, rank=Rank.MATE).save(): a model with a parent, two tables")
ASKING.update(finn=finn)

with recorded(SAVE):
    finn.rank = Rank.ENGINEER
    finn.save()
show("finn.save() again, with the rank changed")

with recorded(SAVE):
    try:
        Sailor(name="Gus", ship=Ship(name="Tern", tonnage=50, home=leith)).save()
    except ValueError as raised:
        note(f"the caller catches ValueError: {raised}")
show("Sailor(name='Gus', ship=Ship(name='Tern', tonnage=50, home=leith)).save(): the ship has not been saved")

with recorded(SAVE):
    berth = Berth.objects.get(pk=(bergen.pk, 2))
    berth.metres = 150
    berth.save()
show("A Berth, whose primary key is two columns, is fetched by pk=(1, 2), changed and saved")
ASKING.update(berth=berth)

ask("berth.pk, Berth._meta.pk.attname, berth._is_pk_set()")
ask("Berth(port=leith, number=None, metres=60).pk, Berth(port=leith, number=None, metres=60)._is_pk_set()")
show("Asked of a Berth")

# After every other save of a Ship, so that the key this one takes shifts no other block's.
with recorded(VALUES):
    wren = Ship(name="Wren", tonnage="300", home=leith)
    wren.save()
ASKING.update(wren=wren)
ask("wren.tonnage, Ship.objects.get(name='Wren').tonnage")
ask("Ship.objects.filter(tonnage='many')")
show("Ship(name='Wren', tonnage='300', home=leith).save(): a string where the field wants a number")

# ---------------------------------------------------------------------------------------------
# Related objects: the descriptors a relation puts on both classes, and the managers they give.

def cache_called(frame) -> str:
    """A read or a write of an instance's cache of related objects. A read given a default,
    which is then what it returns for a relation that is not cached, is written with it."""
    given = frame.f_locals
    said = brief(given["instance"]) + (f", {brief(given['value'])}" if "value" in given else "")
    if "default" in given and given["default"] is not CACHE_NOT_PROVIDED:
        said += f", default={given['default']!r}"
    return f"{q(frame)}({said})  ({whose(given['self'])})"


def manager_called(frame) -> str:
    """A method of a related manager: the objects it was given, and any other argument that is not the default."""
    given, said = frame.f_locals, []
    if "self" not in given:  # a function of the same name that is no method of a manager
        return None
    if "objs" in given:
        said += [brief(o) for o in given["objs"]] if isinstance(given["objs"], tuple) else [brief(given["objs"])]
    for name, default in (("bulk", True), ("clear", False), ("through_defaults", None)):
        if name in given and differs(given[name], default):
            said.append(f"{name}={brief(given[name])}")
    said += [f"{k}={brief(v)}" for k, v in given.get("kwargs", {}).items()]
    return f"{q(frame)}({', '.join(said)})  ({whose(given['self'])})"


def items_called(frame) -> str:
    given = frame.f_locals
    said = [repr(given["source_field_name"]), repr(given["target_field_name"]), *(brief(o) for o in given["objs"])]
    if given.get("through_defaults"):
        said.append(f"through_defaults={brief(given['through_defaults'])}")
    return f"{q(frame)}({', '.join(said)})"


def manager_class_said(frame, value) -> str:
    return f"the class {value.__name__}, whose bases are ({', '.join(b.__name__ for b in value.__bases__)})"


RELATED = {
    **FETCHING,
    **TRANSACTION,
    ("django.db.models.fields.related_descriptors", "ForwardManyToOneDescriptor.__get__"): descriptor_get,
    ("django.db.models.fields.related_descriptors", "ForwardManyToOneDescriptor.__set__"): descriptor_set,
    ("django.db.models.fields.related_descriptors", "ForwardOneToOneDescriptor.__set__"): descriptor_set,
    ("django.db.models.fields.related_descriptors", "ForwardManyToOneDescriptor.get_object"): method("instance"),
    ("django.db.models.fields.related_descriptors", "ForwardOneToOneDescriptor.get_object"): method("instance"),
    ("django.db.models.fields.related_descriptors", "ForwardManyToOneDescriptor.fetch_one"): method("instance"),
    ("django.db.models.fields.related_descriptors", "ForwardManyToOneDescriptor.fetch_many"): method("instances"),
    ("django.db.models.fields.related_descriptors", "ReverseOneToOneDescriptor.__get__"): descriptor_get,
    ("django.db.models.fields.related_descriptors", "ReverseOneToOneDescriptor.__set__"): descriptor_set,
    ("django.db.models.fields.related_descriptors", "ReverseOneToOneDescriptor.fetch_one"): method("instance"),
    ("django.db.models.fields.related_descriptors", "ReverseManyToOneDescriptor.__get__"): descriptor_get,
    ("django.db.models.fields.related_descriptors", "ReverseManyToOneDescriptor.related_manager_cls"): lambda f: f"{q(f)}  ({whose_and_class(f)})",
    ("django.db.models.fields.related_descriptors", "ManyToManyDescriptor.related_manager_cls"): lambda f: f"{q(f)}  ({whose_and_class(f)})",
    ("django.db.models.fields.related_descriptors", "create_reverse_many_to_one_manager"): call("superclass", "rel"),
    ("django.db.models.fields.related_descriptors", "create_forward_many_to_many_manager"): call("superclass", "rel", "=reverse"),
    ("django.db.models.fields.mixins", "FieldCacheMixin.get_cached_value"): cache_called,
    ("django.db.models.fields.mixins", "FieldCacheMixin.set_cached_value"): cache_called,
    ("django.db.models.fields.mixins", "FieldCacheMixin.delete_cached_value"): cache_called,
    ("django.db.models.query", "prefetch_related_objects"):
        lambda f: f"prefetch_related_objects({brief(list(f.f_locals['model_instances']))}, {', '.join(repr(l) for l in f.f_locals['related_lookups'])})",
    "named": {
        "add": manager_called, "remove": manager_called, "clear": manager_called, "set": manager_called, "create": manager_called,
        "_add_base": manager_called, "_remove_base": manager_called, "_clear_base": manager_called, "set_base": manager_called,
        "_add_items": items_called, "_remove_items": items_called,
        "_get_target_ids": lambda f: q(f), "_get_missing_target_ids": lambda f: q(f), "_get_add_plan": lambda f: q(f),
    },
    "named_after": {
        "_get_target_ids": value_after, "_get_missing_target_ids": value_after,
        "_get_add_plan": lambda f, v: f"can_ignore_conflicts={v[0]}, must_send_signals={v[1]}, can_fast_add={v[2]}",
        "create": value_after,
    },
    "named_in": "django.db.models.fields.related_descriptors",
}
AFTER.update({
    ("django.db.models.fields.related_descriptors", "ForwardManyToOneDescriptor.__get__"): value_after,
    ("django.db.models.fields.related_descriptors", "ForwardManyToOneDescriptor.get_object"): value_after,
    ("django.db.models.fields.related_descriptors", "ForwardOneToOneDescriptor.get_object"): value_after,
    ("django.db.models.fields.related_descriptors", "ReverseOneToOneDescriptor.__get__"): value_after,
    ("django.db.models.fields.related_descriptors", "ReverseManyToOneDescriptor.__get__"): lambda f, v: a(type(v).__name__),
    ("django.db.models.fields.related_descriptors", "ReverseManyToOneDescriptor.related_manager_cls"): manager_class_said,
    ("django.db.models.fields.related_descriptors", "ManyToManyDescriptor.related_manager_cls"): manager_class_said,
    ("django.db.models.fields.mixins", "FieldCacheMixin.get_cached_value"): value_after,
})


from django.db.models.fields.mixins import NOT_PROVIDED as CACHE_NOT_PROVIDED  # noqa: E402

bram = Sailor.objects.get(name="Bram")
ASKING.update(bram=bram)

with recorded(RELATED):
    with step("bram.ship is read"):
        bram.ship
    with step("bram.ship is read again"):
        bram.ship
show("A sailor's ship is read twice")

# The same, with each value set under a foreign key's attname: the descriptor that sets it is
# called for every row that becomes an instance, so the other blocks leave it out.
ASSIGNING = {
    **RELATED,
    ("django.db.models.fields.related_descriptors", "ForeignKeyDeferredAttribute.__set__"): descriptor_set,
}

bram = Sailor.objects.get(name="Bram")  # fetched again: an instance with no ship cached
ASKING.update(bram=bram)

with recorded(ASSIGNING):
    with step("bram.ship = gannet"):
        bram.ship = gannet
    ask("bram.ship_id, bram.ship is gannet")
    with step("bram.ship_id = petrel.pk"):
        bram.ship_id = petrel.pk
    with step("bram.ship is read"):
        bram.ship
    with step("bram.ship = None"):
        try:
            bram.ship = None
        except Exception as raised:
            note(f"the caller catches {type(raised).__name__}")
    ask("bram.ship_id")
    with step("bram.ship is read"):
        try:
            bram.ship
        except Exception as raised:
            note(f"the caller catches {type(raised).__qualname__}: {raised}")
    with step("bram.ship = bergen"):
        try:
            bram.ship = bergen
        except ValueError as raised:
            note(f"the caller catches ValueError: {raised}")
show("A sailor is given a ship: by the object, by its id, and wrongly")
bram = Sailor.objects.get(name="Bram")
ASKING.update(bram=bram)

with recorded(RELATED):
    with step("crew = list(Sailor.objects.fetch_mode(models.FETCH_PEERS).order_by('id')[:4])"):
        crew = list(Sailor.objects.fetch_mode(models.FETCH_PEERS).order_by("id")[:4])
    with step("crew[0].ship is read"):
        crew[0].ship
    with step("crew[3].ship is read"):
        crew[3].ship
show("Four sailors fetched together under FETCH_PEERS, and the ship of the first is read")
ASKING.update(crew=crew)

ask("[type(s._state.fetch_mode).__name__ for s in crew], len(crew[0]._state.peers), bram._state.peers")
ask("crew[0].ship is crew[1].ship, crew[0].ship == crew[1].ship, crew[2].ship is crew[3].ship")
show("Asked of the four")

with recorded(RELATED):
    with step("strict = Sailor.objects.fetch_mode(models.FETCH_RAISE).get(name='Bram')"):
        strict = Sailor.objects.fetch_mode(models.FETCH_RAISE).get(name="Bram")
    with step("strict.ship is read"):
        try:
            strict.ship
        except Exception as raised:
            note(f"the caller catches {type(raised).__name__}: {raised}")
show("A sailor fetched under FETCH_RAISE, and its ship is read")

with recorded(RELATED):
    with step("alone = Sailor.objects.fetch_mode(models.FETCH_PEERS).get(name='Bram')"):
        alone = Sailor.objects.fetch_mode(models.FETCH_PEERS).get(name="Bram")
    with step("alone.ship is read"):
        alone.ship
show("A sailor fetched alone under FETCH_PEERS, and its ship is read")

cora = Sailor.objects.get(name="Cora")
ASKING.update(cora=cora)

with recorded(RELATED):
    with step("cora.command is read"):
        cora.command
    with step("cora.command.captain is read"):
        cora.command.captain
    with step("bram.command is read"):
        try:
            bram.command
        except Exception as raised:
            note(f"the caller catches {type(raised).__qualname__}: {raised}")
    with step("bram.command is read again"):
        try:
            bram.command
        except Exception as raised:
            note(f"the caller catches {type(raised).__qualname__}")
show("The other end of a one-to-one relation: a sailor's command")

skua = Ship.objects.get(name="Skua II")
ASKING.update(skua=skua)
with recorded(ASSIGNING):
    ask("cora.command, skua.captain_id")
    with step("cora.command = skua"):
        cora.command = skua
    ask("cora.command, skua.captain_id, skua.captain is cora")
    ask("Ship.objects.get(name='Skua II').captain_id, Ship.objects.get(name='Gannet').captain_id")
show("A sailor is given a command from the far end of the one-to-one relation, and nothing is saved")

ask("cora.command.captain is cora")
ask("Sailor.command.RelatedObjectDoesNotExist.__mro__[1:3]")
ask("issubclass(Sailor.ship.RelatedObjectDoesNotExist, Ship.DoesNotExist), issubclass(Sailor.ship.RelatedObjectDoesNotExist, AttributeError)")
ask("hasattr(bram, 'command'), hasattr(cora, 'command')")
show("Asked of the exception a descriptor raises")

dag = Sailor.objects.get(name="Dag")  # fetched again: an instance with no ship cached
ASKING.update(dag=dag)

with recorded(RELATED):
    with step("petrel.crew is read"):
        petrel.crew
    with step("gannet.crew is read"):
        gannet.crew
    with step("list(petrel.crew.all())"):
        list(petrel.crew.all())
    with step("petrel.crew.add(dag)"):
        petrel.crew.add(dag)
    with step("petrel.crew.create(name='Hal')"):
        petrel.crew.create(name="Hal")
show("The other end of a foreign key: a ship's crew")

ask("petrel.crew is petrel.crew, type(petrel.crew) is type(gannet.crew)")
ask("[c.__name__ for c in type(petrel.crew).__mro__]")
ask("hasattr(petrel.crew, 'aboard'), hasattr(petrel.crew, 'remove'), hasattr(petrel.crew, 'clear')")
ask("dag.ship is petrel, petrel.crew.count()")
ask("petrel.crew.add(Ship(name='Tern'))")
ask("Ship(name='Tern').crew.all()")
ask("[c.__name__ for c in type(bergen.ships).__mro__][:3]")
show("Asked of a ship's crew")

# ---------------------------------------------------------------------------------------------
# Many-to-many.

M2M_SIGNAL = (signals.m2m_changed, "m2m_changed", Voyage.calls.through,
              lambda sent: f"action={sent['action']!r}, reverse={sent['reverse']}, model={sent['model'].__name__}, pk_set={brief(sent['pk_set'])}")

autumn = Voyage.objects.create(ship=gannet, sailed=datetime.date(2025, 10, 1))
ASKING.update(autumn=autumn)

with recorded(RELATED):
    with step("spring.calls is read"):
        spring.calls
    with step("list(spring.calls.all())"):
        list(spring.calls.all())
    with step("spring.calls.add(bergen, lisbon)"):
        spring.calls.add(bergen, lisbon)
show("A voyage's ports of call: read, and add called with two ports, one of them there already, with no receiver of m2m_changed")

with heard(M2M_SIGNAL), recorded(RELATED):
    with step("autumn.calls.add(lisbon, leith)"):
        autumn.calls.add(lisbon, leith)
    with step("autumn.calls.add(lisbon, bergen)"):
        autumn.calls.add(lisbon, bergen)
    with step("autumn.calls.remove(leith)"):
        autumn.calls.remove(leith)
    with step("autumn.calls.set([leith, lisbon])"):
        autumn.calls.set([leith, lisbon])
    with step("autumn.calls.clear()"):
        autumn.calls.clear()
show("The same with a receiver of m2m_changed: add, remove, set, clear")

with recorded(RELATED):
    with step("list(lisbon.voyage_set.all())"):
        list(lisbon.voyage_set.all())
    with step("lisbon.voyage_set.add(autumn)"):
        lisbon.voyage_set.add(autumn)
show("From the other class, and with no receiver connected: the voyages that call at a port")

ask("type(Voyage.calls).__name__, Voyage.calls.reverse, type(Port.voyage_set).__name__, Port.voyage_set.reverse")
ask("Voyage.calls.rel is Port.voyage_set.rel, Voyage.calls.through is Port.voyage_set.through")
ask("[c.__name__ for c in type(spring.calls).__mro__][:3]")
ask("spring.calls.source_field_name, spring.calls.target_field_name, lisbon.voyage_set.source_field_name, lisbon.voyage_set.target_field_name")
ask("spring.calls.count(), spring.calls.exists()")
ask("Voyage(ship=petrel, sailed=datetime.date(2026, 5, 1)).calls")
show("Asked of the two ends of a many-to-many relation")

with recorded(RELATED):
    with step("list(ada.pilots_into.all())"):
        list(ada.pilots_into.all())
    with step("ada.pilots_into.add(leith, through_defaults={'granted': datetime.date(2026, 1, 5)})"):
        ada.pilots_into.add(leith, through_defaults={"granted": datetime.date(2026, 1, 5)})
    with step("ada.pilots_into.add(lisbon)"):
        try:
            ada.pilots_into.add(lisbon)
        except Exception as raised:
            note(f"the caller catches {type(raised).__name__}: {raised}")
show("A many-to-many relation through a model of the project's: the ports a sailor may pilot into")

ask("[(l.sailor.name, l.port.name, l.granted) for l in Licence.objects.order_by('id')]")
show("Asked of the table between")

# ---------------------------------------------------------------------------------------------
# Inheritance: a child with a table of its own, and a proxy.

LINEAGE = {
    **RELATED,
    ("django.db.models.base", "Model.from_db"): from_db_called,
    ("django.db.models.base", "Model.__init__"): init_called,
}

with recorded(LINEAGE):
    with step("master = Officer.objects.get(name='Cora')"):
        master = Officer.objects.get(name="Cora")
    with step("master.sailor_ptr is read"):
        master.sailor_ptr
    with step("master.ship is read"):
        master.ship
    with step("plain = Sailor.objects.get(name='Cora')"):
        plain_ = Sailor.objects.get(name="Cora")
    with step("plain.officer is read"):
        plain_.officer
    with step("bram.officer is read"):
        try:
            bram.officer
        except Exception as raised:
            note(f"the caller catches {type(raised).__qualname__}: {raised}")
show("An Officer is fetched, and the parent's row and the child's are reached from each other")
ASKING.update(master=master)

instance_holds(master, "What the Officer holds in its __dict__")

ask("type(master.sailor_ptr).__name__, master.sailor_ptr == master, master.sailor_ptr.pk == master.pk")
ask("master.pk, master.id, master.sailor_ptr_id")
ask("isinstance(master, Sailor), Officer._meta.get_field('ship').model, Officer.ship is Sailor.ship")
ask("names(Officer._meta.all_parents), Officer._meta.get_ancestor_link(Sailor)")
ask("names(Sailor._meta.all_parents), names(Veteran._meta.all_parents)")
ask("[(type(v).__name__, v.name) for v in Veteran.objects.order_by('id')]")
ask("Veteran.objects.get(name='Ada')._meta.concrete_model.__name__")
ask("Veteran._meta.ordering, Officer._meta.ordering, Sailor._meta.ordering")
ivo = Officer(name="Ivo", ship=gannet, rank=Rank.MATE)
ASKING.update(ivo=ivo)
ask("ivo.pk, ivo.id, ivo.sailor_ptr_id")
ask("setattr(ivo, 'pk', 99) or (ivo.pk, ivo.id, ivo.sailor_ptr_id)")
ask("setattr(ivo, 'id', 77) or (ivo.pk, ivo.id, ivo.sailor_ptr_id)")
show("Asked of a child, a parent and a proxy")

# ---------------------------------------------------------------------------------------------
# A manager's methods.

MANAGERS = {
    ("django.db.models.manager", "ManagerDescriptor.__get__"): lambda f: f"ManagerDescriptor.__get__(None, {f.f_locals['cls'].__name__})",
    ("django.db.models.manager", "BaseManager._get_queryset_methods.<locals>.create_method.<locals>.manager_method"):
        lambda f: f"manager_method  (the method the manager's class was given under the name {f.f_locals['name']!r})",
    ("django.db.models.manager", "BaseManager.get_queryset"): lambda f: f"BaseManager.get_queryset  ({a(type(f.f_locals['self']).__name__)})",
    ("django.db.models.manager", "BaseManager.all"): plain,
    ("harbour.crew.models", "SailorQuerySet.aboard"): call("ship"),
    ("harbour.crew.models", "VeteranManager.get_queryset"): plain,
    ("django.db.models.query", "QuerySet.filter"): lambda f: "QuerySet.filter(" + ", ".join(f"{k}={brief(v)}" for k, v in f.f_locals["kwargs"].items()) + ")",
    ("django.db.models.query", "QuerySet.all"): plain,
}
AFTER.update({
    ("django.db.models.manager", "ManagerDescriptor.__get__"): lambda f, v: a(type(v).__name__),
    ("django.db.models.manager", "BaseManager.get_queryset"): value_after,
    ("harbour.crew.models", "SailorQuerySet.aboard"): value_after,
    ("harbour.crew.models", "VeteranManager.get_queryset"): value_after,
})

with recorded(MANAGERS):
    with step("Sailor.objects.aboard(petrel)"):
        Sailor.objects.aboard(petrel)
    with step("Sailor.objects.filter(name='Ada')"):
        Sailor.objects.filter(name="Ada")
    with step("Veteran.objects.all()"):
        Veteran.objects.all()
    with step("Sailor.objects.all().aboard(petrel)"):
        Sailor.objects.all().aboard(petrel)
show("A manager is read from its class and one of its methods is called")

with recorded(SAVE):
    ask("Veteran.objects.filter(name='Bram').exists(), Veteran._base_manager.filter(name='Bram').exists()")
    with step("hidden = Veteran._base_manager.get(name='Bram'), and hidden.save()"):
        hidden = Veteran._base_manager.get(name="Bram")
        hidden.save()
show("A sailor the default manager of Veteran leaves out is found through the base manager, and saved")

# ---------------------------------------------------------------------------------------------
# Validation: full_clean and what it calls.

def unique_checks_said(frame, value) -> str:
    unique, by_date = value
    said = "[" + ", ".join(f"({model.__name__}, {fields!r})" for model, fields in unique) + "]"
    return f"unique checks {said}, date checks {list(by_date)!r}"


def constraint_validate_called(frame) -> str:
    given = frame.f_locals
    return f"{q(frame)}({given['model'].__name__}, {brief(given['instance'])}, exclude={brief(given['exclude'])})  ({given['self'].name})"


VALID = {
    ("django.db.models.base", "Model.full_clean"): method(exclude=None, validate_unique=True, validate_constraints=True),
    ("django.db.models.base", "Model.clean_fields"): call("=exclude"),
    ("django.db.models.base", "Model.clean"): plain,
    ("django.db.models.base", "Model.validate_unique"): call("=exclude"),
    ("django.db.models.base", "Model._get_unique_checks"): call("=exclude", include_meta_constraints=False),
    ("django.db.models.base", "Model._perform_unique_checks"): plain,
    ("django.db.models.base", "Model._perform_date_checks"): plain,
    ("django.db.models.base", "Model.validate_constraints"): call("=exclude"),
    ("django.db.models.constraints", "CheckConstraint.validate"): constraint_validate_called,
    ("django.db.models.constraints", "UniqueConstraint.validate"): constraint_validate_called,
    "named": {"clean": value_called},
    "named_after": {"clean": value_after},
    "named_in": "django.db.models.fields",
}
AFTER.update({
    ("django.db.models.base", "Model._get_unique_checks"): unique_checks_said,
    ("django.db.models.base", "Model._perform_unique_checks"): lambda f, v: "errors for " + brief(sorted(v)) if v else "no errors",
    ("django.db.models.base", "Model._perform_date_checks"): lambda f, v: "errors for " + brief(sorted(v)) if v else "no errors",
})


def cleaned(text: str, instance) -> None:
    """Call full_clean under a line of words, and write down the messages of what it raised."""
    with step(text):
        try:
            instance.full_clean()
        except ValidationError as raised:
            with step("the caller catches ValidationError, whose message_dict holds"):
                for name, messages in raised.message_dict.items():
                    note(f"{name!r}: {messages!r}")


with recorded(VALID):
    cleaned("Ship(name='Tern', tonnage=50, home=leith).full_clean()", Ship(name="Tern", tonnage=50, home=leith))
show("full_clean on a Ship with nothing wrong")

with recorded(VALID):
    cleaned("Ship(name='Petrel', tonnage=0, home=bergen, captain=cora).full_clean()", Ship(name="Petrel", tonnage=0, home=bergen, captain=cora))
show("full_clean on a Ship that breaks a unique field and both constraints")

with recorded(VALID):
    cleaned("Ship(name='', tonnage=-5, home=bergen).full_clean()", Ship(name="", tonnage=-5, home=bergen))
show("full_clean on a Ship with two fields that do not pass their own cleaning")

with recorded(VALID):
    cleaned("heron.full_clean()", heron)
show("full_clean on a Ship that has a row")

ask("Ship(name='Tern', tonnage=50, home=leith).full_clean(validate_unique=False, validate_constraints=False)")
ask("Ship(name='Petrel', tonnage=0, home=bergen).save()")
ask("Ship._meta.get_field('tonnage').clean('7', None), Ship._meta.get_field('name').clean(7, None)")
ask("Ship._meta.get_field('name').clean('', None)")
ask("Ship._meta.get_field('captain').clean(None, None)")
ask("Ship._meta.get_field('home').clean(None, None)")
ask("Ship._meta.get_field('home').clean(99, Ship())")
ask("Officer._meta.get_field('rank').clean('bosun', None)")
ask("Ship(id=1, name='Zed', tonnage=5, home=bergen).full_clean()")
tern = Ship(name="Tern", tonnage="7", home=leith)
ASKING.update(tern=tern)
ask("tern.tonnage")
ask("tern.full_clean()")
ask("tern.tonnage")
show("Asked of validation")

# ---------------------------------------------------------------------------------------------
# Constraints and indexes: what they are and the SQL they give the schema editor.

def ddl(model, what, how: str) -> Said:
    """What a method of a constraint or an index returns when given a schema editor of this
    database: the statement, as text. Whether an editor sends that statement is the editor's
    affair, and the block after this one shows what SQLite's does to add a constraint."""
    global LISTENING
    listening, LISTENING = LISTENING, False
    with connection.schema_editor(collect_sql=True) as editor:
        made = getattr(what, how)(model, editor)
    LISTENING = listening
    return Said(str(made))


ASKING.update(ddl=ddl, Q=models.Q)

ask("Ship._meta.constraints")
ask("Ship._meta.original_attrs['constraints'][0].name, Ship._meta.constraints[0].name")
ask("Ship._meta.original_attrs['constraints'][0] is Ship._meta.constraints[0]")
ask("Ship._meta.constraints[0].deconstruct()")
ask("Ship._meta.constraints[1].deconstruct()")
ask("ddl(Ship, Ship._meta.constraints[0], 'constraint_sql')")
ask("ddl(Ship, Ship._meta.constraints[0], 'create_sql')")
ask("ddl(Ship, Ship._meta.constraints[0], 'remove_sql')")
ask("ddl(Ship, Ship._meta.constraints[1], 'constraint_sql')")
ask("ddl(Ship, Ship._meta.constraints[1], 'create_sql')")
ask("ddl(Ship, models.UniqueConstraint(fields=['name'], condition=Q(tonnage__gt=1000), name='big_names'), 'constraint_sql')")
ask("ddl(Ship, models.UniqueConstraint(fields=['name'], condition=Q(tonnage__gt=1000), name='big_names'), 'create_sql')")
ask("ddl(Ship, models.UniqueConstraint(models.functions.Lower('name'), name='names_whatever_the_case'), 'create_sql')")
ask("Ship._meta.total_unique_constraints")
ask("models.UniqueConstraint(fields=['name'], name='n') == models.UniqueConstraint(fields=['name'], name='n')")
ask("Ship._meta.indexes")
ask("ddl(Ship, Ship._meta.indexes[0], 'create_sql')")
ask("ddl(Ship, Ship._meta.indexes[0], 'remove_sql')")
ask("models.Index(fields=['name', '-tonnage']).fields_orders, models.Index(fields=['name', '-tonnage']).name")
ask("ddl(Ship, models.Index(fields=['name', '-tonnage'], name='by_name_and_size'), 'create_sql')")
ask("ddl(Ship, models.Index(models.functions.Lower('name'), name='lower_names'), 'create_sql')")
ask("Ship._meta.indexes[0].deconstruct()")
ask("Ship._meta.get_field('name').unique, Ship._meta.get_field('captain').unique, Ship._meta.get_field('home').db_index, Ship._meta.get_field('name').db_index")
ask("Ship._meta.constraints[0].validate(Ship, Ship(name='Tern', tonnage=0, home=leith))")
ask("Ship._meta.constraints[0].validate(Ship, Ship(name='Tern', tonnage=0, home=leith), exclude={'tonnage'})")
ask("Ship._meta.constraints[1].validate(Ship, Ship(name='Petrel', tonnage=5, home=bergen))")
ask("Ship._meta.constraints[1].validate(Ship, petrel)")
ask("Ship._meta.constraints[0].validate(Ship, Ship(name='Tern', tonnage=None, home=leith))")
ask("models.UniqueConstraint(fields=['name'], name='one_name').validate(Ship, Ship(name='Petrel', tonnage=5, home=bergen))")
ask("models.UniqueConstraint(fields=['name'], condition=Q(tonnage__gt=100), name='big_names').validate(Ship, Ship(name='Petrel', tonnage=500, home=bergen))")
ask("ddl(Ship, models.UniqueConstraint(fields=['name'], deferrable=models.Deferrable.DEFERRED, name='later'), 'create_sql')")
show("Asked of the constraints and the index of Ship")

with recorded(TRANSACTION):
    note("a schema editor is entered")
    with connection.schema_editor() as editor:
        # SQLite's editor makes the table again from the constraints the model lists, and ignores the
        # one it is handed: a migration hands it a model that lists the new constraint already. So the
        # constraint is put on Ship's own list for the call, and taken off again.
        extra = models.CheckConstraint(condition=models.Q(tonnage__lt=500000), name="ship_not_too_big")
        Ship._meta.constraints.append(extra)
        try:
            with step("editor.add_constraint(Ship, extra), where extra is a CheckConstraint named 'ship_not_too_big' that Ship._meta.constraints lists for this call"):
                editor.add_constraint(Ship, extra)
        finally:
            Ship._meta.constraints.remove(extra)
        note("the editor is left")
show("A schema editor is asked to add a check constraint to the table of Ship: what SQLite's sends")

# ---------------------------------------------------------------------------------------------
# A file.

def file_read(frame):
    instance = frame.f_locals["instance"]
    return None if instance is None else f"FileDescriptor.__get__({brief(instance)})  ({whose(frame.f_locals['self'])})"


def file_said(frame, value) -> str:
    return f"{a(type(value).__name__)} named {value.name!r}"


def stored(name) -> str:
    """A file's name within its storage, with the separator it is stored with. Between
    generate_filename and get_available_name the name has the machine's own separator, a
    backslash on Windows: the recording writes a forward slash there too, so that it is the
    same on every machine."""
    return repr(str(name).replace("\\", "/"))


FILES = {
    ("django.db.models.base", "Model.save"): SAVE[("django.db.models.base", "Model.save")],
    ("django.db.models.base", "Model._save_table"): save_table_called,
    ("django.db.models.fields.files", "FileDescriptor.__get__"): file_read,
    ("django.db.models.fields.files", "FileDescriptor.__set__"): descriptor_set,
    ("django.db.models.fields.files", "FieldFile.save"):
        lambda f: f"FieldFile.save({f.f_locals['name']!r}, {brief(f.f_locals['content'])}, save={f.f_locals['save']})",
    ("django.db.models.fields.files", "FieldFile.delete"): lambda f: f"FieldFile.delete(save={f.f_locals['save']})",
    ("django.db.models.fields.files", "FileField.pre_save"): pre_save_called,
    ("django.db.models.fields.files", "FileField.generate_filename"): lambda f: f"FileField.generate_filename(instance, {f.f_locals['filename']!r})",
    ("django.db.models.fields.files", "FileField.get_prep_value"): value_called,
    ("django.core.files.storage.base", "Storage.save"):
        lambda f: f"Storage.save({stored(f.f_locals['name'])}, content)  ({a(type(f.f_locals['self']).__name__)})",
    ("django.core.files.storage.base", "Storage.get_available_name"): lambda f: f"Storage.get_available_name({stored(f.f_locals['name'])})",
    ("django.core.files.storage.filesystem", "FileSystemStorage._save"): lambda f: f"FileSystemStorage._save({stored(f.f_locals['name'])}, content)",
    ("django.core.files.storage.filesystem", "FileSystemStorage.delete"): lambda f: f"FileSystemStorage.delete({stored(f.f_locals['name'])})",
}
AFTER.update({
    ("django.db.models.fields.files", "FileDescriptor.__get__"): file_said,
    ("django.db.models.fields.files", "FileField.pre_save"): file_said,
    ("django.db.models.fields.files", "FileField.generate_filename"): lambda f, v: stored(v),
    ("django.db.models.fields.files", "FileField.get_prep_value"): value_after,
    ("django.core.files.storage.base", "Storage.save"): lambda f, v: stored(v),
    ("django.core.files.storage.base", "Storage.get_available_name"): lambda f, v: stored(v),
    ("django.core.files.storage.filesystem", "FileSystemStorage._save"): lambda f, v: stored(v),
})

second = Manifest(voyage=spring, crates=3, kilos_each=25)
ASKING.update(second=second, ContentFile=ContentFile, os=os, MEDIA=MEDIA)

with recorded(FILES):
    with step("second.scan = ContentFile(b'three crates of cod', name='spring.txt')"):
        second.scan = ContentFile(b"three crates of cod", name="spring.txt")
    ask("type(vars(second)['scan']).__name__")
    with step("second.scan is read"):
        second.scan
    ask("type(vars(second)['scan']).__name__, second.scan._committed, os.path.exists(os.path.join(MEDIA, 'manifests', 'spring.txt'))")
    with step("second.save()"):
        second.save()
    ask("second.scan.name, second.scan._committed, os.path.exists(os.path.join(MEDIA, 'manifests', 'spring.txt'))")
show("A Manifest is given a file, and saved")

again = Manifest.objects.get(pk=second.pk)
ASKING.update(again=again)

with recorded(FILES):
    ask("type(vars(again)['scan']).__name__, vars(again)['scan']")
    with step("again.scan is read"):
        again.scan
    ask("type(vars(again)['scan']).__name__, again.scan == 'manifests/spring.txt', again.scan.instance is again")
    ask("again.scan.url, again.scan.size, type(again.scan.storage).__name__")
    ask("again.scan.read()")
    ask("again.scan.close()")
    with step("again.scan.save('amended.txt', ContentFile(b'four crates of cod'), save=False)"):
        again.scan.save("amended.txt", ContentFile(b"four crates of cod"), save=False)
    ask("again.scan.name, Manifest.objects.get(pk=again.pk).scan.name")
    ask("sorted(os.listdir(os.path.join(MEDIA, 'manifests')))")
    with step("again.scan.delete(save=False)"):
        again.scan.delete(save=False)
    ask("again.scan.name, bool(again.scan), sorted(os.listdir(os.path.join(MEDIA, 'manifests')))")
show("The row is fetched again: its file is read; another file is saved under the field with save=False, and then deleted")

ask("bool(first.scan), first.scan.name, type(first.scan).__name__")
ask("first.scan.url")
ask("Manifest._meta.get_field('scan').upload_to, Manifest._meta.get_field('scan').max_length, type(Manifest.scan).__name__")
ask("Manifest._meta.get_field('scan').attr_class.__name__, Manifest._meta.get_field('scan').descriptor_class.__name__")
ask("type(Manifest._meta.get_field('scan').storage).__name__")
show("Asked of a file field")

# ---------------------------------------------------------------------------------------------
# The checks.

from django.core import checks  # noqa: E402
from django.test.utils import isolate_apps  # noqa: E402


def check_called(frame):
    """A check of a model, or the check method of one of its fields, managers, constraints or
    indexes. What those call in turn is left out."""
    given = frame.f_locals
    if "cls" in given:
        return f"{q(frame)}({given['cls'].__name__})"
    if "self" not in given:  # a function of that name that is no method
        return None
    obj = given["self"]
    return f"{q(frame)}  ({whose(obj) if not isinstance(obj, BaseManager) else a(type(obj).__name__)})"


def ids_said(frame, value) -> str:
    return "[" + ", ".join(message.id for message in value) + "]"


CHECKS = {"checks": True}
real_find = find


def find(module: str, qualname: str, name: str):  # noqa: F811
    """As before, and where the rules say so every method of Model whose name begins `_check`,
    with Model.check and the check method of whatever a model holds."""
    if RULES.get("checks") and module.startswith("django.db.models"):
        if qualname == "Model.check" or qualname.startswith("Model._check") or (name == "check" and len(STACK) == 2):
            return check_called
        return None
    return real_find(module, qualname, name)


def checks_after(frame, value):
    return ids_said(frame, value) if isinstance(value, list) else None


real_after = AFTER.get


class ChecksAfter(dict):
    """While the checks are recorded, what a check returned is said as the ids of its messages."""

    def get(self, key, default=None):
        if RULES.get("checks") and (key[1].startswith("Model._check") or key[1].endswith(".check")):
            return checks_after
        return dict.get(self, key, default)


AFTER = ChecksAfter(AFTER)

with recorded(CHECKS):
    Ship.check(databases=["default"])
show("Ship.check(databases=['default']): the checks of a model with nothing wrong, in the order they run")

with isolate_apps("harbour.office"):
    class Wreck(models.Model):
        name_ = models.CharField(max_length=40)
        depth = models.DecimalField()
        lost = models.DateField(auto_now=True, default=datetime.date(1900, 1, 1))
        pk = models.IntegerField()

        class Meta:
            app_label = "office"
            ordering = ["tide"]
            constraints = [models.CheckConstraint(condition=models.Q(fathoms__gt=0), name="deep")]

    class Dive(models.Model):
        wreck = models.ForeignKey(Wreck, on_delete=models.SET_NULL)
        again = models.ForeignKey(Wreck, on_delete=models.CASCADE)
        chart = models.ForeignKey("office.Nowhere", on_delete=models.DB_CASCADE)
        id = models.CharField(max_length=5)

        class Meta:
            app_label = "office"

    def returned(found, title: str) -> None:
        """Each message a check returned: its id, its class, the object it is about (a model by
        its label, as Django prints one), its text, and its hint where it has one."""
        for message in found:
            about = message.obj._meta.label if inspect.isclass(message.obj) else message.obj
            note(f"{message.id}, {type(message).__name__}, on {about}: {message.msg}" + (f" Hint: {message.hint}" if message.hint else ""))
        show(title)

    with recorded(CHECKS):
        found = Wreck.check(databases=["default"])
    show("Wreck.check(databases=['default']): a model with mistakes in it")
    returned(found, "What Wreck.check returned")

    with recorded(CHECKS):
        found = Dive.check(databases=["default"])
    show("Dive.check(databases=['default']): a model with mistakes in its relations")
    returned(found, "What Dive.check returned")

    ASKING.update(Wreck=Wreck, Dive=Dive)
    ask("[message.id for message in Wreck.check()]")
    ask("[message.id for message in Wreck.check(databases=['default'])]")
    show("Wreck.check() with no database named, and with one")

ASKING.update(checks=checks)
ask("connection.features.supports_no_precision_decimalfield")
ask("[m.id for m in checks.run_checks()]")
ask("sorted(c.__name__ for c in checks.registry.registry.get_checks() if checks.Tags.models in c.tags)")
ask("sorted(c.__name__ for c in checks.registry.registry.get_checks(include_deployment_checks=True) if checks.Tags.database in c.tags)")
show("Asked of the backend about a DecimalField with no arguments, and of the check registry about the project's own models")

# ---------------------------------------------------------------------------------------------
# Deleting, last: the rows the other blocks used go.

def objs_said(objs) -> str:
    """What a collector was handed, without running a queryset it has not run."""
    if isinstance(objs, QuerySet):
        return queryset_said(objs)
    if isinstance(objs, models.Model):
        return instance_said(objs)
    if inspect.isclass(objs):
        return f"the class {objs.__name__}"
    return "[" + ", ".join(instance_said(o) for o in objs) + "]"


def collect_called(frame) -> str:
    given = frame.f_locals
    said = [objs_said(given["objs"])]
    if given["source"] is not None:
        said.append(f"source={given['source'].__name__}")
    for name, default in (("nullable", False), ("collect_related", True), ("reverse_dependency", False), ("keep_parents", False),
                          ("fail_on_restricted", True)):
        if given[name] is not default:
            said.append(f"{name}={given[name]}")
    return f"Collector.collect({', '.join(said)})"


def on_delete_called(frame) -> str:
    given = frame.f_locals
    return f"{frame.f_code.co_qualname}(collector, {of_field(given['field'])}, {objs_said(given['sub_objs'])}, {given['using']!r})"


def fast_called(frame) -> str:
    given = frame.f_locals
    return f"Collector.can_fast_delete({objs_said(given['objs'])}" + (f", from_field={of_field(given['from_field'])})" if given["from_field"] else ")")


DELETE = {
    **TRANSACTION,
    ("django.db.models.base", "Model.delete"): method(keep_parents=False),
    ("django.db.models.query", "QuerySet.delete"): lambda f: f"QuerySet.delete  ({queryset_said(f.f_locals['self'])})",
    ("django.db.models.deletion", "Collector.collect"): collect_called,
    ("django.db.models.deletion", "Collector.can_fast_delete"): fast_called,
    ("django.db.models.deletion", "Collector.add"): lambda f: f"Collector.add({objs_said(f.f_locals['objs'])})",
    ("django.db.models.deletion", "Collector.add_field_update"):
        lambda f: f"Collector.add_field_update({of_field(f.f_locals['field'])}, {f.f_locals['value']!r}, {objs_said(f.f_locals['objs'])})",
    ("django.db.models.deletion", "Collector.related_objects"):
        lambda f: f"Collector.related_objects({f.f_locals['related_model'].__name__}, {brief(list(f.f_locals['related_fields']))}, {objs_said(f.f_locals['objs'])})",
    ("django.db.models.deletion", "Collector.delete"): plain,
    ("django.db.models.deletion", "Collector.sort"): plain,
    ("django.db.models.deletion", "CASCADE"): on_delete_called,
    ("django.db.models.deletion", "PROTECT"): on_delete_called,
    ("django.db.models.deletion", "RESTRICT"): on_delete_called,
    ("django.db.models.deletion", "SET_NULL"): on_delete_called,
    ("django.db.models.deletion", "SET_DEFAULT"): on_delete_called,
    ("django.db.models.deletion", "DO_NOTHING"): on_delete_called,
    ("django.db.models.query", "QuerySet._raw_delete"): lambda f: f"QuerySet._raw_delete  ({queryset_said(f.f_locals['self'])})",
    ("django.db.models.sql.subqueries", "DeleteQuery.delete_batch"):
        lambda f: f"DeleteQuery.delete_batch({f.f_locals['pk_list']!r})  ({f.f_locals['self'].model.__name__})",
    ("django.db.models.sql.subqueries", "UpdateQuery.update_batch"):
        lambda f: f"UpdateQuery.update_batch({f.f_locals['pk_list']!r}, {f.f_locals['values']!r})  ({f.f_locals['self'].model.__name__})",
}
AFTER.update({
    ("django.db.models.base", "Model.delete"): value_after,
    ("django.db.models.query", "QuerySet.delete"): value_after,
    ("django.db.models.deletion", "Collector.can_fast_delete"): value_after,
    ("django.db.models.deletion", "Collector.add"): lambda f, v: "not already collected: " + objs_said(v),
    ("django.db.models.deletion", "Collector.related_objects"): value_after,
    ("django.db.models.deletion", "Collector.delete"): value_after,
})


def delete_signals(*senders):
    return tuple(
        (signal, name, sender, lambda sent: f"instance={instance_said(sent['instance'])}")
        for sender in senders for signal, name in ((signals.pre_delete, "pre_delete"), (signals.post_delete, "post_delete"))
    )


with recorded(DELETE):
    with step("bergen.delete()"):
        try:
            bergen.delete()
        except models.ProtectedError as raised:
            note(f"the caller catches ProtectedError: {raised.args[0]}")
            note(f"its protected_objects are Ships with the keys {sorted(o.pk for o in raised.protected_objects)}")
show("A Port that ships call home is not deleted")

licence = Licence.objects.get(sailor=ada, port=leith)
with recorded(DELETE):
    with step("licence.delete()"):
        licence.delete()
show("A Licence is deleted: one row, nothing that points at it, nobody listening")
ASKING.update(licence=licence)

ask("licence.pk, licence._state.adding, Licence.objects.filter(port=leith).exists()")
show("Asked of the Licence afterwards")

with recorded(DELETE):
    with step("autumn.delete()"):
        autumn.delete()
show("A Voyage is deleted, with the rows that point at it")

winter = Voyage.objects.create(ship=gannet, sailed=datetime.date(2025, 12, 1))
winter.calls.add(bergen, leith)
Manifest.objects.create(voyage=winter, crates=5, kilos_each=10)
Manifest.objects.create(voyage=winter, crates=8, kilos_each=30)
with heard(*delete_signals(Manifest)), recorded(DELETE):
    with step("winter.delete()"):
        winter.delete()
show("Another Voyage is deleted, with a receiver of pre_delete and one of post_delete connected for Manifest")

summer = Voyage.objects.create(ship=gannet, sailed=datetime.date(2025, 7, 1))
Voyage.calls.through.objects.create(voyage=summer, port=bergen)
Voyage.calls.through.objects.create(voyage=summer, port=leith)
with heard(*delete_signals(Voyage.calls.through)), recorded(DELETE):
    with step("summer.delete()"):
        summer.delete()
show("A third Voyage is deleted, with a receiver of pre_delete and one of post_delete connected for the table of its calls, a model Django made")

with recorded(DELETE):
    with step("petrel.delete()"):
        petrel.delete()
show("A Ship is deleted: its voyages and their calls and manifests, its sailors and their licences")

ask("petrel.pk, Ship.objects.filter(name='Petrel').exists()")
ask("[s.name for s in Sailor.objects.order_by('id')]")
ask("Voyage.objects.count(), Manifest.objects.count(), Voyage.calls.through.objects.count()")
show("Asked of the tables afterwards")

book = Logbook.objects.create(title="Gannet, 2026")
LogEntry.objects.create(book=book, line="Left Leith at dawn.")
LogEntry.objects.create(book=book, line="Fog off the Bass Rock.")
ASKING.update(book=book)

from django.db.models.deletion import Collector  # noqa: E402

forced = Collector(using="default", force_collection=True)
ASKING.update(forced=forced)
with recorded(DELETE):
    with step("forced = Collector(using='default', force_collection=True), and forced.collect([book])"):
        forced.collect([book])
    ask("{model.__name__: len(found) for model, found in forced.data.items()}")
    ask("forced.fast_deletes, LogEntry.objects.count()")
show("A collector made with force_collection=True is given the Logbook, and nothing is deleted")

with recorded(DELETE):
    ask("LogEntry.objects.count()")
    with step("book.delete()"):
        book.delete()
    ask("LogEntry.objects.count()")
show("A Logbook is deleted: the relation that points at it is DB_CASCADE")

with recorded(DELETE):
    with step("finn.delete(keep_parents=True)"):
        finn.delete(keep_parents=True)
    ask("Officer.objects.filter(pk=6).exists(), Sailor.objects.filter(pk=6).exists()")
    with step("Officer.objects.get(name='Cora').delete()"):
        Officer.objects.get(name="Cora").delete()
    ask("Officer.objects.filter(pk=3).exists(), Sailor.objects.filter(pk=3).exists(), Ship.objects.get(name='Gannet').captain_id")
show("An Officer is deleted: keeping the parent's row, and not")

with recorded(DELETE):
    with step("Berth.objects.filter(port=bergen).delete()"):
        Berth.objects.filter(port=bergen).delete()
    with step("Sailor.objects.filter(name='Finn').delete()"):
        Sailor.objects.filter(name="Finn").delete()
show("A queryset is deleted: the same collector")

# Last of all, so that the serial it takes shifts no other block's: a row that has a file is deleted.
final = Voyage.objects.create(ship=gannet, sailed=datetime.date(2026, 4, 9))
papers = Manifest(voyage=final, crates=2, kilos_each=9)
papers.scan = ContentFile(b"two crates of rope", name="rope.txt")
papers.save()
ASKING.update(papers=papers)
with recorded(DELETE):
    ask("papers.scan.name, sorted(os.listdir(os.path.join(MEDIA, 'manifests')))")
    with step("papers.delete()"):
        papers.delete()
    ask("Manifest.objects.filter(pk='M-0005').exists(), papers.scan.name, sorted(os.listdir(os.path.join(MEDIA, 'manifests')))")
show("A Manifest that has a file is deleted: the row goes and the file stays")


