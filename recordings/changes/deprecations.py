"""The habits of the section "What still warns: the deprecations and the releases that end them",
release by release: which line a deprecation warning names, and what a project sees of it, run
plainly and with python -Wd; the base of the warning classes, which decides what Python shows;
and the old names of those classes. Run by recordings/changes.py under each release; _run.py says
how a habit is written. What each deprecated use does, and when it began to warn, is recorded by
the habits of the section that tells its change.

A habit that runs a project runs it in a directory of its own made for it, under this release's
Python (sys.executable), with no -W option inherited, none of PYTHONWARNINGS, PYTHONDEVMODE and
PYTHONWARNDEFAULTENCODING (each changes which warnings Python shows), PYTHONPATH or
DJANGO_SETTINGS_MODULE, and Python's colours off. Its line is what Python wrote to stderr, the
path of the directory cut. main.py imports diary.py, as a project's code is imported, so that a
warning naming a line of diary.py is the module diary's and not __main__'s: Python's default
filters show a DeprecationWarning of __main__ only, and manage.py, run as a script, is __main__. In
the runs of diary.py a warning is given by its class and the line it names: a line of the project
by its file and line number ("this line" where it is the line of the use), a line of Django by its
file under the django package and the function it is in, so that the line does not depend on
where a release is installed or on its line numbers. The markers diary.py writes, which tell one
use from the next, are not shown, and a use that fails for the name it imports, which its release
lacks (AsyncPaginator under 5.2.17), warns nothing and is not shown either; any other failure
stops the module.
"""
from _run import configure, habit, main

configure()

# The deprecated uses of diary.py, each in the order it runs: the text the line gives it, the
# lines that set it up (which warn nothing), and the line of the use itself.
USES = [
    ("from django.utils.deprecation import MiddlewareMixin", [],
     "from django.utils.deprecation import MiddlewareMixin"),
    ("from django.core.mail import BadHeaderError", [],
     "from django.core.mail import BadHeaderError"),
    ("class EntryAdmin(ModelAdmin): list_select_related = True", ["from django.contrib.admin import ModelAdmin"],
     "class EntryAdmin(ModelAdmin): list_select_related = True"),
    ("Entry.objects.select_related()", ["from journal.models import Entry"],
     "Entry.objects.select_related()"),
    ("Paginator(range(10), 2, orphans=2)", ["from django.core.paginator import Paginator"],
     "Paginator(range(10), 2, orphans=2)"),
    ("AsyncPaginator(range(10), 2, orphans=2)", ["from django.core.paginator import AsyncPaginator"],
     "AsyncPaginator(range(10), 2, orphans=2)"),
    ("urlize(\"journal.example.com\")", ["from django.utils.html import urlize"],
     "urlize(\"journal.example.com\")"),
]

MAIN = '''\
import os
import sys

sys.path.append(os.environ["JOURNAL_RECORDINGS"])

import django
from django.conf import settings

settings.configure(
    INSTALLED_APPS=[
        "django.contrib.contenttypes",
        "django.contrib.auth",
        "django.contrib.admin",
        "django.contrib.sessions",
        "django.contrib.messages",
        "journal",
    ],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    SECRET_KEY="journal-not-secret",
    ROOT_URLCONF="journal.urls",
)
django.setup()

import diary

diary.run()
'''

SETTINGS = '''\
SECRET_KEY = "almanac-not-secret"
INSTALLED_APPS = []
EMAIL_HOST = "smtp.harbour.example"
'''


def diary() -> tuple[str, dict[int, int]]:
    """diary.py, and for each use the number of the line that holds it."""
    lines = ["import sys", "", "",
             "def mark(text):", "    sys.stderr.write('@@ ' + text + '\\n')", "    sys.stderr.flush()", "", "",
             "def run():"]
    holds = {}
    for index, (_, setup, use) in enumerate(USES):
        lines.append(f"    mark('use {index}')")
        lines.append("    try:")
        lines.extend(f"        {line}" for line in setup)
        lines.append(f"        {use}")
        holds[index] = len(lines)
        lines.append("    except Exception as error:")
        lines.append("        mark('failed ' + type(error).__name__ + ' ' + str(getattr(error, 'name_from', None)))")
    lines.append("    mark('end')")
    return "\n".join(lines) + "\n", holds


