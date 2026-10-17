"""The old habits the chapter's opening page tells, release by release: a default that changed
without a word, a deprecated use that still works and warns, and a removed one that fails.
Each section by part of the book has its habits in the module named after it. Run by
recordings/changes.py under each release; _run.py says how a habit is written.
"""
from _run import configure, habit, main

configure()


@habit("settings.DEFAULT_AUTO_FIELD, when the settings do not set it")
def default_auto_field():
    from django.conf import settings
    return repr(settings.DEFAULT_AUTO_FIELD)


@habit("Entry._meta.pk: the key of a model that declares none, in an application that names no default")
def primary_key():
    from journal.models import Entry
    return repr(Entry._meta.pk)


@habit("from django.utils.deprecation import MiddlewareMixin")
def middleware_mixin_from_its_old_module():
    from django.utils.deprecation import MiddlewareMixin
    return MiddlewareMixin.__module__


@habit("salted_hmac(\"journal\", \"entry\").name: the algorithm when none is named")
def salted_hmac_algorithm():
    from django.utils.crypto import salted_hmac
    return repr(salted_hmac("journal", "entry").name)


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


main()
