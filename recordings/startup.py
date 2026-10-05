"""A recording of a process becoming a configured Django: the settings loaded on their first
read, the app registry populated in its three phases, and what each of the two objects answers
before, during and after.

    python recordings/startup.py > recordings/startup.txt

Chapter 2 of the book (pages/startup.md and the pages under it) is written against this
output. It needs only the pinned Django (the project's virtual environment has it) and the
small project beside it, `library/`: three applications, entered in INSTALLED_APPS in the
three forms an entry can take, one of them with a model that names two others by string. Run
it again after a re-pin: where the output changes, the chapter has to.

Startup happens once in a process, so each part of the recording is made in an interpreter of
its own: run with no argument, this script runs itself once for each part and prints what
they print. What is written down is a selection: the calls the chapter names, nested as they
were made, with the arguments that tell them apart. Everything between them ran and is left
out.
"""
import logging
import os
import subprocess
import sys

sys.stdout.reconfigure(newline="\n")  # the same bytes on every machine
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # so that `library` imports, as it would from a project's directory

LINES = []
STACK = []  # the watched frames open at this moment: the depth of the next line
BASE = 0  # how far the calls are set in under the line that says what the script did


def note(text: str) -> None:
    LINES.append("  " * (BASE + len(STACK)) + text)


def show(title: str) -> None:
    print(title)
    for line in LINES:
        print("    " + line)
    print()
    LINES.clear()
    STACK.clear()


def raised(action) -> str:
    """What a call answered: its value, or the exception it raised."""
    try:
        return repr(action())
    except Exception as exc:
        return f"raises {type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------------------------
# What to write down, and how to say it. A label function is given the frame at the moment of
# the call and returns the line, or None for a call not to write down.

def plain(frame) -> str:
    return frame.f_code.co_qualname


def named(frame) -> str:
    return f'{frame.f_code.co_qualname}("{frame.f_locals["name"]}")'


def attribute_read(frame):
    name = frame.f_locals["name"]
    return f'LazyObject.__getattribute__("{name}")' if name.isupper() else None  # a setting, not a method


def attribute_set(frame):
    name, value = frame.f_locals["name"], frame.f_locals["value"]
    if not (name.isupper() or name == "_wrapped"):
        return None  # an attribute of the object's own, not a setting
    shown = repr(value) if isinstance(value, (bool, int, str, list)) else f"a {type(value).__name__}"
    return f'{frame.f_code.co_qualname}("{name}", {shown})'


def imported(frame) -> str:
    return f"import {frame.f_globals['__name__']}"


def config_made(frame) -> str:
    return f'AppConfig.__init__("{frame.f_locals["app_name"]}", app_module)  ({type(frame.f_locals["self"]).__name__})'


def of_app(frame) -> str:
    return f"{frame.f_code.co_qualname}  ({frame.f_locals['self'].label})"


def model_class(frame):
    bases = frame.f_locals["bases"]
    if not any(type(base).__name__ == "ModelBase" for base in bases):
        return None  # Model itself
    return f"ModelBase.__new__  (class {frame.f_locals['name']})"


def keys_text(keys) -> str:
    return ", ".join(f'("{app}", "{model}")' for app, model in keys)


def waiting_function(function):
    """The function a lazy operation was first given, and the field it was given for."""
    keywords = {}
    while hasattr(function, "func"):
        keywords.update(getattr(function, "keywords", None) or {})
        function = function.func
    field = keywords.get("field")
    return function.__name__, (field.name if field is not None else None)


def lazy_operation(frame) -> str:
    registry, keys = frame.f_locals["self"], frame.f_locals["model_keys"]
    name, field = waiting_function(frame.f_locals["function"])
    what = f"{name} for the field {field}" if field else name
    if not keys:
        return f"Apps.lazy_model_operation({what})  no model left to wait for: it is called"
    app, model = keys[0]
    state = "is registered" if model in registry.all_models.get(app, {}) else "is not registered: the function is kept"
    return f"Apps.lazy_model_operation({what}, {keys_text(keys)})  {app}.{model} {state}"


def pending_run(frame) -> str:
    registry, model = frame.f_locals["self"], frame.f_locals["model"]
    waiting = len(registry._pending_operations.get((model._meta.app_label, model._meta.model_name), []))
    return f"Apps.do_pending_operations({model._meta.label})  {waiting} waiting"


def resolved(frame) -> str:
    local = frame.f_locals
    return f"resolve_related_class(model={local['model'].__name__}, related={local['related'].__name__}, field={local['field'].name})"


