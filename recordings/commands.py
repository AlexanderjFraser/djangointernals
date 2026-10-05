"""A recording of management commands: one found and run from the command line, the commands a
project has and where each comes from, what the command line does without settings and with an
error, a command called from code, the system checks, and the development server with its
reloader, which is three processes.

    python recordings/commands.py > recordings/commands.txt

Chapter 3 of the book (pages/commands.md and the pages under it) is written against this
output. It needs only the pinned Django (the project's virtual environment has it) and the
small project beside it, `orchard/`: a manage.py, two applications that each have a
management/commands directory, one model, one system check, and django.contrib.staticfiles,
which ships commands of its own. Run it again after a re-pin: where the output changes, the
chapter has to. The last part starts a server on port 8642 of this machine and stops it.

Most parts run `python manage.py ...` as a process of its own and say what came of it: the
calls it made, what it wrote to each stream, and the status it ended with. The calls are a
selection: the functions on the watch list of orchard/recorder.py, nested as they were made,
with the arguments that tell them apart, and everything between them ran and is left out.
The parts that call Django directly each run in an interpreter of their own as well.
"""
import io
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.stdout.reconfigure(newline="\n")  # the same bytes on every machine
HERE = os.path.dirname(os.path.abspath(__file__))
ORCHARD = os.path.join(HERE, "orchard")
sys.path.insert(0, ORCHARD)  # so that the project imports, as it does for its manage.py
PORT = 8642
SCRATCH = tempfile.mkdtemp()

LINES = []


def note(text: str, depth: int = 0) -> None:
    LINES.append("  " * depth + text)


def show(title: str) -> None:
    print(title)
    for line in LINES:
        print(("    " + line).rstrip())
    print()
    LINES.clear()


def environment(**extra) -> dict:
    """This process's environment without what would change a command's behaviour, and with `extra`."""
    dropped = {
        "DJANGO_SETTINGS_MODULE", "RUN_MAIN", "DJANGO_COLORS", "DJANGO_AUTO_COMPLETE", "COLUMNS", "LINES", "PYTHONSTARTUP",
        "ORCHARD_RECORDING", "ORCHARD_LIST_CHECKS", "TREES_PER_ROW", "SILENCED", "DJANGO_RUNSERVER_HIDE_WARNING",
    }
    return {**{key: value for key, value in os.environ.items() if key not in dropped}, "PYTHONIOENCODING": "utf-8", **extra}


def recorded_calls(base: str) -> list:
    """The files the recorder wrote, one for each process, oldest first: (RUN_MAIN, [(thread, depth, line)])."""
    processes = []
    for name in os.listdir(os.path.dirname(base)):
        path = os.path.join(os.path.dirname(base), name)
        if not path.startswith(base + "."):
            continue
        with open(path, encoding="utf-8") as file:
            head, *rest = file.read().splitlines()
        os.remove(path)
        started, run_main = head.split("\t")[1:]
        processes.append((float(started), run_main, [(thread, int(depth), text) for thread, depth, text in (line.split("\t", 2) for line in rest)]))
    return [(run_main, calls) for started, run_main, calls in sorted(processes)]


def said(stream: str, text: str, depth: int) -> None:
    """What a process wrote to a stream, a line to a line, with the paths of this machine made relative."""
    import recorder

    for line in recorder.tidy(text).expandtabs(8).splitlines():
        note(f"{stream} | {line}".rstrip(), depth)


