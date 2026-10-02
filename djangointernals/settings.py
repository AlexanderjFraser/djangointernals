"""Settings for a site that is baked and never served: no database, no sessions, no users.

Three settings are the book's own. BOOK_DIR is the directory of markdown the
site renders: `pages/`, unless $BOOK or `bake --book` names another (the
specimen). SITE_URL is where the baked book is published. INDEXABLE says
whether what is baked may be indexed and carries canonical URLs: only the
book itself, never the specimen.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

BOOK_DIR = BASE_DIR / os.environ.get("BOOK", "pages")
PIN_FILE = BASE_DIR / "pin.json"
DIST_DIR = BASE_DIR / "dist"
SITE_URL = "https://djangointernals.dev"
REPOSITORY_URL = "https://github.com/AlexanderjFraser/djangointernals"

# The key signs nothing: the site has no sessions, no forms and no users.
SECRET_KEY = "baked-to-static-files"
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "djangointernals",
]
MIDDLEWARE = []
ROOT_URLCONF = "djangointernals.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["djangointernals.views.site"]},
    },
]
DATABASES = {}
USE_TZ = True

# No STATIC_ROOT: the bake copies the static files beside the pages itself.
STATIC_URL = "/static/"