def changed(frame):
    """A send of setting_changed, with how many receivers it reaches."""
    from django.core.signals import setting_changed

    signal, local = frame.f_locals["self"], frame.f_locals["named"]
    if signal is not setting_changed:
        return None
    value = local["value"]
    shown = repr(value) if isinstance(value, (bool, int, str)) else f"a {type(value).__name__}"
    sync, asynchronous = signal._live_receivers(frame.f_locals["sender"])
    return (
        f'setting_changed.{frame.f_code.co_name}(setting="{local["setting"]}", value={shown}, '
        f"enter={local['enter']})  to {len(sync) + len(asynchronous)} receivers"
    )


# (module, qualname) -> the label function. A module ending in "." matches that package and
# everything under it; a qualname of "*.name" matches any method of that name.
SETTINGS = {
    ("django.utils.functional", "LazyObject.__getattribute__"): attribute_read,
    ("django.conf", "LazySettings.__getattr__"): named,
    ("django.conf", "LazySettings._setup"): named,
    ("django.conf", "LazySettings.__setattr__"): attribute_set,
    ("django.conf", "LazySettings.configure"): plain,
    ("django.conf", "Settings.__init__"): lambda f: f'Settings.__init__("{f.f_locals["settings_module"]}")',
    ("django.conf", "UserSettingsHolder.__init__"): lambda f: f"UserSettingsHolder.__init__({f.f_locals['default_settings'].__name__.rsplit('.', 1)[-1]})",
    ("django.conf", "UserSettingsHolder.__getattr__"): named,
    ("library.settings", "<module>"): imported,
}

SETUP = {
    ("django", "setup"): plain,
    ("django.conf", "LazySettings.__getattr__"): named,
    ("django.conf", "LazySettings._setup"): named,
    ("django.conf", "Settings.__init__"): lambda f: f'Settings.__init__("{f.f_locals["settings_module"]}")',
    ("library.", "<module>"): imported,
    ("django.utils.log", "configure_logging"): lambda f: f'configure_logging("{f.f_locals["logging_config"]}", {f.f_locals["logging_settings"]})',
    ("django.utils.log", "AdminEmailHandler.__init__"): plain,
    ("django.urls.base", "set_script_prefix"): lambda f: f'set_script_prefix("{f.f_locals["prefix"]}")',
    ("django.apps.registry", "Apps.populate"): plain,
    ("django.apps.config", "AppConfig.create"): lambda f: f'AppConfig.create("{f.f_locals["entry"]}")',
    ("django.apps.config", "AppConfig.__init__"): config_made,
    ("django.apps.config", "AppConfig.import_models"): of_app,
    ("django.db.models.base", "ModelBase.__new__"): model_class,
    ("django.apps.registry", "Apps.get_containing_app_config"): lambda f: f'Apps.get_containing_app_config("{f.f_locals["object_name"]}")',
    ("django.apps.registry", "Apps.lazy_model_operation"): lazy_operation,
    ("django.apps.registry", "Apps.register_model"): lambda f: f"Apps.register_model({f.f_locals['model']._meta.label})",
    ("django.apps.registry", "Apps.do_pending_operations"): pending_run,
    ("django.db.models.fields.related", "RelatedField.contribute_to_class.<locals>.resolve_related_class"): resolved,
    ("django.apps.registry", "Apps.clear_cache"): plain,
    ("django.apps.config", "AppConfig.ready"): of_app,
    ("library.", "*.ready"): of_app,
}

OVERRIDE = {
    ("django.test.utils", "override_settings.enable"): plain,
    ("django.test.utils", "override_settings.disable"): plain,
    ("django.conf", "UserSettingsHolder.__init__"): lambda f: f"UserSettingsHolder.__init__(a {type(f.f_locals['default_settings']).__name__})",
    ("django.conf", "UserSettingsHolder.__setattr__"): attribute_set,
    ("django.conf", "LazySettings.__setattr__"): attribute_set,
    ("django.conf", "LazySettings.__getattr__"): named,
    ("django.dispatch.dispatcher", "Signal.send"): changed,
    ("django.dispatch.dispatcher", "Signal.send_robust"): changed,
    ("django.apps.registry", "Apps.set_installed_apps"): plain,
    ("django.apps.registry", "Apps.unset_installed_apps"): plain,
    ("django.apps.registry", "Apps.populate"): plain,
    ("django.apps.config", "AppConfig.create"): lambda f: f'AppConfig.create("{f.f_locals["entry"]}")',
    ("django.apps.config", "AppConfig.import_models"): of_app,
    ("library.", "<module>"): imported,
    ("django.apps.registry", "Apps.register_model"): lambda f: f"Apps.register_model({f.f_locals['model']._meta.label})",
    ("django.apps.config", "AppConfig.ready"): of_app,
    ("library.", "*.ready"): of_app,
}

RULES = {}  # the set in force


def find(module: str, qualname: str):
    """The label function for a call of this function, or None."""
    name = qualname.rsplit(".", 1)[-1]
    for (want_module, want), label in RULES.items():
        if module == want_module or (want_module.endswith(".") and module.startswith(want_module)):
            if want == qualname or (want.startswith("*.") and want[2:] == name and "." in qualname):
                return label
    return None