def manage(arguments: str, calls=True, since="", list_checks=False, program="manage.py", traceback_tail=False, **env) -> None:
    """Run one command line in the project's directory and write down what came of it: the
    calls, from the first that begins with `since` if that is given, then the two streams."""
    base = os.path.join(SCRATCH, "calls")
    extra = {key: str(value) for key, value in env.items()}
    if calls:
        extra["ORCHARD_RECORDING"] = base
    if list_checks:
        extra["ORCHARD_LIST_CHECKS"] = "1"
    program_arguments = ["manage.py"] if program == "manage.py" else ["-m", "django"]
    done = subprocess.run(
        [sys.executable, *program_arguments, *arguments.split()], cwd=ORCHARD, env=environment(**extra), capture_output=True, encoding="utf-8",
    )
    setting = "".join(f"{key}={value} " for key, value in env.items())
    note(f"{setting}python {' '.join(program_arguments)} {arguments}")
    if calls:
        for run_main, lines in recorded_calls(base):
            first = next(index for index, (thread, depth, text) in enumerate(lines) if text.startswith(since))
            for thread, depth, text in lines[first:]:
                note(text, 1 + depth - lines[first][1])
    said("stdout", done.stdout, 1)
    stderr = done.stderr
    if traceback_tail and stderr.startswith("Traceback"):
        note("stderr | Traceback (most recent call last):", 1)
        note("stderr |   (the frames)", 1)
        stderr = stderr.strip().splitlines()[-1]
    said("stderr", stderr, 1)
    note(f"exit status {done.returncode}", 1)


def raised(action) -> str:
    """What a call answered: its value, or the exception it raised."""
    try:
        return repr(action())
    except Exception as exc:
        return f"raises {type(exc).__name__}: {exc}"


def did(what: str, action) -> None:
    """One thing this script did, as a line, with the watched calls it set off under it."""
    import recorder

    note(what)
    answer = raised(lambda: recorder.watched(action, lambda thread, depth, text: note(text, 1 + depth)))
    note(f"-> {answer}", 1)


# ---------------------------------------------------------------------------------------------
# The parts that are command lines.

RUN = "BaseCommand.run_from_argv"  # where a block begins that leaves out how the command was found


def part_command_line() -> None:
    manage("count 3 --per-row 10")
    show("A command of the project, from the command line")

    manage("juice --kilos 10", since=RUN)
    show("A command that returns its output and asks for no system checks, from BaseCommand.run_from_argv on")

    manage("prune 4 7", since=RUN)
    show("A LabelCommand that asks for the checks of two tags, from BaseCommand.run_from_argv on")


def part_errors() -> None:
    manage("juice", since=RUN)
    show("A command raises CommandError, from BaseCommand.run_from_argv on")

    manage("juice --traceback", calls=False, traceback_tail=True)
    manage("juice --kilos -1", calls=False, traceback_tail=True)
    show("CommandError with --traceback, and an exception that is not a CommandError")

    manage("juice --kilos ten", since=RUN)
    show("An argument the parser refuses, from BaseCommand.run_from_argv on")

    manage("cont 3", calls=False)
    manage("count", calls=False)
    show("A command that does not exist, and a command given too little")

    manage("count --help", calls=False)
    show("The help of one command: its own arguments, then those every command has")


def part_no_settings() -> None:
    manage("count 3", calls=False, program="django")
    manage("check", calls=False, program="django")
    manage("shell --no-imports -c print(40+2)", calls=False, program="django")
    show("No settings: python -m django, with DJANGO_SETTINGS_MODULE not set")

    manage("count 3 --settings=orchard.no_such_settings", calls=False)
    manage("check --settings=orchard.no_such_settings", calls=False)
    manage("count 3 --settings=orchard.settings", calls=False, program="django")
    show("The --settings option, for a module that does not exist and for one that does")


def part_checks_run() -> None:
    manage("check", since=RUN, list_checks=True)
    show("python manage.py check, from BaseCommand.run_from_argv on")

    manage("check --database default --tag database --tag trees", since="BaseCommand.execute", list_checks=True)
    show("The checks of two tags, one of them the tag that is left out unless asked for, from BaseCommand.execute on")

    manage("count 3", since="BaseCommand.execute", TREES_PER_ROW=18)
    show("A check returns a warning and the command runs, from BaseCommand.execute on")

    manage("count 3", since=RUN, TREES_PER_ROW=30)
    show("A check returns an error and the command does not run, from BaseCommand.run_from_argv on")

    manage("count 3 --skip-checks", calls=False, TREES_PER_ROW=30)
    manage("count 3", calls=False, TREES_PER_ROW=30, SILENCED="trees.E001")
    manage("check", calls=False, TREES_PER_ROW=30, SILENCED="trees.E001")
    manage("check --fail-level WARNING", calls=False, TREES_PER_ROW=18)
    show("The same error skipped and silenced, and a warning made to fail")

    manage("check --deploy", calls=False)
    show("python manage.py check --deploy, for this project")

    manage("check --list-tags", calls=False)
    show("The tags that the registered checks carry")


