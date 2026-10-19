"""A recording of a process becoming a configured Django: the settings loaded on their first
read, the app registry populated in its three phases, and what each of the two objects answers
before, during and after.

    python recordings/startup.py > recordings/startup.txt

The chapter of the book (pages/startup.md and the pages under it) is written against this
output. It needs only the pinned Django (the project's virtual environment has it) and the
small project beside it, `library/`, whose settings module installs three applications,
entered in INSTALLED_APPS in the three forms an entry can take, one of them with a model that
names two others by string; the parts of the second pass install eight more of its
applications, each by name (below). Run it again after a re-pin: where the output changes,
the chapter has to.

Startup happens once in a process, so each part of the recording is made in an interpreter of
its own: run with no argument, this script runs itself once for each part and prints what
they print. What is written down is a selection: the calls the chapter names, nested as they
were made, with the arguments that tell them apart. Everything between them ran and is left
out.

The second pass (2026-10-19) added parts, each again in an interpreter of its own, and put
each after the part of the first pass nearest its subject; no block of the first pass changed.
Most of them name their own INSTALLED_APPS with settings.configure, from eight more
applications of `library/`, each with one job:

    archive        its package imports its own models module
    reading_room   its apps module imports its own models module
    shelving       its package imports catalogue's models module
    reservations   its models module fetches catalogue.Book with get_model(require_ready=False)
    wishlist       its model names two models by string that never resolve: one misspelt
                   (catalogue.Bok), one of an application not installed (periodicals.Issue)
    reopening      its ready calls django.setup()
    notices        its ready connects three receivers to its own signal, book_returned: a
                   function of a module, a method of the AppConfig, a function defined in ready
    misprint       its models module raises AttributeError (a field class misspelt)

What the second pass's lines add to the first's:
- `raises X: message`, in the parts that turn it on: an exception left the watched call above
  it. It is said under the innermost watched call it leaves and not again as it leaves the
  calls around that one; it is said again only where a frame other than the caller of the
  call it last left raises it again. A caller that catches it and raises it again, as
  check_errors' wrapper does in the runserver part, gets no line: that part's lines on
  django.utils.autoreload show what the wrapper kept of it. The profile hook is told such a
  call returned, and sys.monitoring's PY_UNWIND tells the two apart; the script proves that
  on its Python before it records.
- A label after two spaces gives what the call finds as it begins, read from the objects it
  was given: `Apps.check_apps_ready  apps_ready False, ...` the registry's three flags;
  `Apps.populate  (ready False, loading True)` the two flags populate tests, in its order;
  `Apps.get_model(...)  apps_ready True, models_ready False`; `log_response(...)  the 500
  response is already marked` the attribute log_response tests first;
  `UserSettingsHolder.__getattr__("X")  on the holder of DEBUG` the upper-case names set on
  that holder, and any it holds as deleted.
- `-> a WSGIHandler` and the like: what was returned, put into words.
- `settings._wrapped, and below it each default_settings in turn`: the stack of settings
  objects, walked from the proxy down, as it is at that line.
- In the blocks of a server's entry point, only the reads of LOGGING_CONFIG, LOGGING,
  FORCE_SCRIPT_NAME, INSTALLED_APPS and MIDDLEWARE are written down.
- The system check's message is printed a line to a line, its blank lines left out.

What the second pass replaces or arranges:
- runserver is not run: before ManagementUtility.execute is called, the script replaces
  run_from_argv on runserver's Command by a function that writes one line and returns.
- In the logging parts, as in the first pass, emit is replaced on every handler that any
  logger holds (a disabled logger's too) and on Python's handler of last resort, by one that
  writes down the handler's name. The project's handler is named "project".
- In the logging parts a record is logged on the logger logging.getLogger returns, and
  getLogger makes a logger that does not yet exist: the line of such a logger says it was
  made there. In the block of where a record goes with LOGGING that leaves out
  "disable_existing_loggers", "django.security.DisallowedHost" is first made so, after
  django.setup(), as response_for_exception first makes it when it handles such an
  exception.
- The receivers of book_returned are weak, as Signal.connect makes them by default. Each
  listing of them is made after gc.collect(), so that a receiver reads as dead when nothing
  else holds its object, whenever the collector would have run; the script holds the
  NoticesConfig objects it names only weakly, and that part does not turn on the `raises`
  lines, whose bookkeeping holds the frame of the last call that returned. A listing reads
  Signal.receivers as it stands, and the count under it is of the entries alive in it: the
  script does not call Signal._live_receivers, which removes the dead entries, as connect,
  disconnect and a send do.
- log_response's requests go through a WSGIHandler, called with a made environ as a server
  would call it, to a URLconf that is a tuple of the part's own (ROOT_URLCONF may be a
  sequence of patterns), with DEBUG false.
"""
import logging
import os
import subprocess
import sys