def profile(frame, event, arg):
    if event == "call":
        label = find(frame.f_globals.get("__name__", ""), frame.f_code.co_qualname)
        if label is None:
            return
        probe = sys.modules.get("library.probe")
        if getattr(probe, "ASKING", False):
            return  # the probe's own questions are not part of what is recorded
        text = label(frame)
        if text is None:
            return
        note(text)
        STACK.append(frame)
    elif event == "return":
        if STACK and STACK[-1] is frame:
            STACK.pop()


def watched(action, rules=None):
    """Run the action with the watch list in force, and return what it returned."""
    global RULES
    RULES = rules if rules is not None else RULES
    sys.setprofile(profile)
    try:
        return action()
    finally:
        sys.setprofile(None)
        STACK.clear()


def did(what: str, action, rules) -> None:
    """One thing the script did, as a line, with the watched calls it set off under it."""
    global BASE
    note(what)
    BASE = 1
    try:
        answer = raised(lambda: watched(action, rules))
    finally:
        BASE = 0
    if answer != "None":
        note(f"  -> {answer}")


# ---------------------------------------------------------------------------------------------
# The parts. Each runs in an interpreter of its own.

def part_unconfigured() -> None:
    """Nothing names a settings module."""
    from django.conf import settings

    note(f"settings.configured  -> {settings.configured}")
    note(f"settings.DEBUG  -> {raised(lambda: settings.DEBUG)}")
    note(f"settings.configured  -> {settings.configured}")

    def import_models():
        import library.catalogue.models  # noqa: F401

    note(f"import library.catalogue.models  -> {raised(import_models)}")
    show("No settings: DJANGO_SETTINGS_MODULE is not set, and settings.configure has not been called")


def part_model_first() -> None:
    """The settings are named, and a models module is imported before django.setup()."""
    os.environ["DJANGO_SETTINGS_MODULE"] = "library.settings"

    def import_models():
        import library.catalogue.models  # noqa: F401

    note(f"import library.catalogue.models  -> {raised(import_models)}")
    show("A models module is imported before django.setup()")


def part_settings() -> None:
    os.environ["DJANGO_SETTINGS_MODULE"] = "library.settings"
    import django.urls  # noqa: F401  imported here so that its import is not recorded where STATIC_URL first needs it
    from django.conf import settings

    note(f"repr(settings)  -> {settings!r}")
    did("settings.DEBUG, the first read of any setting", lambda: settings.DEBUG, SETTINGS)
    note(f"repr(settings)  -> {settings!r}")
    did("settings.DEBUG, again", lambda: settings.DEBUG, SETTINGS)
    did("settings.USE_TZ, a setting not read before", lambda: settings.USE_TZ, SETTINGS)
    did("settings.STATIC_URL = 'static/'", lambda: setattr(settings, "STATIC_URL", "static/"), SETTINGS)
    did("settings.STATIC_URL", lambda: settings.STATIC_URL, SETTINGS)
    did("settings.NO_SUCH_SETTING", lambda: settings.NO_SUCH_SETTING, SETTINGS)
    did("settings.is_overridden('INSTALLED_APPS')", lambda: settings.is_overridden("INSTALLED_APPS"), {})
    did("settings.is_overridden('USE_TZ')", lambda: settings.is_overridden("USE_TZ"), {})
    show("A settings module: reads, and one assignment")


def part_configure() -> None:
    import django
    from django.conf import settings

    did("settings.configure(DEBUG=True)", lambda: settings.configure(DEBUG=True), SETTINGS)
    note(f"repr(settings)  -> {settings!r}")
    did("settings.DEBUG", lambda: settings.DEBUG, SETTINGS)
    did("settings.USE_TZ", lambda: settings.USE_TZ, SETTINGS)
    did("settings.is_overridden('DEBUG')", lambda: settings.is_overridden("DEBUG"), {})
    did("settings.is_overridden('USE_TZ')", lambda: settings.is_overridden("USE_TZ"), {})
    did("settings.configure(DEBUG=False), a second time", lambda: settings.configure(DEBUG=False), SETTINGS)
    did("django.setup()", django.setup, {("django.apps.registry", "Apps.populate"): lambda f: f"Apps.populate({f.f_locals['installed_apps']})"})
    show("No settings module: settings.configure")