# ---------------------------------------------------------------------------------------------
# The parts that call Django from this process.

def setup() -> None:
    os.environ["DJANGO_SETTINGS_MODULE"] = "orchard.settings"
    import django

    django.setup()


def part_owners() -> None:
    """Which commands there are, and which application each is loaded from."""
    setup()
    from django.apps import apps
    from django.core import management

    owners = management.get_commands()
    places = [("django.core", management.__path__[0])] + [(config.name, os.path.join(config.path, "management")) for config in apps.get_app_configs()]
    for name, path in places:
        mine = sorted(management.find_commands(path))
        note(f"{name}" + ("" if mine else "  has no management/commands directory"))
        line = ""
        for command in mine:
            shadowed = owners[command] != name
            word = f"{command} (not used: {owners[command]} has one)" if shadowed else command
            if len(line) + len(word) > 88:
                note(line.rstrip(), 1)
                line = ""
            line += word + ", "
        if line:
            note(line.rstrip(", "), 1)
    show("The commands of the project: what find_commands finds in each place, in the order of INSTALLED_APPS")


def part_shipped() -> None:
    """For each command class of django.core and of django.contrib.staticfiles: which of the
    attributes that BaseCommand reads its own class sets, and which of BaseCommand's methods
    of the machinery (not add_arguments or handle, which nearly all define) it overrides."""
    setup()
    from django.core import management
    from django.core.management.base import AppCommand, BaseCommand, LabelCommand

    attributes = ("requires_system_checks", "requires_migrations_checks", "requires_settings", "output_transaction", "stealth_options", "suppressed_base_arguments")
    methods = ("__init__", "run_from_argv", "create_parser", "execute", "get_check_kwargs", "check", "check_migrations", "add_base_argument", "get_version")
    for app, path in (("django.core", management.__path__[0]), ("django.contrib.staticfiles", None)):
        path = path or os.path.join(os.path.dirname(sys.modules[app].__file__), "management")
        note(app)
        for name in sorted(management.find_commands(path)):
            cls = type(management.load_command_class(app, name))
            base = next(base for base in cls.__mro__[1:] if base.__module__ != cls.__module__)
            parent = base.__name__ if base in (BaseCommand, AppCommand, LabelCommand) else f"{base.__module__.rsplit('.', 1)[-1]}.{base.__name__}"
            sets = [f"{attribute} = {q(vars(cls)[attribute])}" for attribute in attributes if attribute in vars(cls)]
            overrides = [method for method in methods if method in vars(cls)]
            note(f"{name}  ({parent})", 1)
            for line in sets:
                note(line, 2)
            if overrides:
                note("overrides " + ", ".join(overrides), 2)
    show("The commands of django.core and of django.contrib.staticfiles: the base of each, and what its own class sets and overrides of what BaseCommand defines")


def q(value) -> str:
    import recorder

    return recorder.q(sorted(value) if isinstance(value, (set, frozenset)) else list(value) if isinstance(value, tuple) else value)


