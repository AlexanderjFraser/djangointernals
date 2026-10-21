"""A recording of Django's migrations: how makemigrations compares the models with the state the
migration files make and writes new files, how migrate plans them, applies them and records
what it applied, and what the pieces between them do: a migration and its operations, the
project state and the historical models rendered from it, the graph, the loader, the recorder,
the executor, the autodetector, the questioner, the optimizer, the serializer and the writer.

    python recordings/migrations.py > recordings/migrations.txt

The chapters of the book that quote it (pages/migrations.md and pages/makemigrations.md,
with the pages under them) are written against this
output. It needs the pinned Django (the project's virtual environment has it), the small project
beside it, `harbour/`, which the other recordings of the ORM use too, and for two blocks the drivers of
other backends (`requirements.txt`), whose servers never run: the block on a migration in a
transaction or not makes connections of PostgreSQL's, MySQL's and Oracle's backends, and the
block on OperationWriter imports django.contrib.postgres.operations, which imports PostgreSQL's
driver. It takes about a minute. Run it again after a re-pin: where the output changes, the
chapter has to.

The project. Harbour has no migrations and keeps none: the script copies it into a directory made
for the run, the run's directory, and everything happens to the copy, so that Django writes each
application's migrations where a project has them, `harbour/fleet/migrations/` and so on. To the
copy the script adds `manage.py` and `settings.py` (the first blocks show both) and a fourth
application, yard, a repair yard of two models, Dock and Repair. `settings.py` names two SQLite
files, "default" (`harbour.sqlite3`) and "archive" (`archive.sqlite3`), and no router. Four more
settings modules, each written by the script where its blocks come, shown there, and (but for the
last) removed after them, import `settings.py` and change a thing or two; a database that one of
them adds or replaces has a file of its own; a block run under one says so in its title, and a
command line names it with `--settings`.

Yard's story. Yard's models change as the recording goes, and each version of
`harbour/yard/models.py` is shown where the script writes it. First version: the project's first
makemigrations and migrate; most blocks are recorded here. Second: a field made longer, one
added, one renamed, an index: yard.0002. Third: a column that is not null and has no default:
yard.0003. Then, with no change of models, a data migration written into the file that
`makemigrations --empty` made: yard.0004. Fourth: a second index, for which the script writes
yard.0005 by hand with SeparateDatabaseAndState. Fifth: one more field, yard.0006_dock_covered,
beside which the script puts a colleague's migration, yard.0006_long_dock; the two leaf nodes are
merged by yard.0007_merge. Then the eight are squashed into yard.0001_squashed_0007_merge, the
script finishes the squash by hand (the replaced files removed, `replaces` taken out, their rows
pruned), and makemigrations writes yard.0008 for what the squash left. Sixth, with
django.contrib.auth installed: a foreign key to the user model, yard.0009. The blocks stand in the
order they ran, so a block's place in the story is its place in the output; within a version of
yard they follow the order of the chapter's sections as far as that allows.

The words. A migration is an instance of the class Migration that a migration file defines,
written as its str gives it, `fleet.0001_initial`; its key is the pair ('fleet', '0001_initial').
An operation is written by its class and what its describe() says, `AddField: Add field metres to
dock`; it has a state half (state_forwards) and a database half (database_forwards,
database_backwards). A project state is a ProjectState and a model state a ModelState. A
historical model is a model class rendered from a model state, as against the model a models.py
defines; two kinds of class have a historical model's module and were rendered from no model
state, and are written apart: `the historical model fleet.Voyage_calls, made for a many-to-many
field` is the model between that such a field makes for itself while its own model is rendered,
and is in the state's registry; `the model yard.NewDock that _remake_table made` is the model
SQLite's schema editor makes for the table it builds, and is in a registry of its own. The
state's registry is a project state's StateApps, as against the main registry,
django.apps.apps; a project state is rendered when its registry has been made. The graph is the
MigrationGraph: nodes, each with its parents (what it depends on) and children; root nodes and
leaf nodes. A plan is a list of pairs (migration, backwards?); the full plan is the plan for every
leaf node from a clean start; a target is a key a plan is to reach. Applied means having a row in
django_migrations; the loader's `applied_migrations` holds, besides the migrations that have a
row, a replacing migration that has none where every migration it replaces has one, which is
what showmigrations marks `[-]`: of that the blocks say that the loader counts it applied. The
loader, the recorder, the executor, the autodetector, the questioner, the optimizer and the
writer are each an instance of the class of that name. The from-state and the to-state are the
two project states an operation's database half, or the autodetector, is given. A replacing
migration has `replaces` (the command's word is squashed), and the migrations it names are
replaced. An application is migrated or unmigrated as MigrationLoader.load_disk sorts it. A
statement is SQL sent to the database; what the script runs is a line of Python; a command line
is a process of its own.

The blocks are of five kinds, and a block may mix them. Where the order of calls is the point,
the lines are calls, nested as they were made: the calls a block is about and no others, so
everything between the lines ran and is left out. A line of Python is what the script ran, as it
ran it; under it stand the calls it set going, of those the block is about, and every statement
it sent: a line of Python with no `SQL` line under it sent none, unless the line ends with a
comment that counts the statements it sent (`# 25 statements sent, none written here`); another
comment on a line of Python is the script's own, and says why the line is there. A line of
Python and a question are written as they were run, to the letter.

How a call is written. A method is written by the class that declares it;
`InteractiveMigrationQuestioner.ask_initial('crew')  (MigrationQuestioner.ask_initial)` is the
class of the object and, in parentheses, the class whose method ran; a command's class is
written with its module, `migrate.Command.handle`; a signal's send by the signal's name,
`pre_migrate.send(sender=the AppConfig fleet)  (Signal.send)`, without the keyword arguments it
sends, which the block on the signals shows. Arguments follow, each by its name, those left at
their defaults passed over; the one parameter of a function that has only one is written by its
value alone, `ask_initial('crew')`. Some calls are written with the arguments their block is
about and no others, each by its value: `MigrationExecutor.apply_migration(yard.0003_repair_foreman)`
leaves out the state, `StateApps.register_model('crew', the historical model crew.Sailor)` has
both; a command's handle has its positional arguments and, of its options, those the block is
about, so `migrate.Command.handle()` was still given every option; and
`MigrationGraph.add_dependency(child=..., parent=..., skip_validation=True)` leaves out its
first argument, the migration, whose key is the child. Words in angle brackets stand in place of
a value: `<13 model states>`, `<8 keys>`, `<12 applied>`, and, where a set chose the value, what
can be said of it whichever it was. After a method of an operation its describe() stands in
brackets, after a method of a migration the migration, after ModelState.render the model state,
and after a call on a project state or a registry, in some blocks, which state it is (`[the
autodetector's from_state]`, `[the registry of clone 1]`). Migration.mutate_state is written
with its state only where the script has named that state.

What a call returned follows `->`, put into words when it was returned; `raises` names an
exception, once, at the innermost written-down call it left, and again with its message under
the line of Python it ended; a newline in a message is written `\\n`. Words in parentheses after
a call are the script's own remark on it and nothing the call returned. After a generate_ or
create_ method of the autodetector, `(29 operations added)` is how many operations
generated_operations gained while the method ran, which the script counts (the methods return
nothing). A call followed by `(what it called is not written, nor the N statements it sent)`, or
`nor the statement it sent`, or `it sent no statement`, is one line for every call it made and
every statement it sent; what it printed, what a callback of the script's wrote and what it
returned still stand under it. One followed by `(what it called is not written, and of the N
statements it sent the first and the last)` has those two under it and between them a count of
the rest: SQLite's _remake_table, which the chapter on the backends follows, in the blocks of operations run by
hand.

What is left out of the calls. The state half of an operation is not written when
Migration.mutate_state runs it, as it does for every migration each time a project state is
made. Of the lookups of Apps.get_model only those that an operation, the executor, a migration
file or the script makes are written. StateApps.__init__ is written where a registry is made by
rendering model states, and not where StateApps.clone makes the empty registry it fills with
another's model classes: a line StateApps.__init__ is a rendering, and the clone of a rendered
state has its registry without one. A call made on a connection other than "default", or by an
object that holds one, says which: `(on "fresh")`.

A second kind of block puts one question to a running Django on each line: the expression, then
`->` and its value, with any statement it sent under it; a question that raised has `raises`, the
exception's name and its message for its value. A third kind writes down what an object, a
directory or a table holds, a thing to a line, in the script's words. A fourth is command
lines: `python manage.py ...` is run as a process of its own, in the run's directory, and under
it stand what it printed, each line after the stream it came on (`stdout |`, `stderr |`; all of
standard output first, then standard error), a traceback cut to its first and last lines, and
`exit status N` where N is not 0. Where the command asks a question, the script types each
answer when the process has written its prompt and waits, and a line `stdin  |` stands where the
answer was given: the line break before and after it is the script's, since in what the process
wrote the prompt and whatever it printed next are one line. A fifth is a file as it stands, each
line after `| `; a version of yard's models has `+` before each line put in and `-` before each
taken out, and its other lines two columns further in than in a file shown plain (the lines are
in the order difflib.ndiff gives them, in which a line taken out stands by the new line most
like it, before it or after); where only the changed lines of a file are shown, `...` stands
between them. A text that a name of the lines above holds is written as the name, a colon, and
its lines after `| `.

A command run in the script's own process, by call_command, is given `out` for its standard
output, which writes each thing the command prints as a line `stdout |` among the calls, where it
was printed; `(the line is not ended)` and `(the same line goes on)` mark a line printed in two
pieces. One thing differs from the command line: call_command passes skip_checks=True where its
caller does not say, and the script does not, so the system checks that BaseCommand.execute runs
before handle on a command line are not run in these blocks. No line written here is the checks'.

Two kinds of line stand for a statement. A line `SQL` is a statement as Django handed it to its
cursor, with its `%s` placeholders and its parameters: the script's execute wrapper, put
outermost on each connection as Django makes it, writes it; `SQL (on "archive")` names the alias
where it is not "default". A line `sqlite` is a statement as SQLite ran it, with the parameters
bound: the driver's trace callback writes it, and it is written only in the two blocks whose
titles say so, on one migration's transaction and on RunPython in a transaction or not. Django
commits by calling the driver's commit, which is no `SQL` line: where `sqlite` lines are written
the COMMIT stands among them, and elsewhere a BEGIN stands with no statement after it to close
it. The script stops if putting a call into words ever sends a statement, or makes a state's
registry (reading ProjectState.apps would): no line of the output is the doing of the words.

Other lines. `# ...` says what the script is about to do or has done, where no line of Python
says it; under such a line some blocks show the code of the script's own functions and classes.
`changed:` lines, under a line that ran the state half of an operation, say what differs in the
project state's model states, found by comparing them before and after. `logs` is what a
questioner that asks no one was given to log. `progress(...)` is written by a progress callback
of the script's own given to an executor, and `watching(...)` by a receiver of the script's own
connected to pre_migrate and post_migrate; the blocks show both.

How things are put into words: a migration, an operation, a project state (how many model
states, and whether its registry is rendered, which is asked of its `__dict__` and never by
reading `apps`), a model state, `the model fleet.Ship` and `the historical model fleet.Ship`, the
recorder's model, a state's registry and the main registry, a connection, the schema editor, the
loader and its like, as the words above have them; a state or a registry the script has named is
written by that name (`state`, `previous`, `clone 2`, the names of the lines of Python that made
them); a field bound to a model as `the field yard.Dock.metres`, another as `an unbound
CharField`; in the blocks on the autodetector and the optimizer an operation with, in
parentheses, what tells it from another of its class (a CreateModel's fields by name, a field by
its class and the arguments it deconstructs to, an option's value); among a field's arguments a
reference to a setting, which is a string that also carries the setting's name, as
`settings.AUTH_USER_MODEL ('auth.user')`; a dependency the autodetector gives an operation as
`needs (crew, sailor) created`: what another operation, if there is one, must have done first; a
plan given to a call as `a plan of 5`; a class in an answer with its module; a function by its
name; a list of more than six things as its first two and how many more, but under `full(...)`,
which writes a value whole as its repr, and `whole(...)`, which writes every item in the words
above.

Helpers of the script's own used in lines of Python and questions: `made(...)` (a Migration
instance of yard with the operations given it; its code is shown), `detect(...)` (what the
autodetector makes of a change of the script's own; shown), `overriding(...)` (a question asked
with MIGRATION_MODULES overridden; shown), `raising(...)` (the exception a call raises),
`written(value)` (MigrationWriter.serialize(value): the text, and the imports it needs, sorted),
`field_said(field)`, `default_said(value)` (NOT_PROVIDED by its name), `dialects` (connections of
three other backends, made by a ConnectionHandler of the script's own and never opened),
`as_prepared` (two sets of the autodetector's as one of its methods returned them, kept by the
script because a later method changes one); and, read by the script itself on the driver's
connection, past Django's cursor, so that no `SQL` line stands under them, `columns(table)`,
`tables()`, `indexes(table)`, `table_sql(table)`, `rows(table, ...)` and `recorded_rows(alias,
application)` (the rows of django_migrations as `label.name`, in the order of their ids);
`migration_files()`, `os_listdir(...)` and `os_walk(...)` list files of the run's directory.
`keyboard` stands in for the process's standard input where the interactive questioner is asked
in the script's own process: a line `stdin  |` stands where input() read the line typed ahead.

What is the script's own doing is said: a block run on a migration, a model state, a project
state, a graph or a router's question of the script's own says so in its title or in a `#` line,
and so does one for which the script moved migrations directories out of the project, wrote or
removed a file, set a feature of the connection, or removed or put back a database file. Where
the script
writes or removes a file of a package inside a part, it has the import system look at the
directories again (importlib.invalidate_caches), and takes a module whose file it removed out of
sys.modules, as a process started afterwards would not have it. A block that changes the
database by hand undoes it, or ends by putting the file back from a copy the script kept, and
says which; the three blocks on Migration.apply and Migration.unapply share one copy, and each
says what the one before left it. After every part that is not a step of yard's story, and
around the groups of command lines that only look, the script compares the run's directory with
what it was (every file; in every database the tables, the indexes, the rows of
django_migrations by id, application and name, and the number of rows of each other table) and
stops if they differ; the time in a row is not compared, since the part that records migrate's
calls makes the database again, and says so.

Where the script runs by hand what the executor runs (Migration.apply, Migration.unapply, an
operation's two halves, apply_migration, detect_soft_applied), it gives it what the executor
would: a state whose registry is rendered before the state is cloned, which the line `state.apps`
does, with a comment that says so. The order matters to the output. In a migrate the changed
model is rendered again in the to-state after the from-state's was, so the to-state's fields are
the newer; where a state is cloned before it is rendered, both registries are made inside the
first database half, the to-state's first, and the from-state's fields are the newer. SQLite's
_remake_table orders a table's columns by the order in which their fields were made, and so
gives a remade table another column order in the second case than in the first. sqlmigrate does
start from a state nobody has rendered, and the block on its calls shows what follows from that.

What differs between runs is written the same way every time. The run's directory is left out of
every path, so that a whole path reads as one from the run's directory: the four blocks in which
Django printed or returned a whole path say so; and a path Django printed with this machine's
separators is written with forward slashes, `harbour/yard/migrations/0001_initial.py`. The date
and the time are left out of a migration file's first line, of a name that has them
(`0004_auto_(the date)_(the time)`), of the row written for an applied migration, and of what
showmigrations prints of it; a duration that migrate prints is `(0.000s)`; a memory address is
left out. None of this touches a line of Python or a question: the script stops if it would.
A set is sorted. The autodetector passes a migration's dependencies through a set, so their
order in the instance is the set's and they are shown sorted (in a file the writer sorts them).
In the pictures of generated_operations the applications stand in the dict's own order, and an
operation's dependencies in the order of the list the autodetector gave it, but for the two
kinds of operation it gives `list(set(dependencies))`, the AddField of a relation that
generate_created_models makes and a DeleteModel: those are written sorted. The calls of
unregister_model under ProjectState._reload are written sorted; the names in a
CircularDependencyError's message are asked sorted; and of the first question makemigrations
puts to a router, the application and the model, which a set chooses, are not written. Command
lines and parts are run without the environment variables that would change what Python or
Django prints (FORCE_COLOR and its like, which colour a traceback and argparse's usage even into
a pipe). These are this build's: SQLite 3.50.4; Windows, for which a concrete path is serialized
as a PureWindowsPath; and no `black` on the path, which Django would run on each file it writes.

Yard's models are imported once in a process, so the recording is made in parts. Run whole, the
script never sets Django up: it writes the files, runs command lines, and runs each group of the
other blocks as a part, in an interpreter of its own, in which Django is set up with the settings
module of the moment and the run's directory is the working directory (a part runs a command
line of its own here and there). The database files and the migration files stay in the run's
directory from one part to the next.

    RECORD_EVERYTHING=django.db.migrations.executor python recordings/migrations.py    every call in the modules with that prefix, wherever calls are written
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# The directory of this script goes last on the path and not first, where Python puts a script's
# own: `http.py` in it has the name of a package of the standard library, which Django imports.
# The run's directory, which holds the copy of harbour, goes first: see `set_up`.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != HERE] + [HERE]
sys.dont_write_bytecode = True  # no __pycache__ in the run's directory: a file rewritten within a second is read again

import atexit  # noqa: E402
import datetime  # noqa: E402
import decimal  # noqa: E402
import difflib  # noqa: E402
import enum  # noqa: E402
import functools  # noqa: E402
import hashlib  # noqa: E402
import importlib  # noqa: E402
import inspect  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import sqlite3  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import types  # noqa: E402
import warnings  # noqa: E402
import weakref  # noqa: E402

import django  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # the same bytes on every machine
EVERYTHING = tuple(p for p in os.environ.get("RECORD_EVERYTHING", "").split(",") if p)
PART = sys.argv[1] if len(sys.argv) > 1 else None

# The run's directory, made by the script when it runs whole and handed to each part it runs in
# an interpreter of its own. Its path is never written: see `normalised`.
SCRATCH = os.path.realpath(os.environ.get("RECORDING_SCRATCH") or tempfile.mkdtemp())
os.environ["RECORDING_SCRATCH"] = SCRATCH

LINES = []
STACK = []  # the watched frames open at this moment, which give the depth of the next line
AT = {}  # where in LINES the line of each open watched call is, by the frame
SEEN = {}  # generator frames already written down, each with its generator
PENDING = []  # the watched call that has just returned: (frame, depth, its line, what is to be said of its value)
RAISED = []  # exceptions already written down, at the innermost watched call they left
RESUMABLE = 0x20 | 0x80 | 0x200  # a generator, a coroutine, an asynchronous generator


class Remark(str):
    """What the script itself says of a call as it returns, where the call returned nothing of
    the kind: it is written in parentheses, and not after `->`."""


def flush() -> None:
    """Say what the call that has just returned gave back, if that is to be said: on the
    call's own line where nothing was written under it, and on a line of its own otherwise."""
    while PENDING:
        frame, depth, at, said = PENDING.pop(0)
        if said is not None:
            if isinstance(said, Remark):
                if at == len(LINES) - 1:
                    LINES[at] += f"  ({said})"
                else:
                    LINES.append("  " * depth + f"({said})")
            elif at == len(LINES) - 1:
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


SCRATCH_SPELLINGS = re.compile(
    "|".join(re.escape(spelling) + tail for spelling, tail in (
        (SCRATCH.replace("\\", "\\\\"), r"(?:\\\\)?"), (SCRATCH, r"\\?"), (SCRATCH.replace("\\", "/"), "/?"),
    )),
    re.IGNORECASE,
)


def normalised(line: str) -> str:
    """What differs from run to run, put the same way every time: see the docstring."""
    line = SCRATCH_SPELLINGS.sub(lambda m: "" if m.group(0)[-1] in "\\/" else "(the run's directory)", line)
    # A path below the run's directory, with the separators of this machine or with a string's doubled ones: with forward slashes.
    line = re.sub(r"\bharbour(?:\\{1,2}[\w.~]+)+", lambda m: re.sub(r"\\+", "/", m.group(0)), line)
    line = re.sub(r"(# Generated by Django \S+ on )\d{4}-\d\d-\d\d \d\d:\d\d", r"\1(the date and the time)", line)
    line = re.sub(r"(?<![A-Za-z])(auto|merge)_\d{8}_\d{4}(?!\d)", r"\1_(the date)_(the time)", line)
    line = re.sub(r"\(applied at \d{4}-\d\d-\d\d \d\d:\d\d:\d\d\)", "(applied at (the date and the time))", line)
    if '"django_migrations"' in line:  # the time a row was written, in an INSERT's parameters
        line = re.sub(r"'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?:\.\d+)?'", "'(the date and the time)'", line)
    line = re.sub(r" \(\d+\.\d{3}s\)", " (0.000s)", line)
    line = re.sub(r"\bs\d+_x(\d+)", r"s(the thread)_x\1", line)
    line = re.sub(r" at 0x[0-9A-Fa-f]+", "", line)
    return line.rstrip()


def show(title: str) -> None:
    flush()
    print(normalised(title))
    for line in LINES:
        print("    " + normalised(line))
    print()
    reset()


# ---------------------------------------------------------------------------------------------
# The recorder.

RULES = {}  # the set in force
LABELLING = False  # whether a call is being put into words at this moment: a statement sent then is a fault of this script's
LISTENING = False  # whether a statement sent to the database is written down
SQLITE = False  # whether a statement SQLite ran is written down as a line `sqlite`
AFTER = {}  # (module, qualname) -> what to say of the value a call returned
MUTED = None  # [the frame of a call written as one line, the statements sent under it]: nothing under it is written


class Briefly(str):
    """A label for a call written as one line: none of the calls under it is written, and the
    line says how many statements were sent while it ran."""


class Ends(Briefly):
    """A label for a call under which none of the calls is written, and of the statements it sent
    only the first and the last, with a line between them that counts the others."""


def plain(frame) -> str:
    return short(frame.f_code.co_qualname)


def short(qualname: str) -> str:
    """A qualified name without the functions it is defined inside."""
    return qualname.rsplit("<locals>.", 1)[-1]


def find(module: str, qualname: str):
    label = RULES.get((module, qualname))
    if label is not None:
        return label
    if EVERYTHING and module.startswith(EVERYTHING) and "<" not in qualname:
        return plain
    return None


def stop(why: str) -> None:
    """A fault of this script's: say so and end the process, whatever is on the stack."""
    import traceback

    sys.stdout.flush()
    sys.stderr.write(f"recordings/migrations.py: {why}\n")
    traceback.print_stack(limit=14)
    sys.stderr.flush()
    os._exit(1)


def profile(frame, event, arg):
    global LABELLING, MUTED
    if event not in ("call", "return"):
        return
    code = frame.f_code
    if code is UNWINDING:
        return
    if event == "call":
        if MUTED is not None:
            return
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
        if isinstance(text, Briefly):
            MUTED = [frame, 0, [], isinstance(text, Ends)]
    elif event == "return":
        if STACK and STACK[-1] is frame:
            flush()
            if MUTED is not None and MUTED[0] is frame:
                sent, statements, ends = MUTED[1], MUTED[2], MUTED[3]
                if ends and sent > 2:
                    LINES[AT[id(frame)]] += f"  (what it called is not written, and of the {sent} statements it sent the first and the last)"
                    LINES.extend("  " * len(STACK) + line for line in (statements[0], f"... ({sent - 2} statement{'' if sent == 3 else 's'} between, not written)", statements[-1]))
                elif ends:
                    LINES[AT[id(frame)]] += "  (what it called is not written)"
                    LINES.extend("  " * len(STACK) + line for line in statements)
                else:
                    LINES[AT[id(frame)]] += "  (what it called is not written" + (f", nor the {sent} statements it sent)" if sent != 1 else ", nor the statement it sent)") if sent else "  (what it called is not written; it sent no statement)"
                MUTED = None
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
    """An exception by its class's name."""
    return type(exception).__name__


UNWINDING = unwinding.__code__
MONITOR = sys.monitoring.PROFILER_ID
sys.monitoring.use_tool_id(MONITOR, "recordings/migrations.py")
sys.monitoring.register_callback(MONITOR, sys.monitoring.events.PY_UNWIND, unwinding)
sys.monitoring.set_events(MONITOR, sys.monitoring.events.PY_UNWIND)


class recorded:
    """`with recorded(RULES):` writes down, of what runs in the block, the calls those rules
    name; `with recorded(RULES, sqlite=True):` also each statement SQLite ran."""

    def __init__(self, rules: dict, sqlite: bool = False, after: dict | None = None):
        self.rules = rules
        self.sqlite = sqlite
        self.after = after or {}

    def __enter__(self):
        global RULES, LISTENING, SQLITE
        RULES = self.rules
        self.kept = dict(AFTER)
        AFTER.update(self.after)
        LISTENING = True
        SQLITE = self.sqlite
        sys.setprofile(profile)

    def __exit__(self, *exc):
        global LISTENING, SQLITE, RULES
        sys.setprofile(None)
        LISTENING = False
        SQLITE = False
        flush()
        AFTER.clear()
        AFTER.update(self.kept)
        RULES = {}


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
        raise SystemExit(f"recordings/migrations.py: this Python reports an exception leaving a function otherwise than expected: {LINES!r}")
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


def as_run(text: str) -> str:
    """A line of Python or a question, which has to be written as it is run: the script stops
    if putting what differs between runs the same way every time would change its text."""
    if normalised(text) != text.rstrip():
        stop(f"a line of Python would not be written as it is run: {text!r} would become {normalised(text)!r}")
    return text


def ask(expression: str) -> None:
    """One question and its answer, on one line. The question is evaluated as it is written
    down, so the line cannot say one thing and the script do another."""
    global LISTENING
    as_run(expression)
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
        except SystemExit as left:
            said = f"raises SystemExit: {left.code!r}"
        except Exception as raised:
            said = f"raises {raised_name(raised)}: {message(raised)}"
    warned_lines(warned)
    LISTENING = listening
    LINES[before:] = ["  " * len(STACK) + f"{expression}  ->  {said}", *("  " + line for line in LINES[before:])]
    sys.setprofile(watching)


def do(statement: str) -> None:
    """A line of Python, written down and then run, with what it sets going written under it.
    A name the line binds can be used by the lines and questions after it. Every statement it
    sends is written under it."""
    global LISTENING
    note(as_run(statement))
    STACK.append(None)
    listening, LISTENING = LISTENING, True
    with warnings.catch_warnings(record=True) as warned:
        warnings.simplefilter("always")
        try:
            exec(statement, ASKING)
        except SystemExit as left:
            flush()
            LINES.append("  " * (len(STACK) - 1) + f"raises SystemExit: {left.code!r}")
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
    note(as_run(statement))
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


def silently(statement: str) -> None:
    """A line of Python that is written down and run with nothing written under it: neither
    its calls nor the statements it sent, which a comment on the line counts."""
    global LISTENING
    as_run(statement)
    watching, listening = sys.getprofile(), LISTENING
    sys.setprofile(None)
    LISTENING = False
    SENT.clear()
    try:
        exec(statement, ASKING)
    finally:
        LISTENING = listening
        sys.setprofile(watching)
    note(f"{statement}  # {len(SENT)} statements sent, none written here" if len(SENT) != 1 else f"{statement}  # 1 statement sent, not written here")


def step(words: str) -> None:
    """A line that says what the script is about to do or has set up, where no line of Python says it."""
    note(f"# {words}")


def code(*things) -> None:
    """The source of the script's own functions or classes, each line under the `#` line before it, its blank lines left out."""
    import textwrap

    for thing in things:
        for text in textwrap.dedent(inspect.getsource(thing)).splitlines():
            if text.strip():
                note("  " + text)


# ---------------------------------------------------------------------------------------------
# The statements, as Django handed them to its cursor and as SQLite ran them.

SENT = []  # every statement handed to a cursor since the list was last emptied


def query_sent(execute, sql, params, many, context):
    """The script's execute wrapper, outermost on each connection of `connections`: it writes
    the line `SQL`."""
    global MUTED
    if LABELLING:
        stop(f"putting a call into words sent a statement to the database: {sql}")
    SENT.append(sql)
    where = "" if context["connection"].alias == "default" else f' (on "{context["connection"].alias}")'
    if many:
        rows = params if isinstance(params, (list, tuple)) else "an iterator"
        line = f"SQL{where} {one_line(sql)} with each of {rows!r} (executemany)"
    else:
        line = f"SQL{where} {one_line(sql)} with params {params!r}" if params else f"SQL{where} {one_line(sql)}"
    if MUTED is not None:
        MUTED[1] += 1
        MUTED[2].append(line)
    elif LISTENING:
        note(line)
    return execute(sql, params, many, context)


def ran(statement: str) -> None:
    """The driver's trace callback, set on every connection of the driver's that is made: it
    writes the line `sqlite`."""
    if LABELLING:
        stop(f"putting a call into words ran a statement in SQLite: {statement}")
    if LISTENING and SQLITE and MUTED is None:
        note(f"sqlite {one_line(statement)}")


def one_line(sql: str) -> str:
    """A statement written on several lines, on one: each line break and the spaces around it become one space."""
    return re.sub(r"\s*\n\s*", " ", str(sql).strip())


_connect = sqlite3.dbapi2.connect


def connect(*args, **kwargs):
    """The driver's connect, with the trace callback set on what it returns before anything runs on it."""
    made = _connect(*args, **kwargs)
    made.set_trace_callback(ran)
    return made


sqlite3.dbapi2.connect = connect


def listen(conn) -> None:
    """Put the script's execute wrapper on a connection, outermost."""
    if query_sent not in conn.execute_wrappers:
        conn.execute_wrappers.insert(0, query_sent)


NOT_ENDED = "  (the line is not ended)"


class Printed(io.TextIOBase):
    """What a command run in this process is given as its standard output: each thing written
    to it is a line of the recording, `stdout | ...`, where it was written among the calls."""

    def __init__(self):
        self.open_line = False  # whether the last thing written did not end its line

    def write(self, text: str) -> int:
        flush()
        pieces = text.split("\n")
        for index, piece in enumerate(pieces):
            last = index == len(pieces) - 1
            if last and piece == "":
                break
            head = "stdout | (the same line goes on) " if self.open_line and index == 0 else "stdout | "
            LINES.append("  " * len(STACK) + (head + piece).rstrip() + (NOT_ENDED if last else ""))
        self.open_line = not text.endswith("\n")
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


# ---------------------------------------------------------------------------------------------
# How values and calls are said.


def a(name: str) -> str:
    """A thing by its class's name, with the article the name is read with."""
    return ("an " if name[0] in "AEIOU" and not name.startswith(("One", "Use")) else "a ") + name


def model_said(model) -> str:
    """A model class: `the model fleet.Ship` for the one a models.py defines, `the historical
    model fleet.Ship` for one rendered from a model state. Two kinds of class have a historical
    model's module and were rendered from no model state, and are told apart: the model between
    that a many-to-many field makes for itself while its own model is rendered, which is in the
    state's registry, and the model SQLite's _remake_table makes for the table it builds, which
    is in a registry of its own."""
    from django.db.migrations.state import StateApps

    label = f"{model._meta.app_label}.{model._meta.object_name}"
    if model.__module__ == "__fake__":
        if not isinstance(model._meta.apps, StateApps):
            return f"the model {label} that _remake_table made"
        if model._meta.auto_created:
            return f"the historical model {label}, made for a many-to-many field"
        return f"the historical model {label}"
    if model.__module__ == "django.db.migrations.recorder":
        return "the recorder's model"
    return f"the model {label}"


def state_said(state) -> str:
    """A project state: how many model states it holds, and whether its registry has been made.
    The registry is never read here: reading it would make it."""
    count = len(state.models)
    return f"a ProjectState of {count} model state{'' if count == 1 else 's'}, its registry {'rendered' if 'apps' in state.__dict__ else 'not rendered'}"


def dependency_said(dependency) -> str:
    """One of the autodetector's dependencies of an operation, in words."""
    kind = dependency.type.name
    what = f"({dependency.app_label}, {dependency.model_name})" if dependency.field_name is None else f"({dependency.app_label}, {dependency.model_name}, {dependency.field_name})"
    words = {
        "CREATE": "created", "REMOVE": "removed", "ALTER": "altered", "REMOVE_ORDER_WRT": "no longer what the model is ordered with respect to",
        "ALTER_FOO_TOGETHER": "out of unique_together", "REMOVE_INDEX_OR_CONSTRAINT": "out of every index and constraint",
    }[kind]
    return f"needs {what} {words}"


def operation_said(operation) -> str:
    """An operation: its class, and what its describe() says."""
    return f"{type(operation).__name__}: {operation.describe()}"


NAMED = {}  # things the script has given a name to, by id: a state or a registry a block follows


def brief(value) -> str:
    """A value in few words."""
    from django.apps import apps as main_registry
    from django.apps.config import AppConfig
    from django.apps.registry import Apps
    from django.db import models
    from django.db.backends.base.base import BaseDatabaseWrapper
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations import Migration
    from django.db.migrations.autodetector import MigrationAutodetector, OperationDependency
    from django.db.migrations.executor import MigrationExecutor
    from django.db.migrations.graph import MigrationGraph, Node
    from django.db.migrations.loader import MigrationLoader
    from django.db.migrations.operations.base import Operation
    from django.db.migrations.recorder import MigrationRecorder
    from django.db.migrations.state import ModelState, ProjectState, StateApps
    from django.db.models.constraints import BaseConstraint
    from django.dispatch import Signal
    from django.utils.connection import ConnectionProxy

    if id(value) in NAMED and NAMED[id(value)][0]() is value:
        return NAMED[id(value)][1]
    if isinstance(value, BaseDatabaseWrapper):
        return f'the connection "{value.alias}"'
    if isinstance(value, ConnectionProxy):
        return f'the connection "{value._alias}"'
    if isinstance(value, BaseDatabaseSchemaEditor):
        return "the schema editor" + ("" if value.connection.alias == "default" else f' of "{value.connection.alias}"')
    if isinstance(value, Migration):
        return str(value)
    if isinstance(value, Operation):
        return operation_detail(value) if OPERATIONS_IN_DETAIL else operation_said(value)
    if isinstance(value, ProjectState):
        return state_said(value)
    if isinstance(value, ModelState):
        return f"the model state {value.app_label}.{value.name}"
    if isinstance(value, StateApps):
        return "a state's registry"
    if value is main_registry:
        return "the main registry"
    if isinstance(value, Apps):
        return a(type(value).__name__)
    if isinstance(value, AppConfig):
        return f"the {type(value).__name__} {value.label}"
    if isinstance(value, OperationDependency):
        return dependency_said(value)
    if isinstance(value, Node):
        return f"the node {value.key!r}" if type(value) is Node else f"the {type(value).__name__} {value.key!r}"
    if isinstance(value, (MigrationLoader, MigrationExecutor, MigrationRecorder, MigrationAutodetector)):
        return {MigrationLoader: "the loader", MigrationExecutor: "the executor", MigrationRecorder: "the recorder", MigrationAutodetector: "the autodetector"}[type(value)]
    if isinstance(value, MigrationGraph):
        return f"the graph ({len(value.nodes)} nodes)"
    if isinstance(value, Signal):
        return SIGNAL_NAMES.get(id(value), "a Signal")
    if isinstance(value, models.Model):
        return repr(value)
    if isinstance(value, models.Field):
        model = getattr(value, "model", None)
        return f"the field {model._meta.label}.{value.name}" if inspect.isclass(model) else f"an unbound {type(value).__name__}"
    if isinstance(value, (models.Index, BaseConstraint, models.Q, models.expressions.BaseExpression, models.Manager)):
        return repr(value)
    if isinstance(value, BaseException):
        return f"{type(value).__name__}({str(value)!r})"
    if isinstance(value, (datetime.date, datetime.timedelta, datetime.time)):
        return repr(value)
    if isinstance(value, enum.Enum):
        return f"{type(value).__name__}.{value.name}"
    if isinstance(value, types.ModuleType):
        return f"the module {value.__name__}"
    if inspect.isclass(value):
        if issubclass(value, models.Model) and hasattr(value, "_meta"):
            return model_said(value)
        return value.__name__
    if isinstance(value, types.MethodType):
        return f"the method {short(value.__qualname__)} of {brief(value.__self__)}"
    if isinstance(value, (types.FunctionType, types.BuiltinFunctionType)):
        return f"the function {short(value.__qualname__)}"
    if isinstance(value, functools.partial):
        return f"a partial of {brief(value.func)}"
    if isinstance(value, Whole):
        return "[" + ", ".join(brief(v) for v in value) + "]"
    if isinstance(value, tuple) and hasattr(value, "_fields"):
        return f"{type(value).__name__}(" + ", ".join(f"{name}={brief(item)}" for name, item in zip(value._fields, value)) + ")"
    if isinstance(value, list):
        return "[" + ", ".join(several(value)) + "]"
    if isinstance(value, tuple):
        return "(" + ", ".join(several(value)) + ("," if len(value) == 1 else "") + ")"
    if isinstance(value, (set, frozenset)):
        return "{" + ", ".join(sorted(brief(v) for v in value)) + "}" if value else "set()"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{brief(k) if isinstance(k, tuple) else repr(k)}: {brief(v)}" for k, v in value.items()) + "}"
    if isinstance(value, (str, bytes, int, float, bool, type(None), decimal.Decimal)):
        return repr(value)
    return a(type(value).__name__)


