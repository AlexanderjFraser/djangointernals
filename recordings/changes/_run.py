"""Django configured for the habits, under whichever release runs this interpreter.

Every habits module in this directory imports this, and recordings/changes.py runs each
module under a Python of each release and under this commit's, collecting what it prints.
A habits module looks like this:

    from _run import configure, habit, main

    configure()                        # the journal project's applications, a SQLite database in
                                       # memory, every other setting left at the release's default

    @habit("django.VERSION[:3]")       # the title of the block the page will quote
    def version():
        import django
        return repr(django.VERSION[:3])

    main()                             # runs every habit and prints one record a habit

A habit is a function of no arguments. What it returns, as text, is what the recording shows
for the release that ran it: one line, or several joined with a newline. An exception it
raises is shown as the exception's class and the first line of its message, and every warning
raised while it runs is listed after the text by its class. Everything else that happens in
the function (a table made, a request sent, a file written to the scratch directory) is its
own business, and what it imports from Django it imports inside the function: a name that one
release lacks is then an ImportError shown on that release's line, where an import at the
module's top would stop the whole module under that release.

The rules of a habit, so that the output is the same on every run and every machine: no
address of an object (`<function f at 0x...>`), no time of day, no path of this machine; what
a set's order decides is sorted. recordings/changes.py refuses a module whose habits differ
from one release to another: the same habits, in the same order, under each.

`configure(**settings)` passes its keywords to settings.configure over the base below, and
calls django.setup() with warnings silenced for the duration of setup only. `tables()` makes
every installed model's table (migrate with run_syncdb), for a habit that needs rows.
`create(*models)` makes the tables of models a habit defines in its own function, with the
schema editor; such a model is given `app_label = "journal"` in its Meta and a name no other
habit of its module uses, since the app registry keeps a model for the whole run.
"""
import json
import os
import sys
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
RECORDINGS = os.path.dirname(HERE)
# `journal` imports from recordings/, as it would from a project's directory. The directory goes
# last on the path and not first: `http.py` in it has the name of a package of the standard
# library, which Django imports.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != RECORDINGS] + [RECORDINGS]
sys.stdout.reconfigure(encoding="utf-8", newline="\n")

HABITS: list[tuple[str, object]] = []

BASE = dict(
    INSTALLED_APPS=[
        "django.contrib.contenttypes",
        "django.contrib.auth",
        "django.contrib.sessions",
        "django.contrib.messages",
        "journal",
    ],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    SECRET_KEY="journal-not-secret",
    ROOT_URLCONF="journal.urls",
)


def habit(title: str):
    """Register the function under it as a habit, with the title the recording gives its block."""
    def register(function):
        if any(title == known for known, _ in HABITS):
            raise SystemExit(f"two habits are titled {title!r}: a title names one block of the recording")
        HABITS.append((title, function))
        return function
    return register


def configure(**settings) -> None:
    import django
    from django.conf import settings as conf

    values = dict(BASE)
    values.update(settings)
    conf.configure(**values)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        django.setup()


def tables() -> None:
    from django.core.management import call_command

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        call_command("migrate", run_syncdb=True, verbosity=0)


def create(*models) -> None:
    from django.db import connection

    with connection.schema_editor() as editor:
        for model in models:
            editor.create_model(model)


def run(function) -> tuple[str, list[str]]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            result = function()
            text = "" if result is None else str(result)
        except Exception as error:  # noqa: BLE001 - what the habit raises is what is recorded
            message = str(error)
            if isinstance(error, ImportError) and error.path:
                message = message.replace(f" ({error.path})", "")  # the file's path is this machine's
            first = message.splitlines()
            text = f"{type(error).__name__}: {first[0]}" if first else type(error).__name__
    warned: list[str] = []
    for warning in caught:
        name = warning.category.__name__
        if name not in warned:
            warned.append(name)
    return text, warned


def main() -> None:
    for title, function in HABITS:
        text, warned = run(function)
        print(json.dumps({"title": title, "text": text, "warns": warned}, ensure_ascii=False))
