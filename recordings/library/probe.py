"""Asks the app registry the same four questions at whatever moment it is called, and keeps
the answers for the recording to print. The project's modules call `ask` as they are imported
and as their application is made ready, so the answers show what the registry can say during
each phase of Apps.populate. A question that raises is answered with the exception: its class
and its message."""
from django.apps import apps

ANSWERS = []  # (the moment, the registry's three flags, [(the question, the answer)])
ASKING = False  # true while the questions are put: the recorder leaves those calls out


def answer(question) -> str:
    try:
        value = question()
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    if isinstance(value, list):
        return "[" + ", ".join(model._meta.label for model in value) + "]"
    if isinstance(value, type):
        return f"the class {value._meta.label}"
    return repr(value)


def ask(moment: str) -> None:
    global ASKING
    ASKING = True
    flags = f"apps_ready {apps.apps_ready}, models_ready {apps.models_ready}, ready {apps.ready}"
    ANSWERS.append((moment, flags, [
        ('get_app_config("catalogue")', answer(lambda: apps.get_app_config("catalogue"))),
        ('get_model("catalogue", "Book")', answer(lambda: apps.get_model("catalogue", "Book"))),
        ('get_registered_model("catalogue", "Book")', answer(lambda: apps.get_registered_model("catalogue", "Book"))),
        ("get_models()", answer(lambda: apps.get_models())),
    ]))
    ASKING = False