sys.stdout.reconfigure(newline="\n")  # the same bytes on every machine
HERE = os.path.dirname(os.path.abspath(__file__))
# `library` imports from this directory, as it would from a project's. The directory goes last
# on the path and not first, where Python puts a script's own: `http.py` in it has the name of
# a package of the standard library, which Django imports.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != HERE] + [HERE]

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
        return f"raises {said(exc)}"


def said(exc: BaseException) -> str:
    """An exception put into words: its class, and its message if it has one."""
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


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
            if CATCHING:
                POPPED[:] = [(frame, len(STACK))]
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
        POPPED.clear()


# A watched call that an exception leaves is followed, in the parts that turn this on, by a
# line `raises X: message` under the innermost watched call the exception leaves, and not
# again as it leaves the calls around that one; it is said again only where a frame that is
# not the caller of the frame it last left raises it again. A caller that catches it and
# raises it again gets no line. The profile hook is told that such a call returned;
# sys.monitoring's PY_UNWIND, which comes just after, tells the two apart.
CATCHING = False
POPPED = []  # the watched frame the profile hook has just seen return, and its depth
LEAVING = {}  # id of an exception -> (the exception, the frame it leaves next if it goes on, said yet)


def unwinding(code, offset, exception):
    frame = sys._getframe(1)
    known = LEAVING.get(id(exception))
    told = known is not None and known[0] is exception and known[1] is frame and known[2]
    if POPPED and POPPED[0][0] is frame:
        depth = POPPED.pop()[1]
        if not told and not isinstance(exception, (StopIteration, GeneratorExit)):
            LINES.append("  " * (BASE + depth) + f"raises {said(exception)}")
            told = True
    LEAVING[id(exception)] = (exception, frame.f_back, told)


def _raises():
    raise KeyError("a test")


def catching() -> None:
    """Turn on the `raises` lines, and prove on this Python that a call which raises is told
    apart from one that returns before anything is recorded."""
    global CATCHING
    CATCHING = True
    tool = sys.monitoring.PROFILER_ID
    sys.monitoring.use_tool_id(tool, "recordings/startup.py")
    sys.monitoring.register_callback(tool, sys.monitoring.events.PY_UNWIND, unwinding)
    sys.monitoring.set_events(tool, sys.monitoring.events.PY_UNWIND)
    try:
        watched(_raises, {("__main__", "_raises"): plain})
    except KeyError:
        pass
    if LINES != ["_raises", "  raises KeyError: 'a test'"]:
        sys.exit(f"recordings/startup.py: this Python reports an exception leaving a function otherwise than expected: {LINES!r}")
    LINES.clear()


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


# ---------------------------------------------------------------------------------------------
# The parts added in the second pass. Each runs in an interpreter of its own, as the first
# pass's do, and most configure their own INSTALLED_APPS with settings.configure.

class Said(str):
    """An answer already put into words, written as it is and not as a string's repr."""

    __repr__ = str.__str__


def flags(registry) -> str:
    return f"apps_ready {registry.apps_ready}, models_ready {registry.models_ready}, ready {registry.ready}"


def entry_made(frame) -> str:
    return f'AppConfig.create("{frame.f_locals["entry"]}")'


def import_named(frame):
    path = frame.f_locals["dotted_path"]
    return f'import_string("{path}")' if path.startswith("library") else None  # not the logging's own


PHASE_ONE = {
    ("django.apps.registry", "Apps.populate"): plain,
    ("django.apps.config", "AppConfig.create"): entry_made,
    ("django.apps.config", "AppConfig.__init__"): config_made,
    ("django.utils.module_loading", "import_string"): import_named,
    ("library.", "<module>"): imported,
    ("django.db.models.base", "ModelBase.__new__"): model_class,
    ("django.apps.registry", "Apps.get_containing_app_config"): lambda f: f'Apps.get_containing_app_config("{f.f_locals["object_name"]}")',
    ("django.apps.registry", "Apps.check_apps_ready"): lambda f: f"Apps.check_apps_ready  {flags(f.f_locals['self'])}",
}


