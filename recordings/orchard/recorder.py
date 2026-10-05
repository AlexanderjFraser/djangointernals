"""Writes down, as Django runs a command, each call of the functions on a watch list: nested as
they were made, each with the arguments that tell it apart, and for some the value returned.

Two things use it. The project's manage.py starts it when the environment names a file
(ORCHARD_RECORDING): the process then appends a line to `<that name>.<its pid>` for each call,
headed by the name of the thread that made it, so that a process the recording does not
control (the development server's two) can be read afterwards. And recordings/commands.py
uses it within its own process, through `watched`, for what it calls directly.

An argument is shown where it differs from the function's default. A path is shown from the
project's directory, or from Django's, with forward slashes.
"""
import json
import os
import re
import sys
import threading
import time

PROJECT = os.path.dirname(os.path.abspath(__file__))
LOCAL = threading.local()  # .stack: the watched frames open in this thread; .checks: names, while run_checks runs
LOCK = threading.Lock()
SINK = None  # called with (the thread's name, the depth, the line)
LIST_CHECKS = bool(os.environ.get("ORCHARD_LIST_CHECKS"))  # name the check functions called, not only count them


# ---------------------------------------------------------------------------------------------
# How a value is said.

def q(value) -> str:
    """A value as the book writes a literal: a string in double quotes."""
    if isinstance(value, str):
        return json.dumps(tidy(value))
    if isinstance(value, (list, tuple)):
        text = ", ".join(q(item) for item in value)
        return f"[{text}]" if isinstance(value, list) else f"({text})"
    if isinstance(value, set):
        return "{" + ", ".join(sorted(q(item) for item in value)) + "}" if value else "set()"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{q(key)}: {q(item)}" for key, item in value.items()) + "}"
    return repr(value)


def tidy(text: str) -> str:
    """A path of this machine, as a path from the project's directory or from Django's."""
    import django

    for root, name in ((PROJECT, ""), (os.path.dirname(django.__file__), "django")):
        for spelling in (root, root.replace("\\", "/")):
            if spelling.lower() in text.lower():
                text = text.replace("\\", "/")
                pattern = re.escape(root.replace("\\", "/"))
                text = re.sub(pattern + "/", f"{name}/" if name else "", text, flags=re.IGNORECASE)
                text = re.sub(pattern, name or ".", text, flags=re.IGNORECASE)
    return text


def short(text: str, limit: int = 76) -> str:
    said = json.dumps(tidy(text))
    return said if len(said) <= limit else said[: limit - 4] + '..."'


def keywords(pairs, defaults) -> str:
    return ", ".join(f"{name}={q(value)}" for name, value in pairs if name not in defaults or defaults[name] != value)


# ---------------------------------------------------------------------------------------------
# The watch list. A label function is given the frame at the moment of the call and returns
# the line, or None for a call not to write down, or the line and a function that is given
# what the call returned and says it.

def plain(frame) -> str:
    return frame.f_code.co_qualname


def simple(value) -> str:
    return q(value) if isinstance(value, (str, int, bool, type(None), list, tuple)) else f"a {type(value).__name__}"


def of_command(frame):
    """A method that a command's own class defines: the module says which command."""
    said = f"{frame.f_code.co_qualname}  ({frame.f_globals['__name__']})"
    if frame.f_code.co_name == "get_check_kwargs":
        return said, (lambda result: f"-> {q(result)}")
    if frame.f_code.co_name == "handle_label":
        return f"Command.handle_label({q(frame.f_locals['label'])})  ({frame.f_globals['__name__']})"
    return said


def imported(frame):
    name = frame.f_globals["__name__"]
    if name in ("orchard.urls", "orchard.views") and os.environ.get("RUN_MAIN") == "true":
        # Under the reloader two threads want the root URLconf at the same moment, the one
        # that is about to watch the files and the one that runs the system checks, and
        # which of them imports it is not the same from one run to the next.
        return None
    return f"import {name}"


def found(frame):
    def names(result):
        if len(result) > 6:
            ordered = sorted(result)
            return f'-> {len(result)} names, "{ordered[0]}" to "{ordered[-1]}"'
        return f"-> {q(sorted(result))}"

    return f"find_commands({q(frame.f_locals['management_dir'])})", names


def command_called(frame) -> str:
    local = frame.f_locals
    name = local["command_name"]
    said = [q(name) if isinstance(name, str) else f"a {type(name).__module__}.Command"]
    said += [q(arg) for arg in local["args"]]
    said += [f"{key}={simple(value)}" for key, value in local["options"].items()]
    return f"call_command({', '.join(said)})"