def answer(value) -> str:
    """The answer to a question, as brief puts it, but for a class that is not a model, which is written with its module."""
    from django.db import models

    if inspect.isclass(value) and not (issubclass(value, models.Model) and hasattr(value, "_meta")):
        return f"{value.__module__}.{value.__qualname__}"
    return brief(value)


SIGNAL_NAMES = {}


def several(values) -> list:
    if len(values) > 6:
        return [brief(values[0]), brief(values[1]), f"and {len(values) - 2} more"]
    return [brief(v) for v in values]


def whole(value) -> Said:
    """A list, a tuple, a set or a dict put into words as brief puts each thing, but not shortened: every item is written."""
    if isinstance(value, dict):
        return Said("{" + ", ".join(f"{brief(k) if isinstance(k, tuple) else repr(k)}: {whole(v)}" for k, v in value.items()) + "}")
    if isinstance(value, (set, frozenset)):
        return Said("{" + ", ".join(sorted(str(whole(v)) for v in value)) + "}" if value else "set()")
    if isinstance(value, list):
        return Said("[" + ", ".join(str(whole(v)) for v in value) + "]")
    if isinstance(value, tuple) and not (value and all(isinstance(v, (str, type(None))) for v in value)):
        return Said("(" + ", ".join(str(whole(v)) for v in value) + ("," if len(value) == 1 else "") + ")")
    return Said(brief(value))


def name_it(thing, name: str) -> None:
    """Give a thing a name by which every later line writes it."""
    NAMED[id(thing)] = (weakref.ref(thing), name)


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
    """The connection a method of a connection, or of an object that holds one, ran on, where it is not "default"."""
    from django.db.backends.base.base import BaseDatabaseWrapper

    owner = frame.f_locals.get("self")
    if not isinstance(owner, BaseDatabaseWrapper):
        owner = getattr(owner, "connection", None)
    if isinstance(owner, BaseDatabaseWrapper) and owner.alias != "default":
        return f'  (on "{owner.alias}")'
    return ""


def called(frame) -> str:
    """The name a call is written by: the class that declares the method and the method; where
    the object is of a subclass, the object's class and the method, and then in parentheses the
    class whose method ran. A command's class is written with its module, `migrate.Command`."""
    name = short(frame.f_code.co_qualname)
    module = frame.f_globals.get("__name__", "")
    if module.startswith("django.core.management.commands."):
        return f"{module.rsplit('.', 1)[-1]}.{name}"
    owner = frame.f_locals.get("self", frame.f_locals.get("cls"))
    if owner is not None and "." in name:
        made = (owner if inspect.isclass(owner) else type(owner)).__name__
        declared, method = name.rsplit(".", 1)
        if made != declared and declared in {klass.__name__ for klass in (owner if inspect.isclass(owner) else type(owner)).__mro__}:
            return f"{made}.{method}  ({declared}.{method})"
    return name


def with_arguments(name: str, said: str) -> str:
    """`Class.method(arguments)`, and where the name carries the declaring class in parentheses, the arguments before it."""
    if "  (" in name:
        head, tail = name.split("  (", 1)
        return f"{head}({said})  ({tail}" if said else name
    return f"{name}({said})" if said else name


def generic(frame) -> str:
    return with_arguments(called(frame), given(frame)) + on(frame)


def without(*leave_out):
    def said(frame) -> str:
        return with_arguments(called(frame), given(frame, *leave_out)) + on(frame)
    return said


def bare(frame) -> str:
    """A call by its name alone, and the connection where it is not "default"."""
    return called(frame) + on(frame)


def only(*names):
    """A call by its name and the named arguments alone, each by its value."""
    def said(frame) -> str:
        return with_arguments(called(frame), ", ".join(brief(frame.f_locals[name]) for name in names)) + on(frame)
    return said


def briefly(label):
    """The same label, for a call written as one line with nothing under it."""
    def said(frame):
        text = label(frame)
        return None if text is None else Briefly(text)
    return said


def watch(module: str, *qualnames, label=None) -> dict:
    return {(module, name): label or generic for name in qualnames}


def value_after(frame, value) -> str:
    return brief(value)


def says(module: str, *qualnames, how=value_after) -> dict:
    return {(module, name): how for name in qualnames}


def making_a_state(frame) -> bool:
    """Whether an operation's state half is being run by Migration.mutate_state, as it is for
    every migration each time a project state is made: those calls are not written."""
    return frame.f_back is not None and frame.f_back.f_code.co_qualname == "Migration.mutate_state"


def operation_call(frame) -> str | None:
    """A method of an operation: the operation's class and the method (with the declaring class
    in parentheses where it is another), and what the operation's describe() says."""
    if making_a_state(frame):
        return None
    return f"{called(frame)}  [{frame.f_locals['self'].describe()}]"


def operation_rules(*methods) -> dict:
    """Rules for the named methods of every operation class Django ships, and of the classes they are built on."""
    from django.db.migrations import operations
    from django.db.migrations.operations.base import Operation

    rules = {}
    for exported in operations.__all__:
        for klass in getattr(operations, exported).__mro__:
            if klass is object or not issubclass(klass, Operation):
                continue
            for method in methods:
                if method in vars(klass):
                    rules[(klass.__module__, f"{klass.__qualname__}.{method}")] = operation_call
    return rules


M = "django.db.migrations"
MM = "django.db.migrations.migration"
MS = "django.db.migrations.state"
ML = "django.db.migrations.loader"
MG = "django.db.migrations.graph"
MR = "django.db.migrations.recorder"
MX = "django.db.migrations.executor"
MA = "django.db.migrations.autodetector"
MQ = "django.db.migrations.questioner"
MO = "django.db.migrations.optimizer"
MW = "django.db.migrations.writer"
OB = "django.db.migrations.operations.base"
OS = "django.db.migrations.operations.special"
CMD = "django.core.management.commands."
BS = "django.db.backends.base.schema"
S3S = "django.db.backends.sqlite3.schema"
B = "django.db.backends.base.base"
TX = "django.db.transaction"
DSP = "django.dispatch.dispatcher"
REG = "django.apps.registry"
DBU = "django.db.utils"
OPT = "django.db.models.options"


# ---------------------------------------------------------------------------------------------
# The run's directory: the copy of harbour, the application yard, the settings and manage.py.

SETTINGS = '''\
"""The settings of the project the recording of chapter 12 runs: harbour, and the application yard."""
from pathlib import Path

HERE = Path(__file__).parent
SECRET_KEY = "recording"
DEBUG = False
INSTALLED_APPS = ["harbour.fleet", "harbour.crew", "harbour.office", "harbour.yard"]
DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": HERE / "harbour.sqlite3"},
    "archive": {"ENGINE": "django.db.backends.sqlite3", "NAME": HERE / "archive.sqlite3"},
}
DATABASE_ROUTERS = []
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
'''

MANAGE = '''\
"""The project's command line, as startproject writes it, shortened."""
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
'''

YARD_1 = '''\
from django.db import models


class Dock(models.Model):
    """A dry dock of the repair yard, in one of the fleet's ports."""

    name = models.CharField(max_length=40)
    port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)


class Repair(models.Model):
    """A ship in a dock, under repair."""

    ship = models.ForeignKey("fleet.Ship", on_delete=models.CASCADE)
    dock = models.ForeignKey(Dock, on_delete=models.PROTECT)
    started = models.DateField()
    notes = models.TextField(blank=True)
'''



def changed(text: str, old: str, new: str) -> str:
    """A text with one passage of it replaced: the next version of a file."""
    if text.count(old) != 1:
        raise SystemExit(f"recordings/migrations.py: {old!r} is not once in the text it was to be replaced in")
    return text.replace(old, new)


YARD_2 = changed(changed(changed(changed(
    YARD_1,
    "    name = models.CharField(max_length=40)\n", "    name = models.CharField(max_length=80)\n"),
    '    port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)\n',
    '    port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)\n    metres = models.PositiveSmallIntegerField(default=120)\n'),
    "    started = models.DateField()\n", "    begun = models.DateField()\n"),
    "    notes = models.TextField(blank=True)\n",
    '    notes = models.TextField(blank=True)\n\n    class Meta:\n        indexes = [models.Index(fields=["dock", "begun"], name="repair_by_dock")]\n',
)
YARD_3 = changed(YARD_2, "    notes = models.TextField(blank=True)\n", "    notes = models.TextField(blank=True)\n    foreman = models.CharField(max_length=60)\n")
YARD_3_UPDATED = changed(YARD_3, "    foreman = models.CharField(max_length=60)\n", "    foreman = models.CharField(max_length=80)\n")
YARD_4 = changed(
    YARD_3, '        indexes = [models.Index(fields=["dock", "begun"], name="repair_by_dock")]\n',
    '        indexes = [\n            models.Index(fields=["dock", "begun"], name="repair_by_dock"),\n            models.Index(fields=["foreman"], name="repair_by_foreman"),\n        ]\n',
)
YARD_5 = changed(
    YARD_4, "    metres = models.PositiveSmallIntegerField(default=120)\n",
    "    metres = models.PositiveSmallIntegerField(default=120)\n    covered = models.BooleanField(default=False)\n",
)
YARD_6 = changed(changed(
    YARD_5, "from django.db import models\n", "from django.conf import settings\nfrom django.db import models\n"),
    "    foreman = models.CharField(max_length=60)\n",
    "    foreman = models.CharField(max_length=60)\n    inspector = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)\n",
)

CRANE = '''\
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("yard", "0001_initial")]

    operations = [
        migrations.CreateModel("Crane", [("id", models.BigAutoField(primary_key=True))]),
        migrations.AddField("crane", "tonnes", models.PositiveSmallIntegerField(default=5)),
        migrations.AlterField("crane", "tonnes", models.PositiveIntegerField(default=5)),
    ]
'''

DATA_FUNCTIONS = '''\
def name_foremen(apps, schema_editor):
    """Every repair whose foreman was not recorded is put down to the yard's master."""
    Repair = apps.get_model("yard", "Repair")
    Repair.objects.using(schema_editor.connection.alias).filter(foreman="not recorded").update(foreman="Yard master")


def forget_foremen(apps, schema_editor):
    Repair = apps.get_model("yard", "Repair")
    Repair.objects.using(schema_editor.connection.alias).filter(foreman="Yard master").update(foreman="not recorded")


'''

DATA_OPERATIONS = '''\
    operations = [
        migrations.RunPython(name_foremen, reverse_code=forget_foremen),
        migrations.RunSQL(
            sql="UPDATE yard_repair SET notes = 'No notes were kept.' WHERE notes = ''",
            reverse_sql="UPDATE yard_repair SET notes = '' WHERE notes = 'No notes were kept.'",
        ),
    ]
'''

SEPARATE = '''\
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("yard", "0004_name_the_foremen")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='CREATE INDEX "repair_by_foreman" ON "yard_repair" ("foreman")',
                    reverse_sql='DROP INDEX "repair_by_foreman"',
                ),
            ],
            state_operations=[
                migrations.AddIndex("repair", models.Index(fields=["foreman"], name="repair_by_foreman")),
            ],
        ),
    ]
'''

COLLEAGUE = '''\
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("yard", "0005_repair_by_foreman")]

    operations = [
        migrations.RunSQL(
            sql="UPDATE yard_dock SET metres = 180 WHERE name = 'North dock'",
            reverse_sql="UPDATE yard_dock SET metres = 120 WHERE name = 'North dock'",
        ),
    ]
'''

SETTINGS_YARD_UNMIGRATED = '''\
"""The settings, with yard made an unmigrated application, and a database file of their own."""
from settings import *  # noqa: F403

MIGRATION_MODULES = {"yard": None}
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": HERE / "unmigrated.sqlite3"}}
'''

SETTINGS_THREE = '''\
"""The settings, with two more databases: one that is empty, and one that is a copy of
"default" made before the migrations of yard were squashed and then migrated back."""
from settings import *  # noqa: F403

DATABASES = {
    **DATABASES,
    "fresh": {"ENGINE": "django.db.backends.sqlite3", "NAME": HERE / "fresh.sqlite3"},
    "halfway": {"ENGINE": "django.db.backends.sqlite3", "NAME": HERE / "halfway.sqlite3"},
}
'''

SETTINGS_ROUTED = '''\
"""The settings, with the router of harbour, and two database files of their own."""
from settings import *  # noqa: F403

DATABASE_ROUTERS = ["harbour.routers.LogbookRouter"]
DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": HERE / "routed.sqlite3"},
    "archive": {"ENGINE": "django.db.backends.sqlite3", "NAME": HERE / "routed_archive.sqlite3"},
}
'''

SETTINGS_AUTH = '''\
"""The settings, with two of Django's own applications installed before the project's."""
from settings import *  # noqa: F403

INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", *INSTALLED_APPS]
'''

APPLICATIONS = ("fleet", "crew", "office", "yard")


def models_shown(old: str, new: str) -> None:
    """A version of yard's models beside the one before it: every line of the new file, those
    put in marked `+`, and the lines taken out, marked `-`, where they stood."""
    for line in difflib.ndiff(old.splitlines(), new.splitlines()):
        if not line.startswith("?"):
            note(("| " + line).rstrip())


def path_of(relative: str) -> str:
    """A path of the run's directory, from its name written with forward slashes."""
    return os.path.join(SCRATCH, *relative.split("/"))


def write(relative: str, text: str) -> None:
    os.makedirs(os.path.dirname(path_of(relative)), exist_ok=True)
    with open(path_of(relative), "w", encoding="utf-8", newline="\n") as file:
        file.write(text)


def read(relative: str) -> str:
    with open(path_of(relative), encoding="utf-8") as file:
        return file.read()


def make_project() -> None:
    """The copy of harbour, the application yard with no models yet, the settings and manage.py."""
    shutil.copytree(os.path.join(HERE, "harbour"), path_of("harbour"), ignore=shutil.ignore_patterns("__pycache__"))
    write("harbour/yard/__init__.py", "")
    write("settings.py", SETTINGS)
    write("manage.py", MANAGE)


def migration_files(application: str | None = None) -> list:
    """The migration files there are, as paths from the run's directory, sorted: those of one application, or of all."""
    found = []
    for label in ([application] if application else APPLICATIONS):
        directory = path_of(f"harbour/{label}/migrations")
        if os.path.isdir(directory):
            found += [f"harbour/{label}/migrations/{name}" for name in sorted(os.listdir(directory)) if name.endswith(".py") and name != "__init__.py"]
    return found


def database_files() -> list:
    """The names of the files of the run's directory that end .sqlite3, sorted."""
    return sorted(name for name in os.listdir(SCRATCH) if name.endswith(".sqlite3"))


def file_shown(relative: str, until: str | None = None) -> None:
    """A file of the run's directory, as it stands: every line, or the lines as far as the first that begins with `until`."""
    for line in read(relative).splitlines():
        if until is not None and line.startswith(until):
            note("| ...")
            break
        note(("| " + line).rstrip())


def fingerprint() -> dict:
    """What the run's directory holds, so that a part which is to leave the project as it found
    it can be held to that: every file of the project by a digest of its text (the time in a
    migration file's first line left out), and every database file by its tables, its indexes,
    the rows of django_migrations (id, application and name; not the time, since one part makes
    the database again and says so) and the number of rows of each other table."""
    found = {}
    for directory, folders, names in os.walk(SCRATCH):
        folders[:] = sorted(f for f in folders if f != "__pycache__")
        for name in sorted(names):
            path = os.path.join(directory, name)
            relative = os.path.relpath(path, SCRATCH).replace("\\", "/")
            if name.endswith((".sqlite3-journal", ".sqlite3-wal", ".sqlite3-shm")):
                continue
            if name.endswith(".sqlite3"):
                database = sqlite3.dbapi2.connect(path)
                try:
                    tables = database.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall()
                    found[relative] = {"schema": tables}
                    for kind, table, _ in tables:
                        if kind == "table" and table != "sqlite_sequence":
                            found[relative][table] = (
                                database.execute("SELECT id, app, name FROM django_migrations ORDER BY id").fetchall() if table == "django_migrations"
                                else database.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                            )
                finally:
                    database.close()
            else:
                with open(path, encoding="utf-8") as file:
                    text = re.sub(r"(# Generated by Django \S+ on )\S+ \S+", r"\1...", file.read())
                found[relative] = hashlib.sha256(text.encode()).hexdigest()
    return found


def differences(before: dict, after: dict) -> list:
    return [f"{name}: {before.get(name)!r} became {after.get(name)!r}" for name in sorted({*before, *after}) if before.get(name) != after.get(name)]