def phase_one(entries: list, title: str):
    """A part: django.setup() with these entries, one of which imports a models module as its
    configuration is made."""
    def part() -> None:
        import django
        from django.conf import settings

        catching()
        settings.configure(INSTALLED_APPS=entries)
        did("django.setup()", django.setup, PHASE_ONE)
        show(title)
    return part


def populate_tested(frame) -> str:
    registry = frame.f_locals["self"]
    return f"Apps.populate  (ready {registry.ready}, loading {registry.loading})"  # the two it tests, in its order


REENTRY = {
    ("django", "setup"): plain,
    ("django.utils.log", "configure_logging"): lambda f: f'configure_logging("{f.f_locals["logging_config"]}", {f.f_locals["logging_settings"]})',
    ("django.urls.base", "set_script_prefix"): lambda f: f'set_script_prefix("{f.f_locals["prefix"]}")',
    ("django.apps.registry", "Apps.populate"): populate_tested,
    ("django.apps.config", "AppConfig.create"): entry_made,
    ("django.apps.config", "AppConfig.import_models"): of_app,
    ("library.", "*.ready"): of_app,
}


def part_setup_in_ready() -> None:
    import django
    from django.apps import apps
    from django.conf import settings

    catching()
    settings.configure(INSTALLED_APPS=["library.reopening"])
    did("django.setup()", django.setup, REENTRY)
    note(f"apps.loading {apps.loading}, {flags(apps)}")
    show('django.setup() with INSTALLED_APPS = ["library.reopening"], whose ready calls django.setup(): '
         "the second call configures logging and sets the prefix again, and its Apps.populate raises")


def model_asked(frame) -> str:
    local = frame.f_locals
    registry = local["self"]
    return (f'Apps.get_model("{local["app_label"]}", "{local["model_name"]}", require_ready={local["require_ready"]})  '
            f"apps_ready {registry.apps_ready}, models_ready {registry.models_ready}")


REQUIRE_READY = {
    ("django.apps.registry", "Apps.populate"): plain,
    ("django.apps.config", "AppConfig.create"): entry_made,
    ("django.apps.config", "AppConfig.import_models"): of_app,
    ("library.", "<module>"): imported,
    ("django.apps.registry", "Apps.get_model"): model_asked,
    ("django.apps.config", "AppConfig.get_model"): lambda f: f'AppConfig.get_model("{f.f_locals["model_name"]}", require_ready={f.f_locals["require_ready"]})  ({f.f_locals["self"].label})',
    ("django.db.models.base", "ModelBase.__new__"): model_class,
    ("django.apps.registry", "Apps.register_model"): lambda f: f"Apps.register_model({f.f_locals['model']._meta.label})",
    ("django.apps.config", "AppConfig.ready"): of_app,
}


def part_require_ready() -> None:
    import django
    from django.conf import settings

    settings.configure(INSTALLED_APPS=["library.reservations", "library.catalogue"])
    did("django.setup()", django.setup, REQUIRE_READY)
    show('django.setup() with INSTALLED_APPS = ["library.reservations", "library.catalogue"]: '
         "a models module asks for a later application's model with require_ready=False")


def part_unresolved() -> None:
    import django
    from django.apps import apps
    from django.conf import settings
    from django.core.management import call_command
    from django.core.management.base import SystemCheckError

    settings.configure(INSTALLED_APPS=["library.catalogue", "library.wishlist"])
    note(f"django.setup()  -> {raised(django.setup)}")
    note("apps._pending_operations")
    for key, functions in apps._pending_operations.items():
        for function in functions:
            name, field = waiting_function(function)
            note(f"  {keys_text([key])}: {name} for the field {field}")
    show('django.setup() with INSTALLED_APPS = ["library.catalogue", "library.wishlist"]: '
         "two references by string that never resolve wait in Apps._pending_operations, and nothing is raised")

    try:
        call_command("check")
    except SystemCheckError as exc:
        note("call_command(\"check\")  -> raises SystemCheckError, whose message is:")
        for line in str(exc).splitlines():
            if line.strip():
                note("  " + line)
    else:
        note('call_command("check")  -> None')
    show("The system check, run as manage.py check runs it, on what never resolved")


CONFIGS = []  # weak references to each NoticesConfig a receiver was bound to, in the order met
RECEIVERS = {}  # the key a receiver of book_returned was connected with -> the receiver in words


