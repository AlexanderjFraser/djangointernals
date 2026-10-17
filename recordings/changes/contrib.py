"""The habits of the section "What changed in the other contrib apps", release by release: what
an old use of the generic foreign key, the static files finders and collectstatic, the feed
generator, and the PostgreSQL aggregates and fields returns or raises. GeoDjango's habits are
geodjango.py's. Run by recordings/changes.py under each release; _run.py says how a habit is
written.

PostgreSQL's backend is asked without a server: a connection of it made from settings alone,
told the server is PostgreSQL 17 (which no line asks), compiles an aggregate in an annotation
of the journal's Entry, and the line is the aggregate's own SQL and its parameters, not the
statement's; or it prepares a value. Nothing is sent. django.contrib.postgres is not among the
applications, so that a field of it shows the check that asks for it. The default database is
SQLite in memory, as _run.py configures it.

The module writes into a temporary directory of its own run, which no line names: two
directories of static files, first/ and second/, each holding entry.css, which STATICFILES_DIRS
lists in that order; static/, the STATIC_ROOT; and `journal_finders`, a module with a finder
written for an older Django.
"""
import atexit
import os
import sys
import tempfile

from _run import BASE, configure, habit, main

SCRATCH = tempfile.TemporaryDirectory()
atexit.register(SCRATCH.cleanup)
sys.path.append(SCRATCH.name)


def write(path, text):
    path = os.path.join(SCRATCH.name, *path.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)


write("first/entry.css", "h1 { font-family: serif; }\n")
write("second/entry.css", "h1 { font-family: sans-serif; }\n")
os.mkdir(os.path.join(SCRATCH.name, "static"))
write("journal_finders.py", '''\
from django.contrib.staticfiles.finders import BaseFinder


class OldFinder(BaseFinder):
    def find(self, path, all=False):
        return [] if all else None

    def list(self, ignore_patterns):
        return []
''')

configure(
    INSTALLED_APPS=BASE["INSTALLED_APPS"] + ["django.contrib.staticfiles"],
    STATIC_URL="static/",
    STATIC_ROOT=os.path.join(SCRATCH.name, "static"),
    STATICFILES_DIRS=[os.path.join(SCRATCH.name, "first"), os.path.join(SCRATCH.name, "second")],
)


def postgresql():
    """A connection of PostgreSQL's backend made from settings alone, told its server's version;
    nothing opens it."""
    from django.db.utils import ConnectionHandler

    connection = ConnectionHandler({
        "default": {"ENGINE": "django.db.backends.dummy"},
        "server": {"ENGINE": "django.db.backends.postgresql", "NAME": "journal", "USER": "editor",
                   "HOST": "db.journal.example"},
    })["server"]
    connection.pg_version = 170000
    return connection


def compiled(aggregate) -> str:
    """The SQL of the aggregate as PostgreSQL's compiler writes it in an annotation of Entry."""
    from journal.models import Entry

    query = Entry.objects.values("published").annotate(agg=aggregate).query
    compiler = query.get_compiler(connection=postgresql())
    sql, params = compiler.compile(compiler.query.annotations["agg"])
    return f"{sql}, {tuple(params)!r}" if params else sql


# Content types


@habit("Note.content_object.ct_field: the generic foreign key read on its model's class")
def generic_foreign_key_on_the_class():
    from django.contrib.contenttypes.fields import GenericForeignKey
    from django.contrib.contenttypes.models import ContentType
    from django.db import models

    class Note(models.Model):
        content_type = models.ForeignKey(ContentType, models.CASCADE)
        object_id = models.PositiveIntegerField()
        content_object = GenericForeignKey("content_type", "object_id")

        class Meta:
            app_label = "journal"

    return repr(Note.content_object.ct_field)


# Static files


@habit("find(\"entry.css\", all=True), where both directories of STATICFILES_DIRS hold the file: the directories it was found in")
def find_all_keyword():
    from django.contrib.staticfiles.finders import find

    found = find("entry.css", all=True)
    return repr([os.path.basename(os.path.dirname(path)) for path in found])