def part_setup() -> None:
    os.environ["DJANGO_SETTINGS_MODULE"] = "library.settings"
    import django
    from django.apps import apps

    watched(django.setup, SETUP)
    show("django.setup() in a new process")

    from library import probe

    for moment, flags, answers in probe.ANSWERS:
        note(moment)
        note(f"  {flags}")
        width = max(len(question) for question, answer in answers)
        for question, answer in answers:
            note(f"  {question.ljust(width)}   {answer}")
    show("What the registry answers during each phase")

    for entry, config in zip(django.conf.settings.INSTALLED_APPS, apps.get_app_configs()):
        note(f'"{entry}"')
        note(f"  class {type(config).__name__}, name {config.name!r}, label {config.label!r}, verbose_name {config.verbose_name!r}")
        module = config.models_module.__name__ if config.models_module else None
        note(f"  models_module {module}, models {list(config.models)}")
    show("The applications after django.setup()")

    watched(django.setup, SETUP)
    show("django.setup() a second time in the same process")


def part_failed() -> None:
    """An entry of INSTALLED_APPS cannot be imported, and django.setup() is called again."""
    import django
    from django.apps import apps
    from django.conf import settings

    settings.configure(INSTALLED_APPS=["library.loans", "library.no_such_app"])
    note(f"django.setup()  -> {raised(django.setup)}")
    note(f"apps.loading {apps.loading}, apps_ready {apps.apps_ready}, ready {apps.ready}")
    note(f"django.setup(), again  -> {raised(django.setup)}")
    show('django.setup() with an entry that cannot be imported: INSTALLED_APPS = ["library.loans", "library.no_such_app"]')


def part_override() -> None:
    os.environ["DJANGO_SETTINGS_MODULE"] = "library.settings"
    import django

    django.setup()
    from django.conf import settings
    from django.core.signals import setting_changed

    def receivers() -> list:
        sync, asynchronous = setting_changed._live_receivers(None)
        return [*sync, *asynchronous]

    before = receivers()
    from django.test.utils import override_settings

    def block(**options):
        def run():
            with override_settings(**options):
                note("the block runs: " + ", ".join(f"settings.{name} is {getattr(settings, name)!r}" for name in options))
        return run

    note(f"settings.DEBUG  -> {settings.DEBUG!r}")
    did("with override_settings(DEBUG=True):", block(DEBUG=True), OVERRIDE)
    note(f"settings.DEBUG  -> {settings.DEBUG!r}")
    show("A setting is overridden for a block, and restored")

    did('with override_settings(INSTALLED_APPS=["library.loans", "library.catalogue"]):', block(INSTALLED_APPS=["library.loans", "library.catalogue"]), OVERRIDE)
    show("INSTALLED_APPS is overridden for a block")

    note(f"connected when django.setup() returned: {len(before)}")
    for receiver in before:
        note(f"  {receiver.__name__}  ({receiver.__module__})")
    note("connected by importing django.test:")
    for receiver in receivers()[len(before):]:
        note(f"  {receiver.__name__}  ({receiver.__module__})")
    show("The receivers of setting_changed in this process, in the order they were connected")


def part_logging() -> None:
    os.environ["DJANGO_SETTINGS_MODULE"] = "library.settings"
    import django

    django.setup()
    from django.conf import settings

    reached = []
    handlers = [logging.lastResort]
    for name in ("django", "django.server"):
        logger = logging.getLogger(name)
        handlers += logger.handlers
        names = ", ".join(handler.name for handler in logger.handlers)
        note(f'"{name}": level {logging.getLevelName(logger.level)}, handlers {names}, propagate {logger.propagate}')
    for handler in handlers:
        name = handler.name or "Python's handler of last resort"
        handler.emit = lambda record, name=name: reached.append(name)
    show("The loggers that configure_logging leaves configured, with LOGGING empty")

    records = [
        ("django.request", logging.ERROR), ("django.request", logging.WARNING), ("django.security.DisallowedHost", logging.ERROR),
        ("django.db.backends", logging.DEBUG), ("django", logging.INFO), ("django.server", logging.INFO), ("library", logging.WARNING),
    ]
    for debug in (False, True):
        settings.DEBUG = debug
        note(f"with settings.DEBUG {debug}")
        for name, level in records:
            reached.clear()
            logging.getLogger(name).log(level, "a record")
            said = f'"{name}" {logging.getLevelName(level)}'
            note(f"  {said.ljust(40)}-> {', '.join(reached) or 'no handler'}")
    show("Where a log record goes: the handlers whose emit is called")


PARTS = {
    "unconfigured": part_unconfigured, "model-first": part_model_first, "settings": part_settings,
    "configure": part_configure, "setup": part_setup, "failed": part_failed, "override": part_override,
    "logging": part_logging,
}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        PARTS[sys.argv[1]]()
    else:
        import django

        print("Django", django.get_version(), "and the project library: three applications, one model each\n")
        sys.stdout.flush()
        for part in PARTS:
            done = subprocess.run([sys.executable, __file__, part], capture_output=True, encoding="utf-8")
            if done.returncode:
                sys.exit(done.stderr)
            sys.stdout.write(done.stdout)