def receiver_text(receiver) -> str:
    if not hasattr(receiver, "__func__"):
        return receiver.__qualname__
    import weakref

    owner = receiver.__self__
    number = next((n for n, ref in enumerate(CONFIGS) if ref() is owner), None)
    if number is None:
        CONFIGS.append(weakref.ref(owner))  # weakly: the recorder must not keep the object alive
        number = len(CONFIGS) - 1
    return f"{receiver.__func__.__qualname__}, bound to the {('first', 'second', 'third')[number]} {type(owner).__name__}"


def connected(frame):
    from django.dispatch.dispatcher import _make_id

    signals = sys.modules.get("library.notices.signals")
    if signals is None or frame.f_locals["self"] is not signals.book_returned:
        return None
    receiver = frame.f_locals["receiver"]
    text = receiver_text(receiver)
    RECEIVERS[(_make_id(receiver), _make_id(frame.f_locals["sender"]))] = text
    return f"Signal.connect({text})"


CONNECTS = {
    ("django.apps.registry", "Apps.populate"): plain,
    ("django.test.utils", "override_settings.enable"): plain,
    ("django.test.utils", "override_settings.disable"): plain,
    ("django.apps.registry", "Apps.set_installed_apps"): plain,
    ("django.apps.registry", "Apps.unset_installed_apps"): plain,
    ("library.", "*.ready"): of_app,
    ("django.dispatch.dispatcher", "Signal.connect"): connected,
}


def kept(signal) -> None:
    """What the signal keeps, after a collection, and how many of its receivers a send would
    call: those alive in that list, counted from it. Signal._live_receivers is not called,
    since it removes the dead entries, as a send does."""
    import gc
    import weakref

    gc.collect()
    note("book_returned.receivers, after gc.collect()")
    entries = [(RECEIVERS[key], isinstance(ref, weakref.ReferenceType) and ref() is None) for key, ref, sender, is_async in signal.receivers]
    width = max(len(text) for text, dead in entries)
    for text, dead in entries:
        note(f"  {text.ljust(width)}   {'dead: its weak reference returns None' if dead else 'alive'}")
    note(f"the receivers a send would call: {sum(not dead for text, dead in entries)}")


def part_receivers_twice() -> None:
    import django
    from django.conf import settings

    settings.configure(INSTALLED_APPS=["library.notices"])
    did("django.setup()", django.setup, CONNECTS)
    from library.notices.signals import book_returned

    kept(book_returned)
    show('django.setup() with INSTALLED_APPS = ["library.notices"], whose ready connects three receivers to its signal book_returned')

    from django.test.utils import override_settings

    def block():
        with override_settings(INSTALLED_APPS=["library.notices"]):
            kept(book_returned)

    did('with override_settings(INSTALLED_APPS=["library.notices"]):', block, CONNECTS)
    kept(book_returned)
    show("The same ready run again by override_settings(INSTALLED_APPS=[...]), and what book_returned keeps inside the block and after it")


def refusal(frame) -> str:
    return f'refuse(setting="{frame.f_locals["setting"]}", enter={frame.f_locals["enter"]})'


def part_raising_receiver() -> None:
    os.environ["DJANGO_SETTINGS_MODULE"] = "library.settings"
    import django

    django.setup()
    from django.conf import settings
    from django.core.signals import setting_changed
    from django.test.utils import override_settings

    def refuse(*, setting, enter, **kwargs):
        if setting == "APPEND_SLASH" and enter:
            raise ValueError("APPEND_SLASH may not be overridden")

    setting_changed.connect(refuse)
    catching()

    def block():
        with override_settings(APPEND_SLASH=False, PREPEND_WWW=True):
            note("the block runs")

    rules = {**OVERRIDE, ("__main__", "part_raising_receiver.<locals>.refuse"): refusal}
    did("with override_settings(APPEND_SLASH=False, PREPEND_WWW=True):", block, rules)
    note(f"settings.APPEND_SLASH  -> {settings.APPEND_SLASH!r}")
    note(f"settings.PREPEND_WWW  -> {settings.PREPEND_WWW!r}")
    show("A receiver of setting_changed, refuse, raises as the first of two overridden settings is entered")


def holder_text(holder) -> str:
    names = sorted(name for name in vars(holder) if name.isupper())
    deleted = sorted(holder._deleted)
    return "the holder of " + ", ".join(names) + (f", deleted {', '.join(deleted)}" if deleted else "")


