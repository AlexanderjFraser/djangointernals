"""The settings of the project that the recording of chapter 3 runs commands in: one contrib
application that ships commands of its own, and two applications of the project, each with a
management/commands directory. One settings module serves every part of the recording, so the
two things the parts vary are read from the environment."""
import os

SECRET_KEY = "recording"
DEBUG = True
ROOT_URLCONF = "orchard.urls"
WSGI_APPLICATION = "orchard.wsgi.application"
STATIC_URL = "static/"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

INSTALLED_APPS = [
    "django.contrib.staticfiles",  # ships a runserver of its own, which stands in for Django's
    "trees",  # the commands count and prune, a model, and a system check
    "press",  # a second count, and juice
]

# What the system check of the trees application looks at, and the messages to silence.
TREES_PER_ROW = int(os.environ.get("TREES_PER_ROW", "12"))
SILENCED_SYSTEM_CHECKS = os.environ.get("SILENCED", "").split()
