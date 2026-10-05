#!/usr/bin/env python
"""The orchard's command-line utility: the manage.py that startproject writes, and four lines
more. When recordings/commands.py runs it, the environment names a file, and the process
writes down there each call it makes of the functions on the recorder's watch list."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orchard.settings")
    if os.environ.get("ORCHARD_RECORDING"):
        import recorder

        recorder.start()
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