def executed(frame) -> str:
    local = frame.f_locals
    said = [q(arg) for arg in local["args"]] + [f"{key}={simple(value)}" for key, value in local["options"].items()]
    return f"BaseCommand.execute({', '.join(said)})"


CHECK_DEFAULTS = {"app_configs": None, "tags": None, "display_num_errors": False, "include_deployment_checks": False, "fail_level": 40, "databases": None}


def checked(frame) -> str:
    local = frame.f_locals
    return f"BaseCommand.check({keywords([(name, local[name]) for name in CHECK_DEFAULTS], CHECK_DEFAULTS)})"


def checks_run(frame):
    from django.core.checks.registry import registry

    local = frame.f_locals
    LOCAL.checks, LOCAL.inside = [], []
    LOCAL.check_codes = {id(check.__code__) for check in registry.registered_checks | registry.deployment_checks}
    pairs = [(name, local[name]) for name in ("app_configs", "tags", "include_deployment_checks", "databases")]

    def outcome(result):
        called, inside = sorted(LOCAL.checks), sorted(set(LOCAL.inside))
        LOCAL.checks = LOCAL.inside = LOCAL.check_codes = None
        messages = ", ".join(message.id for message in result) if result else "no messages"
        said = [f"-> {len(called)} check functions called; {messages}"]
        if LIST_CHECKS:
            line = ""
            for name in called:
                if len(line) + len(name) > 92:
                    said.append("   " + line.rstrip())
                    line = ""
                line += name + ", "
            said.append("   " + line.rstrip(", "))
            said += [f"   and from inside them: {text}" for text in inside]
        return said

    return f"CheckRegistry.run_checks({keywords(pairs, CHECK_DEFAULTS)})", outcome


def written(frame):
    wrapper, message = frame.f_locals["self"], frame.f_locals["msg"]
    if frame.f_back.f_code.co_name == "on_bind":
        return None  # the server's banner, which begins with the date and the time
    stream = "stdout" if wrapper._out is sys.stdout else "stderr" if wrapper._out is sys.stderr else f"a {type(wrapper._out).__name__}"
    return f"OutputWrapper.write({short(message)})  to {stream}"


def closed(frame) -> str:
    if type(frame.f_locals["self"]).__name__ != "ConnectionHandler":
        return None  # the caches, closed by a receiver of request_finished
    return "BaseConnectionHandler.close_all  (the database connections)"


def wrapped(frame) -> str:
    return f"the wrapper that check_errors made around {frame.f_locals['fn'].__qualname__}"


def child_run(frame):
    if frame.f_back.f_code.co_name != "restart_with_reloader":
        return None
    env = frame.f_locals["kwargs"]["env"]
    arguments = ["python" if str(arg) == sys.executable else str(arg) for arg in frame.f_locals["popenargs"][0]]
    return f'subprocess.run({q(arguments)}, env with RUN_MAIN={q(env["RUN_MAIN"])})', (
        lambda result: f"-> the process ended with status {result.returncode}"
    )


def signal_sent(frame):
    from django.utils import autoreload

    signal, named = frame.f_locals["self"], frame.f_locals["named"]
    name = {id(autoreload.autoreload_started): "autoreload_started", id(autoreload.file_changed): "file_changed"}.get(id(signal))
    if name is None:
        return None
    if name == "autoreload_started":
        # Its receivers are not said: the translation machinery connects one when it is first
        # used, which another thread may do before this moment or after it.
        return "autoreload_started.send()"
    said = f"{name}.send({', '.join(f'{key}={q(str(value))}' for key, value in named.items())})"
    return said, (lambda result: f"-> {', '.join(f'{receiver.__name__} answered {answer!r}' for receiver, answer in result)}")


def server_made(frame) -> str:
    cls = type(frame.f_locals["self"])
    bases = ", ".join(f"{base.__module__}.{base.__name__}" if base.__module__ != "django.core.servers.basehttp" else base.__name__ for base in cls.__bases__)
    return f"WSGIServer.__init__  (the class is {cls.__name__}, made from {bases})"


def served(frame) -> str:
    local = frame.f_locals
    return f'run("{local["addr"]}", {local["port"]}, a {type(local["wsgi_handler"]).__name__}, threading={local["threading"]}, server_cls={local["server_cls"].__name__})'


def requested(frame) -> str:
    environ = frame.f_locals["environ"]
    return f'{frame.f_code.co_qualname}  {environ["REQUEST_METHOD"]} {environ["PATH_INFO"]}'


def logged(frame) -> str:
    local = frame.f_locals
    return f"WSGIRequestHandler.log_message({short(local['format'] % local['args'])})"


