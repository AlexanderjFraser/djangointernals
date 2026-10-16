"""The old habits the chapter's opening page shows, release by release: a default that changed
without a word, a deprecated use that still works and warns, and a removed one that fails.
Run by recordings/changes.py under each release; _run.py says how a habit is written.
"""
from _run import configure, habit, main

configure()


@habit("settings.USE_TZ, when the settings do not set it")
def use_tz():
    from django.conf import settings
    return repr(settings.USE_TZ)


@habit("settings.DEFAULT_AUTO_FIELD, when the settings do not set it")
def default_auto_field():
    from django.conf import settings
    return repr(settings.DEFAULT_AUTO_FIELD)


@habit("Entry._meta.pk: the key of a model that declares none, in an application that names no default")
def primary_key():
    from journal.models import Entry
    return repr(Entry._meta.pk)


@habit("JsonResponse([1, 2]).content")
def json_response_of_a_list():
    from django.http import JsonResponse
    return repr(JsonResponse([1, 2]).content)


@habit("django.VERSION[:3]")
def version_sliced():
    import django
    return repr(django.VERSION[:3])


@habit("from django.utils.deprecation import MiddlewareMixin")
def middleware_mixin_from_its_old_module():
    from django.utils.deprecation import MiddlewareMixin
    return MiddlewareMixin.__module__


@habit("CommonMiddleware.async_capable")
def async_capable():
    from django.middleware.common import CommonMiddleware
    return repr(CommonMiddleware.async_capable)


@habit("Entry.objects.select_related(), with no field named")
def select_related_with_no_arguments():
    from journal.models import Entry
    return str(Entry.objects.select_related().query)


@habit("Entry.objects.values_list(flat=True), with no field named")
def values_list_flat_with_no_field():
    from journal.models import Entry
    return str(Entry.objects.values_list(flat=True).query)


@habit("salted_hmac(\"journal\", \"entry\").name: the algorithm when none is named")
def salted_hmac_algorithm():
    from django.utils.crypto import salted_hmac
    return repr(salted_hmac("journal", "entry").name)


@habit("urlize(\"journal.example.com\"): the scheme assumed for a bare domain")
def urlize_bare_domain():
    from django.utils.html import urlize
    return urlize("journal.example.com")


@habit("Paginator(range(10), 2, orphans=2).num_pages: orphans not fewer than the page")
def paginator_orphans():
    from django.core.paginator import Paginator
    return repr(Paginator(range(10), 2, orphans=2).num_pages)


@habit("from django.core.mail import BadHeaderError")
def bad_header_error():
    from django.core.mail import BadHeaderError
    return f"{BadHeaderError.__module__}.{BadHeaderError.__name__}"


@habit("class Meta: index_together = [(\"title\", \"published\")]")
def index_together():
    from django.db import models

    class Draft(models.Model):
        title = models.CharField(max_length=100)
        published = models.DateField()

        class Meta:
            app_label = "journal"
            index_together = [("title", "published")]

    return "the class is made"


@habit("from django.utils.timezone import utc")
def utc_alias():
    from django.utils.timezone import utc
    return repr(utc)


main()