def python(arguments: list[str], files: dict[str, str]) -> tuple[str, str]:
    """Run this release's Python with these arguments in a directory of its own holding these
    files: what it wrote to stderr, and the directory's path as it was."""
    import os
    import subprocess
    import sys
    import tempfile

    recordings = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {name: value for name, value in os.environ.items()
           if name not in ("PYTHONWARNINGS", "PYTHONDEVMODE", "PYTHONWARNDEFAULTENCODING",
                           "DJANGO_SETTINGS_MODULE", "PYTHONPATH")}
    env.update(PYTHON_COLORS="0", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1",
               JOURNAL_RECORDINGS=recordings)
    with tempfile.TemporaryDirectory() as root:
        for name, text in files.items():
            path = os.path.join(root, *name.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as file:
                file.write(text)
        done = subprocess.run([sys.executable, *arguments], cwd=root, env=env,
                              capture_output=True, text=True, encoding="utf-8")
        if done.returncode:
            raise RuntimeError(f"exit {done.returncode}: {done.stderr.strip().splitlines()[-1]}")
        return done.stderr, root


def in_django(path: str, number: int) -> str:
    """A line of this release's django package: its file there, and the function it is in."""
    import ast
    import os

    import django

    package = os.path.dirname(os.path.abspath(django.__file__))
    with open(path, encoding="utf-8") as file:
        tree = ast.parse(file.read())
    names: list[str] = []

    def find(node, outer):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                    and child.lineno <= number <= child.end_lineno:
                names[:] = outer + [child.name]
                find(child, outer + [child.name])

    find(tree, [])
    where = "django/" + os.path.relpath(path, package).replace(os.sep, "/")
    return f"{where}, in {'.'.join(names)}" if names else where


def warnings_written(stderr: str, root: str) -> list[tuple[str, str, str]]:
    """The warnings Python wrote, each as (the marker before it, its class, the line it names)."""
    import os
    import re

    found = []
    marker = ""
    for line in stderr.splitlines():
        if line.startswith("@@ "):
            marker = line[3:]
            continue
        match = re.match(r"(.+?):(\d+): (\w+): ", line)
        if not match:
            continue  # the source line Python prints under a warning, or the rest of its message
        path, number, category = match.group(1), int(match.group(2)), match.group(3)
        if path.startswith(root + os.sep):
            named = path[len(root) + 1:].replace(os.sep, "/") + f", line {number}"
        else:
            named = in_django(path, number)
        found.append((marker, category, named))
    return found


def run_diary(flags: list[str]) -> str:
    source, holds = diary()
    stderr, root = python([*flags, "main.py"], {"main.py": MAIN, "diary.py": source})
    width = max(len(shown) for shown, _, _ in USES)
    lines = []
    for marker, category, named in warnings_written(stderr, root):
        if not marker.startswith("use "):
            raise RuntimeError(f"a warning outside the uses of diary.py: {category}, {named}")
        index = int(marker.split()[1])
        if named == f"diary.py, line {holds[index]}":
            named = "diary.py, this line"
        lines.append(f"{USES[index][0]:<{width}}  {category:<26}  {named}")
    marker = ""
    for line in stderr.splitlines():
        if line.startswith("@@ use "):
            marker = line
        elif line.startswith("@@ failed "):
            # A use may fail only for the name it imports that its release lacks, and then warns
            # nothing.
            _, _, category, name = line.split(" ", 3)
            index = int(marker.split()[2])
            codes = [*USES[index][1], USES[index][2]]
            if category != "ImportError" or not any(code.endswith(f" import {name}") for code in codes):
                raise RuntimeError(f"a use of diary.py failed: {USES[index][0]}: {line[3:]}")
    if not lines and any(not line.startswith("@@ ") for line in stderr.splitlines()):
        raise RuntimeError("diary.py's run wrote to stderr what is not a warning")
    return "\n".join(lines) if lines else "nothing written"


def run_manage(flags: list[str]) -> str:
    import os

    import django

    template = os.path.join(os.path.dirname(django.__file__), "conf", "project_template", "manage.py-tpl")
    with open(template, encoding="utf-8") as file:
        manage = file.read().replace("{{ project_name }}", "almanac")
    stderr, root = python([*flags, "manage.py", "check"],
                          {"manage.py": manage, "almanac/__init__.py": "", "almanac/settings.py": SETTINGS})
    text = stderr.replace(root + os.sep, "").replace(root, "…").rstrip()
    return text or "nothing written"


# What a project sees: a module of its own making deprecated calls, run from a script.

@habit("python -Wd main.py, main.py running diary.py's deprecated calls: each call that warns, its warning, and the line the warning names")
def diary_with_wd():
    return run_diary(["-Wd"])


@habit("python main.py, the same calls without -Wd: what Python writes to stderr")
def diary_plainly():
    return run_diary([])


# The settings warnings, raised as manage.py loads the settings.

@habit("python manage.py check, the settings module setting EMAIL_HOST: what Python writes to stderr")
def manage_plainly():
    return run_manage([])


@habit("python -Wd manage.py check, the same settings: what Python writes to stderr")
def manage_with_wd():
    return run_manage(["-Wd"])


# The warning classes.

@habit("The warning a settings module setting EMAIL_HOST raises: the base of its class")
def email_setting_warning_base():
    import sys
    import types
    import warnings

    from django.conf import Settings

    module = types.ModuleType("journal_deprecations_mail")
    module.EMAIL_HOST = "smtp.harbour.example"
    sys.modules[module.__name__] = module
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Settings(module.__name__)
    bases = []
    for warning in caught:
        base = warning.category.__mro__[1].__name__
        if base not in bases:
            bases.append(base)
        # Raised again, so that the line lists the class as every habit's line does.
        warnings.warn_explicit(warning.message, warning.category, warning.filename, warning.lineno)
    return ", ".join(bases) or "no warning"


@habit("from django.utils.deprecation import RemovedInDjango70Warning: the class it gives")
def old_name_70():
    from django.utils.deprecation import RemovedInDjango70Warning
    return f"{RemovedInDjango70Warning.__module__}.{RemovedInDjango70Warning.__qualname__}"


@habit("from django.utils.deprecation import RemovedInDjango71Warning: whether the name exists")
def old_name_71():
    from django.utils.deprecation import RemovedInDjango71Warning
    return f"{RemovedInDjango71Warning.__module__}.{RemovedInDjango71Warning.__qualname__}"


main()