NESTED = {
    ("django.test.utils", "override_settings.enable"): plain,
    ("django.test.utils", "override_settings.disable"): plain,
    ("django.conf", "UserSettingsHolder.__init__"): lambda f: f"UserSettingsHolder.__init__(a {type(f.f_locals['default_settings']).__name__})",
    ("django.conf", "UserSettingsHolder.__setattr__"): attribute_set,
    ("django.conf", "LazySettings.__setattr__"): attribute_set,
    ("django.conf", "LazySettings.__getattr__"): named,
    ("django.conf", "LazySettings.__delattr__"): named,
    ("django.conf", "UserSettingsHolder.__getattr__"): lambda f: f'UserSettingsHolder.__getattr__("{f.f_locals["name"]}")  on {holder_text(f.f_locals["self"])}',
    ("django.conf", "UserSettingsHolder.__delattr__"): lambda f: f'UserSettingsHolder.__delattr__("{f.f_locals["name"]}")  on {holder_text(f.f_locals["self"])}',
    ("django.dispatch.dispatcher", "Signal.send"): changed,
    ("django.dispatch.dispatcher", "Signal.send_robust"): changed,
}


def layers() -> None:
    from django.conf import settings

    note("settings._wrapped, and below it each default_settings in turn")
    layer = settings._wrapped
    while type(layer).__name__ == "UserSettingsHolder":
        note(f"  a UserSettingsHolder, {holder_text(layer)}")
        layer = layer.default_settings
    note(f'  a {type(layer).__name__}, "{layer.SETTINGS_MODULE}"')


def part_nested() -> None:
    os.environ["DJANGO_SETTINGS_MODULE"] = "library.settings"
    import django

    django.setup()
    from django.conf import settings
    from django.test.utils import override_settings

    catching()
    outer, inner = override_settings(DEBUG=True), override_settings(APPEND_SLASH=False)
    note("outer, inner = override_settings(DEBUG=True), override_settings(APPEND_SLASH=False)")
    did("outer.__enter__()", outer.__enter__, NESTED)
    did("inner.__enter__()", inner.__enter__, NESTED)
    layers()
    show("Two overrides, one inside the other, each entered as a with statement enters it: the holders stacked")

    did("settings.APPEND_SLASH", lambda: settings.APPEND_SLASH, NESTED)
    did("settings.DEBUG", lambda: settings.DEBUG, NESTED)
    did("settings.TIME_ZONE", lambda: settings.TIME_ZONE, NESTED)
    show("Inside both overrides: a read falls through the holders until one has the name")

    did("del settings.TIME_ZONE", lambda: delattr(settings, "TIME_ZONE"), NESTED)
    did("settings.TIME_ZONE", lambda: settings.TIME_ZONE, NESTED)
    layers()
    show("Inside both overrides: a setting deleted, and read")

    did("inner.__exit__(None, None, None)", lambda: inner.__exit__(None, None, None), NESTED)
    layers()
    did("outer.__exit__(None, None, None)", lambda: outer.__exit__(None, None, None), NESTED)
    layers()
    show("The two overrides left, the inner first: what the proxy wraps after each")


PREFIX = {
    ("django.utils.functional", "LazyObject.__getattribute__"): attribute_read,
    ("django.conf", "LazySettings.__getattr__"): named,
    ("django.conf", "LazySettings._add_script_prefix"): lambda f: f"LazySettings._add_script_prefix({f.f_locals['value']!r})",
    ("django.urls.base", "get_script_prefix"): plain,
}


def part_script_prefix() -> None:
    from django.conf import settings
    from django.urls import get_script_prefix, set_script_prefix

    settings.configure(STATIC_URL="static/")
    did('set_script_prefix("/first/")', lambda: set_script_prefix("/first/"), PREFIX)
    did("settings.STATIC_URL", lambda: settings.STATIC_URL, PREFIX)
    did('set_script_prefix("/second/")', lambda: set_script_prefix("/second/"), PREFIX)
    note(f"get_script_prefix()  -> {get_script_prefix()!r}")
    did("settings.STATIC_URL", lambda: settings.STATIC_URL, PREFIX)
    show('settings.configure(STATIC_URL="static/"): a relative STATIC_URL read under two script prefixes keeps the first')


def setting_named(frame):
    name = frame.f_locals["name"]
    return f'LazySettings.__getattr__("{name}")' if name in {"LOGGING_CONFIG", "LOGGING", "FORCE_SCRIPT_NAME", "INSTALLED_APPS", "MIDDLEWARE"} else None