def environment(**extra) -> dict:
    """This process's environment without what would change a command's behaviour or what it
    prints (Python colours a traceback and argparse its usage where FORCE_COLOR or PYTHON_COLORS
    says so, pipe or no pipe), and with `extra`."""
    dropped = {
        "DJANGO_SETTINGS_MODULE", "DJANGO_COLORS", "PYTHONPATH", "PYTHONSTARTUP", "COLUMNS", "LINES", "PYTHONHASHSEED", "TZ",
        "FORCE_COLOR", "PYTHON_COLORS", "NO_COLOR", "CLICOLOR", "CLICOLOR_FORCE", "PYTHONWARNINGS", "PYTHONDEVMODE", "PYTHONVERBOSE",
        "PYTHONOPTIMIZE", "PYTHONDEBUG", "PYTHONINSPECT", "PYTHONTRACEMALLOC", "PYTHONPROFILEIMPORTTIME", "PYTHONUTF8",
    }
    kept = {key: value for key, value in os.environ.items() if key not in dropped}
    return {**kept, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1", **extra}


class Collected(threading.Thread):
    """Everything a process writes to one of its streams, gathered as it comes."""

    def __init__(self, stream):
        super().__init__(daemon=True)
        self.stream = stream
        self.text = b""
        self.taken = 0
        self.ended = False
        self.changed = threading.Condition()
        self.start()

    def run(self) -> None:
        while True:
            more = os.read(self.stream.fileno(), 65536)
            with self.changed:
                if not more:
                    self.ended = True
                else:
                    self.text += more
                self.changed.notify_all()
            if not more:
                return

    def take(self) -> str:
        """What has been written since the last call."""
        with self.changed:
            text, self.taken = self.text[self.taken:], len(self.text)
        return text.decode("utf-8").replace("\r\n", "\n")

    def wait_for_prompt(self) -> None:
        """Wait until the process has written a prompt and is reading its standard input."""
        with self.changed:
            while not self.text[self.taken:].endswith(PROMPT_ENDS):
                if self.ended:
                    raise SystemExit(f"recordings/migrations.py: a command ended before it asked what it was expected to ask: {self.text!r}")
                if not self.changed.wait(120):
                    raise SystemExit(f"recordings/migrations.py: a command wrote no prompt in two minutes: {self.text!r}")


# The ends of the questioner's prompts and of squashmigrations': after writing one, the process reads a line of its standard input.
PROMPT_ENDS = (b"[y/N] ", b"Select an option: ", b">>> ", b"yes or no: ", b"valid option: ")


def manage(arguments: str, answers: tuple = (), prompts: str = "stdout", traceback_tail: bool = True, squeeze: tuple = ()) -> int:
    """Run one command line in the run's directory and write down what it printed, and its exit
    status where that is not 0. The answers are typed in one at a time, each when the process
    has written a prompt and waits: a line `stdin` stands where each was given. Of a run of
    lines that begin with one of the texts in `squeeze`, the first two are written and the rest counted."""
    SQUEEZED[:] = squeeze
    note(f"python manage.py {arguments}")
    process = subprocess.Popen(
        [sys.executable, "manage.py", *arguments.split()], cwd=SCRATCH, env=environment(),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    streams = {"stdout": Collected(process.stdout), "stderr": Collected(process.stderr)}
    for reply in answers:
        streams[prompts].wait_for_prompt()
        printed(prompts, streams[prompts].take())
        process.stdin.write((reply + "\n").encode())
        process.stdin.flush()
        note(f"  stdin  | {reply}")
    process.stdin.close()
    process.wait()
    for stream in streams.values():
        stream.join()
    other = "stderr" if prompts == "stdout" else "stdout"
    printed(prompts, streams[prompts].take())
    text = streams[other].take()
    if traceback_tail and other == "stderr" and text.startswith("Traceback"):
        note("  stderr | Traceback (most recent call last):")
        note("  stderr |   (the frames)")
        text = text.strip().splitlines()[-1]
    printed(other, text)
    if process.returncode:
        note(f"  exit status {process.returncode}")
    return process.returncode


def printed(stream: str, text: str) -> None:
    """What a process wrote to a stream, a line to a line."""
    if not text:
        return
    run, kind = 0, None
    for line in [*text.split("\n")[: None if not text.endswith("\n") else -1], None]:
        found = None if line is None else next((start for start in SQUEEZED if line.lstrip().startswith(start)), None)
        if found != kind or found is None:
            if run > 2:
                note(f"  {stream} | ... ({run - 2} more lines that begin {kind!r}, not written)")
            run, kind = 0, found
        if line is None:
            break
        run += 1
        if found is None or run <= 2:
            note(f"  {stream} | {line}".rstrip())


SQUEEZED = []  # the beginnings of the lines that `manage` is to write two of and count the rest


def run_part(name: str, moves: bool = False) -> None:
    """Run a part of the recording in an interpreter of its own, and print what it printed. A
    part that is not a step of yard's story has to leave the run's directory as it found it."""
    sys.stdout.flush()
    before = None if moves else fingerprint()
    done = subprocess.run([sys.executable, os.path.abspath(__file__), name], cwd=SCRATCH, env=environment(), capture_output=True, encoding="utf-8")
    if done.returncode:
        sys.exit(f"recordings/migrations.py: the part {name!r} failed:\n{done.stdout[-3000:]}\n{done.stderr}")
    if done.stderr.strip():
        sys.stderr.write(done.stderr)
    sys.stdout.write(done.stdout)
    sys.stdout.flush()
    if before is not None:
        changed = differences(before, fingerprint())
        if changed:
            sys.exit(f"recordings/migrations.py: the part {name!r} did not leave the run's directory as it found it:\n" + "\n".join(changed))


class unchanged:
    """`with unchanged("what"):` holds what runs in the block to leaving the run's directory as it found it."""

    def __init__(self, what: str):
        self.what = what

    def __enter__(self):
        self.before = fingerprint()

    def __exit__(self, kind, value, trace):
        if kind is None:
            changed = differences(self.before, fingerprint())
            if changed:
                sys.exit(f"recordings/migrations.py: {self.what} did not leave the run's directory as it found it:\n" + "\n".join(changed))


class aside:
    """`with aside("fleet", "yard"):` moves the named applications' migrations directories out of
    the run's directory for the block, and puts them back as it ends."""

    def __init__(self, *applications):
        self.applications = applications

    def __enter__(self):
        self.held = tempfile.mkdtemp()
        for application in self.applications:
            shutil.move(path_of(f"harbour/{application}/migrations"), os.path.join(self.held, application))

    def __exit__(self, kind, value, trace):
        for application in self.applications:
            shutil.move(os.path.join(self.held, application), path_of(f"harbour/{application}/migrations"))
        os.rmdir(self.held)


def set_up(settings_module: str = "settings") -> None:
    """What every part that runs Django in its own process begins with: the run's directory is
    the working directory and first on the path, the settings are the named module, Django is
    set up with nothing recorded, and the script's execute wrapper goes on each connection as
    Django makes it."""
    os.chdir(SCRATCH)
    sys.path.insert(0, SCRATCH)
    os.environ["DJANGO_SETTINGS_MODULE"] = settings_module
    django.setup()

    import harbour
    from django.apps import apps
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connection, connections, migrations, models, router
    from django.db.migrations.autodetector import MigrationAutodetector
    from django.db.migrations.executor import MigrationExecutor
    from django.db.migrations.graph import MigrationGraph
    from django.db.migrations.loader import MigrationLoader
    from django.db.migrations.optimizer import MigrationOptimizer
    from django.db.migrations.questioner import InteractiveMigrationQuestioner, MigrationQuestioner, NonInteractiveMigrationQuestioner
    from django.db.migrations.recorder import MigrationRecorder
    from django.db.migrations.state import ModelState, ProjectState, StateApps
    from django.db.migrations.writer import MigrationWriter, OperationWriter
    from django.db.models.signals import post_migrate, pre_migrate

    if not os.path.realpath(harbour.__file__).startswith(SCRATCH + os.sep):
        raise SystemExit(f"recordings/migrations.py: harbour was imported from {harbour.__file__}, not from the run's directory")

    for made in connections.all(initialized_only=True):
        listen(made)
    create_connection = connections.create_connection

    def listening_connection(alias):
        """`connections`' create_connection, with the script's execute wrapper put on each connection as Django makes it."""
        made = create_connection(alias)
        listen(made)
        return made

    connections.create_connection = listening_connection

    render = StateApps.__init__

    @functools.wraps(render)
    def guarded(self, *args, **kwargs):
        """StateApps.__init__, which the script stops at if a call is being put into words: a
        label that read a state's registry would have made it."""
        if LABELLING:
            stop("putting a call into words made a state's registry")
        return render(self, *args, **kwargs)

    StateApps.__init__ = guarded

    SIGNAL_NAMES.update({id(pre_migrate): "pre_migrate", id(post_migrate): "post_migrate"})
    ASKING.update(
        apps=apps, settings=settings, call_command=call_command, connection=connection, connections=connections, migrations=migrations,
        models=models, router=router, MigrationAutodetector=MigrationAutodetector, MigrationExecutor=MigrationExecutor,
        MigrationGraph=MigrationGraph, MigrationLoader=MigrationLoader, MigrationOptimizer=MigrationOptimizer,
        InteractiveMigrationQuestioner=InteractiveMigrationQuestioner, MigrationQuestioner=MigrationQuestioner,
        NonInteractiveMigrationQuestioner=NonInteractiveMigrationQuestioner, MigrationRecorder=MigrationRecorder, ModelState=ModelState,
        ProjectState=ProjectState, StateApps=StateApps, MigrationWriter=MigrationWriter, OperationWriter=OperationWriter,
        pre_migrate=pre_migrate, post_migrate=post_migrate, full=full, whole=whole, out=Printed(), os=os, sys=sys,
        datetime=datetime, importlib=importlib, columns=columns, tables=tables, indexes=indexes, table_sql=table_sql, recorded_rows=recorded_rows,
        migration_files=migration_files, rows=rows,
    )
    for application in apps.get_app_configs():
        if application.name.startswith("harbour."):
            ASKING.update({model.__name__: model for model in application.get_models()})


def close_connections() -> None:
    from django.db import connections

    for made in connections.all(initialized_only=True):
        made.close()


PARTS = {}


def part(name: str):
    """A part of the recording that runs in an interpreter of its own: `python recordings/migrations.py <name>`."""
    def register(function):
        PARTS[name] = function
        return function
    return register


# ---------------------------------------------------------------------------------------------
# THE PARTS


def signal_sent(frame) -> str | None:
    """Signal.send, by the signal's name, as an object's class is written before the class whose
    method ran, and its sender; the keyword arguments it sends are not written. A signal the
    chapter does not name (class_prepared) is not written at all."""
    signal = frame.f_locals["self"]
    if id(signal) not in SIGNAL_NAMES:
        return None
    return f"{SIGNAL_NAMES[id(signal)]}.send(sender={brief(frame.f_locals.get('sender'))})  (Signal.send)"


def registry_made(frame) -> str | None:
    """StateApps.__init__, by how many model states it is given to render. The empty registry
    that StateApps.clone makes, to fill with copies of another's models, is not written."""
    caller = frame.f_back
    if caller is not None and caller.f_code.co_name == "guarded":
        caller = caller.f_back
    if caller is not None and caller.f_code.co_qualname == "StateApps.clone":
        return None
    count = len(frame.f_locals["models"])
    return f"StateApps.__init__(real_apps={brief(frame.f_locals['real_apps'])}, models=<{count} model state{'' if count == 1 else 's'}>)"


def registry_of(frame) -> str | None:
    """StateApps.__init__ as registry_made writes it, and in brackets the state whose registry
    it is, where the script has given that state a name: the state is the one whose `apps` is
    being read, two frames up."""
    text = registry_made(frame)
    caller = frame.f_back
    if caller is not None and caller.f_code.co_name == "guarded":
        caller = caller.f_back
    state = caller.f_locals.get("self") if caller is not None and caller.f_code.co_name == "apps" else None
    if text is not None and state is not None and id(state) in NAMED and NAMED[id(state)][0]() is state:
        text += f"  [the registry of {NAMED[id(state)][1]}]"
    return text


def applied_to_state(frame) -> str:
    """Migration.apply, whose state every later line of the block writes `state`."""
    name_it(frame.f_locals["project_state"], "state")
    return of_migration(frame)


def model_got(frame) -> str | None:
    """Apps.get_model, where an operation, the executor or the script asks a registry for a
    model; the lookups a registry makes of itself while its models are rendered are not written."""
    caller = frame.f_back.f_globals.get("__name__", "") if frame.f_back is not None else ""
    if caller == MS or not (caller.startswith(M) or caller.startswith("harbour.") or caller == "__main__"):
        return None
    return generic(frame)


def columns(table: str, alias: str = "default") -> list:
    """The names of a table's columns, in the table's order: read from SQLite by the script
    itself, on the driver's connection and past Django's cursor, so that no `SQL` line stands under the question."""
    from django.db import connections

    connections[alias].ensure_connection()
    return [row[1] for row in connections[alias].connection.execute(f'PRAGMA table_info("{table}")').fetchall()]


class Whole(list):
    """A list that an answer writes whole, however long it is."""


def tables(alias: str = "default") -> Whole:
    """The names of the database's tables, sorted: read by the script itself, as `columns` reads."""
    from django.db import connections

    connections[alias].ensure_connection()
    return Whole(sorted(row[0] for row in connections[alias].connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name != 'sqlite_sequence'").fetchall()))


def indexes(table: str, alias: str = "default") -> Whole:
    """The names of a table's indexes that a CREATE INDEX made, sorted: read by the script itself, as `columns` reads."""
    from django.db import connections

    connections[alias].ensure_connection()
    return Whole(sorted(row[0] for row in connections[alias].connection.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL", [table]).fetchall()))


def table_sql(table: str, alias: str = "default") -> Said:
    """The CREATE TABLE statement SQLite keeps for a table: read by the script itself, as `columns` reads."""
    from django.db import connections

    connections[alias].ensure_connection()
    found = connections[alias].connection.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", [table]).fetchone()
    return Said(found[0] if found else "None")


def recorded_rows(alias: str = "default", application: str | None = None) -> Said:
    """The rows of django_migrations, each as its application and name, in the order they were
    written (by id); those of one application, or all: read by the script itself, as `columns` reads."""
    from django.db import connections

    connections[alias].ensure_connection()
    if not connections[alias].connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'django_migrations'").fetchone():
        return Said("no table django_migrations")
    rows = connections[alias].connection.execute("SELECT app, name FROM django_migrations ORDER BY id").fetchall()
    return full([f"{app}.{name}" for app, name in rows if application in (None, app)])


def rows(table: str, *names, alias: str = "default") -> Whole:
    """The rows of a table, in the order of its first column, each as the named columns: read
    by the script itself, as `columns` reads."""
    from django.db import connections

    connections[alias].ensure_connection()
    return Whole(connections[alias].connection.execute(f'SELECT {", ".join(names)} FROM "{table}" ORDER BY 1').fetchall())


def handled(*options):
    """A command's handle: its positional arguments, and of its options the named ones."""
    def said(frame) -> str:
        info = inspect.getargvalues(frame)
        given_ = [repr(value) for value in frame.f_locals[info.varargs]] if info.varargs else []
        given_ += [f"{name}={frame.f_locals[info.keywords][name]!r}" for name in options]
        return f"{called(frame)}({', '.join(given_)})"
    return said


def of_migration(frame) -> str:
    """A method of a migration: its arguments, and the migration in brackets."""
    return f"{generic(frame)}  [{frame.f_locals['self']}]"


def writer_called(frame) -> str:
    return f"{called(frame)}  [{frame.f_locals['self'].migration}]"


def plan_said(plan) -> str:
    return "[]" if not plan else f"a plan of {len(plan)}"


def a_plan(frame, value) -> str:
    return str(whole(value))


def a_plan_or_the_full(frame, value) -> str:
    """The plan migration_plan returns, whole; but the full plan, which it returns when asked with clean_start=True, by its length."""
    return f"the full plan, of {len(value)}" if frame.f_locals["clean_start"] else str(whole(value))


def command_begins() -> dict:
    """Rules for the two things every migrate begins with, each written as one line."""
    return {(MX, "MigrationExecutor.__init__"): briefly(without("progress_callback")), (ML, "MigrationLoader.check_consistent_history"): briefly(generic)}


def executor_frames() -> dict:
    """Rules for what executor.migrate does before and after its plan, each written as one line."""
    return {(MR, "MigrationRecorder.ensure_schema"): briefly(bare), (MX, "MigrationExecutor.check_replacements"): briefly(bare)}


EDITOR_ENTERED = watch(S3S, "DatabaseSchemaEditor.__enter__", "DatabaseSchemaEditor.__exit__", label=bare) | watch(
    BS, "BaseDatabaseSchemaEditor.__enter__", "BaseDatabaseSchemaEditor.__exit__", label=bare,
) | watch(B, "BaseDatabaseWrapper.commit", label=bare)


@part("makemigrations-calls")
def makemigrations_calls() -> None:
    """Block 3: the first makemigrations run again in this process, with its calls written down."""
    set_up()
    for application in APPLICATIONS:
        shutil.rmtree(path_of(f"harbour/{application}/migrations"))
    importlib.invalidate_caches()
    step("the script has removed the four migrations directories that the second command line of the block before made: no application has a migrations directory, and the database file is the empty one the first command line left")
    making = {
        (CMD + "makemigrations", "Command.handle"): handled(),
        (CMD + "makemigrations", "Command.write_migration_files"): generic,
        (ML, "MigrationLoader.__init__"): generic,
        (ML, "MigrationLoader.build_graph"): bare,
        (ML, "MigrationLoader.check_consistent_history"): generic,
        (ML, "MigrationLoader.detect_conflicts"): bare,
        (ML, "MigrationLoader.project_state"): generic,
        (MS, "ProjectState.from_apps"): generic,
        (MQ, "InteractiveMigrationQuestioner.__init__"): without("prompt_output"),
        (MQ, "MigrationQuestioner.ask_initial"): generic,
        (MA, "MigrationAutodetector.__init__"): generic,
        (MA, "MigrationAutodetector.changes"): generic,
        (MA, "MigrationAutodetector._detect_changes"): generic,
        (MA, "MigrationAutodetector.arrange_for_graph"): without("changes"),
        (MA, "MigrationAutodetector._trim_to_apps"): without("changes"),
        (MW, "MigrationWriter.as_string"): writer_called,
    }
    after = says(ML, "MigrationLoader.detect_conflicts", "MigrationLoader.project_state") | says(MS, "ProjectState.from_apps") | says(
        MQ, "MigrationQuestioner.ask_initial",
    ) | says(MA, "MigrationAutodetector._detect_changes", "MigrationAutodetector.arrange_for_graph", "MigrationAutodetector._trim_to_apps", how=lambda f, v: str(whole(v)))
    with recorded(making, after=after):
        do("call_command('makemigrations', 'fleet', 'crew', 'office', 'yard', stdout=out)")
    ASKING.update(migration_files=migration_files)
    ask("full(migration_files())")
    show("makemigrations, the calls: the same command run in this process by call_command (which, unlike the command line, has a command skip its system checks), with the applications named as before; it writes the same five files again, each with the text it had, which the script compares")


@part("migrate-calls")
def migrate_calls() -> None:
    """Blocks 7 and 8: the first migrate run again in this process on an empty database, with its calls written down."""
    set_up()
    os.remove(path_of("harbour.sqlite3"))
    step("the script has removed the database file harbour.sqlite3 that the command line of the block before filled: SQLite makes it again, empty, when the connection opens")

    def applying(frame) -> str:
        """The apply_migration of yard's migration is written in full, each of the others as one line."""
        return generic(frame) if frame.f_locals["migration"].app_label == "yard" else Briefly(generic(frame))

    migrating = {
        (CMD + "migrate", "Command.handle"): handled(),
        (CMD + "migrate", "Command.migration_progress_callback"): generic,
        (B, "BaseDatabaseWrapper.prepare_database"): bare,
        (B, "BaseDatabaseWrapper.schema_editor"): generic,
        (MX, "MigrationExecutor.__init__"): generic,
        (ML, "MigrationLoader.__init__"): generic,
        (ML, "MigrationLoader.build_graph"): bare,
        (ML, "MigrationLoader.check_consistent_history"): generic,
        (ML, "MigrationLoader.detect_conflicts"): bare,
        (MX, "MigrationExecutor.migration_plan"): generic,
        (MX, "MigrationExecutor._create_project_state"): generic,
        (MS, "StateApps.__init__"): registry_made,
        (MS, "ProjectState.clear_delayed_apps_cache"): bare,
        ("django.core.management.sql", "emit_pre_migrate_signal"): bare,
        ("django.core.management.sql", "emit_post_migrate_signal"): bare,
        (DSP, "Signal.send"): signal_sent,
        (MX, "MigrationExecutor.migrate"): lambda f: f"MigrationExecutor.migrate(targets={brief(f.f_locals['targets'])}, plan={plan_said(f.f_locals['plan'])}, state={brief(f.f_locals['state'])}, fake={f.f_locals['fake']}, fake_initial={f.f_locals['fake_initial']})",
        (MR, "MigrationRecorder.ensure_schema"): bare,
        (MR, "MigrationRecorder.has_table"): bare,
        (MX, "MigrationExecutor._migrate_all_forwards"): lambda f: f"MigrationExecutor._migrate_all_forwards(state={brief(f.f_locals['state'])}, plan={plan_said(f.f_locals['plan'])}, full_plan={plan_said(f.f_locals['full_plan'])}, fake={f.f_locals['fake']}, fake_initial={f.f_locals['fake_initial']})",
        (MX, "MigrationExecutor.apply_migration"): applying,
        (MM, "Migration.apply"): of_migration,
        (MS, "ProjectState.add_model"): generic,
        (BS, "BaseDatabaseSchemaEditor.create_model"): generic,
        (MX, "MigrationExecutor.record_migration"): generic,
        (MR, "MigrationRecorder.record_applied"): generic,
        (MX, "MigrationExecutor.check_replacements"): bare,
    } | EDITOR_ENTERED | operation_rules("state_forwards", "database_forwards")
    after = says(ML, "MigrationLoader.detect_conflicts") | says(MX, "MigrationExecutor.migration_plan", how=a_plan) | says(
        MX, "MigrationExecutor._create_project_state", "MigrationExecutor.migrate", "MigrationExecutor._migrate_all_forwards", "MigrationExecutor.apply_migration",
    ) | says(MR, "MigrationRecorder.has_table") | says(MM, "Migration.apply")
    with recorded(migrating, after=after):
        do("call_command('migrate', stdout=out)")
    show("migrate, the calls: the same command run in this process by call_command (which, unlike the command line, has a command skip its system checks), on the database made empty again; the apply_migration of yard.0001_initial, the last of the five, is written in full, and each of the four before it on one line")

    for row in ASKING["MigrationRecorder"].Migration.objects.order_by("id"):
        note(f"django_migrations: id {row.id}, app {row.app!r}, name {row.name!r}, applied (the date and the time)")
    ask("tables()")
    show("What is in the database after the first migrate: the rows of django_migrations, in the order they were written, and the tables")
    close_connections()


# ---------------------------------------------------------------------------------------------
# A migration (blocks 9 to 14).


RENDERED_FIRST = "rendered here, before it is cloned, as the executor renders its state before it applies a migration"


def made(*operations, initial=None, **attributes):
    """A migration of the script's own, of the application yard, with these operations."""
    from django.db.migrations import Migration

    migration = Migration("made", "yard")
    migration.operations = list(operations)
    migration.initial = initial
    for name, value in attributes.items():
        setattr(migration, name, value)
    return migration


def numbering_clones(word: str = "clone", start: int = 1):
    """What to say of the state that ProjectState.clone returns: `clone N`, the name by which every later line writes it."""
    count = [start - 1]

    def said(frame, value) -> str | None:
        if value is None:
            return None
        count[0] += 1
        described = state_said(value)
        name_it(value, f"{word} {count[0]}")
        return f"{word} {count[0]}, {described}"
    return said


def operation_between(frame) -> str | None:
    """A method of an operation, with the state or the two states it was given."""
    if making_a_state(frame):
        return None
    said = ", ".join(f"{name}={brief(frame.f_locals[name])}" for name in ("state", "from_state", "to_state") if name in frame.f_locals)
    return f"{with_arguments(called(frame), said)}  [{frame.f_locals['self'].describe()}]"


def operation_rules_with_states(*methods) -> dict:
    return {key: operation_between for key in operation_rules(*methods)}


def editor_rules(*methods, label=None) -> dict:
    """Rules for the named methods of the schema editor, where the base class or SQLite's declares them."""
    rules = {}
    for module, name in ((BS, "BaseDatabaseSchemaEditor"), (S3S, "DatabaseSchemaEditor")):
        klass = getattr(sys.modules[module], name)
        for method in methods:
            if method in vars(klass):
                rules[(module, f"{name}.{method}")] = label or generic
    return rules


EDITOR_METHODS = (
    "create_model", "delete_model", "add_field", "remove_field", "alter_field", "alter_db_table", "alter_db_table_comment", "add_index", "remove_index",
    "rename_index", "add_constraint", "remove_constraint", "alter_unique_together", "alter_index_together", "_alter_many_to_many",
)


def atomic_entered(frame) -> str:
    block = frame.f_locals["self"]
    said = [f"using={block.using!r}"] if block.using not in (None, "default") else []
    said += ["savepoint=False"] if not block.savepoint else []
    said += ["durable=True"] if block.durable else []
    return "Atomic.__enter__" + (f"  (an Atomic made with {', '.join(said)})" if said else "")


def atomic_left(frame) -> str:
    kind = frame.f_locals["exc_type"]
    return "Atomic.__exit__" + (f"(exc_type={kind.__name__})" if kind else "")


ATOMIC = {(TX, "Atomic.__enter__"): atomic_entered, (TX, "Atomic.__exit__"): atomic_left}


def no_server(*args, **kwargs):
    """The guard on the connections that have no server: a question that would need one stops the script."""
    stop("a question needed a database server, and no server runs here")


def dialects():
    """Connections of PostgreSQL's, MySQL's and Oracle's backends, made by a ConnectionHandler of
    the script's own and never opened: each has the guard for its connect."""
    from django.db.utils import ConnectionHandler

    handler = ConnectionHandler({
        "default": {"ENGINE": "django.db.backends.dummy"},
        "postgresql": {"ENGINE": "django.db.backends.postgresql", "NAME": "harbour", "USER": "purser", "HOST": "db.harbour.example"},
        "mysql": {"ENGINE": "django.db.backends.mysql", "NAME": "harbour", "USER": "purser", "HOST": "db.harbour.example"},
        "oracle": {"ENGINE": "django.db.backends.oracle", "NAME": "harbour", "USER": "purser", "HOST": "db.harbour.example"},
    })
    for alias in ("postgresql", "mysql", "oracle"):
        handler[alias].connect = no_server
        handler[alias].ensure_connection = no_server
    return handler


@part("migration")
def a_migration() -> None:
    """Blocks 9 to 14: what a Migration instance holds and does."""
    set_up()
    ASKING.update(made=made)

    quietly("loader = MigrationLoader(None)")
    quietly("first = loader.disk_migrations['fleet', '0001_initial']")
    for question in (
        "type(first)", "type(first).__mro__[1]", "str(first)", "repr(first)", "first.name", "first.app_label", "first.dependencies", "first.run_before",
        "first.replaces", "first.initial", "first.atomic", "len(first.operations)", "first.operations[0]", "first.operations[-1]",
        "first.operations is type(first).operations", "first.operations == type(first).operations", "first.dependencies is type(first).dependencies",
        "first is loader.graph.nodes['fleet', '0001_initial']", "first == migrations.Migration('0001_initial', 'fleet')",
        "first == loader.disk_migrations['crew', '0001_initial']", "hash(first) == hash('fleet.0001_initial')",
    ):
        ask(question)
    quietly("second = loader.disk_migrations['crew', '0002_initial']")
    for question in ("second.dependencies", "second.initial", "whole(second.operations)"):
        ask(question)
    show("What a Migration instance holds: fleet.0001_initial as the loader made it from its file, and crew.0002_initial, the second migration the first makemigrations wrote for crew")

    given_state = "state = executor._create_project_state(with_applied_migrations=True)"
    with database_kept(span="this block and the two before it"):
        step("yard.0001_initial is applied; for this block and the two after it the script takes it out again with an executor of its own, which also deletes its row, and has that executor's loader read the rows again")
        quietly("executor = MigrationExecutor(connection)")
        silently("executor.migrate([('yard', None)])")
        silently("executor.loader.build_graph()")
        step("the migration; the project state the executor gives apply_migration for it, which is the state of the applied migrations, rendered before a migration is applied; and a schema editor, as MigrationExecutor.apply_migration makes one")
        quietly("migration = executor.loader.graph.nodes['yard', '0001_initial']")
        quietly(given_state)
        quietly("state.apps  # rendered here, as _migrate_all_forwards renders the state before it calls apply_migration")
        for question in ("len(state.models)", "'apps' in state.__dict__", "whole(migration.operations)", "migration.atomic", "connection.features.can_rollback_ddl"):
            ask(question)
        name_it(ASKING["state"], "state")
        quietly("schema_editor = connection.schema_editor(atomic=migration.atomic)")
        ask("schema_editor.atomic_migration")
        applying = {(MM, "Migration.apply"): of_migration, (MS, "ProjectState.clone"): bare} | operation_rules_with_states("state_forwards", "database_forwards") | ATOMIC | editor_rules(*EDITOR_METHODS) | EDITOR_ENTERED
        cloned = numbering_clones()
        with recorded(applying, after=says(MS, "ProjectState.clone", how=cloned) | says(MM, "Migration.apply")):
            do("schema_editor.__enter__()")
            do("returned = migration.apply(state, schema_editor)")
            do("schema_editor.__exit__(None, None, None)")
        ask("returned is state")
        ask("sorted(key for key in state.models if key[0] == 'yard')")
        step("nothing is undone here: yard's two tables are now in the database, made by hand, and yard.0001_initial has no row; the next block begins so")
        show("Migration.apply, one operation at a time: yard.0001_initial applied by hand, as apply_migration applies it, to the state the executor would give it; the state it is given is written `state`, and each state that ProjectState.clone returns `clone N`")

        step("this block begins as the one before ended: yard's two tables are in the database and yard.0001_initial has no row. The same migration is unapplied by hand, as MigrationExecutor.unapply_migration unapplies it, and given the state _migrate_all_backwards keeps for it: the state before the migration, rendered, which is again the state of the applied migrations")
        quietly(given_state)
        quietly("state.apps  # rendered here, as _migrate_all_backwards renders the state before it keeps it for unapply_migration")
        for question in ("len(state.models)", "'apps' in state.__dict__"):
            ask(question)
        name_it(ASKING["state"], "state")
        quietly("schema_editor = connection.schema_editor(atomic=migration.atomic)")
        unapplying = {(MM, "Migration.unapply"): of_migration, (MS, "ProjectState.clone"): bare} | operation_rules_with_states("state_forwards", "database_backwards") | ATOMIC | editor_rules(*EDITOR_METHODS) | EDITOR_ENTERED
        with recorded(unapplying, after=says(MS, "ProjectState.clone", how=cloned) | says(MM, "Migration.unapply")):
            do("schema_editor.__enter__()")
            do("returned = migration.unapply(state, schema_editor)")
            do("schema_editor.__exit__(None, None, None)")
        ask("returned is state")
        ask("sorted(key for key in state.models if key[0] == 'yard')")
        step("nothing is undone here either: yard's two tables are dropped, and yard.0001_initial still has no row; the next block begins so")
        show("Migration.unapply: a first pass makes two clones for each operation and runs its state half on one; a second pass runs the database halves backwards in reverse order, each given the clone after its operation as from_state and the clone before it as to_state")

        step("this block begins as the one before ended: the database has no table of yard's, and yard.0001_initial has no row. The script sets the feature flag can_rollback_ddl to False on this connection for the block, as it is on MySQL's and Oracle's, and takes its own value off again as the block ends")
        quietly("connection.features.can_rollback_ddl = False")
        quietly(given_state)
        quietly("state.apps  # rendered here, as before")
        name_it(ASKING["state"], "state")
        quietly("schema_editor = connection.schema_editor(atomic=migration.atomic)")
        for question in ("schema_editor.atomic_migration", "migration.atomic", "[operation.atomic for operation in migration.operations]"):
            ask(question)
        with recorded(applying, after=says(MS, "ProjectState.clone", how=cloned) | says(MM, "Migration.apply")):
            do("schema_editor.__enter__()")
            do("returned = migration.apply(state, schema_editor)")
            do("schema_editor.__exit__(None, None, None)")
        step("a migration of the script's own with one RunPython, whose function does nothing, applied the same way to the state that apply has just returned:")
        quietly("python = made(migrations.RunPython(migrations.RunPython.noop))")
        for question in ("python.atomic", "python.operations[0].atomic"):
            ask(question)
        quietly("schema_editor = connection.schema_editor(atomic=python.atomic)")
        with recorded(applying, after=says(MS, "ProjectState.clone", how=cloned) | says(MM, "Migration.apply")):
            do("schema_editor.__enter__()")
            do("returned = python.apply(state, schema_editor)")
            do("schema_editor.__exit__(None, None, None)")
        quietly("del connection.features.can_rollback_ddl")
        ask("connection.features.can_rollback_ddl")
    show("Migration.apply where DDL cannot be rolled back (SQLite's connection with can_rollback_ddl set to False by the script for the block): the schema editor begins no transaction; in a migration whose atomic is True, as both of these are, apply begins one around an operation's database half unless the operation's atomic is False, which it is for a CreateModel and is not for a RunPython")

    quietly("state = loader.project_state(('yard', '0001_initial'), at_end=False)")
    quietly("migration = loader.graph.nodes['yard', '0001_initial']")
    ask("('yard', 'dock') in state.models")
    quietly("after = migration.mutate_state(state)")
    ask("after is state")
    ask("('yard', 'dock') in after.models")
    ask("('yard', 'dock') in state.models")
    quietly("same = migration.mutate_state(state, preserve=False)")
    ask("same is state")
    ask("('yard', 'dock') in state.models")
    show("mutate_state: it runs the state half of each operation on a clone and returns the clone; with preserve=False on the state it was given")

    for question in ("first.suggest_name()", "second.suggest_name()", "loader.graph.nodes['yard', '0001_initial'].suggest_name()"):
        ask(question)
    step("migrations of the script's own, each made by `made` from the operations given it:")
    code(made)
    quietly("metres = migrations.AddField('dock', 'metres', models.PositiveSmallIntegerField(default=120))")
    quietly("longer = migrations.AlterField('dock', 'name', models.CharField(max_length=80))")
    quietly("begun = migrations.RenameField('repair', 'started', 'begun')")
    quietly("by_dock = migrations.AddIndex('repair', models.Index(fields=['dock', 'begun'], name='repair_by_dock'))")
    for question in (
        "made(metres).suggest_name()", "made(metres, longer).suggest_name()", "made(begun, metres).suggest_name()", "made(begun, metres, longer).suggest_name()",
        "made(begun, metres, longer, by_dock).suggest_name()", "made(by_dock).suggest_name()", "made(migrations.DeleteModel('Dock')).suggest_name()",
        "made(migrations.RunPython(migrations.RunPython.noop)).suggest_name()", "made(metres, migrations.RunSQL('SELECT 1')).suggest_name()",
        "made().suggest_name()", "made(metres, initial=True).suggest_name()", "[operation.migration_name_fragment for operation in (begun, metres, longer, by_dock)]",
        "migrations.RunPython(migrations.RunPython.noop).migration_name_fragment",
    ):
        ask(question)
    step("two fields of the script's own whose names are 35 and 36 letters long, to find the length at which a fragment is no longer joined on:")
    for question in (
        "made(metres, migrations.AddField('dock', 'a' * 35, models.IntegerField())).suggest_name()",
        "len(made(metres, migrations.AddField('dock', 'a' * 35, models.IntegerField())).suggest_name())",
        "made(metres, migrations.AddField('dock', 'a' * 36, models.IntegerField())).suggest_name()",
    ):
        ask(question)
    show("suggest_name: `initial` for a migration marked initial; else the operations' name fragments joined, as many as stay within 52 characters, then `_and_more`; and `auto_` with the date and the time where an operation has no fragment or there is no operation")

    ASKING.update(dialects=dialects())
    quietly("sqlite, postgresql, mysql, oracle = connection, dialects['postgresql'], dialects['mysql'], dialects['oracle']")
    for name in ("sqlite", "postgresql", "mysql", "oracle"):
        ask(f"{name}.features.can_rollback_ddl")
    for name in ("sqlite", "postgresql", "mysql", "oracle"):
        ask(f"{name}.schema_editor(atomic=True).atomic_migration")
    for name in ("sqlite", "postgresql"):
        ask(f"{name}.schema_editor(atomic=False).atomic_migration")
    show("A migration in a transaction or not: can_rollback_ddl, and atomic_migration of a schema editor that is made and not entered, for SQLite's connection and for connections of PostgreSQL's, MySQL's and Oracle's backends (made by a ConnectionHandler of the script's own; no server ran, and nothing asked a server's version)")
    close_connections()


# ---------------------------------------------------------------------------------------------
# Operations (blocks 15 to 18).


@part("operations")
def the_operations() -> None:
    """Blocks 15 to 18: what every operation has."""
    import copy

    from django.db.migrations import operations
    from django.db.migrations.operations.base import Operation

    set_up()
    ASKING.update(copy=copy)

    quietly("operation = migrations.AddField(model_name='dock', name='metres', field=models.PositiveSmallIntegerField(default=120))")
    for question in (
        "operation._constructor_args", "operation.deconstruct()", "repr(operation)", "operation.describe()", "operation.formatted_description()", "operation.category",
        "str(operation.category)", "operation.migration_name_fragment", "operation.reversible", "operation.reduces_to_sql", "operation.atomic", "operation.elidable",
        "operation.serialization_expand_args", "operation.preserve_default",
    ):
        ask(question)
    quietly("positional = migrations.AddField('dock', 'metres', models.PositiveSmallIntegerField(default=120), False)")
    for question in (
        "positional._constructor_args", "positional.deconstruct()", "copy.replace(operation, name='length')", "copy.replace(operation, name='length') is operation",
        "copy.replace(operation, name='length')._constructor_args", "copy.replace(positional, name='length')._constructor_args", "operation.name",
    ):
        ask(question)
    show("What an operation keeps of how it was made: an AddField made with keyword arguments and one made positionally; copy.replace calls __replace__, which makes another from the kept arguments")

    classes = sorted((getattr(operations, name) for name in operations.__all__), key=lambda klass: (klass.__module__, klass.__name__))
    for klass in classes:
        declares = []
        for name in ("category", "reversible", "reduces_to_sql", "atomic", "elidable"):
            owner = next(base for base in klass.__mro__ if name in vars(base))
            value = vars(owner)[name]
            if name == "category":
                sign = "None" if value is None else f"{value.name} {value.value!r}"
                declares.insert(0, f"category {sign}" + ("" if owner is klass else f" (from {owner.__name__})"))
            elif owner is not Operation:
                declares.append(f"{name} is " + ("a property" if isinstance(value, property) else repr(value)) + ("" if owner is klass else f" (from {owner.__name__})"))
        note(f"{klass.__module__.rsplit('.', 1)[-1]}.{klass.__name__}: " + ", ".join(declares))
    note(f"Operation, the base: category {Operation.category!r}, reversible {Operation.reversible!r}, reduces_to_sql {Operation.reduces_to_sql!r}, atomic {Operation.atomic!r}, elidable {Operation.elidable!r}")
    ask("migrations.RunPython(migrations.RunPython.noop).atomic")
    ask("migrations.RunPython(migrations.RunPython.noop).reversible")
    ask("migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop).reversible")
    ask("migrations.RunSQL('SELECT 1').reversible")
    ask("migrations.RunSQL('SELECT 1', elidable=True).elidable")
    ask("migrations.AlterModelOptions('dock', {}).formatted_description()")
    ask("migrations.SeparateDatabaseAndState().formatted_description()")
    show(f"The operations Django ships, by category: the {len(classes)} classes django.db.migrations.operations exports, by module and name, each with its category and its sign, and what it declares otherwise than the base class of reversible, reduces_to_sql, atomic and elidable")

    step("set up by the script: a loader, the project state its migrations make, a clone of that state for the to-state, and an operation")
    quietly("loader = MigrationLoader(None)")
    quietly("from_state = loader.project_state()")
    quietly(f"from_state.apps  # {RENDERED_FIRST}")
    quietly("to_state = from_state.clone()")
    name_it(ASKING["from_state"], "from_state")
    name_it(ASKING["to_state"], "to_state")
    quietly("operation = migrations.AddField(model_name='dock', name='metres', field=models.PositiveSmallIntegerField(default=120))")
    ask("list(to_state.models['yard', 'dock'].fields)")
    halves = operation_rules_with_states("state_forwards", "database_forwards", "database_backwards") | watch(MS, "ProjectState.add_field", "ProjectState.reload_model") | {
        (MS, "StateApps.__init__"): registry_made, (MS, "StateApps.render_multiple"): rendered_many, (REG, "Apps.get_model"): model_got, (OB, "Operation.allow_migrate_model"): generic, (OPT, "Options.can_migrate"): generic,
        (DBU, "ConnectionRouter.allow_migrate_model"): generic, (DBU, "ConnectionRouter.allow_migrate"): generic,
    } | editor_rules(*EDITOR_METHODS, "_remake_table")
    answers = says(REG, "Apps.get_model") | says(OB, "Operation.allow_migrate_model") | says(OPT, "Options.can_migrate") | says(DBU, "ConnectionRouter.allow_migrate_model", "ConnectionRouter.allow_migrate")
    with recorded(halves, after=answers):
        do("operation.state_forwards('yard', to_state)")
    ask("list(to_state.models['yard', 'dock'].fields)")
    ask("list(from_state.models['yard', 'dock'].fields)")
    ask("to_state.models['yard', 'dock'].fields['metres'] is operation.field")
    with recorded(halves, after=answers):
        do("with connection.schema_editor() as schema_editor: operation.database_forwards('yard', schema_editor, from_state, to_state)")
    ask("columns('yard_dock')")
    with recorded(halves, after=answers):
        do("with connection.schema_editor() as schema_editor: operation.database_backwards('yard', schema_editor, to_state, from_state)")
    ask("columns('yard_dock')")
    show("The two halves of one operation: an AddField of the script's own run by hand on yard, outside the executor, on a state rendered and then cloned as the executor's is; the state half changes a project state and, that state's registry being rendered, has the model and the models related to it rendered again, eight model states; the database half is given the state before and the state after, takes the historical models from their registries, and calls the schema editor; then its database half backwards, which takes the column away again")

    quietly("state = loader.project_state()")
    quietly("operation = migrations.RunSQL('SELECT 1')  # any operation: allow_migrate_model is the base class's")
    asking = {(OB, "Operation.allow_migrate_model"): generic, (OPT, "Options.can_migrate"): generic, (DBU, "ConnectionRouter.allow_migrate_model"): generic, (DBU, "ConnectionRouter.allow_migrate"): generic}
    quietly("HistoricalSailor, HistoricalVeteran = state.apps.get_model('crew', 'Sailor'), state.apps.get_model('crew', 'Veteran')")
    ask("HistoricalVeteran._meta.proxy")
    with recorded(asking, after=answers):
        do("allowed = operation.allow_migrate_model('default', HistoricalVeteran)")
        do("allowed = operation.allow_migrate_model('default', HistoricalSailor)")
    step("a model state of the script's own, of a model that is not managed, added to the state:")
    quietly("state.add_model(ModelState('yard', 'Tide', [('id', models.BigAutoField(primary_key=True)), ('high', models.TimeField())], options={'managed': False}))")
    quietly("Tide = state.apps.get_model('yard', 'Tide')")
    ask("Tide._meta.managed")
    with recorded(asking, after=answers):
        do("allowed = operation.allow_migrate_model('default', Tide)")
    show("allow_migrate_model refuses a proxy and a model that is not managed before any router is asked (the historical models crew.Veteran and crew.Sailor, and yard.Tide from a model state of the script's own; DATABASE_ROUTERS is empty)")
    close_connections()


# ---------------------------------------------------------------------------------------------
# Project state (blocks 19 to 24).


def argument_said(value) -> str:
    """One argument of a field, an index or a constraint, as its deconstruction gives it."""
    from django.db.models.deletion import DatabaseOnDelete

    if isinstance(value, (types.FunctionType, types.BuiltinFunctionType)):
        return short(value.__qualname__)
    if isinstance(value, DatabaseOnDelete):
        return value.__name__
    if inspect.isclass(value):
        return value.__name__
    if isinstance(value, (set, frozenset)):
        return "{" + ", ".join(sorted(repr(item) for item in value)) + "}" if value else "set()"
    if hasattr(value, "setting_name"):  # a SettingsReference: a string that also carries the name of the setting it was read from
        return f"settings.{value.setting_name} ({str(value)!r})"
    return repr(value)


def field_said(field) -> str:
    """A field by its class and the arguments it deconstructs to: `CharField(max_length=40)`."""
    _, _, args, kwargs = field.deconstruct()
    return f"{type(field).__name__}({', '.join([*(argument_said(v) for v in args), *(f'{k}={argument_said(v)}' for k, v in kwargs.items())])})"


def pictured(state) -> dict:
    """What a project state's model states hold at this moment, in words, to compare with what they hold later."""
    return {
        key: {
            "name": repr(model_state.name), "bases": argument_said(model_state.bases) if not isinstance(model_state.bases, tuple) else "(" + ", ".join(argument_said(b) for b in model_state.bases) + ",)",
            "managers": repr(model_state.managers), "fields": {name: field_said(field) for name, field in model_state.fields.items()},
            "options": {name: argument_said(value) for name, value in model_state.options.items()},
        }
        for key, model_state in state.models.items()
    }


def changes_between(before: dict, after: dict, state: str = "state") -> list:
    """What differs between two pictures of a project state, a thing to a line."""
    lines = []
    for key in sorted(before.keys() - after.keys()):
        lines.append(f"{state}.models has no {key!r} any more")
    for key in sorted(after.keys() - before.keys()):
        new = after[key]
        lines.append(f"{state}.models has gained {key!r}: name {new['name']}, fields {{{', '.join(f'{n!r}: {f}' for n, f in new['fields'].items())}}}, options {{{', '.join(f'{n!r}: {v}' for n, v in new['options'].items())}}}, bases {new['bases']}, managers {new['managers']}")
    for key in sorted(before.keys() & after.keys()):
        old, new = before[key], after[key]
        where = f"{state}.models[{key[0]!r}, {key[1]!r}]"
        for attribute in ("name", "bases", "managers"):
            if old[attribute] != new[attribute]:
                lines.append(f"{where}.{attribute}: {old[attribute]} became {new[attribute]}")
        for kind in ("fields", "options"):
            for name in sorted(old[kind].keys() - new[kind].keys()):
                lines.append(f"{where}.{kind} has no {name!r} any more (it was {old[kind][name]})")
            for name in new[kind]:
                if name not in old[kind]:
                    lines.append(f"{where}.{kind} has gained {name!r}: {new[kind][name]}")
                elif old[kind][name] != new[kind][name]:
                    lines.append(f"{where}.{kind}[{name!r}]: {old[kind][name]} became {new[kind][name]}")
        if list(old["fields"]) != list(new["fields"]):
            lines.append(f"{where}.fields are now, in order, {list(new['fields'])!r}")
    return lines


def changing(statement: str, name: str = "state") -> None:
    """A line of Python as `do` runs it, and under it what it changed in the model states of the
    project state of that name: `changed:` lines, found by comparing the state before and after."""
    before = pictured(ASKING[name])
    do(statement)
    found = changes_between(before, pictured(ASKING[name]), name)
    for line in found or ["nothing in " + name + ".models"]:
        note("  changed: " + line)


STATE_METHODS = (
    "add_model", "remove_model", "rename_model", "alter_model_options", "remove_model_options", "alter_model_managers", "add_index", "remove_index",
    "rename_index", "add_constraint", "remove_constraint", "alter_constraint", "add_field", "remove_field", "alter_field", "rename_field",
)
STATE_CHANGES = watch(MS, *(f"ProjectState.{name}" for name in STATE_METHODS))


@part("state")
def the_project_state() -> None:
    """Blocks 19 to 24: ProjectState and ModelState."""
    from django.db.migrations.utils import field_is_referenced, field_references, get_references, resolve_relation

    set_up()
    ASKING.update(field_said=field_said, field_references=field_references, get_references=get_references, field_is_referenced=field_is_referenced, resolve_relation=resolve_relation)

    quietly("state = ProjectState.from_apps(apps)")
    for question in ("type(state)", "full(sorted(state.models))", "state.models['fleet', 'ship']", "state.real_apps", "state.is_delayed", "state._relations", "'apps' in state.__dict__"):
        ask(question)
    quietly("loaded = MigrationLoader(None).project_state()")
    for question in (
        "sorted(loaded.models) == sorted(state.models)", "list(loaded.models) == list(state.models)", "full(list(loaded.models))", "full(list(state.models))", "loaded == state",
        "[key for key in state.models if state.models[key] != loaded.models[key]]",
        "[name for name, field in state.models['office', 'manifest'].fields.items() if field.deconstruct()[1:] != loaded.models['office', 'manifest'].fields[name].deconstruct()[1:]]",
    ):
        ask(question)
    quietly("ours, theirs = state.models['office', 'manifest'].fields['kilos'].deconstruct()[3], loaded.models['office', 'manifest'].fields['kilos'].deconstruct()[3]")
    for question in (
        "[name for name in ours if ours[name] != theirs[name]]", "field_said(ours['output_field'])", "field_said(theirs['output_field'])",
        "models.PositiveIntegerField() == models.PositiveIntegerField()", "MigrationAutodetector(loaded, state).changes(MigrationLoader(None).graph)",
    ):
        ask(question)
    show("ProjectState.from_apps: the project state of the models as models.py has them, made from the main registry, beside the one the loader makes from the migration files; the two are not equal by ==, though the autodetector finds no change between them")

    quietly("ship = ModelState.from_model(Ship)")
    for question in ("ship", "ship.app_label", "ship.name", "ship.name_lower", "list(ship.fields)", "[field_said(field) for field in ship.fields.values()]"):
        ask(question)
    for question in (
        "ship.fields['name'] is Ship._meta.get_field('name')", "hasattr(ship.fields['name'], 'model')", "hasattr(Ship._meta.get_field('name'), 'model')",
        "ship.fields['home'].remote_field.model", "Ship._meta.get_field('home').remote_field.model", "ship.fields['captain'].remote_field.model",
    ):
        ask(question)
    for key in ASKING["ship"].options:
        ask(f"ship.options[{key!r}]")
    for question in (
        "Ship._meta.original_attrs", "ship.options['indexes'][0] is Ship._meta.indexes[0]", "ship.options['indexes'][0] == Ship._meta.indexes[0]", "ship.bases", "Ship.__bases__", "ship.managers",
    ):
        ask(question)
    show("One model state: ModelState.from_model(Ship), the model fleet's models.py defines with the abstract base Named, two constraints and an index that is given no name there")

    for question in (
        "list(ModelState.from_model(Sailor).fields)", "ModelState.from_model(Sailor).fields['pilots_into'].remote_field.through", "Sailor.objects.use_in_migrations",
        "type(Sailor.objects).__name__", "ModelState.from_model(Sailor).managers", "list(ModelState.from_model(Officer).fields)", "ModelState.from_model(Officer).bases",
        "ModelState.from_model(Veteran).bases", "ModelState.from_model(Veteran).options", "list(ModelState.from_model(Veteran).fields)", "type(Veteran.objects).__name__",
        "ModelState.from_model(Veteran).managers", "ModelState.from_model(Manifest).fields['serial'].default", "ModelState.from_model(Manifest).fields['kilos'].expression",
        "ModelState.from_model(Manifest).fields['stamped'].db_default", "list(ModelState.from_model(Berth).fields)", "ModelState.from_model(Berth).fields['pk'].field_names",
        "list(ModelState.from_model(Voyage).fields)", "list(ModelState.from_model(Voyage, exclude_rels=True).fields)", "ModelState.from_model(Dock).options",
    ):
        ask(question)
    show("Model states of other models of the project: a many-to-many field with a model between, a manager made by as_manager, a child with a table of its own, a proxy, a callable default, a generated field, a default of the database's, a primary key of two columns; and a model state made without its relations")

    for question in (
        "ModelState('yard', 'Crane', [('dock', models.ForeignKey('yard.Dock', models.CASCADE))])",
        "ModelState('yard', 'Crane', [('port', Dock._meta.get_field('port'))])",
        "ModelState('yard', 'Crane', [('dock', models.ForeignKey(Dock, models.CASCADE))])",
        "ModelState('yard', 'Crane', [('docks', models.ManyToManyField('yard.Dock', through=Licence))])",
        "ModelState('yard', 'Crane', [], options={'indexes': [models.Index(fields=['dock'])]})",
        "ModelState('yard', 'Crane', []).options",
        "ModelState('yard', 'Crane', []).bases",
    ):
        ask(question)
    show("What a model state refuses: a field already bound to a model, a relation that names a model class and not a string, and an index with no name")

    step("a project state from the loader, its registry not rendered, and operations of the script's own, the state half of each run on it in turn")
    quietly("state = MigrationLoader(None).project_state()")
    with recorded(STATE_CHANGES):
        changing("migrations.CreateModel('Crane', [('id', models.BigAutoField(primary_key=True)), ('dock', models.ForeignKey('yard.Dock', models.CASCADE))], options={'ordering': ['id']}).state_forwards('yard', state)")
        changing("migrations.AddField('crane', 'tonnes', models.PositiveSmallIntegerField(default=5), preserve_default=False).state_forwards('yard', state)")
        ask("state.models['yard', 'crane'].fields['tonnes'].default")
        changing("migrations.AlterField('dock', 'name', models.CharField(max_length=80)).state_forwards('yard', state)")
        changing("migrations.RenameField('repair', 'started', 'begun').state_forwards('yard', state)")
        changing("migrations.RemoveField('repair', 'notes').state_forwards('yard', state)")
        changing("migrations.RenameModel('Dock', 'Basin').state_forwards('yard', state)")
        changing("migrations.AddIndex('repair', models.Index(fields=['dock', 'begun'], name='repair_by_dock')).state_forwards('yard', state)")
        changing("migrations.AlterModelOptions('repair', {'ordering': ['begun']}).state_forwards('yard', state)")
        changing("migrations.AlterModelOptions('crane', {'verbose_name': 'crane'}).state_forwards('yard', state)")
        changing("migrations.DeleteModel('Crane').state_forwards('yard', state)")
    ask("'apps' in state.__dict__")
    show("The state half of ten operations of the script's own, of nine classes, as a change to the project state: the ProjectState method each state_forwards calls, and what that changed in state.models")

    quietly("state = MigrationLoader(None).project_state()")
    ask("state._relations")
    quietly("relations = state.relations")
    for question in (
        "state._relations is relations", "type(relations)", "full(sorted(relations))", "{key: list(fields) for key, fields in relations['fleet', 'port'].items()}",
        "{key: list(fields) for key, fields in relations['yard', 'dock'].items()}", "{key: list(fields) for key, fields in relations['office', 'licence'].items()}",
        "relations['fleet', 'port']['yard', 'dock']['port'] is state.models['yard', 'dock'].fields['port']", "relations['crew', 'veteran'] is relations['crew', 'sailor']",
        "state.models['yard', 'dock'].fields['port'].name",
    ):
        ask(question)
    quietly("migrations.RenameModel('Dock', 'Basin').state_forwards('yard', state)")
    for question in ("('yard', 'dock') in state.relations", "{key: list(fields) for key, fields in state.relations['yard', 'basin'].items()}", "full(sorted(state.relations['fleet', 'port']))"):
        ask(question)
    quietly("migrations.RemoveField('repair', 'dock').state_forwards('yard', state)")
    for question in ("('yard', 'basin') in state.relations", "dict(state.relations['yard', 'basin'])", "{key: list(fields) for key, fields in state.relations['fleet', 'ship'].items()}"):
        ask(question)
    quietly("fresh = MigrationLoader(None).project_state()")
    quietly("migrations.RemoveField('repair', 'dock').state_forwards('yard', fresh)")
    ask("fresh._relations")
    show("relations: for each model that is pointed at, the models and fields that point at it; made at the first read, and kept up through the two changes made after that, a RenameModel and a RemoveField; a state whose relations were never read has none to keep up")

    quietly("state = MigrationLoader(None).project_state()")
    quietly("clone = state.clone()")
    for question in (
        "clone is state", "clone == state", "clone.models is state.models", "clone.models['yard', 'dock'] is state.models['yard', 'dock']",
        "clone.models['yard', 'dock'].fields is state.models['yard', 'dock'].fields", "clone.models['yard', 'dock'].fields['name'] is state.models['yard', 'dock'].fields['name']",
        "clone.models['fleet', 'ship'].options is state.models['fleet', 'ship'].options", "clone.models['fleet', 'ship'].options['indexes'] is state.models['fleet', 'ship'].options['indexes']",
        "clone.real_apps is state.real_apps", "'apps' in clone.__dict__",
    ):
        ask(question)
    quietly("migrations.AddField('dock', 'metres', models.PositiveSmallIntegerField(default=120)).state_forwards('yard', clone)")
    for question in ("list(clone.models['yard', 'dock'].fields)", "list(state.models['yard', 'dock'].fields)", "clone == state"):
        ask(question)
    step("a state whose registry is rendered, and a clone of it:")
    quietly("registry = state.apps")
    quietly("second = state.clone()")
    for question in ("'apps' in second.__dict__", "second.apps is registry", "second.apps.get_model('yard', 'Dock') is registry.get_model('yard', 'Dock')", "second.apps.get_model('yard', 'Dock')._meta.apps is second.apps"):
        ask(question)
    show("Clones share fields: ProjectState.clone makes another dict of other model states, whose fields are the same field objects; and where the state's registry is rendered, the clone is given a clone of the registry, which holds the same model classes")
    close_connections()


# ---------------------------------------------------------------------------------------------
# Historical models (blocks 25 to 29).


def rendered(frame) -> str:
    model_state = frame.f_locals["self"]
    return f"ModelState.render  [{model_state.app_label}.{model_state.name}]"


def rendered_many(frame) -> str:
    """StateApps.render_multiple, by the model states it is given, sorted: where they come from a set, the set gives their order."""
    given_ = sorted(f"{model_state.app_label}.{model_state.name}" for model_state in frame.f_locals["model_states"])
    if not given_:
        return None
    count = f"{len(given_)} model state{'' if len(given_) == 1 else 's'}"
    return f"StateApps.render_multiple(<{count}: {', '.join(given_)}>)" if len(given_) <= 4 else f"StateApps.render_multiple(<{count}>)"


RENDERING = {
    (MS, "StateApps.__init__"): registry_made, (MS, "StateApps.render_multiple"): rendered_many, (MS, "ModelState.render"): rendered,
    (MS, "StateApps.register_model"): only("app_label", "model"), (MS, "ModelState.from_model"): generic,
}


def sort_runs(prefix: str) -> None:
    """Calls made in the order a set gives are written sorted: each run of lines of one depth that begin with the prefix."""
    index = 0
    while index < len(LINES):
        if LINES[index].lstrip().startswith(prefix):
            depth = len(LINES[index]) - len(LINES[index].lstrip())
            end = index
            while end < len(LINES) and LINES[end].lstrip().startswith(prefix) and len(LINES[end]) - len(LINES[end].lstrip()) == depth:
                end += 1
            LINES[index:end] = sorted(LINES[index:end])
            index = end
        else:
            index += 1


@part("historical")
def historical_models() -> None:
    """Blocks 25, 26, 28 and 29: the state's registry and the historical models in it."""
    set_up()

    quietly("state = MigrationLoader(None).project_state()")
    ask("'apps' in state.__dict__")
    with recorded(RENDERING, after=says(MS, "ModelState.render")):
        do("registry = state.apps")
    for question in (
        "'apps' in state.__dict__", "state.apps is registry", "type(registry)", "type(registry).__mro__[1]", "registry is apps", "registry.ready",
        "{label: type(config).__name__ for label, config in registry.app_configs.items()}", "full(sorted(apps.app_configs))", "type(apps.app_configs['yard']).__name__",
        "len(registry.get_models())", "full(sorted(registry.all_models['fleet']))", "registry.real_models", "state.is_delayed",
    ):
        ask(question)
    show("The state's registry, made at the first read of ProjectState.apps: StateApps.__init__ renders every model state, and each model class, as it is made, is registered in that registry")

    quietly("Historical = registry.get_model('crew', 'Sailor')")
    for question in (
        "Historical", "Sailor", "Historical is Sailor", "Historical.__module__", "Sailor.__module__", "Historical.__name__", "Historical._meta.apps is registry",
        "Sailor._meta.apps is apps", "Historical._meta.db_table", "Historical.__str__ is models.Model.__str__", "Sailor.__str__ is models.Model.__str__",
        "[(manager.name, type(manager).__name__) for manager in Historical._meta.managers]", "[(manager.name, type(manager).__name__) for manager in Sailor._meta.managers]",
        "hasattr(Sailor.objects, 'aboard')", "hasattr(Historical.objects, 'aboard')", "full(sorted(field.name for field in Historical._meta.get_fields()))",
        "full(sorted(field.name for field in Sailor._meta.get_fields()))", "Historical._meta.get_field('ship').related_model", "Historical._meta.get_field('pilots_into').remote_field.through",
    ):
        ask(question)
    quietly("HistoricalVeteran, HistoricalShip = registry.get_model('crew', 'Veteran'), registry.get_model('fleet', 'Ship')")
    for question in (
        "HistoricalVeteran._meta.proxy", "HistoricalVeteran.__bases__", "type(Veteran.objects).__name__", "type(HistoricalVeteran.objects).__name__",
        "[klass.__name__ for klass in Ship.__mro__]", "[klass.__name__ for klass in HistoricalShip.__mro__]", "HistoricalShip.__str__ is models.Model.__str__",
        "HistoricalShip._meta.ordering", "[constraint.name for constraint in HistoricalShip._meta.constraints]", "[index.name for index in HistoricalShip._meta.indexes]",
        "registry.get_model('office', 'Manifest')._meta.get_field('serial').default",
    ):
        ask(question)
    show("A historical model and the model: crew.Sailor from the state's registry beside the class crew's models.py defines, then the proxy Veteran and fleet.Ship")

    reloading = watch(MS, "ProjectState.add_field", "ProjectState.reload_model", "ProjectState._find_reload_model", "ProjectState._reload", "ProjectState.clear_delayed_apps_cache") | {
        (MS, "StateApps.unregister_model"): generic, (MS, "StateApps.render_multiple"): rendered_many, (MS, "StateApps.__init__"): registry_made,
    }
    found = says(MS, "ProjectState._find_reload_model", how=lambda f, v: str(whole(v)))
    quietly("state = MigrationLoader(None).project_state()")
    quietly("registry = state.apps")
    ask("state.is_delayed")
    with recorded(reloading, after=found):
        do("migrations.AddField('dock', 'metres', models.PositiveSmallIntegerField(default=120)).state_forwards('yard', state)")
    sort_runs("StateApps.unregister_model")
    ask("state.is_delayed")
    ask("[field.name for field in registry.get_model('yard', 'Dock')._meta.get_fields()]")
    with recorded(reloading, after=found):
        do("migrations.AddField('dock', 'flagship', models.ForeignKey('fleet.Ship', models.SET_NULL, null=True)).state_forwards('yard', state)")
    sort_runs("StateApps.unregister_model")
    ask("state.is_delayed")
    ask("[field.name for field in registry.get_model('yard', 'Dock')._meta.get_fields()]")
    with recorded(reloading, after=found):
        do("state.clear_delayed_apps_cache()")
    ask("'apps' in state.__dict__")
    step("the same operation on a state whose registry has not been rendered:")
    quietly("fresh = MigrationLoader(None).project_state()")
    with recorded(reloading, after=found):
        do("migrations.AddField('dock', 'metres', models.PositiveSmallIntegerField(default=120)).state_forwards('yard', fresh)")
    ask("'apps' in fresh.__dict__")
    show("An operation re-renders: on a state whose registry is rendered, AddField takes out of the registry the models _find_reload_model returns and renders their model states again; for a field that is not a relation it asks with delay=True and the state is marked delayed, and for a foreign key it asks without; on a state not rendered, nothing is rendered (the calls of unregister_model are written sorted: a set gives their order)")

    step("a project state of the script's own, holding one model state whose base is a model the state does not have:")
    quietly("orphan = ProjectState()")
    quietly("orphan.add_model(ModelState('crew', 'Officer', [('rank', models.CharField(max_length=10))], bases=('crew.sailor',)))")
    ask("orphan.apps")
    ask("'apps' in orphan.__dict__")
    show("A base that cannot be resolved: rendering a state in which a model's base is missing")
    close_connections()


# ---------------------------------------------------------------------------------------------
# The model operations, the field operations, and those on indexes and constraints, run by hand
# (blocks 30 to 32 and 34 to 37).


class database_kept:
    """`with database_kept():` puts the database file back, as the block ends, as it was when the
    block began: the script keeps a copy of it, outside the run's directory. `span` names what
    the copy was kept across, where that is more than one block of the output."""

    def __init__(self, name: str = "harbour.sqlite3", span: str = "the block"):
        self.name = name
        self.span = span

    def __enter__(self):
        close_connections()
        handle, self.copy = tempfile.mkstemp(suffix=".kept")
        os.close(handle)
        shutil.copyfile(path_of(self.name), self.copy)

    def __exit__(self, kind, value, trace):
        close_connections()
        shutil.copyfile(self.copy, path_of(self.name))
        os.remove(self.copy)
        if kind is None:
            step(f"the script has put the database file {self.name} back as it was before {self.span}, from a copy it kept")


def remade(frame) -> str:
    """SQLite's _remake_table, which the chapter on the backends follows: its first and last statements are written."""
    return Ends(generic(frame))


def by_hand(*methods) -> dict:
    """The rules for a database half run by hand: the half itself with the two states it is given,
    and the schema editor's methods it calls, SQLite's remaking of a table cut to its ends."""
    return operation_rules_with_states(*methods) | editor_rules(*EDITOR_METHODS) | editor_rules("_remake_table", label=remade) | editor_rules("_constraint_names", label=briefly(generic))


STATE_FOLLOWS = "the operation's database half has been run backwards, and the script goes on from the state before the operation, which describes the table again"


def state_by_hand() -> None:
    """The state `state` that the blocks of operations run by hand begin from: the one the loader
    makes of every migration, rendered before anything is cloned from it. Migration.apply is
    given a rendered state and clones it before each operation, and the operation's state half
    then renders the changed model again in the to-state, whose fields are so the newer. Were
    the state cloned before it was rendered, both registries would be made inside the first
    database half, the to-state's first, and SQLite's _remake_table, which orders columns by
    the order their fields were made in, would order a remade table otherwise than in a migrate."""
    quietly("state = MigrationLoader(None).project_state()")
    quietly(f"state.apps  # {RENDERED_FIRST}")


def operated(name: str, operation: str, backwards: bool = False) -> None:
    """One operation of the script's own run by hand on the state `state` and the database, as
    Migration.apply runs one: its state half on the state, of which `previous` is a clone made
    just before, and then its database half."""
    quietly(f"{name} = {operation}")
    quietly("previous = state.clone()")
    name_it(ASKING["previous"], "previous")
    name_it(ASKING["state"], "state")
    with recorded(STATE_CHANGES):
        changing(f"{name}.state_forwards('yard', state)")
    with recorded(by_hand("database_forwards", "database_backwards"), after=says(BS, "BaseDatabaseSchemaEditor._constraint_names")):
        do(f"{name}.database_forwards('yard', schema_editor, previous, state)")
        if backwards:
            do(f"{name}.database_backwards('yard', schema_editor, state, previous)")
            do(f"{name}.database_forwards('yard', schema_editor, previous, state)")


@part("model-operations")
def model_operations() -> None:
    """Blocks 30 to 32: CreateModel, DeleteModel, RenameModel and the operations on a model's options, by hand."""
    set_up()

    with database_kept():
        step("set up by the script: the project state the migrations make, written `without`, and a clone of it to which the state half of a CreateModel of the script's own has added a model, Crane, written `with_crane`")
        quietly("without = MigrationLoader(None).project_state()")
        quietly(f"without.apps  # {RENDERED_FIRST}")
        quietly("create = migrations.CreateModel('Crane', [('id', models.BigAutoField(primary_key=True)), ('dock', models.ForeignKey('yard.Dock', models.CASCADE)), ('tonnes', models.PositiveSmallIntegerField())])")
        quietly("with_crane = without.clone()")
        quietly("create.state_forwards('yard', with_crane)")
        quietly("delete = migrations.DeleteModel('Crane')")
        name_it(ASKING["without"], "without")
        name_it(ASKING["with_crane"], "with_crane")
        rules = by_hand("database_forwards", "database_backwards")
        quietly("schema_editor = connection.schema_editor()")
        quietly("schema_editor.__enter__()")
        with recorded(rules):
            do("create.database_forwards('yard', schema_editor, without, with_crane)")
        ask("full([str(statement) for statement in schema_editor.deferred_sql])")
        quietly("schema_editor.__exit__(None, None, None)")
        ask("'yard_crane' in tables()")
        quietly("schema_editor = connection.schema_editor()")
        quietly("schema_editor.__enter__()")
        with recorded(rules):
            do("delete.database_forwards('yard', schema_editor, with_crane, without)")
            do("delete.database_backwards('yard', schema_editor, without, with_crane)")
        ask("full([str(statement) for statement in schema_editor.deferred_sql])")
        with recorded(rules):
            do("create.database_backwards('yard', schema_editor, with_crane, without)")
        ask("full([str(statement) for statement in schema_editor.deferred_sql])")
        quietly("schema_editor.__exit__(None, None, None)")
        ask("'yard_crane' in tables()")
    show("CreateModel and DeleteModel, each way, by hand: the database halves of a CreateModel and a DeleteModel of the script's own, for a model Crane added to yard's state for the block; each forwards is the other's backwards")

    with database_kept():
        step("set up by the script: Dock is given a many-to-many field for the block, visitors, by an AddField of the script's own run on the state and on the database; `before` is the state with it, and `after` a clone on which the state half of the RenameModel has run")
        quietly("before = MigrationLoader(None).project_state()")
        quietly(f"before.apps  # {RENDERED_FIRST}")
        quietly("visitors = migrations.AddField('dock', 'visitors', models.ManyToManyField('fleet.Ship'))")
        quietly("plain = before.clone()")
        quietly("visitors.state_forwards('yard', before)")
        silently("with connection.schema_editor() as schema_editor: visitors.database_forwards('yard', schema_editor, plain, before)")
        quietly("rename = migrations.RenameModel('Dock', 'Basin')")
        quietly("after = before.clone()")
        name_it(ASKING["before"], "before")
        name_it(ASKING["after"], "after")
        with recorded(STATE_CHANGES):
            changing("rename.state_forwards('yard', after)", name="after")
        ask("[name for name in tables() if name.startswith('yard_')]")
        quietly("schema_editor = connection.schema_editor()")
        quietly("schema_editor.__enter__()")
        with recorded(by_hand("database_forwards", "database_backwards")):
            do("rename.database_forwards('yard', schema_editor, before, after)")
        ask("[name for name in tables() if name.startswith('yard_')]")
        ask("table_sql('yard_repair')")
        ask("columns('yard_basin_visitors')")
        with recorded(operation_rules_with_states("database_forwards", "database_backwards") | editor_rules(*EDITOR_METHODS, label=briefly(generic))):
            do("rename.database_backwards('yard', schema_editor, after, before)")
        ask("(rename.old_name, rename.new_name)")
        quietly("schema_editor.__exit__(None, None, None)")
        ask("[name for name in tables() if name.startswith('yard_')]")
    show("RenameModel, by hand: Dock renamed Basin, with Repair pointing at it by a foreign key and a many-to-many table of its own (given it for the block): the table renamed, the field that points at it altered, and the many-to-many table made anew under its new name, with its column renamed and its rows copied; and backwards, which exchanges the two names and calls database_forwards")

    with database_kept():
        step("operations of the script's own, each run by hand in turn, as Migration.apply runs an operation: its state half on `state`, of which `previous` is a clone made just before, then its database half, given the two")
        state_by_hand()
        quietly("schema_editor = connection.schema_editor()")
        quietly("schema_editor.__enter__()")
        operated("options", "migrations.AlterModelOptions('repair', {'ordering': ['started'], 'verbose_name': 'repair'})")
        operated("managers", "migrations.AlterModelManagers('repair', [('afloat', models.Manager())])")
        operated("comment", "migrations.AlterModelTableComment('dock', 'The dry docks of the yard')")
        ask("connection.features.supports_comments")
        operated("table", "migrations.AlterModelTable('dock', 'yard_drydock')")
        ask("[name for name in tables() if name.startswith('yard_')]")
        operated("together", "migrations.AlterUniqueTogether('repair', {('ship', 'started')})")
        operated("ordered", "migrations.AlterOrderWithRespectTo('repair', 'dock')")
        ask("columns('yard_repair')")
        quietly("schema_editor.__exit__(None, None, None)")
        ask("indexes('yard_repair')")
    show("The operations on a model's options, by hand: AlterModelOptions, AlterModelManagers, AlterModelTableComment, AlterModelTable, AlterUniqueTogether and AlterOrderWithRespectTo: what the state half of each changed, and the statements of its database half, or none")
    close_connections()


@part("field-operations")
def field_operations() -> None:
    """Blocks 34 to 37: the field operations and those on indexes and constraints, by hand, and what refers to what."""
    from django.db.migrations.utils import field_is_referenced, field_references, get_references, resolve_relation

    set_up()
    ASKING.update(field_references=field_references, get_references=get_references, field_is_referenced=field_is_referenced, resolve_relation=resolve_relation)

    with database_kept():
        step("operations of the script's own, each run by hand in turn, as Migration.apply runs an operation: its state half on `state`, of which `previous` is a clone made just before, then its database half, given the two")
        state_by_hand()
        quietly("schema_editor = connection.schema_editor()")
        quietly("schema_editor.__enter__()")
        operated("longer", "migrations.AlterField('dock', 'name', models.CharField(max_length=80))")
        ask("table_sql('yard_dock')")
        with recorded(by_hand("database_forwards", "database_backwards")):
            do("longer.database_backwards('yard', schema_editor, state, previous)")
        ask("table_sql('yard_dock')")
        quietly(f"state = previous  # {STATE_FOLLOWS}")
        operated("begun", "migrations.RenameField('repair', 'started', 'begun')")
        ask("columns('yard_repair')")
        with recorded(by_hand("database_forwards", "database_backwards")):
            do("begun.database_backwards('yard', schema_editor, state, previous)")
        ask("columns('yard_repair')")
        quietly("schema_editor.__exit__(None, None, None)")
    show("AlterField and RenameField, by hand: Dock.name made longer, which SQLite does by remaking the table, and Repair.started renamed, which it does with one statement; AlterField's database_backwards calls its database_forwards, with the states it was given")

    with database_kept():
        state_by_hand()
        ask("columns('yard_repair')")
        quietly("schema_editor = connection.schema_editor()")
        quietly("schema_editor.__enter__()")
        operated("remove", "migrations.RemoveField('repair', 'notes')")
        ask("columns('yard_repair')")
        with recorded(by_hand("database_forwards", "database_backwards")):
            do("remove.database_backwards('yard', schema_editor, state, previous)")
        ask("columns('yard_repair')")
        quietly(f"state = previous  # {STATE_FOLLOWS}")
        operated("unship", "migrations.RemoveField('repair', 'ship')")
        ask("columns('yard_repair')")
        quietly("schema_editor.__exit__(None, None, None)")
    show("RemoveField, by hand, forwards and backwards: a text column dropped with one statement, and put back by remaking the table, in which it then stands second where it stood third; and a foreign key's column, for which the table is remade")

    with database_kept():
        state_by_hand()
        quietly("schema_editor = connection.schema_editor()")
        quietly("schema_editor.__enter__()")
        operated("add", "migrations.AddIndex('repair', models.Index(fields=['dock', 'started'], name='repair_by_dock'))")
        operated("rename", "migrations.RenameIndex('repair', new_name='repair_dock_day', old_name='repair_by_dock')")
        ask("connection.features.can_rename_index")
        operated("remove", "migrations.RemoveIndex('repair', 'repair_dock_day')")
        step("an index with no name of its own, as the option index_together once made them, for RenameIndex to find by its fields:")
        operated("together", "migrations.AlterIndexTogether('repair', {('ship', 'started')})")
        ask("indexes('yard_repair')")
        operated("named", "migrations.RenameIndex('repair', new_name='repair_ship_day', old_fields=('ship', 'started'))")
        ask("indexes('yard_repair')")
        with recorded(by_hand("database_forwards", "database_backwards")):
            do("named.database_backwards('yard', schema_editor, state, previous)")
        ask("indexes('yard_repair')")
        quietly("schema_editor.__exit__(None, None, None)")
    show("AddIndex, RenameIndex and RemoveIndex, by hand: an index made, renamed by its name (SQLite cannot rename an index: it is dropped and made again) and removed; then an index that has no name in the state, renamed by the fields it is on, whose backwards does nothing")

    with database_kept():
        state_by_hand()
        quietly("schema_editor = connection.schema_editor()")
        quietly("schema_editor.__enter__()")
        operated("unique", "migrations.AddConstraint('dock', models.UniqueConstraint(fields=['port', 'name'], name='one_name_to_a_port_dock'))")
        operated("check", "migrations.AddConstraint('repair', models.CheckConstraint(condition=models.Q(started__gte=datetime.date(2000, 1, 1)), name='repair_this_century'))")
        operated("alter", "migrations.AlterConstraint('repair', 'repair_this_century', models.CheckConstraint(condition=models.Q(started__gte=datetime.date(2000, 1, 1)), name='repair_this_century', violation_error_message='Too long ago.'))")
        operated("uncheck", "migrations.RemoveConstraint('repair', 'repair_this_century')")
        operated("ununique", "migrations.RemoveConstraint('dock', 'one_name_to_a_port_dock')")
        quietly("schema_editor.__exit__(None, None, None)")
    show("AddConstraint, AlterConstraint and RemoveConstraint, by hand: a unique constraint and a check constraint, for each of which SQLite remakes the table, to add it and to remove it; AlterConstraint changes the state and sends nothing")

    quietly("state = MigrationLoader(None).project_state()")
    for question in (
        "resolve_relation('fleet.Port')", "resolve_relation('Dock', 'yard')", "resolve_relation('Dock')", "resolve_relation('self', 'yard', 'dock')", "resolve_relation('self')",
        "resolve_relation(Dock)",
    ):
        ask(question)
    quietly("dock, pilots = state.models['yard', 'repair'].fields['dock'], state.models['crew', 'sailor'].fields['pilots_into']")
    for question in (
        "field_references(('yard', 'repair'), dock, ('yard', 'dock'))", "field_references(('yard', 'repair'), dock, ('fleet', 'port'))", "dock.to_fields",
        "field_references(('yard', 'repair'), dock, ('yard', 'dock'), 'id', state.models['yard', 'dock'].fields['id'])",
        "field_references(('yard', 'repair'), dock, ('yard', 'dock'), 'name', state.models['yard', 'dock'].fields['name'])",
        "field_references(('yard', 'repair'), dock, ('yard', 'dock'), 'name')",
        "field_references(('crew', 'sailor'), pilots, ('fleet', 'port'))", "field_references(('crew', 'sailor'), pilots, ('office', 'licence'))",
        "[(model_state.name, name) for model_state, name, field, reference in get_references(state, ('fleet', 'port'))]",
        "[(model_state.name, name) for model_state, name, field, reference in get_references(state, ('office', 'licence'))]",
        "field_is_referenced(state, ('yard', 'dock'), ('id', state.models['yard', 'dock'].fields['id']))",
        "field_is_referenced(state, ('yard', 'dock'), ('name', state.models['yard', 'dock'].fields['name']))",
        "migrations.AddField('repair', 'dock', dock).references_model('Dock', 'yard')", "migrations.AddField('repair', 'dock', dock).references_model('Port', 'fleet')",
        "migrations.AddField('repair', 'dock', dock).references_field('Dock', 'id', 'yard')", "migrations.AlterField('dock', 'name', models.CharField(max_length=80)).references_field('Dock', 'name', 'yard')",
        "migrations.AlterField('dock', 'name', models.CharField(max_length=80)).references_field('Dock', 'port', 'yard')",
    ):
        ask(question)
    show("What refers to what: resolve_relation, field_references, get_references and field_is_referenced of django.db.migrations.utils, asked about the state the migrations make, and an operation's references_model and references_field, which the optimizer asks")
    close_connections()


# ---------------------------------------------------------------------------------------------
# The graph (blocks 44 to 47).


def raising(question):
    """The exception that calling `question` raises, or None if it raises none."""
    try:
        question()
    except Exception as raised:
        return raised
    return None


def mutated(frame) -> str:
    """Migration.mutate_state, with the state it is given where the script has given that state a name."""
    state = frame.f_locals["project_state"]
    named = f"{NAMED[id(state)][1]}, " if id(state) in NAMED and NAMED[id(state)][0]() is state else ""
    return f"Migration.mutate_state({named}preserve={frame.f_locals['preserve']})  [{frame.f_locals['self']}]"


@part("graph")
def the_graph() -> None:
    """Blocks 44 to 47: the MigrationGraph of the project after the first makemigrations."""
    set_up()
    ASKING.update(raising=raising)

    quietly("loader = MigrationLoader(None)")
    quietly("graph = loader.graph")
    for question in ("type(graph)", "str(graph)", "full(sorted(graph.nodes))", "graph.nodes['yard', '0001_initial']", "graph.node_map['yard', '0001_initial']", "type(graph.node_map['yard', '0001_initial'])"):
        ask(question)
    for key in sorted(ASKING["graph"].nodes):
        ask(f"sorted(node.key for node in graph.node_map[{key[0]!r}, {key[1]!r}].parents)")
        ask(f"sorted(node.key for node in graph.node_map[{key[0]!r}, {key[1]!r}].children)")
    for question in ("graph.root_nodes()", "graph.leaf_nodes()", "graph.root_nodes('crew')", "graph.leaf_nodes('crew')", "graph.root_nodes('fleet')", "graph.leaf_nodes('fleet')", "graph.leaf_nodes('nosuch')"):
        ask(question)
    show("The graph of the project after the first makemigrations: five nodes, each with its parents (the nodes it depends on) and its children, and the root nodes and leaf nodes, which are counted within an application")

    for question in (
        "graph.forwards_plan(('office', '0001_initial'))", "graph.forwards_plan(('crew', '0002_initial'))", "graph.forwards_plan(('yard', '0001_initial'))",
        "graph.backwards_plan(('fleet', '0001_initial'))", "graph.backwards_plan(('crew', '0001_initial'))", "graph.backwards_plan(('yard', '0001_initial'))",
        "graph.forwards_plan(('yard', '0002_missing'))", "('yard', '0001_initial') in graph", "('yard', '0002_missing') in graph",
    ):
        ask(question)
    show("Plans from the graph: forwards_plan, a node's ancestors in an order in which they can be applied, ending with the node; backwards_plan, its descendants in an order in which they can be unapplied, ending with the node")

    step("a graph of the script's own, with one node, given a dependency as the loader gives one: the migration, its key, and the key it depends on")
    quietly("small = MigrationGraph()")
    quietly("yard_first = graph.nodes['yard', '0001_initial']")
    quietly("small.add_node(('yard', '0001_initial'), yard_first)")
    quietly("small.add_dependency(yard_first, ('yard', '0001_initial'), ('fleet', '0009_missing'), skip_validation=True)")
    for question in ("small.node_map['fleet', '0009_missing']", "small.nodes['fleet', '0009_missing']", "small.validate_consistency()", "raising(small.validate_consistency).node", "raising(small.validate_consistency).origin"):
        ask(question)
    step("the same call without skip_validation, on another graph of one node: add_dependency then calls validate_consistency itself")
    quietly("checked = MigrationGraph()")
    quietly("checked.add_node(('yard', '0001_initial'), yard_first)")
    ask("checked.add_dependency(yard_first, ('yard', '0001_initial'), ('fleet', '0009_missing'))")
    step("a third graph of the script's own, of two nodes that each depend on the other:")
    quietly("ring = MigrationGraph()")
    quietly("ring.add_node(('fleet', '0001_initial'), graph.nodes['fleet', '0001_initial'])")
    quietly("ring.add_node(('crew', '0001_initial'), graph.nodes['crew', '0001_initial'])")
    quietly("ring.add_dependency(graph.nodes['fleet', '0001_initial'], ('fleet', '0001_initial'), ('crew', '0001_initial'))")
    quietly("ring.add_dependency(graph.nodes['crew', '0001_initial'], ('crew', '0001_initial'), ('fleet', '0001_initial'))")
    ask("type(raising(ring.ensure_not_cyclic))")
    step("the message names the cycle's migrations beginning with whichever a set gave first, so its names are asked sorted:")
    ask("sorted(str(raising(ring.ensure_not_cyclic)).split(', '))")
    ask("graph.ensure_not_cyclic()")
    show("A dependency on a migration that is not there, and a cycle: add_dependency makes a DummyNode for a key that is no node, and validate_consistency raises for it, as add_dependency does itself unless it is told to skip the validation; ensure_not_cyclic raises for a cycle (three graphs of the script's own)")

    for question in ("graph.make_state()", "full(sorted(graph.make_state().models)) == full(sorted(ProjectState.from_apps(apps).models))", "MigrationGraph().make_state()"):
        ask(question)
    with recorded({(MG, "MigrationGraph.make_state"): generic, (MG, "MigrationGraph._generate_plan"): generic, (MM, "Migration.mutate_state"): mutated},
                  after=says(MG, "MigrationGraph._generate_plan", how=lambda f, v: str(full(v))) | says(MG, "MigrationGraph.make_state")):
        do("at_end = graph.make_state(('yard', '0001_initial'))")
        do("before = graph.make_state(('yard', '0001_initial'), at_end=False)")
    for question in (
        "sorted(key for key in at_end.models if key[0] == 'yard')", "sorted(key for key in before.models if key[0] == 'yard')", "full(sorted(before.models))",
        "('office', 'licence') in at_end.models", "loader.project_state(('yard', '0001_initial')) == at_end",
    ):
        ask(question)
    show("make_state: the project state at a node is made by running mutate_state of each migration of the node's forwards plan, in order, on one ProjectState; with at_end=False the node's own migration is left out")
    close_connections()


# ---------------------------------------------------------------------------------------------
# The loader (blocks 48 to 54).


def overriding(modules: dict, question):
    """The answer to `question`, asked while settings.MIGRATION_MODULES is `modules`."""
    from django.test.utils import override_settings

    with override_settings(MIGRATION_MODULES=modules):
        return question()


def forget(*names) -> None:
    """Take modules out of sys.modules, and have the import system look at the directories again:
    a process started after the script changed a file would not have them."""
    for name in list(sys.modules):
        if name in names or name.startswith(tuple(f"{n}." for n in names)):
            del sys.modules[name]
    importlib.invalidate_caches()


def imported(frame) -> str | None:
    """import_module, for a migrations package or a module in one."""
    name = frame.f_locals["name"]
    return f"import_module({name!r})" if ".migrations" in name else None


def edge_added(frame) -> str:
    """MigrationGraph.add_dependency, without its first argument, the migration, whose key is the child."""
    return f"MigrationGraph.add_dependency(child={frame.f_locals['child']!r}, parent={frame.f_locals['parent']!r}{', skip_validation=True' if frame.f_locals['skip_validation'] else ''})"


@part("no-migrations")
def no_migrations() -> None:
    """Block 48 and what goes with it: the project before the first makemigrations. The script
    moves the four migrations directories out of the project before this part and back after it."""
    set_up()

    step("the script has moved the four migrations directories out of the project for this block and the one after it: the project's files are as they were before the first makemigrations; the database keeps its tables and its five rows, and no line of the two blocks reads it")
    quietly("loader = MigrationLoader(None)")
    for question in (
        "loader.migrated_apps", "loader.unmigrated_apps", "loader.disk_migrations", "loader.graph.nodes", "loader.graph.leaf_nodes()", "loader.project_state()",
        "loader.project_state().real_apps", "MigrationLoader.migrations_module('fleet')", "'harbour.fleet.migrations' in sys.modules",
        "MigrationQuestioner().ask_initial('fleet')", "MigrationQuestioner(specified_apps={'fleet'}).ask_initial('fleet')",
        "MigrationQuestioner(defaults={'ask_initial': True}).ask_initial('fleet')",
    ):
        ask(question)
    step("the autodetector asked for yard alone, as `makemigrations yard` asks it:")
    quietly("autodetector = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps), MigrationQuestioner(specified_apps={'yard'}))")
    quietly("changes = autodetector.changes(graph=loader.graph, trim_to_apps={'yard'}, convert_apps={'yard'})")
    for question in ("changes", "changes['yard'][0].dependencies", "loader.check_key(('fleet', '__first__'), 'yard')"):
        ask(question)
    show("An application with no migrations, before the first makemigrations: the loader counts all four as unmigrated applications, the questioner answers no to a first migration unless the application is named or its defaults say yes, and a migration made for yard alone depends on fleet's first, whichever that will be")

    step("the script has made harbour/yard/migrations/__init__.py, an empty file, as startapp makes it")
    write("harbour/yard/migrations/__init__.py", "")
    forget("harbour.yard.migrations")
    quietly("loader = MigrationLoader(None)")
    for question in (
        "loader.migrated_apps", "'yard' in loader.unmigrated_apps", "loader.disk_migrations", "loader.graph.leaf_nodes('yard')", "MigrationQuestioner().ask_initial('yard')",
        "loader.check_key(('yard', '__first__'), 'fleet')", "MigrationLoader(None, ignore_no_migrations=True).check_key(('yard', '__first__'), 'fleet')",
    ):
        ask(question)
    step("the script has removed that file, leaving harbour/yard/migrations a directory with no __init__.py, and taken the old module out of sys.modules")
    os.remove(path_of("harbour/yard/migrations/__init__.py"))
    forget("harbour.yard.migrations")
    quietly("loader = MigrationLoader(None)")
    for question in ("loader.migrated_apps", "'yard' in loader.unmigrated_apps", "sys.modules['harbour.yard.migrations'].__file__", "type(sys.modules['harbour.yard.migrations'].__path__).__name__"):
        ask(question)
    step("the script has removed the directory and made a module in its place, harbour/yard/migrations.py, empty, and taken the old module out of sys.modules")
    os.rmdir(path_of("harbour/yard/migrations"))
    write("harbour/yard/migrations.py", "")
    forget("harbour.yard.migrations")
    quietly("loader = MigrationLoader(None)")
    for question in ("loader.migrated_apps", "'yard' in loader.unmigrated_apps", "hasattr(sys.modules['harbour.yard.migrations'], '__path__')"):
        ask(question)
    os.remove(path_of("harbour/yard/migrations.py"))
    forget("harbour.yard.migrations")
    step("the script has removed harbour/yard/migrations.py")
    show("A migrations package with nothing in it, a directory that is no package, and a module called migrations: only the first makes yard a migrated application, with no migration, and for it the questioner is for a first migration")
    close_connections()


@part("loader")
def the_loader() -> None:
    """Blocks 49 to 54: MigrationLoader after the first makemigrations and migrate."""
    set_up()
    ASKING.update(overriding=overriding)

    building = {
        (ML, "MigrationLoader.__init__"): generic, (ML, "MigrationLoader.build_graph"): bare, (ML, "MigrationLoader.load_disk"): bare, ("importlib", "import_module"): imported,
        ("importlib", "reload"): lambda f: f"reload(the module {f.f_locals['module'].__name__})", (MR, "MigrationRecorder.applied_migrations"): bare,
        (MG, "MigrationGraph.add_node"): generic, (ML, "MigrationLoader.add_internal_dependencies"): generic, (ML, "MigrationLoader.add_external_dependencies"): generic,
        (ML, "MigrationLoader.check_key"): generic, (MG, "MigrationGraph.add_dependency"): edge_added, (MG, "MigrationGraph.validate_consistency"): bare,
        (MG, "MigrationGraph.ensure_not_cyclic"): bare,
    }
    answers = says(MR, "MigrationRecorder.applied_migrations") | says(ML, "MigrationLoader.check_key")
    with recorded(building, after=answers):
        do("loader = MigrationLoader(connection)")
    for question in (
        "full(list(loader.disk_migrations))", "full(list(loader.applied_migrations))", "loader.applied_migrations['yard', '0001_initial']", "loader.migrated_apps", "loader.unmigrated_apps",
        "loader.replacements", "loader.replace_migrations", "loader.ignore_no_migrations",
    ):
        ask(question)
    show("build_graph, in order: the migration packages and modules imported (the applications in the order of INSTALLED_APPS, each one's modules in the order pkgutil.iter_modules lists its directory, which is by file name), the rows of django_migrations read, a node added for each migration, then the edges within an application, then those between applications, then the two checks")

    with recorded({(ML, "MigrationLoader.load_disk"): bare, ("importlib", "import_module"): imported, ("importlib", "reload"): lambda f: f"reload(the module {f.f_locals['module'].__name__})"}):
        do("second = MigrationLoader(None)")
    for question in (
        "second.applied_migrations", "second.disk_migrations['yard', '0001_initial'] is loader.disk_migrations['yard', '0001_initial']",
        "type(second.disk_migrations['yard', '0001_initial']) is type(loader.disk_migrations['yard', '0001_initial'])",
        "second.disk_migrations['yard', '0001_initial'] == loader.disk_migrations['yard', '0001_initial']",
    ):
        ask(question)
    show("A second loader in the same process, made with no connection: load_disk reloads each migrations package, and import_module gives it the migration modules the process already has, of whose classes it makes new instances")

    step("the script has added to harbour/yard/migrations a module _draft.py and a module ~backup.py, each of the one line `raise RuntimeError('imported')`, and a package notes with an empty __init__.py")
    write("harbour/yard/migrations/_draft.py", "raise RuntimeError('imported')\n")
    write("harbour/yard/migrations/~backup.py", "raise RuntimeError('imported')\n")
    write("harbour/yard/migrations/notes/__init__.py", "")
    forget()
    ASKING.update(os_listdir=lambda relative: Whole(sorted(name for name in os.listdir(path_of(relative)) if name != "__pycache__")))
    ask("os_listdir('harbour/yard/migrations')")
    quietly("passing = MigrationLoader(None)")
    ask("sorted(name for label, name in passing.disk_migrations if label == 'yard')")
    ask("[name for name in sys.modules if name.startswith('harbour.yard.migrations.')]")
    step("the script has added a module 0002_empty.py of the one line `from django.db import migrations`, which defines no class Migration")
    write("harbour/yard/migrations/0002_empty.py", "from django.db import migrations\n")
    forget()
    ask("MigrationLoader(None)")
    for name in ("_draft.py", "~backup.py", "0002_empty.py", "notes/__init__.py"):
        os.remove(path_of(f"harbour/yard/migrations/{name}"))
    os.rmdir(path_of("harbour/yard/migrations/notes"))
    forget("harbour.yard.migrations.0002_empty")
    step("the script has removed the four files it added, and taken the module 0002_empty out of sys.modules")
    ask("os_listdir('harbour/yard/migrations')")
    show("Files the loader passes over: a module whose name begins with _ or ~ and a package inside the migrations package are not imported; a module with no class Migration is an error")

    step("the setting MIGRATION_MODULES is overridden for each question by a helper of the script's own; the questions are about yard, on whose migrations no other application's depend:")
    code(overriding)
    for question in (
        "settings.MIGRATION_MODULES", "MigrationLoader.migrations_module('yard')", "MigrationLoader(None).unmigrated_apps",
        "overriding({'yard': None}, lambda: MigrationLoader.migrations_module('yard'))",
        "overriding({'yard': None}, lambda: MigrationLoader(None).unmigrated_apps)",
        "overriding({'yard': 'harbour.yard.history'}, lambda: MigrationLoader.migrations_module('yard'))",
        "overriding({'yard': 'harbour.yard.history'}, lambda: MigrationLoader(None))",
        "overriding({'yard': 'harbour.yard.history'}, lambda: MigrationLoader(None, ignore_no_migrations=True).unmigrated_apps)",
        "overriding({'yard': 'harbour.nosuch.history'}, lambda: MigrationLoader(None, ignore_no_migrations=True).unmigrated_apps)",
    ):
        ask(question)
    show("MIGRATION_MODULES: None for an application makes it an unmigrated application; a module's name is where its migrations are looked for, and where that module is not there the loader raises, unless it was made with ignore_no_migrations, for which the application is then unmigrated")

    for question in (
        "loader.check_key(('crew', '0001_initial'), 'yard')", "loader.check_key(('crew', '__first__'), 'yard')", "loader.check_key(('crew', '__latest__'), 'yard')",
        "loader.check_key(('fleet', '__first__'), 'yard')", "loader.check_key(('yard', '__first__'), 'yard')", "loader.check_key(('yard', '__latest__'), 'yard')",
        "loader.check_key(('nosuch', '__first__'), 'yard')", "overriding({'yard': None}, lambda: MigrationLoader(None).check_key(('yard', '__first__'), 'office'))",
        "overriding({'yard': None}, lambda: MigrationLoader(None).unmigrated_apps)", "overriding({'office': None}, lambda: MigrationLoader(None))",
    ):
        ask(question)
    show("__first__ and __latest__: check_key turns a dependency on an application's first or latest migration into a key, or into None for the application's own and for an unmigrated application; and what the loader makes of an application made unmigrated when a migration file names one of its migrations")

    ask("sorted(node.key for node in loader.graph.node_map['office', '0001_initial'].parents)")
    step("the script has written a migration of its own, harbour/yard/migrations/0002_before_office.py:")
    write("harbour/yard/migrations/0002_before_office.py", RUN_BEFORE)
    forget()
    file_shown("harbour/yard/migrations/0002_before_office.py")
    with recorded({
        (ML, "MigrationLoader.add_external_dependencies"): lambda f: generic(f) if f.f_locals["key"][1] == "0002_before_office" else None,
        (ML, "MigrationLoader.check_key"): lambda f: generic(f) if f.f_locals["current_app"] == "yard" and f.f_locals["key"][0] == "office" else None,
        (MG, "MigrationGraph.add_dependency"): lambda f: edge_added(f) if "0002_before_office" in (f.f_locals["child"][1], f.f_locals["parent"][1]) else None,
    }, after=says(ML, "MigrationLoader.check_key")):
        do("loader = MigrationLoader(None)")
    for question in (
        "sorted(node.key for node in loader.graph.node_map['office', '0001_initial'].parents)", "loader.graph.forwards_plan(('office', '0001_initial'))",
        "loader.graph.leaf_nodes('yard')", "loader.check_consistent_history(connection)",
    ):
        ask(question)
    os.remove(path_of("harbour/yard/migrations/0002_before_office.py"))
    forget("harbour.yard.migrations.0002_before_office")
    step("the script has removed the file, and taken its module out of sys.modules")
    quietly("loader = MigrationLoader(connection)")
    ask("sorted(node.key for node in loader.graph.node_map['office', '0001_initial'].parents)")
    show("run_before: a migration of the script's own in yard that names office's first migration in run_before becomes a parent of that node; office's is applied and the new one is not, which check_consistent_history refuses")

    for question in (
        "loader.get_migration_by_prefix('fleet', '0001')", "loader.get_migration_by_prefix('crew', '0002_i')", "loader.get_migration_by_prefix('crew', '000')",
        "loader.get_migration_by_prefix('fleet', '9')", "loader.get_migration_by_prefix('nosuch', '0001')", "loader.get_migration('fleet', '0001_initial')",
        "loader.get_migration('fleet', '0001')",
    ):
        ask(question)
    show("A name by its prefix: get_migration_by_prefix looks among the migrations on disk for the one of the application whose name begins so; get_migration takes the whole name")

    step("the script takes the row of fleet.0001_initial out of django_migrations by hand, keeping it to put back:")
    quietly("kept = MigrationRecorder.Migration.objects.get(app='fleet', name='0001_initial')")
    quietly("number = kept.pk")
    quietly("kept.delete()")
    ask("loader.check_consistent_history(connection)")
    manage("migrate")
    manage("makemigrations")
    step("the script puts the row back as it was:")
    quietly("kept.pk = number; kept.save(force_insert=True)")
    ask("loader.check_consistent_history(connection)")
    show("An inconsistent history: with the row of fleet.0001_initial gone, office.0001_initial is applied and a migration it depends on is not; check_consistent_history raises, and migrate and makemigrations end with its exception")
    close_connections()


RUN_BEFORE = '''\
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("yard", "0001_initial")]
    run_before = [("office", "0001_initial")]
    operations = []
'''


# ---------------------------------------------------------------------------------------------
# The recorder (blocks 55 and 56).


@part("recorder")
def the_recorder() -> None:
    """Blocks 55 and 56: MigrationRecorder, its model, and the table django_migrations."""
    set_up()

    ask("MigrationRecorder._migration_class")
    quietly("Recorded = MigrationRecorder.Migration")
    for question in (
        "MigrationRecorder._migration_class is Recorded", "MigrationRecorder.Migration is Recorded", "Recorded", "Recorded.__module__", "Recorded.__qualname__",
        "Recorded._meta.app_label", "Recorded._meta.db_table", "[(field.name, type(field).__name__) for field in Recorded._meta.fields]", "Recorded._meta.get_field('applied').default",
        "Recorded._meta.apps is apps", "type(Recorded._meta.apps)", "dict(Recorded._meta.apps.all_models)", "'migrations' in apps.all_models", "'migrations' in apps.app_configs",
        "str(Recorded(app='fleet', name='0001_initial'))", "MigrationRecorder(connection).migration_qs.db",
    ):
        ask(question)
    show("The recorder's model: the class MigrationRecorder.Migration, made at the first read and kept on MigrationRecorder, a model in a registry of its own and not in the main registry")

    step('a recorder for the connection "archive", whose database file does not exist yet: SQLite makes it, empty, when the connection opens')
    quietly("recorder = MigrationRecorder(connections['archive'])")
    recording = watch(MR, "MigrationRecorder.has_table", "MigrationRecorder.ensure_schema", "MigrationRecorder.applied_migrations", "MigrationRecorder.record_applied", "MigrationRecorder.record_unapplied", "MigrationRecorder.flush") | editor_rules("create_model")
    answers = says(MR, "MigrationRecorder.has_table", "MigrationRecorder.applied_migrations")
    for question in ("recorder._has_table", "recorder.has_table()", "recorder._has_table", "recorder.applied_migrations()"):
        ask(question)
    with recorded(recording, after=answers):
        do("recorder.ensure_schema()")
    for question in ("recorder._has_table", "tables('archive')"):
        ask(question)
    with recorded(recording, after=answers):
        do("recorder.ensure_schema()")
        do("recorder.record_applied('yard', '0001_initial')")
        do("applied = recorder.applied_migrations()")
    for question in ("type(applied['yard', '0001_initial'])", "applied['yard', '0001_initial'].app", "type(applied['yard', '0001_initial'].applied).__name__"):
        ask(question)
    with recorded(recording, after=answers):
        do("recorder.record_unapplied('yard', '0001_initial')")
        do("recorder.record_applied('yard', '0001_initial')")
        do("recorder.flush()")
    ask("recorder.applied_migrations()")
    close_connections()
    os.remove(path_of("archive.sqlite3"))
    step("the script has closed the connection and removed the file archive.sqlite3")
    show('has_table, ensure_schema, applied_migrations, record_applied and record_unapplied, on the connection "archive", whose database is empty: the table is made at the first ensure_schema, and a migration is applied for as long as it has a row')
    close_connections()


# ---------------------------------------------------------------------------------------------
# The autodetector (blocks 71 to 75, 78, 79, 81 to 85).


def operation_detail(operation) -> str:
    """An operation as operation_said writes it, and in parentheses what tells it from another
    of its class: a CreateModel's fields by name, a field's class and arguments, an option's value."""
    from django.db.migrations import operations as shipped
    from django.db.migrations.operations.models import AlterTogetherOptionOperation

    extra = None
    if isinstance(operation, shipped.CreateModel):
        extra = "fields " + (", ".join(name for name, _ in operation.fields) or "none")
        if operation.options:
            extra += "; options " + ", ".join(f"{name}={argument_said(value)}" for name, value in operation.options.items())
        if operation.bases != (shipped.CreateModel("X", []).bases):
            extra += "; bases " + ", ".join(argument_said(base) for base in operation.bases)
    elif getattr(operation, "field", None) is not None:
        extra = field_said(operation.field) + (", with preserve_default=False" if getattr(operation, "preserve_default", True) is False else "")
    elif isinstance(operation, shipped.AlterModelOptions):
        extra = repr(operation.options)
    elif isinstance(operation, AlterTogetherOptionOperation):
        extra = argument_said(operation.option_value)
    elif isinstance(operation, shipped.AlterModelManagers):
        extra = "managers " + ", ".join(f"{name}: {type(manager).__name__}" for name, manager in operation.managers)
    return f"{operation_said(operation)} ({extra})" if extra else operation_said(operation)


def operations_pictured(generated: dict, through_a_set: set) -> list:
    """The autodetector's generated_operations at this moment, an operation to a line: the
    applications in the dict's own order, which is the order in which each was first given an
    operation, and each operation with its dependencies in words, in the order of the list the
    autodetector gave it. An operation whose id is in `through_a_set` was given
    `list(set(dependencies))`, so a set ordered them: those are written sorted."""
    lines = []
    for label in generated:
        for operation in generated[label]:
            needs = [dependency_said(dependency) for dependency in operation._auto_deps]
            if id(operation) in through_a_set:
                needs.sort()
            lines.append(f"{label}: {operation_detail(operation)}  [{'; '.join(needs) if needs else 'needs nothing'}]")
    return lines or ["(no operations)"]


PICTURE_ORDER = (
    "the applications stand in the order of the dict generated_operations, which is the order in which each was first given an operation; "
    "an operation's dependencies stand in the order of the list the autodetector gave it, but those of an AddField that generate_created_models "
    "made and of a DeleteModel, which it passes through a set: those are written sorted"
)


def migrations_pictured(made_: dict) -> list:
    """The autodetector's migrations at this moment: each with its dependencies, sorted (a set gave their order), and its operations."""
    lines = []
    for label, migrations in made_.items():
        for migration in migrations:
            lines.append(f"{migration}: initial {migration.initial}, dependencies {sorted(migration.dependencies)!r}")
            lines.extend(f"  {operation_detail(operation)}" for operation in migration.operations)
    return lines or ["(no migrations)"]


def detecting(pictures: dict) -> tuple:
    """The rules for one run of the autodetector, and what to say as its methods return: each
    generate_ and create_ method with the number of operations it added (the script's count: the
    methods return nothing), and, kept in `pictures` for the blocks after, the two sets of field
    keys as _prepare_field_lists returned, and what generated_operations and migrations held as
    _sort_migrations, _build_migration_list, _optimize_migrations and arrange_for_graph were called or returned."""
    from django.db.migrations import operations as shipped
    from django.db.migrations.autodetector import MigrationAutodetector

    counts = {}
    # The two places where the autodetector gives an operation `list(set(dependencies))`: the AddField
    # of a relation in generate_created_models, and the DeleteModel in generate_deleted_models.
    deduplicating = {"MigrationAutodetector.generate_created_models": shipped.AddField, "MigrationAutodetector.generate_deleted_models": shipped.DeleteModel}
    through_a_set = set()

    def every(frame) -> list:
        return [operation for found in frame.f_locals["self"].generated_operations.values() for operation in found]

    def generating(frame) -> str:
        counts[id(frame)] = {id(operation) for operation in every(frame)}
        return called(frame)

    def generated(frame, value) -> Remark:
        before = counts.pop(id(frame))
        new = [operation for operation in every(frame) if id(operation) not in before]
        klass = deduplicating.get(frame.f_code.co_qualname)
        if klass is not None:
            through_a_set.update(id(operation) for operation in new if type(operation) is klass)
        return Remark("no operation added" if not new else f"{len(new)} operation{'' if len(new) == 1 else 's'} added")

    def prepared(frame, value) -> None:
        autodetector = frame.f_locals["self"]
        pictures["field keys"] = {"old_field_keys": sorted(autodetector.old_field_keys), "new_field_keys": sorted(autodetector.new_field_keys)}

    def resolving(frame) -> str:
        """ProjectState.resolve_fields_and_relations, with which of the autodetector's two states it is called on."""
        state, caller = frame.f_locals["self"], frame.f_back.f_locals.get("self")
        for which in ("from_state", "to_state"):
            if isinstance(caller, MigrationAutodetector) and state is getattr(caller, which):
                return f"ProjectState.resolve_fields_and_relations  [the autodetector's {which}]"
        return "ProjectState.resolve_fields_and_relations"

    def sorting(frame) -> str:
        pictures["before sorting"] = operations_pictured(frame.f_locals["self"].generated_operations, through_a_set)
        return called(frame)

    def sorted_(frame, value) -> None:
        pictures["after sorting"] = operations_pictured(frame.f_locals["self"].generated_operations, through_a_set)

    def built(frame, value) -> None:
        pictures["cut"] = migrations_pictured(frame.f_locals["self"].migrations)

    def optimized(frame, value) -> None:
        pictures["optimized"] = migrations_pictured(frame.f_locals["self"].migrations)

    def arranged(frame, value) -> str:
        pictures["arranged"] = migrations_pictured(value)
        return str(whole(value))

    rules, after = {}, {}
    for name in vars(MigrationAutodetector):
        if name.startswith(("generate_", "create_")):
            rules[(MA, f"MigrationAutodetector.{name}")] = generating
            after[(MA, f"MigrationAutodetector.{name}")] = generated
    rules |= watch(MA, "MigrationAutodetector.changes", "MigrationAutodetector._detect_changes", "MigrationAutodetector.arrange_for_graph", label=bare) | watch(
        MA, "MigrationAutodetector._prepare_field_lists", "MigrationAutodetector._generate_through_model_map", "MigrationAutodetector._build_migration_list",
        "MigrationAutodetector._optimize_migrations", "MigrationAutodetector._trim_to_apps", label=bare,
    ) | {(MA, "MigrationAutodetector._sort_migrations"): sorting, (MS, "ProjectState.resolve_fields_and_relations"): resolving}
    after |= {
        (MA, "MigrationAutodetector._prepare_field_lists"): prepared,
        (MA, "MigrationAutodetector._sort_migrations"): sorted_, (MA, "MigrationAutodetector._build_migration_list"): built,
        (MA, "MigrationAutodetector._optimize_migrations"): optimized, (MA, "MigrationAutodetector.arrange_for_graph"): arranged,
    }
    return rules, after


@part("first-detection")
def first_detection() -> None:
    """Blocks 71, 72 and 81 to 83: the autodetector at the first makemigrations. The script moves
    the four migrations directories out of the project before this part and back after it."""
    set_up()
    pictures = {}
    rules, after = detecting(pictures)

    step("the script has moved the four migrations directories out of the project for this block and the five after it: the project's files are as they were before the first makemigrations; the database keeps its tables and its five rows, and no line of the six blocks reads it")
    step("a loader, and an autodetector made as makemigrations makes it, but with a questioner that asks no one, and called as `makemigrations fleet crew office yard` calls it")
    quietly("loader = MigrationLoader(None, ignore_no_migrations=True)")
    quietly("named = {'fleet', 'crew', 'office', 'yard'}")
    quietly("autodetector = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps), MigrationQuestioner(specified_apps=named))")
    with recorded(rules, after=after):
        do("changes = autodetector.changes(graph=loader.graph, trim_to_apps=named, convert_apps=named)")
    for question in (
        "full(sorted(autodetector.old_model_keys))", "full(sorted(autodetector.new_model_keys))", "full(sorted(autodetector.old_proxy_keys))", "full(sorted(autodetector.new_proxy_keys))",
        "full(sorted(autodetector.kept_model_keys))", "autodetector.through_users", "autodetector.existing_apps",
    ):
        ask(question)
    show("The two states compared, at the first makemigrations: the methods _detect_changes calls, in order, each generate_ or create_ method with the number of operations it added to generated_operations (the script's count, in parentheses: the methods return nothing), and the sets of model keys it began from")

    step(PICTURE_ORDER)
    for line in pictures["before sorting"]:
        note(line)
    show("generated_operations before sorting, at the first makemigrations: each application's operations as the generate methods left them, each with the dependencies the autodetector gave it (what another operation, if there is one, must have done first); every foreign key and many-to-many field here is an AddField of its own and not in its model's CreateModel, but for Officer's sailor_ptr, which is its model's primary key and its link to its parent and stays in the CreateModel")

    step(PICTURE_ORDER)
    for line in pictures["after sorting"]:
        note(line)
    show("generated_operations after _sort_migrations: within each application, an operation now stands after the operations of that application it depends on")

    step("the same again, with another autodetector, for this block and the two after it:")
    later = {}
    rules, after = detecting(later)
    quietly("autodetector = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps), MigrationQuestioner(specified_apps=named))")
    cutting = {key: label for key, label in rules.items() if key[1].endswith(("_build_migration_list", "_optimize_migrations", "arrange_for_graph"))} | {(MM, "Migration.__init__"): generic}
    with recorded(cutting, after=after):
        do("changes = autodetector.changes(graph=loader.graph, trim_to_apps=named, convert_apps=named)")
    step("what the autodetector's migrations held as _build_migration_list returned, each migration with its dependencies sorted and its operations:")
    for line in later["cut"]:
        note(line)
    show("_build_migration_list at the first makemigrations: the migrations in the order they were cut from the lists of operations (each line Migration.__init__ is one being made), and what each holds before the optimizer; crew's operations are cut in two: its second migration begins at the first operation that needs a model of fleet's or office's, whose own migrations need crew's Sailor, and holds every operation after that one too")

    for line in later["optimized"]:
        note(line)
    show("After _optimize_migrations at the first makemigrations: crew's second migration now depends on its first, and the optimizer has folded each AddField that stood in a migration with its model's CreateModel into that CreateModel; fleet's AddIndex and its two AddConstraints stand as they were")

    for line in later["arranged"]:
        note(line)
    for question in ("MigrationAutodetector.parse_number('0003_x')", "MigrationAutodetector.parse_number('0001_squashed_0004_y')", "MigrationAutodetector.parse_number('custom')"):
        ask(question)
    show("After arrange_for_graph at the first makemigrations: auto_1 and auto_2 are renamed 0001_initial and 0002_initial, and the dependencies that named them follow; and parse_number, which reads a migration's number from its name")
    close_connections()


@part("yard-alone")
def yard_alone() -> None:
    """Block 85: yard made after the other applications have migrations. The script moves yard's
    migrations directory out of the project before this part and back after it."""
    set_up()
    step("the script has moved harbour/yard/migrations out of the project for this block: yard has no migrations, and the three other applications have theirs; the database is as the first migrate left it, and no line of the block reads it")
    quietly("loader = MigrationLoader(None, ignore_no_migrations=True)")
    for question in ("loader.unmigrated_apps", "loader.graph.leaf_nodes('fleet')", "loader.project_state().real_apps"):
        ask(question)
    quietly("autodetector = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps), MigrationQuestioner(specified_apps={'yard'}))")
    quietly("changes = autodetector.changes(graph=loader.graph, trim_to_apps={'yard'}, convert_apps={'yard'})")
    for question in ("changes", "changes['yard'][0].dependencies", "changes['yard'][0].initial"):
        ask(question)
    quietly("everything = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps), MigrationQuestioner()).changes(graph=loader.graph)")
    ask("everything")
    show("A dependency on an application made earlier: the autodetector asked for yard alone when fleet has migrations and yard has none makes yard's first migration depend on fleet's leaf node; asked with no application named, it makes nothing for yard")
    close_connections()


def detect(*, before=(), after=(), questioner=None, **answers) -> Said:
    """What the autodetector makes of a change of the script's own. The from-state is the one
    the loader makes from the migration files and the to-state the one ProjectState.from_apps
    makes from the models; the state halves of the operations in `before` are run on both, to
    set the scene, and those in `after` on the to-state alone, which is the change. The answer
    is each migration that changes() returns, with its operations."""
    from django.apps import apps
    from django.db.migrations.autodetector import MigrationAutodetector
    from django.db.migrations.loader import MigrationLoader
    from django.db.migrations.questioner import MigrationQuestioner
    from django.db.migrations.state import ProjectState

    loader = MigrationLoader(None)
    from_state, to_state = loader.project_state(), ProjectState.from_apps(apps)
    for operation in before:
        operation.state_forwards("yard", from_state)
        operation.state_forwards("yard", to_state)
    for operation in after:
        operation.state_forwards("yard", to_state)
    autodetector = MigrationAutodetector(from_state, to_state, questioner or MigrationQuestioner(defaults=answers))
    changes = autodetector.changes(graph=loader.graph)
    return Said("; ".join(f"{migration}: [{', '.join(operation_detail(operation) for operation in migration.operations)}]" for migrations in changes.values() for migration in migrations) or "no changes")


def logged(text: str) -> None:
    """What a questioner that asks no one is given as its `log`: each thing logged is a line `logs`."""
    LINES.append("  " * len(STACK) + f"logs {text!r}")


@part("detection")
def detection() -> None:
    """Blocks 73 to 75, 78 and 79: the autodetector asked about changes of the script's own."""
    set_up()

    from django.core.validators import RegexValidator
    from django.db import models

    from harbour import serials

    class Afloat(models.Manager):
        use_in_migrations = True

    ASKING.update(detect=detect, logged=logged, functools=functools, re=re, RegexValidator=RegexValidator, next_serial=serials.next_serial, Afloat=Afloat, field_said=field_said)

    quietly("autodetector = MigrationAutodetector(ProjectState(), ProjectState())")
    for question in (
        "autodetector.deep_deconstruct(models.CharField(max_length=40))", "models.CharField(max_length=40).deconstruct()",
        "autodetector.deep_deconstruct(models.ForeignKey('fleet.Port', models.CASCADE))", "autodetector.deep_deconstruct(models.CharField(max_length=8, default=next_serial))",
        "autodetector.deep_deconstruct(functools.partial(round, ndigits=2))", "autodetector.deep_deconstruct(re.compile('^M-[0-9]{4}$', re.IGNORECASE))",
        "autodetector.deep_deconstruct(re.compile('^M-[0-9]{4}$', re.IGNORECASE)).pattern", "autodetector.deep_deconstruct(re.compile('^M-')) == autodetector.deep_deconstruct(re.compile('^M-'))",
        "autodetector.deep_deconstruct(RegexValidator('^M-'))", "RegexValidator('^M-').deconstruct()", "autodetector.deep_deconstruct(models.Model)",
        "autodetector.deep_deconstruct([models.Index(fields=['dock'], name='by_dock')])", "autodetector.deep_deconstruct({'default': next_serial, 'choices': ('a', 'b')})",
        "autodetector.deep_deconstruct(models.CharField(max_length=40)) == autodetector.deep_deconstruct(models.CharField(max_length=40))",
        "models.CharField(max_length=40) == models.CharField(max_length=40)",
    ):
        ask(question)
    quietly("state = MigrationLoader(None).project_state()")
    ask("full(autodetector.only_relation_agnostic_fields(state.models['yard', 'repair'].fields))")
    ask("full(autodetector.only_relation_agnostic_fields(state.models['yard', 'dock'].fields))")
    show("deep_deconstruct: a field, and whatever its arguments hold, turned into values that can be compared, which is how the autodetector tells that a field has changed; and only_relation_agnostic_fields, a model's fields without their names and without what a relation points at, by which it tells a renamed model")

    step("changes of the script's own are put to the autodetector by `detect`:")
    code(detect)
    ask("detect()")
    ask("detect(after=[migrations.RenameModel('Dock', 'Basin')], ask_rename_model=True)")
    ask("detect(after=[migrations.RenameModel('Dock', 'Basin')], ask_rename_model=False)")
    ask("detect(after=[migrations.RenameModel('Dock', 'Basin'), migrations.AlterField('basin', 'name', models.CharField(max_length=80))], ask_rename_model=True)")
    ask("detect(after=[migrations.RenameModel('Dock', 'Basin'), migrations.AddField('basin', 'metres', models.PositiveSmallIntegerField(default=120))], ask_rename_model=True)")
    show("A model renamed (to-states of the script's own, in which Dock is Basin): with a questioner that says yes, a RenameModel; with one that says no, the old model deleted and the new one created; the question is put only where the two models' fields are the same")

    for question in (
        "detect(after=[migrations.CreateModel('DryDock', [], options={'proxy': True}, bases=('yard.dock',))])",
        "detect(before=[migrations.CreateModel('DryDock', [], options={'proxy': True}, bases=('yard.dock',))], after=[migrations.DeleteModel('DryDock')])",
        "detect(after=[migrations.AlterModelOptions('dock', {'ordering': ['name']})])", "detect(after=[migrations.AlterModelTable('dock', 'yard_drydock')])",
        "detect(after=[migrations.AlterModelTableComment('dock', 'The dry docks')])", "detect(after=[migrations.AlterModelManagers('dock', [('afloat', Afloat())])])",
        "detect(after=[migrations.AlterModelManagers('dock', [('afloat', models.Manager())])])", "detect(after=[migrations.AlterOrderWithRespectTo('repair', 'dock')])",
        "detect(after=[migrations.DeleteModel('Repair')])", "detect(after=[migrations.DeleteModel('Repair'), migrations.DeleteModel('Dock')])",
    ):
        ask(question)
    show("A proxy, an option, a table, a manager (states of the script's own: where a question has `before`, the from-state is the script's making too): the operation the autodetector makes for each kind of change to a model that is not a change to its fields, and for models taken away")

    for question in (
        "detect(after=[migrations.AlterField('dock', 'name', models.CharField(max_length=40, verbose_name='dock name'))])",
        "detect(after=[migrations.AlterField('dock', 'name', models.CharField(max_length=80))])",
        "detect(before=[migrations.AlterField('repair', 'notes', models.TextField(blank=True, null=True))], after=[migrations.AlterField('repair', 'notes', models.TextField(blank=True))])",
        "detect(before=[migrations.AlterField('repair', 'notes', models.TextField(blank=True, null=True))], after=[migrations.AlterField('repair', 'notes', models.TextField(blank=True))], questioner=NonInteractiveMigrationQuestioner(log=logged))",
        "detect(after=[migrations.AlterField('dock', 'name', models.ForeignKey('fleet.Ship', models.CASCADE, null=True))])",
        "detect(after=[migrations.AlterField('dock', 'name', models.ManyToManyField('fleet.Ship'))])",
        "detect(after=[migrations.RenameField('repair', 'started', 'begun')], ask_rename=True)", "detect(after=[migrations.RenameField('repair', 'started', 'begun')], ask_rename=False)",
        "detect(after=[migrations.RenameField('repair', 'started', 'begun'), migrations.AlterField('repair', 'begun', models.DateField(db_column='started'))], ask_rename=True)",
        "detect(after=[migrations.RenameField('repair', 'started', 'begun'), migrations.AlterField('repair', 'begun', models.DateField(null=True))], ask_rename=True)",
        "detect(after=[migrations.AddField('repair', 'foreman', models.CharField(max_length=60))])",
        "detect(after=[migrations.AddField('repair', 'foreman', models.CharField(max_length=60, blank=True))])",
        "detect(after=[migrations.AddField('repair', 'logged', models.DateTimeField(auto_now_add=True))])",
    ):
        ask(question)
    show("A field altered or not (states of the script's own, as in the block before): a change that is not the column's still makes an AlterField; a field made not null asks the questioner; a column that becomes a many-to-many field is removed and added; a rename is asked about only where the two fields deconstruct alike, or alike but for a db_column that keeps the old column")

    quietly("by_dock = migrations.AddIndex('repair', models.Index(fields=['dock', 'started'], name='repair_by_dock'))")
    quietly("recent = models.CheckConstraint(condition=models.Q(started__gte=datetime.date(2000, 1, 1)), name='repair_this_century')")
    quietly("worded = models.CheckConstraint(condition=models.Q(started__gte=datetime.date(2000, 1, 1)), name='repair_this_century', violation_error_message='Too long ago.')")
    quietly("later = models.CheckConstraint(condition=models.Q(started__gte=datetime.date(2020, 1, 1)), name='repair_this_century')")
    for question in (
        "detect(after=[by_dock])", "detect(before=[by_dock], after=[migrations.RenameIndex('repair', new_name='repair_dock_day', old_name='repair_by_dock')])",
        "detect(before=[by_dock], after=[migrations.RemoveIndex('repair', 'repair_by_dock'), migrations.AddIndex('repair', models.Index(fields=['ship', 'started'], name='repair_by_dock'))])",
        "detect(before=[by_dock], after=[migrations.RemoveIndex('repair', 'repair_by_dock')])",
        "detect(before=[migrations.AlterIndexTogether('repair', {('ship', 'started')})], after=[migrations.AlterIndexTogether('repair', set()), migrations.AddIndex('repair', models.Index(fields=['ship', 'started'], name='repair_ship_day'))])",
        "detect(after=[migrations.AddConstraint('repair', recent)])", "detect(before=[migrations.AddConstraint('repair', recent)], after=[migrations.AlterConstraint('repair', 'repair_this_century', worded)])",
        "detect(before=[migrations.AddConstraint('repair', recent)], after=[migrations.AlterConstraint('repair', 'repair_this_century', later)])",
        "detect(after=[migrations.AlterUniqueTogether('repair', {('ship', 'started')})])",
        "detect(before=[migrations.AlterUniqueTogether('repair', {('ship', 'started')})], after=[migrations.AlterUniqueTogether('repair', {('dock', 'started')})])",
        "detect(before=[migrations.AlterUniqueTogether('repair', {('ship', 'started')})], after=[migrations.AlterUniqueTogether('repair', {('ship', 'started'), ('dock', 'started')})])",
        "detect(before=[migrations.AlterUniqueTogether('repair', {('ship', 'started')})], after=[migrations.AlterUniqueTogether('repair', set())])",
    ):
        ask(question)
    show("Indexes and constraints (states of the script's own, as in the two blocks before): an index that differs only in its name is renamed, one that differs otherwise is removed and added; a constraint that differs only in what does not reach the database is altered, one that differs otherwise is removed and added; and unique_together")

    step("to-states of the script's own in which a model of fleet and a model of yard have both changed, and the autodetector asked for yard alone, as `makemigrations yard` asks it")
    trimming = {(MA, "MigrationAutodetector._trim_to_apps"): lambda f: f"MigrationAutodetector._trim_to_apps(changes={whole(f.f_locals['changes'])}, app_labels={brief(f.f_locals['app_labels'])})"}
    trimmed = says(MA, "MigrationAutodetector._trim_to_apps", how=lambda f, v: str(whole(v)))
    quietly("loader = MigrationLoader(None)")
    quietly("deeper = migrations.AddField('port', 'depth', models.PositiveSmallIntegerField(default=10))")
    for change in (
        "migrations.AddField('dock', 'metres', models.PositiveSmallIntegerField(default=120))",
        "migrations.AddIndex('repair', models.Index(fields=['dock', 'started'], name='repair_by_dock'))",
    ):
        quietly("to_state = ProjectState.from_apps(apps)")
        quietly("deeper.state_forwards('fleet', to_state)")
        quietly(f"{change}.state_forwards('yard', to_state)")
        with recorded(trimming, after=trimmed):
            do("changes = MigrationAutodetector(loader.project_state(), to_state).changes(loader.graph, trim_to_apps={'yard'})")
        ask("{label: sorted(migration.dependencies) for label, [migration] in changes.items()}")
    show("_trim_to_apps: asked for yard alone when fleet has a change too, changes() drops fleet's migration where yard's migration depends on none of fleet's, and keeps it where yard's depends on one: an index on Repair, which points at fleet's Ship, is enough to keep it")
    close_connections()


# ---------------------------------------------------------------------------------------------
# The questioner (blocks 88 and 89).


class Keyboard(io.TextIOBase):
    """What the interactive questioner reads its answers from in this part, in place of the
    process's standard input: the lines the script has typed ahead, each written as a line
    `stdin` of the recording as input() reads it."""

    def __init__(self):
        self.lines = []

    def readline(self, size: int = -1) -> str:
        if not self.lines:
            return ""
        line = self.lines.pop(0)
        if LINES and LINES[-1].endswith(NOT_ENDED):  # the prompt: the line typed ends its line
            LINES[-1] = LINES[-1][: -len(NOT_ENDED)]
            ASKING["out"].open_line = False
        LINES.append("  " * len(STACK) + f"stdin  | {line}")
        return line + "\n"


@part("questioner")
def the_questioner() -> None:
    """Blocks 88 and 89: the three questioners."""
    set_up()

    from django.core.management.base import OutputWrapper

    keyboard = Keyboard()
    sys.stdin = keyboard
    ASKING.update(logged=logged, keyboard=keyboard, OutputWrapper=OutputWrapper)

    quietly("plain = MigrationQuestioner()")
    quietly("yes = MigrationQuestioner(defaults={'ask_initial': True, 'ask_rename': True, 'ask_rename_model': True, 'ask_merge': True})")
    quietly("silent = NonInteractiveMigrationQuestioner(log=logged)")
    quietly("old, new = ModelState('yard', 'Dock', []), ModelState('yard', 'Basin', [])")
    for method, arguments in (
        ("ask_initial", "'yard'"), ("ask_rename", "'repair', 'started', 'begun', models.DateField()"), ("ask_rename_model", "old, new"), ("ask_merge", "'yard'"),
        ("ask_not_null_addition", "'foreman', 'repair'"), ("ask_not_null_alteration", "'notes', 'repair'"), ("ask_auto_now_add_addition", "'logged', 'repair'"),
        ("ask_unique_callable_default_addition", "'serial', 'manifest'"),
    ):
        for name in ("plain", "yes", "silent"):
            ask(f"{name}.{method}({arguments})")
    ask("MigrationQuestioner(specified_apps={'yard'}).ask_initial('yard')")
    ask("NonInteractiveMigrationQuestioner(verbosity=0, log=logged).ask_not_null_addition('foreman', 'repair')")
    show("The answers of the questioners that ask no one: MigrationQuestioner with no defaults (`plain`), with defaults that say yes (`yes`), and NonInteractiveMigrationQuestioner (`silent`), each asked each question; yard has a migrations package with a migration in it")

    step("an interactive questioner, given a prompt_output that writes into this recording as `stdout` lines, as makemigrations gives it its own standard output; and for the process's standard input a stand-in of the script's own, from which input() reads the lines the script types ahead:")
    code(Keyboard)
    quietly("asking = InteractiveMigrationQuestioner(prompt_output=OutputWrapper(out))")

    def typed(lines: list, statement: str) -> None:
        quietly(f"keyboard.lines = {lines!r}")
        do(statement)
        ask("answer")

    typed(["y"], "answer = asking.ask_rename('repair', 'started', 'begun', models.DateField())")
    typed([""], "answer = asking.ask_rename('repair', 'started', 'begun', models.DateField())")
    typed(["perhaps", "No"], "answer = asking.ask_rename('repair', 'started', 'begun', models.DateField())")
    typed(["y"], "answer = asking.ask_rename_model(old, new)")
    typed(["y"], "answer = asking.ask_merge('yard')")
    show("The interactive questioner, with answers typed ahead: the questions answered yes or no")

    typed(["1", "timezone.now"], "answer = asking.ask_not_null_addition('foreman', 'repair')")
    typed(["1", "forman", "", "'not recorded'"], "answer = asking.ask_not_null_addition('foreman', 'repair')")
    quietly("keyboard.lines = ['1', 'exit']")
    do("answer = asking.ask_not_null_addition('foreman', 'repair')")
    quietly("keyboard.lines = ['7', 'two', '2']")
    do("answer = asking.ask_not_null_addition('foreman', 'repair')")
    show("The interactive questioner asked for a default for a new column that is not null: the value typed is evaluated as Python, with datetime and timezone to hand; `exit` raises SystemExit with the status 1, and the second choice, to quit, with 3 (the script catches both: no process ends here)")

    typed(["2"], "answer = asking.ask_not_null_alteration('notes', 'repair')")
    typed(["1", "''"], "answer = asking.ask_not_null_alteration('notes', 'repair')")
    typed(["1", ""], "answer = asking.ask_auto_now_add_addition('logged', 'repair')")
    typed(["1"], "answer = asking.ask_unique_callable_default_addition('serial', 'manifest')")
    quietly("dry = InteractiveMigrationQuestioner(dry_run=True, prompt_output=OutputWrapper(out))")
    for question in ("dry.ask_not_null_addition('foreman', 'repair')", "dry.ask_not_null_alteration('notes', 'repair')", "dry.ask_auto_now_add_addition('logged', 'repair')"):
        ask(question)
    typed(["y"], "answer = dry.ask_rename('repair', 'started', 'begun', models.DateField())")
    show("The interactive questioner's other questions: a column made not null, with its choice to leave the rows to the developer; a field with auto_now_add, whose default is offered; a unique field with a callable default; and a questioner made for a dry run, which answers None to the three questions about a default without asking, and still asks about a rename")
    close_connections()


# ---------------------------------------------------------------------------------------------
# The optimizer (blocks 90 and 91).

OPERATIONS_IN_DETAIL = False  # whether brief writes an operation as operation_detail does: set in the part on the optimizer


def inner_pass(frame) -> str:
    return f"MigrationOptimizer.optimize_inner(<{len(frame.f_locals['operations'])} operations>)"


@part("optimizer")
def the_optimizer() -> None:
    """Blocks 90 and 91: each operation's reduce, and MigrationOptimizer over whole lists."""
    global OPERATIONS_IN_DETAIL
    set_up()
    OPERATIONS_IN_DETAIL = True

    step("operations of the script's own; in this part an operation is written with what tells it from another of its class")
    for line in (
        "create = migrations.CreateModel('Crane', [('id', models.BigAutoField(primary_key=True))])",
        "tonnes = migrations.AddField('crane', 'tonnes', models.PositiveSmallIntegerField(default=5))",
        "heavier = migrations.AlterField('crane', 'tonnes', models.PositiveIntegerField(default=5))",
        "heaviest = migrations.AlterField('crane', 'tonnes', models.BigIntegerField(default=5))",
        "load = migrations.RenameField('crane', 'tonnes', 'load')",
        "burden = migrations.RenameField('crane', 'load', 'burden')",
        "no_tonnes = migrations.RemoveField('crane', 'tonnes')",
        "hoist = migrations.RenameModel('Crane', 'Hoist')",
        "options = migrations.AlterModelOptions('crane', {'ordering': ['id']})",
        "by_tonnes = migrations.AddIndex('crane', models.Index(fields=['tonnes'], name='crane_by_tonnes'))",
        "no_index = migrations.RemoveIndex('crane', 'crane_by_tonnes')",
        "light = migrations.AddConstraint('crane', models.CheckConstraint(condition=models.Q(tonnes__lt=100), name='crane_is_light'))",
        "no_light = migrations.RemoveConstraint('crane', 'crane_is_light')",
        "no_crane = migrations.DeleteModel('Crane')",
        "metres = migrations.AddField('dock', 'metres', models.PositiveSmallIntegerField(default=120))",
        "on_dock = migrations.AddField('crane', 'dock', models.ForeignKey('yard.Dock', models.CASCADE))",
        "sql = migrations.RunSQL('UPDATE yard_dock SET name = name')",
        "passing = migrations.RunSQL('UPDATE yard_dock SET name = name', elidable=True)",
    ):
        quietly(line)
    for question in (
        "create.reduce(tonnes, 'yard')", "create.reduce(no_crane, 'yard')", "create.reduce(hoist, 'yard')", "create.reduce(options, 'yard')", "create.reduce(by_tonnes, 'yard')",
        "create.reduce(on_dock, 'yard')", "tonnes.reduce(heavier, 'yard')", "tonnes.reduce(no_tonnes, 'yard')", "tonnes.reduce(load, 'yard')", "heavier.reduce(heaviest, 'yard')",
        "heavier.reduce(no_tonnes, 'yard')", "heavier.reduce(load, 'yard')", "load.reduce(burden, 'yard')", "no_tonnes.reduce(no_crane, 'yard')", "by_tonnes.reduce(no_index, 'yard')",
        "light.reduce(no_light, 'yard')", "tonnes.reduce(metres, 'yard')", "metres.reduce(tonnes, 'yard')", "create.reduce(metres, 'yard')", "no_tonnes.reduce(tonnes, 'yard')",
        "tonnes.reduce(by_tonnes, 'yard')", "on_dock.reduce(metres, 'yard')", "metres.reduce(on_dock, 'yard')", "sql.reduce(tonnes, 'yard')", "tonnes.reduce(sql, 'yard')",
        "passing.reduce(tonnes, 'yard')", "tonnes.reduce(passing, 'yard')", "migrations.RunPython(migrations.RunPython.noop).reduce(tonnes, 'yard')",
        "create.reduce(migrations.RunPython(migrations.RunPython.noop), 'yard')",
    ):
        ask(question)
    show("reduce, pair by pair: what an operation answers when the optimizer asks whether the operation after it can be folded into it: a list of the operations to put in place of the two, True if the second may be moved across it, False if it may not")

    passes = {(MO, "MigrationOptimizer.optimize"): lambda f: f"MigrationOptimizer.optimize(<{len(f.f_locals['operations'])} operations>, 'yard')", (MO, "MigrationOptimizer.optimize_inner"): inner_pass}
    results = says(MO, "MigrationOptimizer.optimize_inner", "MigrationOptimizer.optimize", how=lambda f, v: str(whole(v)))
    quietly("optimizer = MigrationOptimizer()")
    for title, operations in (
        ("a fold to the right, and another on the next pass", "[create, tonnes, heavier]"),
        ("an operation between that may be moved across", "[create, metres, tonnes]"),
        ("a model created between, which the folded operation points at: the fold goes right, to where the last operation stood", "[create, migrations.CreateModel('Hook', [('id', models.BigAutoField(primary_key=True))]), migrations.AddField('crane', 'hook', models.ForeignKey('yard.Hook', models.CASCADE))]"),
        ("an operation between that points at the model: the fold goes left, to where the first operation stood", "[create, migrations.CreateModel('Hook', [('id', models.BigAutoField(primary_key=True)), ('crane', models.ForeignKey('yard.Crane', models.CASCADE))]), tonnes]"),
        ("a RunPython between, which nothing is moved across", "[create, migrations.RunPython(migrations.RunPython.noop), tonnes]"),
        ("a RunSQL between that is marked elidable", "[create, passing, tonnes]"),
        ("a model created and deleted, with a field between", "[create, tonnes, no_crane]"),
    ):
        step(f"{title}:")
        quietly(f"operations = {operations}")
        ask("whole(operations)")
        with recorded(passes, after=results):
            do("result = optimizer.optimize(operations, 'yard')")
        ask("optimizer._iterations")
    ask("optimizer.optimize([create], None)")
    show("optimize, whole lists: each pass of optimize_inner makes at most one fold and returns the new list, and optimize calls it until a pass returns the list it was given")
    close_connections()


# ---------------------------------------------------------------------------------------------
# The serializer and the writer (blocks 93 to 99).


def written(value) -> Said:
    """MigrationWriter.serialize(value): the text it writes for the value, and then the import
    lines the text needs, sorted (a set holds them)."""
    from django.db.migrations.writer import MigrationWriter

    text, imports = MigrationWriter.serialize(value)
    text = text.replace("\n", "\\n")  # a text of several lines on one, as an exception's message is written
    return Said(f"{text}   needs {sorted(imports)!r}" if imports else f"{text}   needs no import")


def text_shown(name: str) -> None:
    """The text a name of the lines above holds, a line to a line."""
    note(f"{name}:")
    for line in str(ASKING[name]).splitlines():
        note(("  | " + line).rstrip())


@part("serializer")
def the_serializer() -> None:
    """Blocks 93 to 96: what MigrationWriter.serialize writes for a value."""
    import collections
    import pathlib
    import uuid
    import zoneinfo

    set_up()

    from django.conf import SettingsReference
    from django.db import models
    from django.db.migrations.serializer import BaseSerializer, Serializer, serializer_factory
    from django.utils.deconstruct import deconstructible
    from django.utils.translation import gettext_lazy

    from harbour import serials
    from harbour.crew.models import Rank

    @deconstructible(path="__main__.Tide")
    class Tide:
        """A value of the script's own that knows how to deconstruct itself."""

        def __init__(self, high, low=0):
            self.high, self.low = high, low

    class Fathoms:
        """A value of the script's own that Django has no serializer for."""

        def __init__(self, number):
            self.number = number

    class FathomsSerializer(BaseSerializer):
        """A serializer of the script's own for Fathoms, as a project registers one."""

        def serialize(self):
            return f"harbour.depths.Fathoms({self.value.number})", {"import harbour.depths"}

    def nested():
        def inner():
            return 1
        return inner

    class Afloat(models.Manager):
        """A manager of the script's own that asks to be kept in migrations."""

        use_in_migrations = True

    sys.modules["__main__"].Tide = Tide
    sys.modules["__main__"].Afloat = Afloat
    ASKING.update(Afloat=Afloat)
    ASKING.update(
        written=written, decimal=decimal, uuid=uuid, pathlib=pathlib, zoneinfo=zoneinfo, functools=functools, re=re, collections=collections, Rank=Rank,
        next_serial=serials.next_serial, SettingsReference=SettingsReference, gettext_lazy=gettext_lazy, Tide=Tide, Fathoms=Fathoms, FathomsSerializer=FathomsSerializer,
        serializer_factory=serializer_factory, nested=nested, types=types, Serializer=Serializer,
    )

    for question in (
        "written('North dock')", "written(480)", "written(None)", "written(True)", "written(b'M-0001')", "written(1.5)", "written(float('nan'))", "written(float('inf'))",
        "written(decimal.Decimal('12.50'))", "written(datetime.datetime(2026, 3, 2, 9, 0, tzinfo=datetime.UTC))",
        "written(datetime.datetime(2026, 3, 2, 10, 0, tzinfo=zoneinfo.ZoneInfo('Europe/Oslo')))", "written(datetime.datetime(2026, 3, 2, 9, 0))",
        "written(datetime.date(2026, 3, 2))", "written(datetime.time(9, 0))", "written(datetime.timedelta(days=14))", "written(uuid.UUID('12345678-1234-5678-1234-567812345678'))",
        "written(['Bergen', 'Leith'])", "written(('Bergen',))", "written(())", "written({'Leith', 'Bergen', 'Lisbon'})", "written(set())", "written(frozenset({2, 1}))",
        "written({'tonnage': 480, 'name': 'Petrel'})", "written(range(1, 4))", "written(iter(['Bergen']))",
    ):
        ask(question)
    show("Plain values written, one by one: the text MigrationWriter.serialize writes for a value of each plain kind, and the imports the text needs; a set and a dict are written sorted")

    for question in (
        "written(uuid.SafeUUID.safe)", "written(re.IGNORECASE | re.MULTILINE)", "written(Rank.MATE)", "written(models.CharField(max_length=10, choices=Rank))",
        "written(re.compile('^M-[0-9]{4}$'))", "written(re.compile('^m-', re.IGNORECASE))", "written(functools.partial(round, ndigits=2))", "written(next_serial)",
        "written(datetime.date.today)", "written(len)", "written(pathlib.PurePosixPath('manifests/2026'))", "written(pathlib.Path('manifests'))",
        "written(zoneinfo.ZoneInfo('Europe/Oslo'))", "written(datetime.UTC)", "written(models.Model)", "written(int)", "written(types.NoneType)", "written(Sailor)",
        "written(list[int])", "written(SettingsReference(settings.AUTH_USER_MODEL, 'AUTH_USER_MODEL'))", "written(settings.AUTH_USER_MODEL)", "written(gettext_lazy('Dock'))",
        "written(models.CASCADE)", "written(models.SET_NULL)", "written(models.DB_CASCADE)",
    ):
        ask(question)
    show("Named things written, one by one: an enum member, a member of a Choices class, a compiled regular expression, a partial, a function, a path (a concrete one is written as the pure path of the machine's kind, here Windows), a time zone, a class, a reference to a setting, a lazy string; and three values of on_delete, CASCADE, SET_NULL and DB_CASCADE, each written by its name (the block on which serializer has the serializers of the first and the third)")

    for question in (
        "written(models.SET(1))", "written(models.CharField(max_length=40))",
        "written(models.ForeignKey('fleet.Port', models.CASCADE, related_name='docks'))", "written(models.CharField(max_length=8, default=next_serial))",
        "written(Dock._meta.get_field('port'))", "written(Sailor.objects)", "written(models.Manager())", "Afloat.use_in_migrations", "written(Afloat())", "Afloat().deconstruct()",
        "written(migrations.AddField('dock', 'metres', models.PositiveSmallIntegerField(default=120)))",
        "written(models.Index(fields=['dock', 'begun'], name='repair_by_dock'))", "written(models.Q(tonnage__gt=0) | models.Q(name='Petrel'))", "written(models.F('crates') * models.F('kilos_each'))",
        "written(models.CheckConstraint(condition=models.Q(tonnage__gt=0), name='ship_has_tonnage'))", "written(Tide(high=4.2))", "Tide(high=4.2).deconstruct()",
    ):
        ask(question)
    step("Tide and Afloat are classes of the script's own, which the script has made attributes of its module, __main__, where their deconstruct methods look for them:")
    code(Tide, Afloat)
    show("Deconstructible values written, one by one: what knows how to deconstruct itself (what models.SET returns, a field, a manager, an operation, an index, a Q, an expression, a constraint, a class of the script's own) is written as a call with the arguments it deconstructs to: of its class for most, of models.SET for what SET(1) returned, and of the queryset class's as_manager for a manager that as_manager made")

    for question in ("written(lambda: 1)", "written(nested())", "written(object())", "written(Fathoms(12))", "written(models.CharField(max_length=40, default=lambda: 'x'))"):
        ask(question)
    step("`nested` is a function of the script's own that returns one defined inside it:")
    code(nested)
    show("What cannot be serialized: a lambda, a function defined inside a function, and an object that has no serializer and no deconstruct")

    for question in (
        "type(serializer_factory('North dock')).__name__", "type(serializer_factory(True)).__name__", "type(serializer_factory(1.5)).__name__",
        "type(serializer_factory(datetime.datetime(2026, 3, 2, 9, 0))).__name__", "type(serializer_factory(datetime.date(2026, 3, 2))).__name__",
        "type(serializer_factory(Rank.MATE)).__name__", "type(serializer_factory(uuid.SafeUUID.safe)).__name__", "type(serializer_factory(models.CharField(max_length=40))).__name__",
        "type(serializer_factory(Sailor.objects)).__name__", "type(serializer_factory(migrations.RunSQL('SELECT 1'))).__name__", "type(serializer_factory(Sailor)).__name__",
        "type(serializer_factory(Tide(high=4.2))).__name__", "type(serializer_factory(models.Q(tonnage__gt=0))).__name__", "type(serializer_factory(models.CASCADE)).__name__",
        "type(serializer_factory(models.DB_CASCADE)).__name__", "type(serializer_factory(models.SET(1))).__name__", "type(serializer_factory(('Bergen',))).__name__",
        "type(serializer_factory(collections.OrderedDict(a=1))).__name__", "type(serializer_factory(iter(['Bergen']))).__name__", "type(serializer_factory(gettext_lazy('Dock'))).__name__",
        "type(serializer_factory(pathlib.Path('manifests'))).__name__", "hasattr(models.SET(1), 'deconstruct')", "hasattr(models.CASCADE, 'deconstruct')",
    ):
        ask(question)
    show("Which serializer: serializer_factory tries a field, a manager, an operation, a class, and anything with a deconstruct method, in that order, and then the registry, an entry at a time")

    step("Fathoms is a class of the script's own with no deconstruct method, and FathomsSerializer a serializer for it:")
    code(Fathoms, FathomsSerializer)
    ask("written(Fathoms(12))")
    quietly("MigrationWriter.register_serializer(Fathoms, FathomsSerializer)")
    ask("list(Serializer._registry)[-1] is Fathoms")
    ask("written(Fathoms(12))")
    ask("type(serializer_factory(Fathoms(12))).__name__")
    ask("MigrationWriter.register_serializer(Fathoms, Fathoms)")
    quietly("MigrationWriter.unregister_serializer(Fathoms)")
    ask("Fathoms in Serializer._registry")
    ask("written(Fathoms(12))")
    show("A serializer registered: MigrationWriter.register_serializer puts a class and its serializer at the end of the registry, and unregister_serializer takes it out again")
    close_connections()


@part("writer")
def the_writer() -> None:
    """Blocks 97 to 99: OperationWriter, MigrationWriter.as_string and where the file goes."""
    set_up()

    from django.contrib.postgres.operations import TrigramExtension

    ASKING.update(made=made, TrigramExtension=TrigramExtension, overriding=overriding)

    quietly("text, imports = OperationWriter(migrations.AddField('dock', 'metres', models.PositiveSmallIntegerField(default=120), preserve_default=False)).serialize()")
    text_shown("text")
    ask("imports")
    quietly("create = migrations.CreateModel('Crane', [('id', models.BigAutoField(primary_key=True)), ('dock', models.ForeignKey('yard.Dock', models.CASCADE))], options={'ordering': ['id']}, bases=('yard.dock',))")
    ask("create.serialization_expand_args")
    quietly("text, imports = OperationWriter(create).serialize()")
    text_shown("text")
    ask("sorted(imports)")
    quietly("text, imports = OperationWriter(migrations.CreateModel('Crane', [('id', models.BigAutoField(primary_key=True))]), indentation=0).serialize()")
    text_shown("text")
    quietly("text, imports = OperationWriter(migrations.AlterModelManagers('dock', [('objects', models.Manager())])).serialize()")
    text_shown("text")
    quietly("text, imports = OperationWriter(TrigramExtension()).serialize()")
    text_shown("text")
    ask("imports")
    ask("getattr(migrations, 'TrigramExtension', None)")
    show("OperationWriter: an operation written as a call of its class, with the arguments its deconstruct returns; the arguments a class names in serialization_expand_args are spread over lines, an item to a line; an operation that django.db.migrations does not export is written by its module, with an import (django.contrib.postgres's TrigramExtension, which is made here and not run)")

    quietly("loader = MigrationLoader(None)")
    quietly("migration = loader.disk_migrations['fleet', '0001_initial']")
    quietly("writer = MigrationWriter(migration)")
    ask("sorted(set().union(*(OperationWriter(operation).serialize()[1] for operation in migration.operations)))")
    quietly("head = writer.as_string().split('    operations = [')[0]")
    text_shown("head")
    ask("writer.needs_manual_porting")
    ASKING.update(pathlib=__import__("pathlib"))
    ask("writer.as_string().splitlines()[1:] == pathlib.Path(writer.path).read_text().splitlines()[1:]")
    ask("MigrationWriter(migration, include_header=False).as_string().splitlines()[0]")
    show("as_string, for fleet.0001_initial as the loader made it: the imports its operations ask for, and the file's text as far as its operations, in which the two imports of django.db are merged into one line; but for its first line, the text is the file's")

    step("migrations of the script's own, made by `made` (which the block on suggest_name shows), to see the other parts of the text:")
    quietly("text = MigrationWriter(made(dependencies=[('yard', '0001_initial'), ('fleet', '0001_initial'), ('crew', '0002_initial')]), include_header=False).as_string()")
    text_shown("text")
    quietly("text = MigrationWriter(made(migrations.RunSQL('SELECT 1'), initial=True, atomic=False, run_before=[('office', '0001_initial')], replaces=[('yard', '0001_initial'), ('yard', '0002_made')], dependencies=[('__setting__', 'AUTH_USER_MODEL')]), include_header=False).as_string()")
    text_shown("text")
    show("as_string, the other parts: dependencies are written sorted, whatever their order in the migration; and a migration of the script's own that has every part: replaces, initial, atomic, run_before, and a dependency on a setting, which is written as a call of swappable_dependency")

    step("basedir and path are whole paths, from the root of the file system; the run's directory, with which each begins, is left out of the answers here, as it is of every path in the recording")
    for question in ("writer.filename", "writer.basedir", "writer.path", "os.path.isabs(writer.basedir)", "os.path.isabs(writer.path)", "MigrationWriter(made()).path"):
        ask(question)
    for question in (
        "overriding({'yard': None}, lambda: MigrationWriter(made()).basedir)", "overriding({'yard': 'nowhere.history'}, lambda: MigrationWriter(made()).basedir)",
        "overriding({'yard': 'harbour.yard.archive'}, lambda: MigrationWriter(made()).basedir)",
        "os.path.exists(overriding({'yard': 'harbour.yard.archive'}, lambda: MigrationWriter(made()).basedir))",
        "overriding({'yard': 'harbour.history.yard'}, lambda: MigrationWriter(made()).basedir)",
    ):
        ask(question)
    ASKING.update(os_walk=lambda relative: Whole(sorted(os.path.relpath(os.path.join(directory, name), SCRATCH).replace("\\", "/") for directory, _, names in os.walk(path_of(relative)) for name in names)))
    ask("os_walk('harbour/history')")
    shutil.rmtree(path_of("harbour/history"))
    forget("harbour.history")
    step("the script has removed the directory harbour/history that the last question made, and taken its modules out of sys.modules")
    show("Where the file goes: the directory of the application's migrations package, or where that package would be; with MIGRATION_MODULES None for the application, basedir raises; with it naming a package that is not there: directly under the application's own package, basedir only says where it would be; under another package that can be imported, it makes it, a directory and an __init__.py for each missing part of the name; under none that can be imported, it raises")
    close_connections()


# ---------------------------------------------------------------------------------------------
# Yard's second and third versions.


@part("rows")
def the_rows() -> None:
    """The rows the later blocks work on, put in with the models of yard's first version."""
    set_up()

    from harbour.fleet.models import Port, Ship
    from harbour.yard.models import Dock, Repair

    bergen = Port.objects.create(name="Bergen", country="Norway")
    petrel = Ship.objects.create(name="Petrel", tonnage=480, home=bergen)
    gannet = Ship.objects.create(name="Gannet", tonnage=1200, home=bergen)
    north = Dock.objects.create(name="North dock", port=bergen)
    Repair.objects.create(ship=petrel, dock=north, started=datetime.date(2026, 3, 2), notes="Hull scraped and painted.")
    Repair.objects.create(ship=gannet, dock=north, started=datetime.date(2026, 5, 18))
    note("Port: " + ", ".join(f"{port.pk} {port.name} ({port.country})" for port in Port.objects.order_by("pk")))
    note("Ship: " + ", ".join(f"{ship.pk} {ship.name} ({ship.tonnage} tons, home {ship.home.name})" for ship in Ship.objects.order_by("pk")))
    note("Dock: " + ", ".join(f"{dock.pk} {dock.name!r} (port {dock.port.name})" for dock in Dock.objects.order_by("pk")))
    note("Repair: " + ", ".join(f"{repair.pk} (ship {repair.ship.name}, dock {repair.dock.name!r}, started {repair.started}, notes {repair.notes!r})" for repair in Repair.objects.order_by("pk")))
    show("The rows the script now puts in, with the models as they stand, before yard's models change: a port, two ships, a dock and two repairs")
    close_connections()


QUESTIONS = watch(
    MQ, "MigrationQuestioner.ask_initial", "MigrationQuestioner.ask_rename", "MigrationQuestioner.ask_rename_model", "MigrationQuestioner.ask_not_null_addition",
    "MigrationQuestioner.ask_not_null_alteration", "MigrationQuestioner.ask_auto_now_add_addition", "MigrationQuestioner.ask_merge",
)
ANSWERS = says(
    MQ, "MigrationQuestioner.ask_initial", "MigrationQuestioner.ask_rename", "MigrationQuestioner.ask_rename_model", "MigrationQuestioner.ask_not_null_addition",
    "MigrationQuestioner.ask_not_null_alteration", "MigrationQuestioner.ask_auto_now_add_addition", "MigrationQuestioner.ask_merge",
)


def migrating(frame) -> str:
    """MigrationExecutor.migrate with every argument, a plan by its length."""
    return f"MigrationExecutor.migrate(targets={brief(frame.f_locals['targets'])}, plan={plan_said(frame.f_locals['plan'])}, state={brief(frame.f_locals['state'])}, fake={frame.f_locals['fake']}, fake_initial={frame.f_locals['fake_initial']})" + on(frame)


@part("nothing-to-apply")
def nothing_to_apply() -> None:
    """Block 65: migrate when every migration is applied and yard's models have moved on."""
    set_up()
    rules = {
        (CMD + "migrate", "Command.handle"): handled(), (MX, "MigrationExecutor.migration_plan"): generic, (MX, "MigrationExecutor._create_project_state"): generic,
        ("django.core.management.sql", "emit_pre_migrate_signal"): briefly(bare), ("django.core.management.sql", "emit_post_migrate_signal"): briefly(bare),
        (MA, "MigrationAutodetector.__init__"): generic, (MA, "MigrationAutodetector.changes"): generic, (MX, "MigrationExecutor.migrate"): migrating,
        (MR, "MigrationRecorder.has_table"): bare, (MR, "MigrationRecorder.ensure_schema"): bare, (MX, "MigrationExecutor.check_replacements"): bare,
        (ML, "MigrationLoader.project_state"): generic, (MS, "ProjectState.from_apps"): generic, (MX, "MigrationExecutor.__init__"): briefly(without("progress_callback")),
        (ML, "MigrationLoader.check_consistent_history"): briefly(generic),
    } | QUESTIONS
    after = ANSWERS | says(MX, "MigrationExecutor.migration_plan", how=a_plan) | says(MA, "MigrationAutodetector.changes", how=lambda f, v: str(whole(v))) | says(
        MX, "MigrationExecutor._create_project_state", "MigrationExecutor.migrate") | says(MR, "MigrationRecorder.has_table") | says(ML, "MigrationLoader.project_state") | says(MS, "ProjectState.from_apps")
    with recorded(rules, after=after):
        do("call_command('migrate', stdout=out)")
    show("Nothing to apply, the calls: migrate run in this process with yard's models at their second version; the plan is empty, emit_pre_migrate_signal and emit_post_migrate_signal are called all the same, and an autodetector with a questioner that asks no one compares the migrations' state with the models to see whether to print the notice")
    close_connections()


def of_dock_name(frame) -> str | None:
    """deep_deconstruct, where generate_altered_fields calls it for the field name of yard's Dock."""
    caller = frame.f_back
    if caller is None or caller.f_code.co_name != "generate_altered_fields":
        return None
    if (caller.f_locals.get("model_name"), caller.f_locals.get("field_name")) != ("dock", "name"):
        return None
    return f"MigrationAutodetector.deep_deconstruct({field_said(frame.f_locals['obj'])})"


@part("second-detection")
def second_detection() -> None:
    """Blocks 77 and 83: the autodetector on yard's second version, before its migration is written."""
    global OPERATIONS_IN_DETAIL
    set_up()
    OPERATIONS_IN_DETAIL = True
    pictures = {}
    rules, after = detecting(pictures)
    rules |= QUESTIONS | {(MA, "MigrationAutodetector.deep_deconstruct"): of_dock_name}
    after |= ANSWERS | says(MA, "MigrationAutodetector.deep_deconstruct")

    step("a loader, and an autodetector made as `makemigrations yard` makes it, but with a questioner of the script's own choosing, which answers yes to a rename and asks no one")
    quietly("loader = MigrationLoader(None, ignore_no_migrations=True)")
    quietly("autodetector = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps), MigrationQuestioner(defaults={'ask_rename': True}, specified_apps={'yard'}))")
    with recorded(rules, after=after):
        do("changes = autodetector.changes(graph=loader.graph, trim_to_apps={'yard'}, convert_apps={'yard'})")
    step("`as_prepared` is what the script kept of the autodetector's two sets of field keys as _prepare_field_lists returned, each sorted:")
    ASKING.update(as_prepared=pictures["field keys"])
    for question in (
        "full([key for key in as_prepared['old_field_keys'] if key[0] == 'yard'])", "full([key for key in as_prepared['new_field_keys'] if key[0] == 'yard'])",
    ):
        ask(question)
    step("and the autodetector as changes() left it: generate_renamed_fields has put the new name in place of the old in old_field_keys")
    for question in (
        "full(sorted(key for key in autodetector.old_field_keys if key[0] == 'yard'))", "full(sorted(key for key in autodetector.new_field_keys if key[0] == 'yard'))",
        "autodetector.renamed_fields", "full(sorted(autodetector.kept_model_keys))", "autodetector.altered_indexes['yard', 'repair']", "autodetector.altered_indexes['yard', 'dock']",
    ):
        ask(question)
    show("Yard's second version, in calls: the methods _detect_changes calls, each generate_ or create_ method with the number of operations it added (the script's count), the question put to the questioner, and the two deconstructions generate_altered_fields compares for Dock.name (of the calls of deep_deconstruct only those two are written)")

    step(PICTURE_ORDER)
    for line in pictures["before sorting"]:
        note(line)
    step("and after _sort_migrations:")
    for line in pictures["after sorting"]:
        note(line)
    show("generated_operations for yard's second version, before sorting and after: the four operations, each with the dependencies the autodetector gave it")

    for line in pictures["arranged"]:
        note(line)
    for question in (
        "loader.graph.leaf_nodes('yard')", "changes['yard'][0].name", "full(sorted(changes['yard'][0].dependencies))", "changes['yard'][0].initial",
        "MigrationAutodetector.parse_number('0001_initial')", "changes['yard'][0].suggest_name()", "[operation.migration_name_fragment for operation in changes['yard'][0].operations]",
    ):
        ask(question)
    show("Yard's second migration after arrange_for_graph: it depends on yard's leaf node, takes the number after that node's, and is named by suggest_name; its dependency on fleet comes from the index, whose model has a foreign key to fleet's Ship")

    step("the same with a questioner that answers no to the rename, and has no answer for the default the new column then needs:")
    quietly("autodetector = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps), MigrationQuestioner(specified_apps={'yard'}))")
    with recorded(QUESTIONS, after=ANSWERS):
        do("changes = autodetector.changes(graph=loader.graph, trim_to_apps={'yard'}, convert_apps={'yard'})")
    ask("changes['yard'][0].name")
    ask("whole(changes['yard'][0].operations)")
    show("Yard's second version with the rename refused: the old field removed and the new one added, for which the questioner is asked a default")
    close_connections()


def watching(sender, **kwargs):
    """A receiver of the script's own, connected to pre_migrate and to post_migrate for the block:
    it writes down what it is given, in full where the sender is yard's AppConfig."""
    from django.apps import apps as main_registry

    name = SIGNAL_NAMES[id(kwargs["signal"])]
    if sender.label != "yard":
        note(f"watching(sender={brief(sender)}, ...)  for {name}")
        return
    note(f"watching(sender={brief(sender)}, ...)  for {name}, with the keyword arguments {', '.join(sorted(kwargs))}")
    note(f"  app_config is sender: {kwargs['app_config'] is sender}; using: {kwargs['using']!r}; verbosity: {kwargs['verbosity']!r}; interactive: {kwargs['interactive']!r}")
    note(f"  plan: {whole(kwargs['plan'])}")
    registry = kwargs["apps"]
    note(f"  apps: {brief(registry)}; apps is the main registry: {registry is main_registry}")
    note(f"  the fields of apps.get_model('yard', 'Repair'): {[field.name for field in registry.get_model('yard', 'Repair')._meta.fields]!r}")


@part("signals")
def the_signals() -> None:
    """Block 66: migrate applies yard's second migration, with a receiver of the script's own on both signals."""
    set_up()
    ASKING.update(watching=watching)
    step("a receiver of the script's own:")
    code(watching)
    quietly("pre_migrate.connect(watching)")
    quietly("post_migrate.connect(watching)")
    rules = {
        (CMD + "migrate", "Command.handle"): handled(), ("django.core.management.sql", "emit_pre_migrate_signal"): bare, ("django.core.management.sql", "emit_post_migrate_signal"): bare,
        (DSP, "Signal.send"): signal_sent, (MX, "MigrationExecutor._create_project_state"): generic, (MS, "StateApps.__init__"): registry_made,
        (MX, "MigrationExecutor.migrate"): lambda f: Briefly(migrating(f)), (MS, "ProjectState.clear_delayed_apps_cache"): bare,
        (MX, "MigrationExecutor.__init__"): briefly(without("progress_callback")), (ML, "MigrationLoader.check_consistent_history"): briefly(generic),
    }
    with recorded(rules, after=says(MX, "MigrationExecutor._create_project_state", "MigrationExecutor.migrate")):
        do("call_command('migrate', stdout=out)")
    quietly("pre_migrate.disconnect(watching)")
    quietly("post_migrate.disconnect(watching)")
    ask("recorded_rows(application='yard')")
    ask("columns('yard_dock')")
    ask("columns('yard_repair')")
    show("The signals: migrate run in this process applies yard's second migration; pre_migrate is sent to each application before anything is applied, with the registry of the state the applied migrations make, and post_migrate after, with the registry of the state the executor returned")
    close_connections()


def default_said(value) -> str:
    from django.db.models import NOT_PROVIDED

    return "NOT_PROVIDED" if value is NOT_PROVIDED else repr(value)


def field_added(frame) -> str:
    """The schema editor's add_field, with the default the field has at the moment of the call."""
    return f"{generic(frame)}  [field.default is {default_said(frame.f_locals['field'].default)} at this moment]"


@part("foreman")
def the_foreman() -> None:
    """Block 33: the AddField of yard's third migration, which has preserve_default=False, run by hand."""
    global OPERATIONS_IN_DETAIL
    set_up()
    ASKING.update(default_said=lambda value: Said(default_said(value)))
    OPERATIONS_IN_DETAIL = True

    with database_kept():
        step("yard.0003_repair_foreman is written and not applied; its one operation is run by hand here, on the state before it and on the database, which is put back afterwards")
        quietly("loader = MigrationLoader(None)")
        quietly("operation = loader.graph.nodes['yard', '0003_repair_foreman'].operations[0]")
        for question in ("operation", "operation.preserve_default", "operation.field.default"):
            ask(question)
        quietly("state = loader.project_state(('yard', '0003_repair_foreman'), at_end=False)")
        quietly(f"state.apps  # {RENDERED_FIRST}")
        quietly("previous = state.clone()")
        name_it(ASKING["state"], "state")
        name_it(ASKING["previous"], "previous")
        with recorded(STATE_CHANGES):
            changing("operation.state_forwards('yard', state)")
        for question in ("state.models['yard', 'repair'].fields['foreman'] is operation.field", "default_said(state.models['yard', 'repair'].fields['foreman'].default)"):
            ask(question)
        quietly("field = state.apps.get_model('yard', 'Repair')._meta.get_field('foreman')")
        ask("default_said(field.default)")
        quietly("schema_editor = connection.schema_editor()")
        quietly("schema_editor.__enter__()")
        with recorded(operation_rules_with_states("database_forwards") | editor_rules("_remake_table") | editor_rules("add_field", label=field_added)):
            do("operation.database_forwards('yard', schema_editor, previous, state)")
        ask("default_said(field.default)")
        quietly("schema_editor.__exit__(None, None, None)")
        ask("table_sql('yard_repair')")
        ask("rows('yard_repair', 'id', 'foreman', 'notes')")
    show("AddField with preserve_default=False, by hand: the state half puts into the state a clone of the field with no default; the database half gives the historical model's field the operation's default for the length of the schema editor's call, which fills the rows there are with it, and takes it off again")
    close_connections()


# ---------------------------------------------------------------------------------------------
# The executor and the migrate command, with yard's three migrations applied (blocks 57 to 64, 67 and 70).


def progress(action, migration=None, fake=False):
    """A progress callback of the script's own, given to an executor: it writes down what it is called with."""
    note(f"progress({action!r}" + (f", {migration}" if migration is not None else "") + (", fake=True" if fake else "") + ")")


def all_forwards(frame) -> str:
    return f"MigrationExecutor._migrate_all_forwards(state={brief(frame.f_locals['state'])}, plan={whole(frame.f_locals['plan'])}, full_plan={plan_said(frame.f_locals['full_plan'])}, fake={frame.f_locals['fake']}, fake_initial={frame.f_locals['fake_initial']})"


def all_backwards(frame) -> str:
    return f"MigrationExecutor._migrate_all_backwards(plan={whole(frame.f_locals['plan'])}, full_plan={plan_said(frame.f_locals['full_plan'])}, fake={frame.f_locals['fake']})"


YARD_KEYS = "first, second, third = ('yard', '0001_initial'), ('yard', '0002_rename_started_repair_begun_dock_metres_and_more'), ('yard', '0003_repair_foreman')"


@part("executor")
def the_executor() -> None:
    """Blocks 57 to 63: MigrationExecutor, with yard's three migrations applied as each block begins."""
    set_up()
    ASKING.update(progress=progress)

    with database_kept():
        step("every migration is applied; three names for yard's keys:")
        quietly(YARD_KEYS)
        quietly("executor = MigrationExecutor(connection)")
        for question in (
            "executor.loader.graph.leaf_nodes()", "executor.migration_plan(executor.loader.graph.leaf_nodes())", "executor.migration_plan([third])", "executor.migration_plan([second])",
            "executor.migration_plan([first])", "executor.migration_plan([('yard', None)])", "executor.migration_plan([('fleet', '0001_initial')])",
            "whole(executor.migration_plan([('fleet', None)]))", "whole(executor.migration_plan(executor.loader.graph.leaf_nodes(), clean_start=True))",
        ):
            ask(question)
        step("the script unapplies yard's second and third migrations with the executor, and has the executor's loader read the rows again:")
        silently("executor.migrate([first])")
        silently("executor.loader.build_graph()")
        for question in (
            "recorded_rows(application='yard')", "executor.migration_plan(executor.loader.graph.leaf_nodes())", "executor.migration_plan([second])", "executor.migration_plan([third])",
            "executor.migration_plan([first])", "executor.migration_plan([('yard', None)])", "executor.migration_plan([second, third])", "executor.loader.graph.root_nodes('yard')",
        ):
            ask(question)
        step("a target that is no node of the graph: before it raises, migration_plan takes the target for a replaced migration, sets its loader to replace none and has it build the graph again, which is the two statements under the question")
        for question in ("executor.loader.replace_migrations", "executor.migration_plan([('yard', '0009_missing')])", "executor.loader.replace_migrations"):
            ask(question)
    show("Plans from targets: migration_plan for a target that is not applied gives the migrations of its forwards plan that are not applied; for one that is applied, the applied migrations of the backwards plans of its children in its own application, and not the target itself; for (label, None), the applied migrations of the backwards plan of each root node of the application, of which yard has one")

    with database_kept():
        step("a progress callback of the script's own:")
        code(progress)
        quietly(YARD_KEYS)
        step("the script unapplies yard's second and third migrations with an executor that has no callback, so that there are two to apply:")
        silently("MigrationExecutor(connection).migrate([first])")
        quietly("executor = MigrationExecutor(connection, progress)")
        forwards = {
            (MX, "MigrationExecutor.migrate"): only("targets"), (MX, "MigrationExecutor.migration_plan"): generic, (MX, "MigrationExecutor._create_project_state"): generic,
            (MM, "Migration.mutate_state"): mutated, (MX, "MigrationExecutor._migrate_all_forwards"): all_forwards, (MS, "StateApps.__init__"): registry_made,
            (MX, "MigrationExecutor.apply_migration"): briefly(generic), (MR, "MigrationRecorder.ensure_schema"): briefly(bare), (MX, "MigrationExecutor.check_replacements"): briefly(bare),
        }
        def the_state(frame, value) -> str:
            """The state _create_project_state returns, which every later line of the block writes `state`."""
            described = state_said(value)
            name_it(value, "state")
            return f"state, {described}"

        answers = says(MX, "MigrationExecutor.migration_plan", how=a_plan_or_the_full) | says(MX, "MigrationExecutor._create_project_state", how=the_state) | says(
            MX, "MigrationExecutor._migrate_all_forwards", "MigrationExecutor.apply_migration", "MigrationExecutor.migrate")
        with recorded(forwards, after=answers):
            do("state = executor.migrate([third])")
        for question in ("len(state.models)", "'apps' in state.__dict__", "recorded_rows(application='yard')"):
            ask(question)
    show("Forwards: executor.migrate called with a target and nothing else, to apply two migrations of yard: the state of the applied migrations is made first (it is written `state` from where _create_project_state returns it), its registry is rendered before the first migration is applied, and each apply_migration is given that state and returns it, as migrate does in the end")

    with database_kept():
        quietly(YARD_KEYS)
        quietly("executor = MigrationExecutor(connection)")
        step("the script unapplies yard's third migration with the executor, to apply it again:")
        silently("executor.migrate([second])")
        silently("executor.loader.build_graph()")
        quietly("state = executor._create_project_state(with_applied_migrations=True)")
        quietly("state.apps  # rendered here, as _migrate_all_forwards renders the state before it calls apply_migration")
        one = {
            (MX, "MigrationExecutor.apply_migration"): only("migration"), (B, "BaseDatabaseWrapper.schema_editor"): generic, (MM, "Migration.apply"): lambda f: Briefly(f"Migration.apply  [{f.f_locals['self']}]"),
            (MX, "MigrationExecutor.record_migration"): generic, (MR, "MigrationRecorder.record_applied"): generic,
        } | EDITOR_ENTERED | ATOMIC
        with recorded(one, sqlite=True):
            do("state = executor.apply_migration(state, executor.loader.graph.nodes[third])")
        step("the script unapplies all three of yard's migrations, to apply the first again, whose schema editor is left with deferred statements:")
        silently("executor.loader.build_graph(); executor.migrate([('yard', None)])")
        silently("executor.loader.build_graph()")
        quietly("state = executor._create_project_state(with_applied_migrations=True)")
        quietly("state.apps  # rendered here, as before")
        with recorded(one, sqlite=True):
            do("state = executor.apply_migration(state, executor.loader.graph.nodes[first])")
    show("One migration's transaction (with the statements as SQLite ran them, `sqlite`): apply_migration writes the migration's row inside the schema editor's block, before its COMMIT, where the editor has no deferred statements when the migration has run; and after the block, in a statement of its own, where it has")

    with database_kept():
        quietly(YARD_KEYS)
        quietly("executor = MigrationExecutor(connection, progress)")
        backwards = {
            (MX, "MigrationExecutor.migrate"): only("targets"), (MX, "MigrationExecutor.migration_plan"): generic, (MX, "MigrationExecutor._migrate_all_backwards"): all_backwards,
            (MX, "MigrationExecutor._create_project_state"): generic, (MM, "Migration.mutate_state"): mutated, (MS, "StateApps.__init__"): registry_made,
            (MX, "MigrationExecutor.unapply_migration"): only("state", "migration"), (MM, "Migration.unapply"): lambda f: Briefly(f"Migration.unapply  [{f.f_locals['self']}]"),
            (MX, "MigrationExecutor.record_migration"): generic, (MR, "MigrationRecorder.record_unapplied"): generic, (MR, "MigrationRecorder.ensure_schema"): briefly(bare),
            (MX, "MigrationExecutor.check_replacements"): briefly(bare), (B, "BaseDatabaseWrapper.schema_editor"): generic,
        }
        numbered = numbering_clones("state", start=0)

        def kept_state(frame, value) -> str | None:
            """The state mutate_state returns, where it is a clone of the one it was given: numbered on from the first."""
            return numbered(frame, value) if frame.f_locals["preserve"] else None

        answers = says(MX, "MigrationExecutor.migration_plan", how=a_plan_or_the_full) | says(MX, "MigrationExecutor._migrate_all_backwards", "MigrationExecutor.migrate") | says(
            MM, "Migration.mutate_state", how=kept_state) | says(MX, "MigrationExecutor._create_project_state", how=numbered)
        with recorded(backwards, after=answers):
            do("state = executor.migrate([first])")
        for question in ("'apps' in state.__dict__", "list(state.models['yard', 'repair'].fields)", "recorded_rows(application='yard')", "columns('yard_repair')"):
            ask(question)
        manage("migrate yard zero")
        ask("recorded_rows(application='yard')")
        ask("[name for name in tables() if name.startswith('yard_')]")
    show("Backwards: executor.migrate with yard's first migration for its target unapplies the two after it: a first pass over the full plan makes the state before each migration to unapply, and a second unapplies them in the plan's order, each with its own state, deleting its row; then `migrate yard zero` as a command line")

    quietly(YARD_KEYS)
    quietly("executor = MigrationExecutor(connection)")
    quietly("one, two = executor.loader.graph.nodes[second], executor.loader.graph.nodes[third]")
    ask("executor.migrate(None, plan=[(one, False), (two, True)])")
    ask("recorded_rows(application='yard')")
    show("A plan both ways: executor.migrate given a plan with one migration forwards and one backwards refuses it")

    with database_kept():
        manage("migrate yard 0002 --fake")
        ask("recorded_rows(application='yard')")
        ask("columns('yard_repair')")
        faking = {
            (CMD + "migrate", "Command.handle"): handled("app_label", "fake"), (MX, "MigrationExecutor.migration_plan"): lambda f: None if f.f_locals["clean_start"] else generic(f),
            (MX, "MigrationExecutor.migrate"): migrating, (MX, "MigrationExecutor.apply_migration"): generic, (CMD + "migrate", "Command.migration_progress_callback"): generic,
            (B, "BaseDatabaseWrapper.schema_editor"): generic, (MX, "MigrationExecutor.record_migration"): generic, (MR, "MigrationRecorder.record_applied"): generic,
            (MM, "Migration.apply"): of_migration,
        } | command_begins() | executor_frames()
        with recorded(faking, after=says(MX, "MigrationExecutor.migration_plan", how=a_plan)):
            do("call_command('migrate', 'yard', fake=True, stdout=out)")
        ask("recorded_rows(application='yard')")
    show("--fake: `migrate yard 0002 --fake` as a command line deletes the row of yard's third migration and leaves its column; then `migrate yard --fake` run in this process: apply_migration makes no schema editor and calls no Migration.apply, and writes the row")

    with database_kept():
        manage("migrate yard 0001")
        manage("migrate yard zero --fake")
        ask("recorded_rows(application='yard')")
        ask("[name for name in tables() if name.startswith('yard_')]")
        quietly(YARD_KEYS)
        quietly("loader = MigrationLoader(None)")
        ask("[loader.graph.nodes[key].initial for key in (first, second, third)]")
        ask("[loader.graph.nodes[key].dependencies for key in (second, third)]")
        detecting_ = {
            (MX, "MigrationExecutor.detect_soft_applied"): generic,
            (MM, "Migration.mutate_state"): lambda f: mutated(f) if f.f_back.f_code.co_qualname == "MigrationExecutor.detect_soft_applied" else None,
            (MX, "MigrationExecutor.detect_soft_applied.<locals>.should_skip_detecting_model"): lambda f: f"should_skip_detecting_model({brief(f.f_locals['migration'])}, {brief(f.f_locals['model'])})",
            (DBU, "ConnectionRouter.allow_migrate"): lambda f: generic(f) if f.f_back.f_code.co_name == "should_skip_detecting_model" else None,
            ("django.db.backends.base.introspection", "BaseDatabaseIntrospection.table_names"): briefly(bare),
            ("django.db.backends.sqlite3.introspection", "DatabaseIntrospection.get_table_description"): briefly(only("table_name")),
        }
        found = says(MX, "MigrationExecutor.detect_soft_applied", how=lambda f, v: str(whole(v))) | says(MX, "MigrationExecutor.detect_soft_applied.<locals>.should_skip_detecting_model") | says(DBU, "ConnectionRouter.allow_migrate")
        faking_initial = detecting_ | {
            (CMD + "migrate", "Command.handle"): handled("app_label", "fake_initial"), (MX, "MigrationExecutor.migration_plan"): lambda f: None if f.f_locals["clean_start"] else generic(f),
            (MX, "MigrationExecutor.migrate"): migrating, (MX, "MigrationExecutor.apply_migration"): generic, (MM, "Migration.apply"): lambda f: Briefly(f"Migration.apply  [{f.f_locals['self']}]"),
            (MX, "MigrationExecutor.record_migration"): generic,
        } | command_begins() | executor_frames()
        with recorded(faking_initial, after=found | says(MX, "MigrationExecutor.migration_plan", how=a_plan)):
            do("call_command('migrate', 'yard', fake_initial=True, stdout=out)")
        ask("recorded_rows(application='yard')")
        step("a migration of crew, which is marked initial and adds fields: the many-to-many field has no table of its own (its model between is office's Licence, whose table is looked for), and the column of the other is looked for. It is applied, and no plan has it; the script calls detect_soft_applied itself, and gives it what apply_migration would, the state before the migration, rendered:")
        ask("whole(loader.graph.nodes['crew', '0002_initial'].operations)")
        quietly("executor = MigrationExecutor(connection)")
        quietly("state = executor.loader.project_state(('crew', '0002_initial'), at_end=False)")
        quietly("state.apps")
        with recorded(detecting_, after=found):
            do("answer = executor.detect_soft_applied(state, executor.loader.graph.nodes['crew', '0002_initial'])")
    show("--fake-initial and detect_soft_applied: with yard's first tables in the database and no row for yard (the script's doing: `migrate yard 0001`, then `migrate yard zero --fake`), `migrate yard --fake-initial` run in this process: apply_migration asks detect_soft_applied about each migration before it applies it, giving it its state; for yard's initial migration, whose two tables are found, the answer is True, and the row is written with no Migration.apply; the two after it are not marked initial and depend on a migration of yard's own: for each the answer is False at once, and it is applied; then detect_soft_applied called by the script for a migration that adds fields")
    close_connections()


@part("migrate-command")
def the_migrate_command() -> None:
    """Blocks 64 and 70: what the migrate command makes of its arguments, and sqlmigrate."""
    set_up()

    targeting = {
        (CMD + "migrate", "Command.handle"): handled("app_label", "migration_name", "plan"), (ML, "MigrationLoader.get_migration_by_prefix"): generic,
        (MX, "MigrationExecutor.migration_plan"): generic,
    } | command_begins()
    answers = says(ML, "MigrationLoader.get_migration_by_prefix") | says(MX, "MigrationExecutor.migration_plan", how=a_plan)
    for arguments in ("", "'yard', ", "'yard', '0002', ", "'yard', 'zero', ", "'fleet', '0001_initial', "):
        with recorded(targeting, after=answers):
            do(f"call_command('migrate', {arguments}plan=True, stdout=out)")
    show("Targets from the command line: migrate run in this process with --plan, which prints the plan and applies nothing: the targets handle gives migration_plan for no argument, an application, an application and the start of a migration's name, zero, and an application and a whole name; every migration is applied")

    collecting = {
        (CMD + "sqlmigrate", "Command.handle"): handled("app_label", "migration_name", "backwards"), (ML, "MigrationLoader.__init__"): generic,
        (ML, "MigrationLoader.get_migration_by_prefix"): generic, (ML, "MigrationLoader.collect_sql"): lambda f: f"MigrationLoader.collect_sql(plan={whole(f.f_locals['plan'])})",
        (B, "BaseDatabaseWrapper.schema_editor"): generic, (ML, "MigrationLoader.project_state"): generic, (MM, "Migration.apply"): of_migration,
        (BS, "BaseDatabaseSchemaEditor.execute"): lambda f: f"DatabaseSchemaEditor.execute({one_line(str(f.f_locals['sql']))[:60] + ('...' if len(one_line(str(f.f_locals['sql']))) > 60 else '')!r})  (BaseDatabaseSchemaEditor.execute)",
    } | {key: (lambda f: operation_between(f) if f.f_back.f_code.co_qualname == "Migration.apply" else None) for key in operation_rules("state_forwards", "database_forwards")} | editor_rules("add_field", "_remake_table") | {
        (MS, "StateApps.__init__"): registry_of, (MM, "Migration.apply"): applied_to_state,
        (MS, "ProjectState.clone"): lambda f: "ProjectState.clone" if f.f_back.f_code.co_qualname == "Migration.apply" else None,
    }
    collected = says(ML, "MigrationLoader.get_migration_by_prefix", "MigrationLoader.project_state") | says(ML, "MigrationLoader.collect_sql", how=lambda f, v: f"a list of {len(v)} lines") | says(
        MS, "ProjectState.clone", how=numbering_clones())
    with recorded(collecting, after=collected):
        do("call_command('sqlmigrate', 'yard', '0003', stdout=out)")
    ask("recorded_rows(application='yard')")
    step("the table as migrate made it when it applied the same migration, to set beside the CREATE TABLE that sqlmigrate printed:")
    ask("table_sql('yard_repair')")
    show("sqlmigrate, the calls: sqlmigrate yard 0003 run in this process: a loader that replaces no migration, a schema editor made to collect, and Migration.apply told to collect, and given a state that the loader made and nothing has rendered: its registry and the from-state's are made inside the operation's database half, the to-state's first, and in the remade table that sqlmigrate prints the new column stands second, where in the table migrate made it stands last; the schema editor's execute keeps each statement and sends none; the statements sent are the two with which the loader reads the rows of django_migrations, and those with which SQLite's schema editor opens and closes")
    close_connections()


@part("unmigrated")
def an_unmigrated_application() -> None:
    """Blocks 27 and 67, with the settings module settings_yard_unmigrated: yard an unmigrated
    application, and a database file of its own."""
    set_up("settings_yard_unmigrated")

    for question in ("settings.MIGRATION_MODULES", "settings.DATABASES['default']['NAME'].name"):
        ask(question)
    quietly("loader = MigrationLoader(None)")
    for question in ("loader.unmigrated_apps", "loader.migrated_apps", "full(sorted(loader.disk_migrations))", "MigrationLoader.migrations_module('yard')"):
        ask(question)
    quietly("state = loader.project_state()")
    for question in ("state.real_apps", "len(state.models)", "('yard', 'dock') in state.models"):
        ask(question)
    with recorded({(MS, "StateApps.__init__"): registry_made, (MS, "ModelState.from_model"): generic, (MS, "StateApps.render_multiple"): rendered_many, (MS, "ModelState.render"): lambda f: rendered(f) if f.f_locals["self"].app_label == "yard" else None},
                  after=says(MS, "ModelState.render")):
        do("registry = state.apps")
    for question in (
        "[(model_state.name, list(model_state.fields)) for model_state in registry.real_models]", "list(ModelState.from_model(Repair).fields)",
        "registry.get_model('yard', 'Repair').__module__", "[field.name for field in registry.get_model('yard', 'Repair')._meta.get_fields()]",
        "[field.name for field in Repair._meta.get_fields()]", "full(sorted(registry.app_configs))",
    ):
        ask(question)
    show("real_apps, an unmigrated application in a project state (the settings module settings_yard_unmigrated, in which MIGRATION_MODULES gives None for yard): its models are no model states of the state; the state's registry renders them from the main registry's, without the fields that are relations")

    os.remove(path_of("unmigrated.sqlite3"))
    step("the script has removed the database file unmigrated.sqlite3 that the command lines two blocks before this one filled: the database is empty again")
    syncing = {
        (CMD + "migrate", "Command.handle"): handled("run_syncdb"), (MX, "MigrationExecutor.migration_plan"): lambda f: None if f.f_locals["clean_start"] else generic(f),
        (CMD + "migrate", "Command.sync_apps"): generic, (DBU, "ConnectionRouter.get_migratable_models"): generic, (OPT, "Options.can_migrate"): generic,
        (MX, "MigrationExecutor.migrate"): lambda f: Briefly(migrating(f)), ("django.core.management.sql", "emit_pre_migrate_signal"): briefly(bare),
        ("django.core.management.sql", "emit_post_migrate_signal"): briefly(bare), (MS, "StateApps.unregister_model"): generic, (MS, "StateApps.render_multiple"): rendered_many,
        (MX, "MigrationExecutor.__init__"): briefly(without("progress_callback")), (ML, "MigrationLoader.check_consistent_history"): briefly(generic),
        (MS, "StateApps.__init__"): registry_made, (MS, "ProjectState.clear_delayed_apps_cache"): bare,
    } | editor_rules("create_model") | EDITOR_ENTERED
    with recorded(syncing, after=says(MX, "MigrationExecutor.migration_plan", how=a_plan) | says(DBU, "ConnectionRouter.get_migratable_models") | says(OPT, "Options.can_migrate")):
        do("call_command('migrate', run_syncdb=True, stdout=out)")
    for question in ("recorded_rows()", "tables()"):
        ask(question)
    close_connections()
    os.remove(path_of("unmigrated.sqlite3"))
    step("the script has closed the connection and removed the database file unmigrated.sqlite3")
    show("--run-syncdb, the calls: migrate --run-syncdb run in this process on the database made empty again: sync_apps makes the tables of yard's models, as models.py has them, in one schema editor and with no migration; then the migrations of the other applications are applied; no row of django_migrations is yard's")
    close_connections()


# ---------------------------------------------------------------------------------------------
# RunPython, RunSQL and SeparateDatabaseAndState (blocks 38 to 43).


def count_repairs(apps, schema_editor):
    """A function of the script's own for a RunPython: it counts the repairs, with the historical model."""
    apps.get_model("yard", "Repair").objects.using(schema_editor.connection.alias).count()


def executed(frame) -> str:
    """The schema editor's execute, by the statement it is given, cut to sixty characters."""
    sql = one_line(str(frame.f_locals["sql"]))
    return f"DatabaseSchemaEditor.execute({sql[:60] + ('...' if len(sql) > 60 else '')!r}, params={frame.f_locals['params']!r})  (BaseDatabaseSchemaEditor.execute)"


def special_rules(*functions) -> dict:
    """Rules for the blocks on RunPython and RunSQL: the two halves of every operation, what
    RunPython asks first, the router, the migration file's own functions, and the registry asked for a model."""
    rules = operation_rules("state_forwards", "database_forwards", "database_backwards") | {
        (MS, "ProjectState.clear_delayed_apps_cache"): bare, (DBU, "ConnectionRouter.allow_migrate"): generic, (REG, "Apps.get_model"): model_got,
        (OS, "RunSQL._run_sql"): lambda f: f"RunSQL._run_sql(sqls={f.f_locals['sqls']!r})", (MS, "StateApps.__init__"): registry_made,
    }
    for module, name in functions:
        rules[(module, name)] = generic
    return rules


SPECIAL_ANSWERS = says(DBU, "ConnectionRouter.allow_migrate") | says(REG, "Apps.get_model")
DATA_MODULE = "harbour.yard.migrations.0004_name_the_foremen"


@part("data-migration")
def the_data_migration() -> None:
    """Blocks 39 to 41: yard's fourth migration, a RunPython and a RunSQL, applied, unapplied and applied again."""
    set_up()

    from django.core.management.commands.migrate import Command as MigrateCommand

    ASKING.update(count_repairs=count_repairs, made=made, MigrateCommand=MigrateCommand)
    ask("rows('yard_repair', 'id', 'foreman', 'notes')")
    running = special_rules((DATA_MODULE, "name_foremen"), (DATA_MODULE, "forget_foremen")) | {
        (CMD + "migrate", "Command.handle"): handled("app_label", "migration_name"), (MX, "MigrationExecutor.migrate"): migrating, (MX, "MigrationExecutor.apply_migration"): only("migration"),
        (MX, "MigrationExecutor.unapply_migration"): only("migration"), (MM, "Migration.apply"): lambda f: f"Migration.apply  [{f.f_locals['self']}]",
        (MM, "Migration.unapply"): lambda f: f"Migration.unapply  [{f.f_locals['self']}]", (MX, "MigrationExecutor.record_migration"): generic,
        ("django.core.management.sql", "emit_pre_migrate_signal"): briefly(bare), ("django.core.management.sql", "emit_post_migrate_signal"): briefly(bare),
        (BS, "BaseDatabaseSchemaEditor.execute"): executed,
    } | command_begins() | executor_frames() | EDITOR_ENTERED | ATOMIC
    with recorded(running, after=SPECIAL_ANSWERS):
        do("call_command('migrate', 'yard', stdout=out)")
    ask("rows('yard_repair', 'id', 'foreman', 'notes')")
    ask("recorded_rows(application='yard')")
    show("RunPython and RunSQL run: migrate applies yard's fourth migration, in this process: RunPython's database half calls clear_delayed_apps_cache on the from-state, asks the router, and calls the function with the from-state's registry and the schema editor; RunSQL's asks the router and hands its statement to the schema editor's execute; both ran inside the migration's one transaction")

    with recorded(running, after=SPECIAL_ANSWERS):
        do("call_command('migrate', 'yard', '0003', stdout=out)")
    ask("rows('yard_repair', 'id', 'foreman', 'notes')")
    ask("recorded_rows(application='yard')")
    step("the script applies the migration again, with nothing written:")
    silently("call_command('migrate', 'yard', verbosity=0)")
    ask("rows('yard_repair', 'id', 'foreman', 'notes')")
    show("RunPython and RunSQL backwards: migrate yard 0003, in this process, unapplies the fourth migration: the operations' database halves backwards in reverse order, RunSQL's reverse_sql and then RunPython's reverse_code")

    step("a function of the script's own, and a migration of the script's own whose RunPython is given no reverse_code:")
    code(count_repairs)
    quietly("oneway = made(migrations.RunPython(count_repairs))")
    for question in ("oneway.operations[0].reversible", "oneway.operations[0].reverse_code", "MigrateCommand.describe_operation(oneway.operations[0], backwards=False)", "MigrateCommand.describe_operation(oneway.operations[0], backwards=True)"):
        ask(question)
    state_by_hand()
    quietly("schema_editor = connection.schema_editor()")
    quietly("schema_editor.__enter__()")
    with recorded(special_rules(("__main__", "count_repairs")) | {(MM, "Migration.unapply"): lambda f: f"Migration.unapply  [{f.f_locals['self']}]"}, after=SPECIAL_ANSWERS):
        do("oneway.unapply(state, schema_editor)")
        do("oneway.operations[0].database_backwards('yard', schema_editor, state, state)")
    quietly("schema_editor.__exit__(None, None, None)")
    show("An operation that cannot be reversed: Migration.unapply raises IrreversibleError in its first pass, before any database half has run; RunPython's own database_backwards raises NotImplementedError")

    with database_kept():
        step("operations of the script's own, each run by hand in turn, as in the blocks on the field operations: its state half on `state`, of which `previous` is a clone made just before, then its database half")
        state_by_hand()
        quietly("schema_editor = connection.schema_editor()")
        quietly("schema_editor.__enter__()")
        ask("repr(migrations.RunSQL.noop)")
        by_hand_ = special_rules() | {(BS, "BaseDatabaseSchemaEditor.execute"): executed, (MS, "ProjectState.add_field"): generic}

        def run_sql(name: str, operation: str, backwards: bool = False) -> None:
            quietly(f"{name} = {operation}")
            quietly("previous = state.clone()")
            with recorded(by_hand_, after=SPECIAL_ANSWERS):
                changing(f"{name}.state_forwards('yard', state)")
                do(f"{name}.database_forwards('yard', schema_editor, previous, state)")
                if backwards:
                    do(f"{name}.database_backwards('yard', schema_editor, state, previous)")

        run_sql("several", "migrations.RunSQL(sql=[('UPDATE yard_dock SET metres = %s WHERE name = %s', [150, 'North dock']), 'UPDATE yard_dock SET metres = metres + 1'], reverse_sql=migrations.RunSQL.noop)", backwards=True)
        ask("several.reversible")
        ask("rows('yard_dock', 'id', 'name', 'metres')")
        run_sql("script", "migrations.RunSQL('UPDATE yard_dock SET metres = 120; UPDATE yard_dock SET name = name;', hints={'model_name': 'dock'})", backwards=True)
        run_sql("column", "migrations.RunSQL('ALTER TABLE yard_dock ADD COLUMN cranes integer NOT NULL DEFAULT 0', state_operations=[migrations.AddField('dock', 'cranes', models.IntegerField(default=0))])")
        ask("columns('yard_dock')")
        run_sql("nothing", "migrations.RunSQL(migrations.RunSQL.noop)")
        quietly("schema_editor.__exit__(None, None, None)")
    show("RunSQL, by hand: a list of statements, one with parameters; RunSQL.noop for reverse_sql, which makes the operation reversible and sends nothing; a string of two statements, which is split; hints, which go to the router; and state_operations, which are its state half")

    with database_kept():
        step("two migrations of the script's own that are not atomic, each with one RunPython: one made with atomic left alone, one with atomic=True; each is applied by hand, as apply_migration applies a migration, to the state the loader makes of every migration, rendered first")
        quietly("loader = MigrationLoader(None)")
        quietly("state = loader.project_state()")
        quietly("state.apps  # rendered here, as the executor renders its state before it applies a migration")
        quietly("connection.ensure_connection()  # opened here, so that what a connection sends as it opens is not among the lines below")
        quietly("alone = made(migrations.RunPython(count_repairs), atomic=False)")
        quietly("guarded = made(migrations.RunPython(count_repairs, atomic=True), atomic=False)")
        for question in ("alone.operations[0].atomic", "guarded.operations[0].atomic", "connection.schema_editor(atomic=alone.atomic).atomic_migration"):
            ask(question)
        applying = special_rules(("__main__", "count_repairs")) | {(MM, "Migration.apply"): lambda f: f"Migration.apply  [{f.f_locals['self']}, its atomic {f.f_locals['self'].atomic}]"} | ATOMIC
        with recorded(applying, after=SPECIAL_ANSWERS, sqlite=True):
            do("with connection.schema_editor(atomic=alone.atomic) as schema_editor: state = alone.apply(state, schema_editor)")
            do("with connection.schema_editor(atomic=guarded.atomic) as schema_editor: state = guarded.apply(state, schema_editor)")
    show("RunPython in a transaction or not (with the statements as SQLite ran them, `sqlite`): in a migration that is not atomic, the function runs with no transaction begun unless the RunPython was made with atomic=True, for which Migration.apply runs its database half in an atomic block")
    close_connections()


@part("separate")
def separate_database_and_state() -> None:
    """Block 42: yard's fifth migration, a SeparateDatabaseAndState written by hand, applied."""
    set_up()
    numbered = numbering_clones()

    def applied_to(frame) -> str:
        """Migration.apply, whose state every later line of the block writes `state`."""
        name_it(frame.f_locals["project_state"], "state")
        return f"Migration.apply(state, the schema editor)  [{frame.f_locals['self']}]"

    running = {key: operation_between for key in operation_rules("state_forwards", "database_forwards")} | {
        (CMD + "migrate", "Command.handle"): handled("app_label"), (MX, "MigrationExecutor.migrate"): lambda f: f"MigrationExecutor.migrate(targets={brief(f.f_locals['targets'])}, plan={whole(f.f_locals['plan'])}, state={brief(f.f_locals['state'])}, fake={f.f_locals['fake']}, fake_initial={f.f_locals['fake_initial']})",
        (MX, "MigrationExecutor.apply_migration"): only("migration"), (MM, "Migration.apply"): applied_to,
        (MS, "ProjectState.clone"): lambda f: "ProjectState.clone" if f.f_back.f_code.co_qualname in ("Migration.apply", "SeparateDatabaseAndState.database_forwards") else None,
        (MS, "ProjectState.add_index"): lambda f: None if f.f_back.f_back.f_code.co_qualname == "Migration.mutate_state" else generic(f),
        (DBU, "ConnectionRouter.allow_migrate"): generic, ("django.core.management.sql", "emit_pre_migrate_signal"): briefly(bare),
        ("django.core.management.sql", "emit_post_migrate_signal"): briefly(bare),
    } | command_begins() | executor_frames()
    ask("indexes('yard_repair')")
    with recorded(running, after=says(MS, "ProjectState.clone", how=numbered) | says(DBU, "ConnectionRouter.allow_migrate")):
        do("call_command('migrate', 'yard', stdout=out)")
    for question in (
        "indexes('yard_repair')", "recorded_rows(application='yard')",
        "[index.name for index in MigrationLoader(None).project_state().models['yard', 'repair'].options['indexes']]",
        "MigrationAutodetector(MigrationLoader(None).project_state(), ProjectState.from_apps(apps)).changes(MigrationLoader(None).graph)",
    ):
        ask(question)
    show("SeparateDatabaseAndState: migrate applies yard's fifth migration, in this process: the state half runs the state halves of the state operations on the project state (written `state`); the database half runs each database operation between a from-state and a clone of it on which it has run that operation's own state half, and never the state operations")
    close_connections()


# ---------------------------------------------------------------------------------------------
# Two branches, and squashed migrations (blocks 102 to 107).


@part("conflict")
def the_conflict() -> None:
    """Block 102, in this process: the loader's view of two leaf nodes in one application."""
    set_up()
    quietly("loader = MigrationLoader(None)")
    for question in (
        "loader.graph.leaf_nodes('yard')", "loader.detect_conflicts()", "sorted(node.key for node in loader.graph.node_map['yard', '0005_repair_by_foreman'].children)",
        "loader.graph.forwards_plan(('yard', '0006_dock_covered'))[-2:]", "loader.graph.forwards_plan(('yard', '0006_long_dock'))[-2:]", "loader.graph.leaf_nodes('fleet')",
        "MigrationExecutor(connection).migration_plan(loader.graph.leaf_nodes())",
    ):
        ask(question)
    show("Two leaf nodes: with a migration of a colleague's beside the one makemigrations wrote, both depending on yard.0005_repair_by_foreman, yard has two leaf nodes, which detect_conflicts reports; a plan for both can still be made")
    close_connections()


SQUASHED = "0001_squashed_0007_merge"
RESQUASHED = "harbour/yard/migrations/0001_resquashed.py"  # a name that sorts before the squashed migration's: see the block
SQUASHED_AGAIN = '''\
from django.db import migrations


class Migration(migrations.Migration):

    replaces = [("yard", "0001_squashed_0007_merge")]
    initial = True
    dependencies = [("fleet", "0001_initial")]
    operations = []
'''


def replaced_said(name: str):
    """One of the graph's two methods for a replacing migration: its key, and how many keys it replaces."""
    def said(frame) -> str:
        count = len(frame.f_locals["replaced"])
        return f"MigrationGraph.{name}(replacement={frame.f_locals['replacement']!r}, replaced=<{count} key{'' if count == 1 else 's'}>)"
    return said


REPLACING = {
    (ML, "MigrationLoader.replace_migration"): generic, (ML, "MigrationLoader._resolve_replaced_migration_keys"): only("migration"),
    (MG, "MigrationGraph.remove_replaced_nodes"): replaced_said("remove_replaced_nodes"), (MG, "MigrationGraph.remove_replacement_node"): replaced_said("remove_replacement_node"),
}
RESOLVED = says(ML, "MigrationLoader._resolve_replaced_migration_keys", how=lambda f, v: f"a set of {len(v)} keys")


@part("squashed")
def squashed_migrations() -> None:
    """Blocks 104 to 107, with the settings module settings_three: the loader and the executor
    with a replacing migration among yard's files, on three databases."""
    set_up("settings_three")
    ASKING.update(squashed=("yard", SQUASHED))
    states = (
        ("default", "every migration the replacing migration replaces is applied, and it has no row itself"),
        ("fresh", "no migration is applied: the database is empty"),
        ("halfway", "yard's first three migrations are applied, and the five after them are not"),
    )
    step("`squashed` is the replacing migration's key:")
    ask("squashed")
    for alias, words in states:
        step(f'the connection "{alias}": {words}' + (" (SQLite makes its file, fresh.sqlite3, as the connection first opens, which it does for the question below)" if alias == "fresh" else ""))
        ask(f"recorded_rows('{alias}', 'yard')")
        with recorded(REPLACING, after=RESOLVED):
            do(f"loader = MigrationLoader(connections['{alias}'])")
        for question in (
            "full(sorted(name for label, name in loader.graph.nodes if label == 'yard'))", "full(sorted(name for label, name in loader.applied_migrations if label == 'yard'))",
            "loader.replacements", "loader.replacements_progress", "loader.graph.leaf_nodes('yard')",
            f"whole(MigrationExecutor(connections['{alias}']).migration_plan(loader.graph.leaf_nodes()))",
        ):
            ask(question)
    show("The loader and a replacing migration, three ways (the settings module settings_three): where every replaced migration is applied, or none is, remove_replaced_nodes takes the replaced nodes out of the graph; where some are, remove_replacement_node takes the replacing node out instead; the loader counts the replacing migration among its applied_migrations only where every replaced one has a row; and the plan migrate would follow on each")

    step(f"the script has written a migration of its own, {RESQUASHED}, which replaces the replacing migration; build_graph goes through the replacing migrations in the order of their file names, and this name comes before the other's:")
    write(RESQUASHED, SQUASHED_AGAIN)
    forget()
    file_shown(RESQUASHED)
    for alias, words in states[1:]:
        step(f'the connection "{alias}": {words}')
        with recorded(REPLACING, after=RESOLVED):
            do(f"loader = MigrationLoader(connections['{alias}'])")
        for question in ("list(loader.replacements)", "full(sorted(name for label, name in loader.graph.nodes if label == 'yard'))", "loader.replacements_progress"):
            ask(question)
    ask("full(sorted(loader._resolve_replaced_migration_keys(loader.replacements['yard', '0001_resquashed'])))")
    os.remove(path_of(RESQUASHED))
    forget("harbour.yard.migrations.0001_resquashed")
    step("the script has removed the file, and taken its module out of sys.modules")
    show("A replacing migration replaced: with a migration of the script's own that replaces the replacing migration and is reached first, replace_migration calls itself for the inner one before it settles the outer, and the outer one is judged by the migrations the inner one replaces; the loop's own call for the inner one, which comes after, has nothing under it")

    def applying(frame) -> str:
        return generic(frame) if frame.f_locals["migration"].app_label == "yard" else Briefly(generic(frame))

    recording = {
        (CMD + "migrate", "Command.handle"): handled("app_label", "database"), (MX, "MigrationExecutor.migration_plan"): lambda f: None if f.f_locals["clean_start"] else generic(f),
        (MX, "MigrationExecutor.migrate"): migrating, (MX, "MigrationExecutor.apply_migration"): applying, (MM, "Migration.apply"): lambda f: Briefly(f"Migration.apply  [{f.f_locals['self']}]"),
        (MX, "MigrationExecutor.record_migration"): generic, (MR, "MigrationRecorder.record_applied"): generic,
        (MR, "MigrationRecorder.ensure_schema"): lambda f: Briefly(bare(f)) if f.f_back.f_code.co_qualname == "MigrationExecutor.migrate" else None,
        (MX, "MigrationExecutor.check_replacements"): bare, (ML, "MigrationLoader.all_replaced_applied"): lambda f: f"MigrationLoader.all_replaced_applied({f.f_locals['migration_key']!r}, <{len(f.f_locals['applied'])} applied>)",
        (MR, "MigrationRecorder.applied_migrations"): briefly(bare), ("django.core.management.sql", "emit_pre_migrate_signal"): briefly(bare),
        ("django.core.management.sql", "emit_post_migrate_signal"): briefly(bare),
    } | command_begins()
    answers = says(MX, "MigrationExecutor.migration_plan", how=a_plan) | says(ML, "MigrationLoader.all_replaced_applied")
    with recorded(recording, after=answers):
        do("call_command('migrate', 'yard', database='fresh', stdout=out)")
    ask("recorded_rows('fresh')")
    show('Recording a replacing migration, where none of the replaced was applied: migrate yard --database fresh, in this process (the settings module settings_three): the replacing migration is applied, and record_migration writes a row for each migration it replaces and then its own')

    ask("recorded_rows('default', 'yard')")
    with recorded(recording, after=answers):
        do("call_command('migrate', stdout=out)")
    ask("recorded_rows('default', 'yard')")
    show("check_replacements records a replacing migration where every replaced one was applied: migrate, in this process: nothing is applied, and check_replacements writes the replacing migration's row")

    quietly("plain = MigrationLoader(connections['fresh'], replace_migrations=False)")
    for question in (
        "len([key for key in plain.graph.nodes if key[0] == 'yard'])", "squashed in plain.graph.nodes", "sorted(node.key for node in plain.graph.node_map[squashed].parents)",
        "sorted(node.key for node in plain.graph.node_map[squashed].children)", "plain.graph.leaf_nodes('yard')", "plain.detect_conflicts()", "plain.replacements",
    ):
        ask(question)
    quietly("executor = MigrationExecutor(connections['fresh'])")
    quietly("second = ('yard', '0002_rename_started_repair_begun_dock_metres_and_more')")
    for question in ("sorted(name for label, name in executor.loader.graph.nodes if label == 'yard')", "second in executor.loader.graph.nodes", "second in executor.loader.applied_migrations", "executor.loader.replace_migrations"):
        ask(question)
    with recorded({(MX, "MigrationExecutor.migration_plan"): generic, (ML, "MigrationLoader.build_graph"): bare}, after=says(MX, "MigrationExecutor.migration_plan", how=a_plan)):
        do("plan = executor.migration_plan([second])")
    for question in ("executor.loader.replace_migrations", "len([key for key in executor.loader.graph.nodes if key[0] == 'yard'])"):
        ask(question)
    show('replace_migrations=False: a loader made so keeps every node, the replaced and the replacing side by side; and an executor asked for a target that is a replaced migration no longer in its graph sets its loader so, builds the graph again, and plans on that (on "fresh", where every migration of yard now has a row)')
    close_connections()


def router_asked(frame) -> str:
    """The router asked by makemigrations' consistency check: the application and the model are
    whichever a set gives first, so they are not written; what is written of the name is whether
    it is spelt as the object_name of a model of that application, which the script looks up in
    the main registry."""
    from django.apps import apps

    label = frame.f_locals["app_label"]
    name = frame.f_locals["model_name"] if "model_name" in frame.f_locals else frame.f_locals["hints"].get("model_name")
    spelt = name is not None and apps.get_model(label, name)._meta.object_name == name
    return f"{called(frame)}(db={frame.f_locals['db']!r}, app_label=<an application's label>, model_name=<a name that is the object_name of a model of that application: {spelt}>)"


@part("routing")
def the_routing() -> None:
    """Block 108 and the routing halves of blocks 18 and 100, with the settings module
    settings_routed: harbour's router, and two database files of its own."""
    set_up("settings_routed")
    for question in ("settings.DATABASE_ROUTERS", "recorded_rows('default')", "recorded_rows('archive')", "recorded_rows('default') == recorded_rows('archive')", "tables('default')", "tables('archive')", "[name for name in tables('archive') if name not in tables('default')]"):
        ask(question)
    show('What the two commands left (the settings module settings_routed): every migration has its row in both databases, though "default" was not given the two tables the router keeps for "archive"')

    step("office's first migration, the states before and after it, and a schema editor that collects statements and sends none:")
    quietly("loader = MigrationLoader(None)")
    quietly("before, after = loader.project_state(('office', '0001_initial'), at_end=False), loader.project_state(('office', '0001_initial'))")
    quietly("before.apps; after.apps  # both rendered here: the executor's states are rendered before a database half is run")
    name_it(ASKING["before"], "before")
    name_it(ASKING["after"], "after")
    quietly("creating = {operation.name: operation for operation in loader.graph.nodes['office', '0001_initial'].operations}")
    quietly("schema_editor = connection.schema_editor(collect_sql=True)")
    quietly("schema_editor.__enter__()")
    asking = operation_rules_with_states("database_forwards") | {
        (OB, "Operation.allow_migrate_model"): generic, (OPT, "Options.can_migrate"): generic, (DBU, "ConnectionRouter.allow_migrate_model"): generic,
        (DBU, "ConnectionRouter.allow_migrate"): generic, ("harbour.routers", "LogbookRouter.allow_migrate"): generic,
    } | editor_rules("create_model")
    answers = says(OB, "Operation.allow_migrate_model") | says(OPT, "Options.can_migrate") | says(DBU, "ConnectionRouter.allow_migrate_model", "ConnectionRouter.allow_migrate") | says("harbour.routers", "LogbookRouter.allow_migrate")
    with recorded(asking, after=answers):
        do("creating['Logbook'].database_forwards('office', schema_editor, before, after)")
        do("creating['Licence'].database_forwards('office', schema_editor, before, after)")
    ask("full(schema_editor.collected_sql)")
    quietly("schema_editor.__exit__(None, None, None)")
    quietly("HistoricalLogbook = after.apps.get_model('office', 'Logbook')")
    for question in (
        "creating['Logbook'].allow_migrate_model('default', HistoricalLogbook)", "creating['Logbook'].allow_migrate_model('archive', HistoricalLogbook)",
        "router.allow_migrate_model('default', Logbook)", "router.allow_migrate_model('archive', Logbook)", "router.allow_migrate_model('archive', Port)",
        "router.allow_migrate('default', 'office', model_name='logbook')", "router.allow_migrate('default', 'office', model_name='Logbook')", "router.allow_migrate('default', 'office')",
        "Logbook._meta.model_name", "Logbook._meta.object_name",
    ):
        ask(question)
    show('A CreateModel that is let through and one that is not (the settings module settings_routed): the database halves of two operations of office.0001_initial, run by hand on "default" with a schema editor that collects: for Logbook the router answers False and nothing is made; for Licence it answers None, which allows')

    step("makemigrations run in this process, as a dry run; the application whose models its check asks the router about first is whichever a set gives first, so the label and the name it passes are not written here: in their place stands whether the name is spelt as the object_name of a model of that application, which the script looks up")
    checking = {
        (CMD + "makemigrations", "Command.handle"): handled("dry_run"), (DBU, "ConnectionRouter.allow_migrate"): router_asked, ("harbour.routers", "LogbookRouter.allow_migrate"): router_asked,
        (ML, "MigrationLoader.check_consistent_history"): generic, (ML, "MigrationLoader.detect_conflicts"): bare,
    }
    with recorded(checking, after=says(DBU, "ConnectionRouter.allow_migrate") | says("harbour.routers", "LogbookRouter.allow_migrate") | says(ML, "MigrationLoader.detect_conflicts")):
        do("call_command('makemigrations', dry_run=True, stdout=out)")
    show("The consistency check and the router (the settings module settings_routed): with a router set, makemigrations looks at every database, in the order of the aliases' names; for each it asks the router about a model, giving the model's object_name for model_name, and, the model being allowed (here the first asked is), checks that database's history")
    close_connections()


@part("swappable-detection")
def swappable_detection() -> None:
    """Block 109, first half, with the settings module settings_auth: the autodetector and a foreign key to the user model."""
    set_up("settings_auth")
    from django.db.migrations.autodetector import OperationDependency

    ASKING.update(OperationDependency=OperationDependency)
    pictures = {}
    rules, after = detecting(pictures)
    for question in ("settings.AUTH_USER_MODEL", "full(settings.INSTALLED_APPS)", "Repair._meta.get_field('inspector').remote_field.model", "Repair._meta.get_field('inspector').swappable_setting"):
        ask(question)
    quietly("loader = MigrationLoader(None, ignore_no_migrations=True)")
    for question in ("loader.graph.leaf_nodes('yard')", "loader.graph.leaf_nodes('auth')", "loader.graph.root_nodes('auth')"):
        ask(question)
    quietly("autodetector = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps), MigrationQuestioner(specified_apps={'yard'}))")
    with recorded({(MA, "MigrationAutodetector._resolve_dependency"): generic} | {key: label for key, label in rules.items() if key[1].endswith(("_sort_migrations", "_build_migration_list"))},
                  after=after | says(MA, "MigrationAutodetector._resolve_dependency")):
        do("changes = autodetector.changes(graph=loader.graph, trim_to_apps={'yard'}, convert_apps={'yard'})")
    step("generated_operations as _sort_migrations was called, which the script kept: the one operation, with the dependencies the autodetector gave it, in the order of its list")
    for line in pictures["before sorting"]:
        note(line)
    for question in (
        "changes", "full(sorted(changes['yard'][0].dependencies))", "MigrationAutodetector.parse_number('0008_alter_repair_foreman')",
        "MigrationAutodetector._resolve_dependency(OperationDependency('yard', 'dock', None, OperationDependency.Type.CREATE))",
    ):
        ask(question)
    show("A dependency on a setting (the settings module settings_auth; yard's models at their sixth version): the autodetector gives the AddField of a foreign key to the user model a dependency on the setting's name, resolves it to the model the setting names only to order the operations, and leaves the migration depending on ('__setting__', 'AUTH_USER_MODEL')")
    close_connections()


@part("swappable")
def the_swappable_dependency() -> None:
    """Blocks 109 and 110, with the settings module settings_auth: the migration as the loader
    reads it back, and the receivers of post_migrate."""
    set_up("settings_auth")
    quietly("loader = MigrationLoader(None)")
    quietly("migration = loader.graph.nodes[loader.graph.leaf_nodes('yard')[0]]")
    for question in (
        "migration", "migration.dependencies", "[type(dependency).__name__ for dependency in migration.dependencies]", "[getattr(dependency, 'setting', None) for dependency in migration.dependencies]",
        "migrations.swappable_dependency('auth.User')", "migrations.swappable_dependency('auth.User').setting", "loader.check_key(('auth', '__first__'), 'yard')",
        "sorted(node.key for node in loader.graph.node_map[migration.app_label, migration.name].parents)", "full(loader.graph.forwards_plan((migration.app_label, migration.name)))",
        "migration.operations[0].field.remote_field.model", "migration.operations[0].field.swappable_setting",
    ):
        ask(question)
    quietly("text = MigrationWriter(migration, include_header=False).as_string().split('    operations = [')[0]")
    text_shown("text")
    show("The dependency read back (the settings module settings_auth): the loaded migration's dependency is a SwappableTuple, ('auth', '__first__') with the setting's value beside it; check_key turns it into auth's root node, which is the edge in the graph; a writer given the loaded migration writes the tuple and not the call, which it writes only for ('__setting__', 'AUTH_USER_MODEL')")

    for question in (
        "len(post_migrate.receivers)", "[(receiver.__module__, receiver.__qualname__) for receiver in post_migrate._live_receivers(None)[0]]",
        "len(pre_migrate.receivers)", "[(receiver.__module__, receiver.__qualname__) for receiver in pre_migrate._live_receivers(None)[0]]",
        "[(receiver.__module__, receiver.__qualname__) for receiver in pre_migrate._live_receivers(apps.get_app_config('contenttypes'))[0]]",
    ):
        ask(question)
    show("The receivers of post_migrate (the settings module settings_auth): the functions that django.contrib.auth and django.contrib.contenttypes connected as the applications were made ready, in the order they are called")
    close_connections()


def changes_shown(old: str, new: str) -> None:
    """What differs between two versions of a file: the lines taken out marked `-` and those put
    in marked `+`, each run of them with a line of the file before and after it, and `...` between runs."""
    first = True
    for line in list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=1))[2:]:
        if line.startswith("@@"):
            if not first:
                note("| ...")
            first = False
        else:
            note(("| " + line[:1] + " " + line[1:]).rstrip())


# ---------------------------------------------------------------------------------------------
# THE STORY: what the script does when it runs whole, in order.


def story() -> None:
    pin = json.load(open(os.path.join(os.path.dirname(HERE), "pin.json"), encoding="utf-8"))["trees"]["django"]["commit"]
    make_project()
    print(
        f"Django {django.VERSION[0]}.{django.VERSION[1]} in development ({django.get_version()}), at the commit {pin}, on Python {sys.version_info[0]}.{sys.version_info[1]}"
        f" with SQLite {sqlite3.sqlite_version}{', on Windows' if sys.platform == 'win32' else ''},\n"
        "and a copy of the project harbour made for the run, with a fourth application, yard, whose models change as the recording goes.\n"
        f"The formatter black {'is' if shutil.which('black') else 'is not'} on the path: Django runs it on each migration file it writes when it is.\n"
    )
    for directory, folders, names in os.walk(SCRATCH):
        folders.sort()
        for name in sorted(names):
            note(os.path.relpath(os.path.join(directory, name), SCRATCH).replace("\\", "/") + ("  (empty)" if not os.path.getsize(os.path.join(directory, name)) else ""))
    show("The run's directory as the recording begins, every file in it: the copy of harbour, and what the script has added to it, which is manage.py, settings.py and harbour/yard/__init__.py; no application has a migrations directory, and there is no database file")
    file_shown("settings.py")
    step("and manage.py, which every command line of the recording runs, in the run's directory:")
    file_shown("manage.py")
    show("The settings and manage.py, as the script wrote them: settings.py")

    write("harbour/yard/models.py", YARD_1)
    file_shown("harbour/yard/models.py")
    show("The models of yard, first version: harbour/yard/models.py")

    manage("makemigrations")
    step(
        f"the files of the run's directory that end .sqlite3 are now {database_files()!r}, of {os.path.getsize(path_of('harbour.sqlite3'))} bytes; "
        f"the applications that have a migrations directory are {[label for label in APPLICATIONS if os.path.isdir(path_of(f'harbour/{label}/migrations'))]!r}"
    )
    manage("makemigrations fleet crew office yard")
    show("makemigrations, the first time, as command lines: with no application named it makes nothing, since no application has a migrations package yet; with the four named it writes five migration files")
    run_part("makemigrations-calls")
    file_shown("harbour/fleet/migrations/0001_initial.py")
    show("A migration file as it was written: harbour/fleet/migrations/0001_initial.py")
    file_shown("harbour/yard/migrations/0001_initial.py")
    show("A second migration file as it was written: harbour/yard/migrations/0001_initial.py")
    with unchanged("migrate --plan"):
        manage("migrate --plan")
    show("migrate --plan, as a command line, on the empty database: the plan and each migration's operations, and nothing applied")
    manage("migrate")
    show("migrate, the first time, as a command line")
    run_part("migrate-calls")
    snapshot("s1")
    for name in ("migration", "operations", "state", "historical", "model-operations", "field-operations", "graph"):
        run_part(name)
    with unchanged("the part no-migrations"), aside(*APPLICATIONS):
        run_part("no-migrations", moves=True)
    for name in ("loader", "recorder"):
        run_part(name)
    snapshot("s1b")
    with unchanged("the part first-detection"), aside(*APPLICATIONS):
        run_part("first-detection", moves=True)
    with unchanged("the part yard-alone"), aside("yard"):
        run_part("yard-alone", moves=True)
    for name in ("detection", "questioner", "optimizer", "serializer", "writer"):
        run_part(name)
    snapshot("s1c")

    with unchanged("optimizemigration"):
        step("the script has written a migration of its own, harbour/yard/migrations/0002_crane.py:")
        write("harbour/yard/migrations/0002_crane.py", CRANE)
        file_shown("harbour/yard/migrations/0002_crane.py")
        manage("optimizemigration yard 0002_crane --check")
        manage("optimizemigration yard 0002_crane")
        step("the file as the command has written it again:")
        file_shown("harbour/yard/migrations/0002_crane.py")
        manage("optimizemigration yard 0002_crane")
        os.remove(path_of("harbour/yard/migrations/0002_crane.py"))
        step("the script has removed the file")
    show("optimizemigration, as command lines, on a migration of the script's own with three operations that fold into one: with --check it says so and ends with status 1; without, it writes the file again (the command prints the file's whole path, where makemigrations prints a path from the working directory; the run's directory is left out of it here)")

    with unchanged("the commands with nothing to do"):
        manage("makemigrations")
        manage("makemigrations yard")
        manage("makemigrations --check")
        manage("makemigrations --merge")
        manage("makemigrations yard nosuch")
        manage("migrate")
        manage("migrate --check")
    show("No changes, as command lines: makemigrations and migrate when the models and the migrations agree and every migration is applied; and makemigrations given a label that is no application's")
    run_part("rows", moves=True)
    snapshot("s1d")

    write("harbour/yard/models.py", YARD_2)
    models_shown(YARD_1, YARD_2)
    show("The models of yard, second version: harbour/yard/models.py, each line put in marked + and each line taken out marked -; four changes at once: Dock.name made longer, Dock.metres added, Repair.started renamed begun, and an index on Repair")
    with unchanged("migrate with nothing to apply"):
        manage("migrate")
    show("Nothing to apply, and models that have changed, as a command line: migrate with yard's models at their second version and no migration yet for the change")
    run_part("nothing-to-apply")
    with unchanged("makemigrations, dry"):
        manage("makemigrations yard --dry-run --noinput")
        manage("makemigrations yard --dry-run", answers=("n",))
    show("Yard's second version, what the autodetector sees, as command lines that write nothing: with --noinput no question can be put, and the command ends with status 3 at the first that has no answer; with a dry run and the rename refused, the default the new column needs is not asked for")
    run_part("second-detection")
    manage("makemigrations yard", answers=("y",))
    file_shown(migration_files("yard")[-1])
    show(f"Yard's second version, the question and the file: makemigrations yard as a command line, the answer y typed when it asked; and the file it wrote, {migration_files('yard')[-1]}")
    run_part("signals", moves=True)
    snapshot("s2")

    write("harbour/yard/models.py", YARD_3)
    models_shown(YARD_2, YARD_3)
    show("The models of yard, third version: harbour/yard/models.py, the line put in marked +")
    with unchanged("makemigrations, checking"):
        manage("makemigrations yard --check")
        manage("makemigrations yard --dry-run -v 3")
    show("makemigrations --check and --dry-run -v 3, as command lines, with yard's third version not yet in a migration: --check writes nothing and ends with status 1; a dry run at verbosity 3 prints the file it would write, and asks for no default")
    manage("makemigrations yard", answers=("1", "'not recorded'"))
    file_shown("harbour/yard/migrations/0003_repair_foreman.py")
    show("Yard's third version: makemigrations yard as a command line, with the answers typed when it asked: 1, for a default to be given now, and then the default; and the file it wrote, harbour/yard/migrations/0003_repair_foreman.py")
    with unchanged("makemigrations --update"):
        step("for this block the script makes Repair.foreman's max_length 80 in harbour/yard/models.py: a change not yet in a migration, while yard's latest migration is not yet applied")
        kept = read("harbour/yard/migrations/0003_repair_foreman.py")
        write("harbour/yard/models.py", YARD_3_UPDATED)
        manage("makemigrations yard --update")
        step(f"yard's migration files are now {[name.rsplit('/', 1)[-1] for name in migration_files('yard')]!r}, and the new one is:")
        file_shown(migration_files("yard")[-1])
        os.remove(path_of(migration_files("yard")[-1]))
        write("harbour/yard/migrations/0003_repair_foreman.py", kept)
        write("harbour/yard/models.py", YARD_3)
        step("the script has removed that file and put back harbour/yard/models.py and harbour/yard/migrations/0003_repair_foreman.py as they were")
    show("makemigrations --update, as a command line: the change is folded into the application's latest migration, which is written under a new name and its old file removed; the AddField the optimizer made of the two operations has the altered field, without the default that was typed, and still has preserve_default=False")
    with unchanged("the commands that only look"):
        manage("migrate --check")
        manage("migrate --plan --check")
        manage("showmigrations")
        manage("showmigrations --plan")
        manage("showmigrations --plan -v 2")
        manage("showmigrations yard -v 2")
        manage("showmigrations nosuch")
    show("migrate --check and showmigrations, as command lines, with yard's third migration written and not applied: --check ends with status 1 where there is something to apply; showmigrations lists by application, or with --plan in the order of the plan")
    run_part("foreman")
    manage("migrate")
    with unchanged("migrate --check"):
        manage("migrate --check")
    show("Yard's third migration applied, as a command line; migrate --check then ends with status 0 and prints nothing")
    snapshot("s3")

    run_part("executor")
    with unchanged("migrate with targets that are refused"):
        manage("migrate nosuch")
        manage("migrate yard 9999")
        manage("migrate yard 000")
        manage("migrate yard 0002 extra")
    show("Targets the migrate command refuses, as command lines: an application that is not installed, a name no migration begins with, a start of a name that several begin with, and one argument too many")
    with unchanged("sqlmigrate"):
        manage("sqlmigrate yard 0001")
        manage("sqlmigrate yard 0002 --backwards")
        manage("sqlmigrate crew 0002")
    show("sqlmigrate, as command lines: the statements sqlmigrate collects for a migration, forwards or backwards, each operation under a comment that names it; an operation that sends nothing has (no-op) under its name; where a table is remade, its columns need not stand in the order migrate gives them, which the block on sqlmigrate's calls shows")
    run_part("migrate-command")
    with unchanged("the unmigrated application"):
        write("settings_yard_unmigrated.py", SETTINGS_YARD_UNMIGRATED)
        file_shown("settings_yard_unmigrated.py")
        show("A second settings module, written by the script for the three blocks after this one: settings_yard_unmigrated.py")
        manage("migrate --settings=settings_yard_unmigrated")
        manage("migrate --run-syncdb --settings=settings_yard_unmigrated")
        manage("migrate yard --settings=settings_yard_unmigrated")
        manage("migrate yard --run-syncdb --settings=settings_yard_unmigrated")
        show("--run-syncdb, as command lines, with yard an unmigrated application and an empty database: migrate alone applies the migrations of the other applications and makes no table for yard; with --run-syncdb it makes yard's tables; and yard can be named only with --run-syncdb")
        run_part("unmigrated", moves=True)
        os.remove(path_of("settings_yard_unmigrated.py"))
    snapshot("s3b")

    with unchanged("makemigrations --empty, dry"):
        manage("makemigrations yard --empty --dry-run -v 3")
    manage("makemigrations yard --empty --name name_the_foremen")
    file_shown("harbour/yard/migrations/0004_name_the_foremen.py")
    show("makemigrations --empty, as command lines: a migration with no operations for the developer to fill, named auto_ and the date and the time unless --name gives a name; a dry run first, then the file written, harbour/yard/migrations/0004_name_the_foremen.py")
    empty = read("harbour/yard/migrations/0004_name_the_foremen.py")
    write("harbour/yard/migrations/0004_name_the_foremen.py", changed(changed(empty, "class Migration", DATA_FUNCTIONS + "class Migration"), "    operations = [\n    ]\n", DATA_OPERATIONS))
    file_shown("harbour/yard/migrations/0004_name_the_foremen.py")
    show("The data migration's file: harbour/yard/migrations/0004_name_the_foremen.py after the script has written two functions and two operations into the file makemigrations --empty made, as a developer would by hand")
    run_part("data-migration", moves=True)

    write("harbour/yard/models.py", YARD_4)
    models_shown(YARD_3, YARD_4)
    show("The models of yard, fourth version: harbour/yard/models.py, with a second index in Repair's Meta, the lines put in marked + and the line taken out marked -")
    write("harbour/yard/migrations/0005_repair_by_foreman.py", SEPARATE)
    file_shown("harbour/yard/migrations/0005_repair_by_foreman.py")
    with unchanged("makemigrations with nothing to do"):
        manage("makemigrations yard --check")
        manage("migrate --plan")
    show("A migration written by hand with SeparateDatabaseAndState: harbour/yard/migrations/0005_repair_by_foreman.py, which the script wrote whole, for the index of the fourth version: SQL of its own for the database, an AddIndex for the state; makemigrations then finds nothing to do")
    run_part("separate", moves=True)
    with unchanged("sqlmigrate"):
        manage("sqlmigrate yard 0004")
        manage("sqlmigrate yard 0004 --backwards")
        manage("sqlmigrate yard 0005")
    show("What sqlmigrate writes for them, as command lines: a RunSQL's own statements, and for a RunPython a comment that it cannot be written as SQL, forwards and backwards; and for the SeparateDatabaseAndState what its database operations send")
    snapshot("s4")

    write("harbour/yard/models.py", YARD_5)
    models_shown(YARD_4, YARD_5)
    show("The models of yard, fifth version: harbour/yard/models.py, the line put in marked +")
    manage("makemigrations yard --scriptable")
    file_shown("harbour/yard/migrations/0006_dock_covered.py")
    show("makemigrations --scriptable, as a command line, for yard's fifth version: what the command says goes to standard error, and standard output has only the path of each file written; and the file, harbour/yard/migrations/0006_dock_covered.py")
    write("harbour/yard/migrations/0006_long_dock.py", COLLEAGUE)
    file_shown("harbour/yard/migrations/0006_long_dock.py")
    show("A colleague's migration: harbour/yard/migrations/0006_long_dock.py, which the script wrote whole, as merging a colleague's branch would bring it; it depends on the migration that yard.0006_dock_covered depends on")
    run_part("conflict")
    with unchanged("the commands that refuse two leaf nodes"):
        manage("makemigrations")
        manage("migrate")
        manage("showmigrations yard")
        manage("makemigrations --merge --dry-run -v 3", answers=("y",))
        manage("makemigrations --merge --dry-run --noinput")
    show("Two leaf nodes, as command lines: makemigrations and migrate refuse; makemigrations --merge shows the operations of each branch and asks; a dry run at verbosity 3 prints the file it would write, whose name is made of the two leaf nodes' names; with --noinput it does not ask")
    manage("makemigrations --merge --name merge", answers=("y",))
    file_shown("harbour/yard/migrations/0007_merge.py")
    with unchanged("the commands that only look"):
        manage("showmigrations yard")
        manage("makemigrations --merge")
    manage("migrate")
    show("makemigrations --merge --name merge, as a command line, with the answer y typed when it asked: the file written, harbour/yard/migrations/0007_merge.py, has no operations and depends on both leaf nodes (the command prints the file's whole path, of which the run's directory is left out here); yard then has one leaf node, and migrate applies the three migrations")
    snapshot("s5")

    write("settings_three.py", SETTINGS_THREE)
    file_shown("settings_three.py")
    shutil.copyfile(path_of("harbour.sqlite3"), path_of("halfway.sqlite3"))
    step("the script has copied harbour.sqlite3 to halfway.sqlite3; there is no file fresh.sqlite3")
    manage("migrate yard 0003 --database halfway --settings=settings_three")
    show('A third settings module and two more databases, for the blocks on squashed migrations: settings_three.py, which adds "fresh", an empty database, and "halfway", a copy of "default" in which the script now unapplies yard\'s migrations after the third')

    squashed = f"harbour/yard/migrations/{SQUASHED}.py"
    manage(f"squashmigrations yard 0007", answers=("y",))
    file_shown(squashed)
    with unchanged("showmigrations with a squashed migration that cannot be imported"):
        manage("showmigrations yard")
    show(f"squashmigrations yard 0007, as a command line, with the answer y typed when it asked: twelve operations become seven, and the file written, {squashed}, names the eight migrations it replaces; its RunPython still names its two functions by the module of the migration they are in, which is no Python, and the comment at the file's head says to copy them (the command prints the file's whole path, of which the run's directory is left out here)")
    before = read(squashed)
    ported = changed(
        before,
        "# Functions from the following migrations need manual copying.\n# Move them and any dependencies into this file, then update the\n"
        "# RunPython operations to refer to the local versions:\n# harbour.yard.migrations.0004_name_the_foremen\n\n",
        DATA_FUNCTIONS,
    )
    ported = changed(ported, "code=harbour.yard.migrations.0004_name_the_foremen.name_foremen", "code=name_foremen")
    ported = changed(ported, "reverse_code=harbour.yard.migrations.0004_name_the_foremen.forget_foremen", "reverse_code=forget_foremen")
    write(squashed, ported)
    changes_shown(before, ported)
    with unchanged("the commands that only look"):
        manage("showmigrations yard")
        manage("migrate --plan")
        manage("makemigrations --dry-run")
    show(f"The squashed migration made importable: what the script changed in {squashed}, by hand as the comment asks: the two functions copied in, and the RunPython made to name them; showmigrations then lists it as one migration and marks it [-], which the block after this one accounts for: it has no row, and the loader counts it applied because every migration it replaces has one; and a dry run of makemigrations finds a change to make")
    run_part("squashed", moves=True)
    manage("migrate yard --database halfway --settings=settings_three")
    with unchanged("the commands that only look"):
        manage("showmigrations yard --database halfway --settings=settings_three")
        manage("migrate yard 0002 --plan --database fresh --settings=settings_three")
    show('The replacing migration where some of the replaced were applied, as command lines: on "halfway" migrate applies the five replaced migrations that were not applied, one by one, and the replacing migration is then recorded too; and on "fresh", a replaced migration can still be named as a target')
    snapshot("s6")

    for name in ("fresh.sqlite3", "halfway.sqlite3", "settings_three.py"):
        os.remove(path_of(name))
    replaced = [name for name in migration_files("yard") if not name.endswith(f"{SQUASHED}.py")]
    for name in replaced:
        os.remove(path_of(name))
    step(f"the script has removed settings_three.py and its two database files, and the {len(replaced)} migration files that the squashed migration replaces; yard's migration files are now {[name.rsplit('/', 1)[-1] for name in migration_files('yard')]!r}")
    with unchanged("the commands that only look"):
        manage("showmigrations yard")
        manage("migrate yard --prune")
    before = read(squashed)
    without_replaces, cut = re.subn(r"\n    replaces = \[.*\]\n", "", before)
    if cut != 1:
        sys.exit("recordings/migrations.py: the squashed migration has no line `replaces` to take out")
    write(squashed, without_replaces)
    step(f"the script has taken the attribute replaces out of {squashed}:")
    changes_shown(before, without_replaces)
    manage("migrate yard --prune")
    with unchanged("the commands that only look"):
        manage("migrate yard --prune")
        manage("migrate --prune")
        manage("showmigrations yard")
    show("The squash finished by hand, and --prune, as command lines: with the replaced files gone and replaces still in the squashed migration, migrate --prune refuses; with replaces taken out, it deletes the rows of the migrations that have no file; and it wants an application named")

    manage("makemigrations yard")
    file_shown(migration_files("yard")[-1])
    manage("migrate")
    show(f"What the squash left to do: the optimizer folded the AddField of Repair.foreman into the CreateModel with the default the developer typed for the rows there were, which the model does not have; makemigrations now writes an AlterField for it, {migration_files('yard')[-1]}, numbered after the last migration the squashed one replaced, and migrate applies it")
    snapshot("s7")

    write("settings_routed.py", SETTINGS_ROUTED)
    file_shown("settings_routed.py")
    step("and the router it names, harbour/routers.py, as chapter 11's recording left it:")
    file_shown("harbour/routers.py")
    step(f"the files of the run's directory that end .sqlite3 are {database_files()!r}")
    show("A fourth settings module, for the blocks on routing: settings_routed.py, with harbour's router and two database files of its own, neither of which exists yet")
    manage("migrate --settings=settings_routed")
    manage("migrate --database archive --settings=settings_routed")
    step(f"the files of the run's directory that end .sqlite3 are now {database_files()!r}")
    show('migrate with a router, as command lines (the settings module settings_routed): first for "default", then for "archive" with --database; each prints the same, for each applies every migration')
    run_part("routing")
    for name in ("routed.sqlite3", "routed_archive.sqlite3", "settings_routed.py"):
        os.remove(path_of(name))
    snapshot("s8")

    write("settings_auth.py", SETTINGS_AUTH)
    file_shown("settings_auth.py")
    write("harbour/yard/models.py", YARD_6)
    step("and harbour/yard/models.py, sixth version, the lines put in marked +:")
    models_shown(YARD_5, YARD_6)
    show("A fifth settings module, for the blocks on swappable models and on post_migrate: settings_auth.py, which installs django.contrib.auth and django.contrib.contenttypes; and the models of yard, sixth version, in which Repair has a foreign key to settings.AUTH_USER_MODEL")
    run_part("swappable-detection")
    manage("makemigrations yard --settings=settings_auth")
    file_shown(migration_files("yard")[-1])
    show(f"makemigrations yard, as a command line (the settings module settings_auth), and the file it wrote, {migration_files('yard')[-1]}: the dependency on the setting is written as a call of swappable_dependency, and the field's `to` as the setting")
    run_part("swappable")
    manage("migrate -v 2 --settings=settings_auth", squeeze=("Adding permission", "Adding content type"))
    show("migrate at verbosity 2, as a command line (the settings module settings_auth): the applications' migrations applied, each with the time it took, and around them the lines emit_pre_migrate_signal and emit_post_migrate_signal print for each application before they send; the receivers' own lines follow the application they were called for")


if PART is not None:
    PARTS[PART]()
    sys.stdout.flush()
    sys.exit(0)


def tidy() -> None:
    shutil.rmtree(SCRATCH, ignore_errors=True)


def snapshot(name: str) -> None:
    """For work on this script: with RECORDING_SNAPSHOTS naming a directory, a copy of the run's
    directory is left there at each stage of yard's story, so that one part can be tried alone."""
    kept = os.environ.get("RECORDING_SNAPSHOTS")
    if kept:
        shutil.rmtree(os.path.join(kept, name), ignore_errors=True)
        shutil.copytree(SCRATCH, os.path.join(kept, name))
    if os.environ.get("RECORDING_STOP_AT") == name:
        sys.exit(0)


atexit.register(tidy)
story()
