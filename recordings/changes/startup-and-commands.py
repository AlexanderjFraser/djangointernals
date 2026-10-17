"""The habits of the section "What changed in settings, startup and the commands", release by
release: what the settings object does with the email settings that MAILERS replaces, what the
project and application templates write, what the shell imports, which databases the checks are
given, what a command does when the settings module fails to load, and the smaller changes to the
commands. Run by recordings/changes.py under each release; _run.py says how a habit is written.

The databases are SQLite's in memory, "default", and an alias "mysql" of MySQL's backend, which
no server answers: the one habit that reaches it puts a stand-in of its own in the place of the
driver's connect, which refuses. DEFAULT_AUTO_FIELD names BigAutoField, so that the check
command under 5.2 has nothing to say of journal's key. A habit that writes files writes them in
a directory of its own made for it, and one that runs a command in a Python of its own (with
`python -m django`, as django-admin runs) runs the release's Python there, with Python's colours
off; its line is the command's exit status and what it wrote to stderr, a traceback by its last
line. Where a message of Django's holds the path of such a directory, the path is cut and "…"
stands in its place.
"""
from _run import configure, habit, main

configure(
    DATABASES={
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"},
        "mysql": {"ENGINE": "django.db.backends.mysql", "NAME": "journal"},
    },
    DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
)


def settings_of(name: str, **values):
    """A LazySettings of a settings module made in memory, loaded with every warning silenced."""
    import sys
    import types
    import warnings

    from django.conf import LazySettings, Settings

    module = types.ModuleType(name)
    for key, value in values.items():
        setattr(module, key, value)
    sys.modules[name] = module
    settings = LazySettings()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        settings._wrapped = Settings(name)
    return settings


def load(name: str, **values):
    """Load a settings module made in memory, recording what the load raises and warns."""
    import sys
    import types

    from django.conf import Settings

    module = types.ModuleType(name)
    for key, value in values.items():
        setattr(module, key, value)
    sys.modules[name] = module
    Settings(name)


def run_django(arguments: list[str], settings_module: str, files: dict[str, str]) -> str:
    """Run `python -m django` with these arguments under this release's Python, in a directory of
    its own holding these files, with DJANGO_SETTINGS_MODULE set: its exit status, and what it
    wrote to stderr (a traceback by its last line)."""
    import os
    import subprocess
    import sys
    import tempfile

    with tempfile.TemporaryDirectory() as root:
        for name, text in files.items():
            with open(os.path.join(root, name), "w", encoding="utf-8") as file:
                file.write(text)
        work = os.path.join(root, "work")
        os.mkdir(work)
        # PYTHON_COLORS: a traceback is not coloured, whatever the terminal's FORCE_COLOR says.
        env = dict(os.environ, DJANGO_SETTINGS_MODULE=settings_module, PYTHONPATH=root, PYTHON_COLORS="0")
        done = subprocess.run([sys.executable, "-m", "django", *arguments], cwd=work, env=env,
                              capture_output=True, text=True, encoding="utf-8")
    stderr = done.stderr.strip()
    if stderr.startswith("Traceback"):
        return f"exit {done.returncode}, a traceback ending {stderr.splitlines()[-1]}"
    if stderr:
        return f"exit {done.returncode}: {stderr}"
    return f"exit {done.returncode}"


def written_by(command: str, name: str, path: list[str]):
    """Run startproject or startapp into a directory of its own; the namespace of the file it wrote
    at this path, run as Python."""
    import os
    import runpy
    import tempfile

    from django.core.management import call_command

    with tempfile.TemporaryDirectory() as root:
        call_command(command, name, root)
        return runpy.run_path(os.path.join(root, *path))


# The settings object and the deprecated email settings.

@habit("EMAIL_HOST = \"smtp.harbour.example\" in the settings module: the module loaded")
def email_setting_loaded():
    load("journal_mail_loaded", EMAIL_HOST="smtp.harbour.example")


@habit("settings.EMAIL_HOST, which the settings module sets")
def email_setting_read():
    settings = settings_of("journal_mail_read", EMAIL_HOST="smtp.harbour.example")
    return repr(settings.EMAIL_HOST)


@habit("settings.EMAIL_HOST; settings.EMAIL_HOST, which the settings module sets: the second read, the first's warning silenced")
def email_setting_read_again():
    import warnings

    settings = settings_of("journal_mail_again", EMAIL_HOST="smtp.harbour.example")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        settings.EMAIL_HOST
    return repr(settings.EMAIL_HOST)