@habit("find(\"entry.css\"), with STATICFILES_FINDERS a project's finder whose find(self, path, all=False) takes all")
def finder_with_all():
    from django.contrib.staticfiles.finders import find, get_finder
    from django.test import override_settings

    with override_settings(STATICFILES_FINDERS=["journal_finders.OldFinder"]):
        try:
            return repr(find("entry.css"))
        finally:
            get_finder.cache_clear()


@habit("collectstatic --noinput, where both directories of STATICFILES_DIRS hold entry.css: what it writes at verbosity 1")
def collectstatic_conflict():
    import io

    from django.conf import settings
    from django.core.management import call_command
    from django.test import override_settings

    out = io.StringIO()
    finders = ["django.contrib.staticfiles.finders.FileSystemFinder"]  # STATICFILES_DIRS alone, not the applications
    with override_settings(STATICFILES_FINDERS=finders):
        call_command("collectstatic", interactive=False, verbosity=1, stdout=out, stderr=io.StringIO())
    lines = [line for line in out.getvalue().replace(settings.STATIC_ROOT, "STATIC_ROOT").splitlines() if line]
    return "\n".join(lines)


@habit("ManifestStaticFilesStorage.save_manifest(), its hashed_files holding journal/entry.css and then admin/base.css: "
       "the order of \"paths\" in staticfiles.json")
def manifest_order():
    import json

    from django.contrib.staticfiles.storage import ManifestStaticFilesStorage

    storage = ManifestStaticFilesStorage(location=os.path.join(SCRATCH.name, "manifest"))
    storage.hashed_files = {"journal/entry.css": "journal/entry.0d3b4c.css", "admin/base.css": "admin/base.9a1e2f.css"}
    storage.save_manifest()
    with storage.manifest_storage.open(storage.manifest_name) as manifest:
        return repr(list(json.loads(manifest.read().decode())["paths"]))


# Feeds


@habit("Atom1Feed(\"Journal\", \"/\", \"\", stylesheets=[\"/feed.xsl\"]).writeString(\"utf-8\"): the processing instructions it writes")
def atom_stylesheets():
    import re

    from django.utils.feedgenerator import Atom1Feed

    feed = Atom1Feed("Journal", "/", "", stylesheets=["/feed.xsl"])
    return repr(re.findall(r"<\?xml-stylesheet[^?]*\?>", feed.writeString("utf-8")))


# PostgreSQL


@habit("ArrayAgg(\"title\", ordering=\"-title\"), compiled for PostgreSQL")
def array_agg_ordering():
    from django.contrib.postgres.aggregates import ArrayAgg

    return compiled(ArrayAgg("title", ordering="-title"))


@habit("django.contrib.postgres.aggregates.StringAgg(\"title\", delimiter=\", \"), compiled for PostgreSQL")
def postgres_string_agg():
    from django.contrib.postgres.aggregates import StringAgg

    return compiled(StringAgg("title", delimiter=", "))


@habit("django.contrib.postgres.aggregates.BitAnd(\"id\"), compiled for PostgreSQL")
def postgres_bit_and():
    from django.contrib.postgres.aggregates import BitAnd

    return compiled(BitAnd("id"))


@habit("class Agg(OrderableAggMixin, Aggregate)")
def orderable_agg_mixin():
    from django.contrib.postgres.aggregates.mixins import OrderableAggMixin
    from django.db.models import Aggregate

    class Agg(OrderableAggMixin, Aggregate):
        function = "ARRAY_AGG"

    return "the class is made"


@habit("ArrayField(JSONField()).get_db_prep_save([None, {\"tide\": \"high\"}], connection), for PostgreSQL")
def array_of_json_none():
    from django.contrib.postgres.fields import ArrayField
    from django.db.models import JSONField

    return repr(ArrayField(JSONField()).get_db_prep_save([None, {"tide": "high"}], postgresql()))


@habit("Tagged._meta.get_field(\"tags\").check(), an ArrayField, django.contrib.postgres not in INSTALLED_APPS: the ids")
def array_field_without_the_application():
    from django.contrib.postgres.fields import ArrayField
    from django.db import models

    class Tagged(models.Model):
        tags = ArrayField(models.CharField(max_length=20))

        class Meta:
            app_label = "journal"

    return repr([error.id for error in Tagged._meta.get_field("tags").check()])


main()
