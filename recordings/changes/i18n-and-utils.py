"""The habits of the section "What changed in time zones, translation and the utilities",
release by release: what an old project's time-zone code meets (the default of USE_TZ, the
alias utc, is_dst refused by make_aware and taken by a truncation), what the removed USE_L10N
still does when set, whether Haitian Creole, listed since 6.0, is ever chosen, and what the
utilities do with an old call: itercompat's is_iterable, a duration in weeks, import_string
given a module's path (a top-level module, a submodule not yet imported, a submodule beside an
attribute of its name, and a submodule its package imports and then rebinds the name of), and
django.VERSION read past its second part. The package almanac is written for its habit into a
temporary directory, on the path for that call only. Run by recordings/changes.py under each
release; _run.py says how a habit is written.
"""
from _run import configure, habit, main

configure()


def shown(value):
    """A module by its name, since its repr carries a path of this machine; anything else by repr."""
    import types

    if isinstance(value, types.ModuleType):
        return f"the module {value.__name__}"
    return repr(value)


# Time zones

@habit("settings.USE_TZ, when the settings do not set it")
def use_tz():
    from django.conf import settings
    return repr(settings.USE_TZ)


@habit("from django.utils.timezone import utc")
def utc_alias():
    from django.utils.timezone import utc
    return repr(utc)


@habit("timezone.make_aware(datetime(2026, 10, 25, 2, 30), is_dst=True)")
def make_aware_is_dst():
    from datetime import datetime

    from django.utils import timezone

    return repr(timezone.make_aware(datetime(2026, 10, 25, 2, 30), is_dst=True))


@habit("TruncDay(\"arrived\", is_dst=True): the query's SQL, beside the same query without is_dst")
def trunc_is_dst():
    from django.db import models
    from django.db.models.functions import TruncDay

    class Arrival(models.Model):
        arrived = models.DateTimeField()

        class Meta:
            app_label = "journal"

    with_it = str(Arrival.objects.annotate(day=TruncDay("arrived", is_dst=True)).query)
    without = str(Arrival.objects.annotate(day=TruncDay("arrived")).query)
    return "accepted, and the SQL is the same" if with_it == without else "accepted, and the SQL differs"


# Localization

@habit("formats.localize(1234.5) in Dutch, under the setting USE_L10N = False")
def use_l10n_false():
    from django.test import override_settings
    from django.utils import formats, translation

    with override_settings(USE_L10N=False), translation.override("nl"):
        return repr(formats.localize(1234.5))


# Languages

@habit("\"ht\" in dict(settings.LANGUAGES): Haitian Creole")
def haitian_creole_listed():
    from django.conf import settings
    return repr("ht" in dict(settings.LANGUAGES))


@habit("translation.get_language_from_request(request): a request sent with Accept-Language: ht")
def haitian_creole_chosen():
    from django.test import RequestFactory
    from django.utils import translation

    request = RequestFactory().get("/", HTTP_ACCEPT_LANGUAGE="ht")
    return repr(translation.get_language_from_request(request))


# The utilities

@habit("from django.utils.itercompat import is_iterable; is_iterable([\"Harbour\"])")
def itercompat_is_iterable():
    from django.utils.itercompat import is_iterable
    return repr(is_iterable(["Harbour"]))


@habit("parse_duration(\"P1W2DT3H\"): a week, two days and three hours")
def parse_duration_weeks():
    from django.utils.dateparse import parse_duration
    return repr(parse_duration("P1W2DT3H"))


@habit("import_string(\"json\"): a top-level module")
def import_string_top_level():
    from django.utils.module_loading import import_string
    return shown(import_string("json"))


@habit("import_string(\"django.utils.archive\"): a submodule nothing has imported")
def import_string_unimported_submodule():
    from django.utils.module_loading import import_string
    return shown(import_string("django.utils.archive"))


@habit("import_string(\"almanac.tides\"): a submodule, where almanac's __init__.py binds tides = \"high water\"")
def import_string_submodule_or_attribute():
    import importlib
    import os
    import sys
    import tempfile

    from django.utils.module_loading import import_string

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        package = os.path.join(directory, "almanac")
        os.mkdir(package)
        with open(os.path.join(package, "__init__.py"), "w", encoding="utf-8") as init:
            init.write('tides = "high water"\n')
        with open(os.path.join(package, "tides.py"), "w", encoding="utf-8") as tides:
            tides.write('"""The tides, a submodule of almanac."""\n')
        sys.path.insert(0, directory)
        importlib.invalidate_caches()
        try:
            return shown(import_string("almanac.tides"))
        finally:
            sys.path.remove(directory)


@habit("import_string(\"unittest.main\"): a submodule that unittest's __init__.py imports, then rebinds to a class")
def import_string_rebound_submodule():
    from django.utils.module_loading import import_string
    return shown(import_string("unittest.main"))


@habit("django.VERSION[:3]")
def version_sliced():
    import django
    return repr(django.VERSION[:3])


main()