SERVER = {
    ("django", "setup"): lambda f: f"setup(set_prefix={f.f_locals['set_prefix']})",
    ("django.conf", "LazySettings.__getattr__"): setting_named,
    ("django.conf", "LazySettings._setup"): named,
    ("django.conf", "Settings.__init__"): lambda f: f'Settings.__init__("{f.f_locals["settings_module"]}")',
    ("library.settings", "<module>"): imported,
    ("django.utils.log", "configure_logging"): lambda f: f'configure_logging("{f.f_locals["logging_config"]}", {f.f_locals["logging_settings"]})',
    ("django.urls.base", "set_script_prefix"): lambda f: f'set_script_prefix("{f.f_locals["prefix"]}")',
    ("django.apps.registry", "Apps.populate"): plain,
    ("django.core.handlers.wsgi", "WSGIHandler.__init__"): plain,
    ("django.core.handlers.asgi", "ASGIHandler.__init__"): plain,
    ("django.core.handlers.base", "BaseHandler.load_middleware"): lambda f: f"BaseHandler.load_middleware(is_async={f.f_locals['is_async']})",
}


def server_start(kind: str):
    """A part: a server's entry point called in a new process, as the project's wsgi.py or
    asgi.py calls it when the server imports it."""
    def part() -> None:
        os.environ["DJANGO_SETTINGS_MODULE"] = "library.settings"
        import importlib

        get_application = getattr(importlib.import_module(f"django.core.{kind}"), f"get_{kind}_application")
        article = "an" if kind == "asgi" else "a"
        did(f"get_{kind}_application()", lambda: Said(f"{article} {type(get_application()).__name__}"), SERVER)
        show(f"get_{kind}_application() in a new process: django.setup(set_prefix=False), then the handler")
    return part


RUNSERVER = {
    ("django.utils.autoreload", "check_errors.<locals>.wrapper"): plain,
    ("django", "setup"): plain,
    ("django.apps.registry", "Apps.populate"): plain,
    ("django.apps.config", "AppConfig.create"): entry_made,
    ("django.apps.config", "AppConfig.import_models"): of_app,
    ("library.", "<module>"): imported,
    ("django.db.models.base", "ModelBase.__new__"): model_class,
    ("django.apps.registry", "Apps.register_model"): lambda f: f"Apps.register_model({f.f_locals['model']._meta.label})",
    ("django.core.management", "ManagementUtility.fetch_command"): lambda f: f'ManagementUtility.fetch_command("{f.f_locals["subcommand"]}")',
}


def part_runserver_broken() -> None:
    from django.apps import apps
    from django.conf import settings
    from django.core.management import ManagementUtility
    from django.core.management.commands import runserver

    catching()
    settings.configure(INSTALLED_APPS=["library.catalogue", "library.misprint"])

    def not_run(self, argv):
        note(f"runserver's Command.run_from_argv({argv!r}), replaced: it writes this line and returns")

    runserver.Command.run_from_argv = not_run
    argv = ["manage.py", "runserver", "--nostatic"]
    did(f"ManagementUtility({argv!r}).execute()", ManagementUtility(argv).execute, RUNSERVER)
    from django.utils import autoreload

    note(f"autoreload._exception[1]  -> {autoreload._exception[1]!r}")
    files = [os.path.relpath(path, HERE).replace(os.sep, "/") for path in autoreload._error_files]
    note(f"autoreload._error_files  -> {files!r}, each path relative to recordings/")
    show('ManagementUtility.execute() for runserver, INSTALLED_APPS = ["library.catalogue", "library.misprint"] and '
         "misprint's models module raising: the error is swallowed, and the command, replaced by the script, is not run")

    note(f"apps.app_configs  -> {apps.app_configs!r}")
    note(f"dict(apps.all_models)  -> {dict(apps.all_models)!r}")
    note(flags(apps))
    note(f"apps.loading  -> {apps.loading!r}")
    note(f"apps.ready_event.is_set()  -> {apps.ready_event.is_set()!r}")
    show("The registry as ManagementUtility.execute() leaves it when django.setup() has failed under runserver")


# Two LOGGING settings a project might write. Neither handler writes anywhere: every handler's
# emit is replaced before a record is logged.
LOG_TO_ROOT = {"version": 1, "handlers": {"project": {"class": "logging.StreamHandler"}}, "root": {"handlers": ["project"], "level": "INFO"}}
LOG_DJANGO = {"version": 1, "disable_existing_loggers": False, "handlers": {"project": {"class": "logging.StreamHandler"}},
              "loggers": {"django": {"handlers": ["project"], "level": "INFO"}}}