MANAGEMENT = "django.core.management"
BASE = "django.core.management.base"
RELOAD = "django.utils.autoreload"
HTTP = "django.core.servers.basehttp"

# (module, qualname) -> the label function. A module ending in "." matches that package and
# everything under it; a qualname of "Command.*" matches every method of a class of that name.
RULES = {
    (MANAGEMENT, "execute_from_command_line"): lambda f: f"execute_from_command_line({q([os.path.basename(a) if os.path.isabs(a) else a for a in f.f_locals['argv']])})",
    (MANAGEMENT, "ManagementUtility.execute"): plain,
    (MANAGEMENT, "ManagementUtility.autocomplete"): plain,
    (MANAGEMENT, "ManagementUtility.main_help_text"): plain,
    (MANAGEMENT, "ManagementUtility.fetch_command"): lambda f: f'ManagementUtility.fetch_command("{f.f_locals["subcommand"]}")',
    (MANAGEMENT, "get_commands"): plain,
    (MANAGEMENT, "find_commands"): found,
    (MANAGEMENT, "load_command_class"): lambda f: f'load_command_class("{f.f_locals["app_name"]}", "{f.f_locals["name"]}")',
    (MANAGEMENT, "call_command"): command_called,
    (BASE, "handle_default_options"): lambda f: f"handle_default_options(settings={q(f.f_locals['options'].settings)}, pythonpath={q(f.f_locals['options'].pythonpath)})",
    (BASE, "BaseCommand.run_from_argv"): lambda f: f"BaseCommand.run_from_argv({q([os.path.basename(a) if os.path.isabs(a) else a for a in f.f_locals['argv']])})",
    (BASE, "BaseCommand.create_parser"): lambda f: f'BaseCommand.create_parser("{os.path.basename(f.f_locals["prog_name"])}", "{f.f_locals["subcommand"]}")',
    (BASE, "CommandParser.parse_args"): lambda f: f"CommandParser.parse_args({q(f.f_locals['args'])})",
    (BASE, "CommandParser.error"): lambda f: f"CommandParser.error({q(f.f_locals['message'])})",
    (BASE, "LabelCommand.add_arguments"): plain,
    (BASE, "AppCommand.add_arguments"): plain,
    (BASE, "BaseCommand.execute"): executed,
    (BASE, "BaseCommand.get_check_kwargs"): lambda f: ("BaseCommand.get_check_kwargs", lambda result: f"-> {q(result)}"),
    (BASE, "BaseCommand.check"): checked,
    (BASE, "BaseCommand.check_migrations"): plain,
    (BASE, "LabelCommand.handle"): lambda f: f"LabelCommand.handle({', '.join(q(label) for label in f.f_locals['labels'])})",
    (BASE, "OutputWrapper.write"): written,
    ("django.core.checks.registry", "CheckRegistry.run_checks"): checks_run,
    ("django", "setup"): lambda f: "django.setup",
    ("django.conf", "Settings.__init__"): lambda f: f'Settings.__init__("{f.f_locals["settings_module"]}")',
    ("django.utils.connection", "BaseConnectionHandler.close_all"): closed,
    ("django.core.management.commands.", "<module>"): imported,
    ("django.contrib.staticfiles.management.commands.", "<module>"): imported,
    ("django.core.management.commands.", "Command.*"): of_command,
    ("django.contrib.staticfiles.management.commands.", "Command.*"): of_command,
    ("trees.", "<module>"): imported,
    ("press.", "<module>"): imported,
    ("orchard.", "<module>"): imported,
    ("trees.management.commands.", "Command.*"): of_command,
    ("press.management.commands.", "Command.*"): of_command,
    (RELOAD, "check_errors.<locals>.wrapper"): wrapped,
    (RELOAD, "raise_last_exception"): plain,
    (RELOAD, "run_with_reloader"): lambda f: f"run_with_reloader({f.f_locals['main_func'].__qualname__})  with RUN_MAIN {q(os.environ.get('RUN_MAIN'))} in the environment",
    (RELOAD, "restart_with_reloader"): plain,
    (RELOAD, "get_child_arguments"): plain,
    ("subprocess", "run"): child_run,
    (RELOAD, "get_reloader"): lambda f: ("get_reloader", lambda result: f"-> a {type(result).__name__}"),
    (RELOAD, "start_django"): lambda f: f"start_django(a {type(f.f_locals['reloader']).__name__}, {f.f_locals['main_func'].__qualname__})",
    (RELOAD, "BaseReloader.run"): plain,
    (RELOAD, "BaseReloader.wait_for_apps_ready"): lambda f: ("BaseReloader.wait_for_apps_ready", lambda result: f"-> {result}"),
    ("django.urls.resolvers", "get_resolver"): lambda f: "get_resolver" if f.f_back.f_code.co_qualname == "BaseReloader.run" else None,
    (RELOAD, "BaseReloader.run_loop"): plain,
    (RELOAD, "BaseReloader.notify_file_changed"): lambda f: f"BaseReloader.notify_file_changed({q(str(f.f_locals['path']))})",
    (RELOAD, "trigger_reload"): lambda f: f"trigger_reload({q(str(f.f_locals['filename']))})",
    ("django.dispatch.dispatcher", "Signal.send"): signal_sent,
    (HTTP, "get_internal_wsgi_application"): plain,
    (HTTP, "run"): served,
    (HTTP, "WSGIServer.__init__"): server_made,
    (HTTP, "WSGIRequestHandler.handle"): plain,
    (HTTP, "WSGIRequestHandler.handle_one_request"): plain,
    (HTTP, "WSGIRequestHandler.log_message"): logged,
    (HTTP, "ServerHandler.finish_response"): plain,
    (HTTP, "ServerHandler.close"): plain,
    ("django.core.wsgi", "get_wsgi_application"): plain,
    ("django.core.handlers.wsgi", "WSGIHandler.__init__"): plain,
    ("django.core.handlers.wsgi", "WSGIHandler.__call__"): requested,
    ("django.contrib.staticfiles.handlers", "StaticFilesHandler.__init__"): plain,
    ("django.contrib.staticfiles.handlers", "StaticFilesHandler.__call__"): requested,
    ("socketserver", "BaseServer.serve_forever"): plain,
    ("socketserver", "ThreadingMixIn.process_request"): lambda f: "ThreadingMixIn.process_request  (a connection is accepted: a thread is started for it)",
    ("socketserver", "ThreadingMixIn.process_request_thread"): plain,
    ("wsgiref.handlers", "BaseHandler.run"): lambda f: f"BaseHandler.run(a {type(f.f_locals['application']).__name__})",
}
FOUND = {}  # (a code object's file, line and qualified name) -> its label function, or None