@habit("EMAIL_HOST and MAILERS in the settings module: the module loaded")
def email_setting_beside_mailers():
    load("journal_mail_both", EMAIL_HOST="smtp.harbour.example",
         MAILERS={"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}})


@habit("settings.EMAIL_BACKEND, when the settings module defines MAILERS and not EMAIL_BACKEND")
def email_setting_hidden_by_mailers():
    settings = settings_of("journal_mailers",
                           MAILERS={"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}})
    return repr(settings.EMAIL_BACKEND)


@habit("with override_settings(EMAIL_BACKEND=\"django.core.mail.backends.locmem.EmailBackend\"): entered and left")
def email_setting_overridden():
    from django.test import override_settings

    with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
        pass


# What the project and application templates write.

@habit("django-admin startproject almanac: DEFAULT_AUTO_FIELD in the settings module it writes")
def startproject_default_auto_field():
    namespace = written_by("startproject", "almanac", ["almanac", "settings.py"])
    return repr(namespace["DEFAULT_AUTO_FIELD"]) if "DEFAULT_AUTO_FIELD" in namespace else "not defined"


@habit("django-admin startproject almanac: MAILERS in the settings module it writes")
def startproject_mailers():
    namespace = written_by("startproject", "almanac", ["almanac", "settings.py"])
    return repr(namespace["MAILERS"]) if "MAILERS" in namespace else "not defined"


@habit("django-admin startapp logbook: default_auto_field on the AppConfig it writes")
def startapp_default_auto_field():
    namespace = written_by("startapp", "logbook", ["apps.py"])
    config = namespace["LogbookConfig"]
    return repr(vars(config)["default_auto_field"]) if "default_auto_field" in vars(config) else "not set"


@habit("django-admin startproject almanac …/site/almanac: a directory that does not exist, nor its parent")
def startproject_into_a_new_directory():
    import os
    import tempfile

    from django.core.management import CommandError, call_command

    with tempfile.TemporaryDirectory() as root:
        target = os.path.join(root, "site", "almanac")
        try:
            call_command("startproject", "almanac", target)
        except CommandError as error:
            raise CommandError(str(error).replace(root, "…").replace(os.sep, "/")) from None
        return ", ".join(sorted(os.listdir(target)))


# The shell.

@habit("shell.Command().get_auto_imports(): what the shell imports before it starts")
def shell_auto_imports():
    from django.core.management.commands.shell import Command

    return "\n".join(Command().get_auto_imports())


# The checks and the databases.

@habit("CheckRegistry().run_checks(): the databases a check function is given when none are named")
def check_function_databases():
    from django.core.checks.registry import CheckRegistry

    registry = CheckRegistry()
    given = []

    def journal_check(app_configs=None, databases=None, **kwargs):
        given.append(databases)
        return []

    registry.register(journal_check)
    registry.run_checks()
    return repr(given[0])


@habit("call_command(\"check\"): DATABASES names a MySQL database beside SQLite's, and no MySQL server answers")
def check_command_and_mysql():
    import io

    import MySQLdb

    from django.core.management import call_command

    def refuse(*args, **kwargs):
        raise MySQLdb.OperationalError(2003, "Can't connect to MySQL server (refused by a stand-in for MySQLdb.connect)")

    connect = MySQLdb.connect
    MySQLdb.connect = refuse
    try:
        out = io.StringIO()
        call_command("check", stdout=out, stderr=out)
        return out.getvalue().strip()
    finally:
        MySQLdb.connect = connect


# A settings module that fails to load.

@habit("python -m django check, DJANGO_SETTINGS_MODULE naming a module that does not exist")
def command_with_a_missing_settings_module():
    return run_django(["check"], "almanac_nowhere", {})


@habit("python -m django startproject almanac, the settings module importing a package that is not installed")
def command_with_a_settings_module_that_fails():
    return run_django(["startproject", "almanac"], "almanac_settings",
                      {"almanac_settings.py": "import almanac_missing_package\n"})


# The smaller changes to the commands.

@habit("call_command(\"check\", \"--fail-level=WARN\"): a mistyped choice, on Python 3.14")
def mistyped_choice():
    from django.core.management import call_command

    call_command("check", "--fail-level=WARN")


@habit("call_command(\"listurls\", no_color=True)")
def listurls():
    import io

    from django.core.management import call_command

    out = io.StringIO()
    call_command("listurls", stdout=out, no_color=True)
    return out.getvalue().rstrip()


main()