def emits_written(reached: list) -> None:
    """Replace emit, on every handler any logger holds and on Python's handler of last resort,
    by one that writes down the handler's name."""
    handlers = [logging.lastResort]
    for logger in [logging.root, *logging.root.manager.loggerDict.values()]:
        for handler in getattr(logger, "handlers", []):  # a PlaceHolder has none
            if handler not in handlers:
                handlers.append(handler)
    for handler in handlers:
        name = handler.name or "Python's handler of last resort"
        handler.emit = lambda record, name=name: reached.append(name)


def where(reached: list, name: str, level: int) -> str:
    """A record logged on the logger of this name, and the handlers whose emit it reached. A
    logger that getLogger makes here, because none had the name, is said to be made here."""
    made = not isinstance(logging.root.manager.loggerDict.get(name), logging.Logger)
    reached.clear()
    logging.getLogger(name).log(level, "a record")
    said = f'"{name}" {logging.getLevelName(level)}'
    line = f"{said.ljust(40)}-> {', '.join(reached) or 'no handler'}"
    return line + ("  (the logger is made at this line, by logging.getLogger)" if made else "")


def part_logging_root() -> None:
    import django
    from django.conf import settings

    logging.getLogger("library.early")
    note('logging.getLogger("library.early"), before django.setup()')
    settings.configure(LOGGING=LOG_TO_ROOT)
    note(f"settings.configure(LOGGING={LOG_TO_ROOT!r})")
    note("django.setup()")
    django.setup()
    logging.getLogger("library.late")
    note('logging.getLogger("library.late"), after it')
    note("every logger whose name begins with django or library, as it is now")
    loggers = logging.root.manager.loggerDict
    for name in sorted(loggers):
        if name.startswith(("django", "library")) and isinstance(loggers[name], logging.Logger):
            note(f'  "{name}": disabled {loggers[name].disabled}')
    show('LOGGING without "disable_existing_loggers": the loggers that existed when django.setup() applied it are disabled')

    reached = []
    emits_written(reached)
    for name, level in [("django.request", logging.ERROR), ("django.server", logging.INFO), ("django.security.DisallowedHost", logging.ERROR),
                        ("library.early", logging.WARNING), ("library.late", logging.WARNING)]:
        note(where(reached, name, level))
    show('Where a log record goes, with LOGGING that leaves out "disable_existing_loggers": the handlers whose emit is called')


def part_logging_django() -> None:
    import django
    from django.conf import settings

    settings.configure(LOGGING=LOG_DJANGO)
    note(f"settings.configure(LOGGING={LOG_DJANGO!r})")
    note("django.setup()")
    django.setup()
    for name in ("django", "django.server"):
        logger = logging.getLogger(name)
        names = ", ".join(handler.name for handler in logger.handlers) or "none"
        note(f'"{name}": level {logging.getLevelName(logger.level)}, handlers {names}, propagate {logger.propagate}')
    reached = []
    emits_written(reached)
    for name, level in [("django.server", logging.INFO), ("django.request", logging.ERROR)]:
        note(where(reached, name, level))
    show('LOGGING that names "django" and not "django.server": the server\'s logger is reset, and its records go to the project\'s handler')


def part_logging_twice() -> None:
    import django
    from django.conf import settings

    settings.configure(LOGGING=LOG_TO_ROOT)
    note(f"settings.configure(LOGGING={LOG_TO_ROOT!r})")
    rules = {("django.utils.log", "configure_logging"): plain}
    did("django.setup()", django.setup, rules)
    first = logging.root.handlers[0]
    between = logging.getLogger("library.between")
    note('between = logging.getLogger("library.between")')
    reached = []
    emits_written(reached)
    note(f"between.disabled  -> {between.disabled}")
    note(where(reached, "library.between", logging.WARNING))
    did("django.setup(), a second time", django.setup, rules)
    emits_written(reached)
    note(f"between.disabled  -> {between.disabled}")
    note(where(reached, "library.between", logging.WARNING))
    note(f"the root logger's handler is the one the first django.setup() made: {logging.root.handlers[0] is first}")
    show('django.setup() twice in one process, with LOGGING that leaves out "disable_existing_loggers": '
         "a logger obtained between the two calls is disabled by the second")


