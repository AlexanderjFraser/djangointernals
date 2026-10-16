"""A recording of what each supported release of Django does with the same code, beside this
commit: the habits of an older Django, run under 5.2.17, 6.0.8 and 6.1.1 and under the pinned
tree, so that what an older release did is shown by a run and not told from its release notes.

    python recordings/changes.py > recordings/changes.txt

The chapter "What changed" (pages/changes.md and the pages under it) quotes this output.
Every habits module in recordings/changes/ (each .py there whose name does not begin with an
underscore; recordings/changes/_run.py says how one is written) is run four times, under a
Python of each release and under this one, and what each run prints is set out as one block
a habit, the releases in order of age:

    the habit's title
        5.2.17       what that release did: a value, or the exception raised, and the warnings
        6.0.8        ...
        6.1.1        ...
        this commit  ...

A value of several lines stands under its release's line, indented once more.

The releases are the newest of each series that was supported on the date of this commit,
2026-09-26 (pin.json says what the commit is): 5.2.17 and 6.0.8, both released 2026-08-04,
and 6.1.1, released 2026-09-02. Each is installed from PyPI into a virtual environment of its
own under reference/releases/, beside the pinned trees and gitignored with them, the first
time this runs, by the Python that runs this script; after that it is used as it is. An
environment whose Django is not the version named here is refused, never repaired: delete
it and run again. The habits run over the journal project of the chapter "A request, end to
end" (recordings/journal/), the smallest project of the book, which every release here loads.

Run it again after a re-pin, with the releases list brought up to date: where the output
changes, the chapter has to.
"""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # the same bytes on every machine

HERE = os.path.dirname(os.path.abspath(__file__))
BOOK = os.path.dirname(HERE)
HABITS = os.path.join(HERE, "changes")
RELEASES = ["5.2.17", "6.0.8", "6.1.1"]  # the newest of each supported series on 2026-09-26, oldest first
ENVIRONMENTS = os.path.join(BOOK, "reference", "releases")
THIS = "this commit"
WIDTH = 13  # the width of a release's label on a line, "this commit" and two spaces


def python_of(environment: str) -> str:
    return os.path.join(environment, "Scripts" if sys.platform == "win32" else "bin",
                        "python.exe" if sys.platform == "win32" else "python")


def version_in(python: str) -> str:
    done = subprocess.run([python, "-c", "import django; print(django.get_version())"],
                          capture_output=True, text=True, encoding="utf-8")
    return done.stdout.strip() if done.returncode == 0 else ""


def ensure(version: str) -> str:
    """The Python of a virtual environment holding exactly this release; made if it is missing."""
    environment = os.path.join(ENVIRONMENTS, f"django-{version}")
    python = python_of(environment)
    if not os.path.exists(python):
        print(f"making reference/releases/django-{version} and installing Django=={version}", file=sys.stderr)
        os.makedirs(ENVIRONMENTS, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", environment], check=True)
        subprocess.run([python, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                        f"Django=={version}"], check=True)
    found = version_in(python)
    if found != version:
        raise SystemExit(f"reference/releases/django-{version} holds Django {found or 'not at all'}, not {version}: "
                         f"delete the directory and run this again")
    return python


def run(python: str, module: str) -> list[dict]:
    """One habits module under one Python: the records it prints, one a habit."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    done = subprocess.run([python, module], cwd=HABITS, capture_output=True, env=env)
    if done.returncode:
        raise SystemExit(f"{os.path.relpath(module, BOOK)} failed under {python}:\n"
                         + done.stderr.decode("utf-8", "replace")[-3000:])
    return [json.loads(line) for line in done.stdout.decode("utf-8").splitlines() if line.strip()]


def line(label: str, record: dict) -> list[str]:
    text, warns = record["text"], record["warns"]
    warned = ("warns " + ", ".join(warns)) if warns else ""
    lines = text.split("\n") if text else []
    if len(lines) <= 1:
        value = lines[0] if lines else ""
        shown = ", ".join(part for part in (value, warned) if part) or "(no value, no error, no warning)"
        return [f"    {label:<{WIDTH}}{shown}"]
    return [f"    {label:<{WIDTH}}{warned}".rstrip()] + [f"        {text_line}" for text_line in lines]


def main() -> None:
    pythons = [(version, ensure(version)) for version in RELEASES] + [(THIS, sys.executable)]
    modules = sorted(name for name in os.listdir(HABITS) if name.endswith(".py") and not name.startswith("_"))
    this = version_in(sys.executable)
    print(f"Django {', '.join(RELEASES[:-1])} and {RELEASES[-1]} beside this commit, {this}: the same habits run "
          f"under each, over the journal project")
    print()
    for name in modules:
        module = os.path.join(HABITS, name)
        results = {label: run(python, module) for label, python in pythons}
        titles = [record["title"] for record in results[THIS]]
        for label, records in results.items():
            if [record["title"] for record in records] != titles:
                raise SystemExit(f"{name}: the habits under {label} are not those under {THIS}: a habits module "
                                 f"defines the same habits, in the same order, under every release")
        for index, title in enumerate(titles):
            print(title)
            for label, records in results.items():
                for text_line in line(label, records[index]):
                    print(text_line)
            print()


if __name__ == "__main__":
    main()
