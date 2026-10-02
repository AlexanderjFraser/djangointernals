#!/usr/bin/env python3
"""The book's site is a Django project, and this is its command line.

    python manage.py bake                     bake pages/ to dist/, as static files
    python manage.py bake --book specimen     bake the specimen: the page spec, exercised
    python manage.py bake --probe             prove the bake refuses what it should
    python manage.py runserver                serve the book as it stands, read again when a file changes
                                              (the book is pages/, or the directory $BOOK names)

Run it with the project's virtual environment (Python 3.12 or later, Django
installed from the pinned clone, and requirements.txt).
"""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "djangointernals.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