def part_call_command() -> None:
    setup()
    from django.core.management import call_command

    out = io.StringIO()
    did('call_command("count", 3, per_row=10, stdout=out)', lambda: call_command("count", 3, per_row=10, stdout=out))
    note(f"out.getvalue()  -> {out.getvalue()!r}")
    show("call_command: a command called from code")

    out = io.StringIO()
    did('call_command("juice", kilos=10, stdout=out), a command that returns its output', lambda: call_command("juice", kilos=10, stdout=out))
    note(f"out.getvalue()  -> {out.getvalue()!r}")
    show("call_command: what the command returns is returned, and written as well")

    out = io.StringIO()
    did('call_command("count", 3, "--per-row", "10", stdout=out), the option as the command line spells it', lambda: call_command("count", 3, "--per-row", "10", stdout=out))
    note(f"out.getvalue()  -> {out.getvalue()!r}")
    out = io.StringIO()
    did('call_command("count", 3, per_row="10", stdout=out), the option as a keyword, and its value a string', lambda: call_command("count", 3, per_row="10", stdout=out))
    note(f"out.getvalue()  -> {out.getvalue()!r}")
    show("call_command: an option given as an argument is parsed, and one given as a keyword is not")

    did('call_command("juice")', lambda: call_command("juice"))
    did('call_command("count", "three")', lambda: call_command("count", "three"))
    did('call_command("count", 3, colour=True)', lambda: call_command("count", 3, colour=True))
    did('call_command("cont", 3)', lambda: call_command("cont", 3))
    show("call_command: errors reach the caller as exceptions")

    did('call_command("count", rows=3)', lambda: call_command("count", rows=3))
    show("call_command: a positional argument given as a keyword")


def part_call_command_checks() -> None:
    os.environ["TREES_PER_ROW"] = "30"
    setup()
    from django.core.management import call_command

    out = io.StringIO()
    note("TREES_PER_ROW is 30, for which the check of the trees application returns an error")
    did('call_command("count", 3, stdout=out)', lambda: call_command("count", 3, stdout=out))
    did('call_command("count", 3, stdout=out, skip_checks=False)', lambda: raised_first_line(lambda: call_command("count", 3, stdout=out, skip_checks=False)))
    show("call_command runs no system checks unless it is asked to")

    did('call_command("juice", kilos=10, stdout=out, skip_checks=False)', lambda: call_command("juice", kilos=10, stdout=out, skip_checks=False))
    did('call_command("check", stdout=out)', lambda: raised_first_line(lambda: call_command("check", stdout=out)))
    show("call_command and the checks: a command whose class asks for none, and the check command")


def raised_first_line(action):
    """As `action`, with a message of several lines cut to its first."""
    try:
        return action()
    except Exception as exc:
        raise type(exc)(str(exc).strip().splitlines()[0] + " ...") from None


def part_registry() -> None:
    setup()
    from django.core.checks.registry import registry

    def home(check) -> str:
        return check.__module__

    for title, checks in (("registered_checks", registry.registered_checks), ("deployment_checks", registry.deployment_checks)):
        note(title)
        by_module = {}
        for check in checks:
            by_module.setdefault(home(check), []).append(check)
        for module in sorted(by_module):
            tags = sorted({tag for check in by_module[module] for tag in check.tags})
            names = sorted(check.__name__ for check in by_module[module])
            note(f"{module}  tagged {', '.join(tags) if tags else '(no tag)'}", 1)
            line = ""
            for name in names:
                if len(line) + len(name) > 84:
                    note(line.rstrip(), 2)
                    line = ""
                line += name + ", "
            note(line.rstrip(", "), 2)
    show("The check registry after django.setup(), by the module that defines each check")


# ---------------------------------------------------------------------------------------------
# The development server and its reloader.

def get(path: str, patience: float):
    """Ask the server for a path until it answers or patience runs out: the status, or the error."""
    end = time.time() + patience
    while True:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=5) as response:
                return response.status
        except OSError as exc:
            if time.time() > end:
                return "no answer"
            time.sleep(0.2)


def wait_for(condition, patience: float) -> bool:
    end = time.time() + patience
    while not condition():
        if time.time() > end:
            return False
        time.sleep(0.1)
    return True