def logged(frame) -> str:
    local = frame.f_locals
    response, exc = local["response"], local["exception"]
    arguments = ", ".join([f'"{local["message"]}"', *(repr(a) for a in local["args"])])
    mark = "already marked" if getattr(response, "_has_been_logged", False) else "not yet marked"
    return f"log_response({arguments}, exception={type(exc).__name__ if exc else None})  the {response.status_code} response is {mark}"


LOGGED = {
    ("django.core.handlers.base", "BaseHandler.get_response"): plain,
    ("__main__", "part_log_response.<locals>.broken"): lambda f: "broken  (the view)",
    ("django.core.handlers.base", "BaseHandler.resolve_request"): plain,
    ("django.core.handlers.exception", "response_for_exception"): lambda f: f"response_for_exception(request, a {type(f.f_locals['exc']).__name__})",
    ("django.core.handlers.exception", "handle_uncaught_exception"): plain,
    ("django.utils.log", "log_response"): logged,
    ("django.utils.log", "log_message"): lambda f: f'log_message(the logger "{f.f_locals["logger"].name}", level={f.f_locals["level"]!r}, status_code={f.f_locals["status_code"]})',
    ("logging", "Logger.error"): lambda f: f'Logger.error  ("{f.f_locals["self"].name}")',
    ("logging", "Logger.warning"): lambda f: f'Logger.warning  ("{f.f_locals["self"].name}")',
}


def part_log_response() -> None:
    import io

    import django
    from django.conf import settings
    from django.core.handlers.wsgi import WSGIHandler
    from django.urls import path

    def broken(request):
        raise ValueError("the view fails")

    catching()
    settings.configure(ROOT_URLCONF=(path("broken/", broken),))
    django.setup()
    handler = WSGIHandler()

    def get(url: str):
        def request():
            environ = {"REQUEST_METHOD": "GET", "PATH_INFO": url, "SERVER_NAME": "recording", "SERVER_PORT": "80",
                       "SERVER_PROTOCOL": "HTTP/1.1", "wsgi.input": io.BytesIO(b""), "wsgi.url_scheme": "http"}
            response = handler(environ, lambda status, headers: note(f'start_response("{status}", headers)'))
            response.close()
        return request

    did("GET /broken/, a view that raises", get("/broken/"), LOGGED)
    show("log_response for one 500: called where the exception is caught and again by the handler, which finds the response marked")
    did("GET /missing/, a path no pattern matches", get("/missing/"), LOGGED)
    show("log_response for a 404: called once, by the handler")


# In the order they print. The parts of the second pass stand after the part of the first
# nearest their subject.
PARTS = {
    "unconfigured": part_unconfigured, "model-first": part_model_first, "settings": part_settings,
    "script-prefix": part_script_prefix,
    "configure": part_configure, "setup": part_setup,
    "phase-one-package": phase_one(
        ["library.archive"],
        'django.setup() with INSTALLED_APPS = ["library.archive"], whose package imports its own models module: '
        "the class statement is refused in phase one, and the package is imported three times"),
    "phase-one-apps": phase_one(
        ["library.reading_room"],
        'django.setup() with INSTALLED_APPS = ["library.reading_room"], whose apps module imports its own models module: '
        "the class statement is refused in phase one"),
    "phase-one-earlier": phase_one(
        ["library.catalogue", "library.shelving"],
        'django.setup() with INSTALLED_APPS = ["library.catalogue", "library.shelving"], shelving\'s package importing '
        "catalogue's models: the class statement is refused in phase one, though catalogue's configuration is made"),
    "require-ready": part_require_ready, "unresolved": part_unresolved,
    "failed": part_failed, "setup-in-ready": part_setup_in_ready,
    "wsgi": server_start("wsgi"), "asgi": server_start("asgi"), "runserver-broken": part_runserver_broken,
    "override": part_override, "receivers-twice": part_receivers_twice, "raising-receiver": part_raising_receiver,
    "nested": part_nested,
    "logging": part_logging, "logging-root": part_logging_root, "logging-django": part_logging_django,
    "logging-twice": part_logging_twice, "log-response": part_log_response,
}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        PARTS[sys.argv[1]]()
    else:
        import django

        print("Django", django.get_version(), "and the project library: three applications installed by its settings, "
              "one model each, and eight more installed only by the parts that name them\n")
        sys.stdout.flush()
        for part in PARTS:
            done = subprocess.run([sys.executable, __file__, part], capture_output=True, encoding="utf-8")
            if done.returncode:
                sys.exit(done.stderr)
            sys.stdout.write(done.stdout)