def find(code, module: str):
    qualname = code.co_qualname
    for (want_module, want), label in RULES.items():
        if module == want_module or (want_module.endswith(".") and module.startswith(want_module)):
            if want == qualname or (want == "Command.*" and qualname.startswith("Command.") and qualname.count(".") == 1):
                return label
    return None


def profile(frame, event, arg):
    if event == "call":
        code = frame.f_code
        codes = getattr(LOCAL, "check_codes", None)
        if codes and id(code) in codes:
            LOCAL.checks.append(code.co_name)
            return
        # Two code objects are equal when their contents are, and every empty module's are:
        # the file is part of the key.
        key = (code.co_filename, code.co_firstlineno, code.co_qualname)
        try:
            label = FOUND[key]
        except KeyError:
            label = FOUND[key] = find(code, frame.f_globals.get("__name__", ""))
        if label is None:
            return
        said = label(frame)
        if said is None:
            return
        text, after = said if isinstance(said, tuple) else (said, None)
        if codes:
            # Inside run_checks. The registry keeps its checks in a set, so the order they run
            # in, and so the order of what they call, is not the same from one run to the next.
            LOCAL.inside.append(text)
            return
        stack = LOCAL.__dict__.setdefault("stack", [])
        SINK(threading.current_thread().name, len(stack), text)
        stack.append((frame, after))
    elif event == "return":
        stack = LOCAL.__dict__.get("stack")
        if stack and stack[-1][0] is frame:
            after = stack.pop()[1]
            if after is not None and arg is not None:
                answer = after(arg)
                for line in [answer] if isinstance(answer, str) else answer or []:
                    SINK(threading.current_thread().name, len(stack) + 1, line)


def start() -> None:
    """Record this process, every thread of it, into a file of its own."""
    global SINK
    out = open(f"{os.environ['ORCHARD_RECORDING']}.{os.getpid()}", "a", encoding="utf-8")
    out.write(f"#\t{time.time()}\t{os.environ.get('RUN_MAIN')}\n")
    out.flush()

    def sink(thread: str, depth: int, text: str) -> None:
        with LOCK:
            out.write(f"{thread}\t{depth}\t{text}\n")
            out.flush()

    SINK = sink
    threading.setprofile(profile)
    sys.setprofile(profile)


def watched(action, sink):
    """Run the action in this thread with the watch list in force, each line given to `sink`."""
    global SINK
    SINK = sink
    LOCAL.stack = []
    sys.setprofile(profile)
    try:
        return action()
    finally:
        sys.setprofile(None)