def part_runserver() -> None:
    import recorder

    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", PORT)) == 0:
            sys.exit(f"port {PORT} is in use: the recording of the development server needs it")
    base = os.path.join(SCRATCH, "server")
    views = os.path.join(ORCHARD, "orchard", "views.py")
    modified = os.stat(views).st_mtime

    def logs() -> list:
        return [name for name in os.listdir(SCRATCH) if name.startswith("server.")]

    def reached(text: str, process: int) -> bool:
        """Whether the process of that number, oldest first, has written a line that holds the text."""
        names = sorted(logs(), key=lambda name: open(os.path.join(SCRATCH, name), encoding="utf-8").readline())
        if len(names) <= process:
            return False
        return text in open(os.path.join(SCRATCH, names[process]), encoding="utf-8").read()

    server = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", str(PORT)], cwd=ORCHARD, env=environment(ORCHARD_RECORDING=base, PYTHONUNBUFFERED="1"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8",
    )
    try:
        note(f"python manage.py runserver {PORT}")
        note(f"GET /  -> {get('/', 60)}")
        # The reloader's first look at the files only notes their times. Let it finish one.
        wait_for(lambda: reached("BaseReloader.run_loop", 1), 30)
        time.sleep(3)
        stamp = max(time.time(), modified) + 2
        os.utime(views, (stamp, stamp))
        note("the modification time of orchard/views.py is set two seconds ahead")
        wait_for(lambda: reached("serve_forever", 2), 60)
        note(f"GET /  -> {get('/', 60)}")
        note(f"GET /stop/, whose view ends its process with os._exit(7)  -> {get('/stop/', 0)}")
        output = server.communicate(timeout=60)[0]
        note(f"the first process ends with status {server.returncode}")
        show("The development server: what the recording did, and what it was answered")
    finally:
        os.utime(views, (modified, modified))
        if server.poll() is None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(server.pid)], capture_output=True)
            else:
                server.kill()

    ordinal = ["first", "second", "third"]
    asked = iter(["GET /", "GET /", "GET /stop/"])
    for number, (run_main, calls) in enumerate(recorded_calls(base)):
        threads = []
        for thread, depth, text in calls:
            if thread not in threads:
                threads.append(thread)
        for thread in threads:
            mine = [(depth, text) for name, depth, text in calls if name == thread]
            later = ""
            if number == 2 and thread == "MainThread":
                # As the second process's, line for line, as far as this call.
                first = next(index for index, (depth, text) in enumerate(mine) if text.startswith("run_with_reloader"))
                mine, later = [(depth - mine[first][0], text) for depth, text in mine[first:]], ", from run_with_reloader on"
            for depth, text in mine:
                note(text, depth)
            if thread == "MainThread":
                which = ("its main thread" if len(threads) > 1 else "its only thread") + later
            elif thread == "django-main-thread":
                which = "the thread django-main-thread"
            else:
                which = f"the thread started for the connection that sent {next(asked)}"
            origin = "python manage.py runserver, with RUN_MAIN not set" if run_main == "None" else f'started by the first with RUN_MAIN="{run_main}"'
            show(f"The development server: the {ordinal[number]} process ({origin}), {which}")

    for line in recorder.tidy(output).splitlines():
        line = re.sub(r"^\w+ \d{2}, \d{4} - \d{2}:\d{2}:\d{2}$", "(the date and the time)", line)
        line = re.sub(r"^\[\d{2}/\w{3}/\d{4} \d{2}:\d{2}:\d{2}\]", "[(the date and the time)]", line)
        note(f"| {line}".rstrip())
    show("The development server: what the three processes wrote to the terminal, standard output and standard error together")


PARTS = {
    "command-line": part_command_line, "owners": part_owners, "shipped": part_shipped, "no-settings": part_no_settings, "errors": part_errors,
    "call-command": part_call_command, "call-command-checks": part_call_command_checks, "registry": part_registry,
    "checks-run": part_checks_run, "runserver": part_runserver,
}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        PARTS[sys.argv[1]]()
    else:
        import django

        print(
            f"Django {django.get_version()} on Python {sys.version_info.major}.{sys.version_info.minor} ({sys.platform}), and the project orchard: "
            "django.contrib.staticfiles and two applications with commands\n"
        )
        sys.stdout.flush()
        for part in PARTS:
            done = subprocess.run([sys.executable, __file__, part], capture_output=True, encoding="utf-8", env=environment())
            if done.returncode:
                sys.exit(done.stderr or done.stdout)
            sys.stdout.write(done.stdout)
