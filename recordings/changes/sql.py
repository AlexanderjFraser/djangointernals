"""The habits of the section "What changed in expressions, lookups and the compiler", release
by release: what an expression's or a lookup's as_sql returns, how the compiler writes an alias,
what the aggregates accept, what None means on a JSON field, and the names that came, moved or
went. Run by recordings/changes.py under each release; _run.py says how a habit is written.

Beside the journal's three entries, Dawn, Dusk and Noon, published in that order, the habits
share two models of their own. Note is a note on an entry, with a JSON document: five notes hold
the five shapes of a document the JSON habits ask about, each titled by its shape, "mood null"
({"mood": null}), "mood calm" ({"mood": "calm", "tags": [...]}), "no mood" ({}), "JSON null"
(the document is JSON's null) and "SQL NULL" (the column is NULL). Line has a composite key, an
entry and a number, and each entry has lines 1 and 2.

The statements run on SQLite, the version the running Python is built with, the same for every
release's line (3.50.4 when the recording was made). Some lines depend on it: an aggregate's
ORDER BY, and so StringAgg(order_by=...), needs SQLite 3.44
(django/db/backends/sqlite3/features.py), and under an older SQLite those lines differ.
"""
import warnings

from _run import configure, create, habit, main, tables

configure()

NOTE = LINE = None


def _setup():
    """The entries, the notes and the lines, made before any habit runs, with their warnings
    silenced."""
    global NOTE, LINE
    import datetime

    from django.db import models
    from journal.models import Entry

    tables()

    class Note(models.Model):
        title = models.CharField(max_length=100)
        entry = models.ForeignKey(Entry, models.CASCADE, null=True, related_name="notes")
        data = models.JSONField(null=True)

        class Meta:
            app_label = "journal"

    create(Note)
    dawn = Entry.objects.create(title="Dawn", published=datetime.date(2026, 1, 5))
    dusk = Entry.objects.create(title="Dusk", published=datetime.date(2026, 2, 5))
    noon = Entry.objects.create(title="Noon", published=datetime.date(2026, 3, 5))
    Note.objects.create(title="mood null", entry=dawn, data={"mood": None})
    Note.objects.create(title="mood calm", entry=noon, data={"mood": "calm", "tags": ["rain", "wind", "sun"]})
    Note.objects.create(title="no mood", entry=dusk, data={})
    Note.objects.create(title="JSON null", data=models.Value(None, models.JSONField()))
    Note.objects.create(title="SQL NULL", data=None)

    class Line(models.Model):
        pk = models.CompositePrimaryKey("entry", "number")
        entry = models.ForeignKey(Entry, models.CASCADE)
        number = models.IntegerField()

        class Meta:
            app_label = "journal"

    create(Line)
    for entry in (dawn, dusk, noon):
        Line.objects.create(entry=entry, number=1)
        Line.objects.create(entry=entry, number=2)
    NOTE, LINE = Note, Line


with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    _setup()


def titles(queryset) -> str:
    return repr(sorted(queryset.values_list("title", flat=True)))


# Parameters

@habit("Lower(Value(\"Dawn\")).as_sql(compiler, connection)")
def func_as_sql():
    from django.db import connection
    from django.db.models import Value
    from django.db.models.functions import Lower
    from journal.models import Entry

    compiler = Entry.objects.all().query.get_compiler(connection=connection)
    return repr(Lower(Value("Dawn")).as_sql(compiler, connection))


@habit("Entry.objects.filter(title__within=(\"Dawn\", \"Dusk\")): a custom lookup whose as_sql returns lhs_params + list(self.rhs)")
def custom_lookup_list():
    from django.db.models import CharField, Lookup
    from journal.models import Entry

    class Within(Lookup):
        lookup_name = "within"
        prepare_rhs = False

        def as_sql(self, compiler, connection):
            lhs, lhs_params = self.process_lhs(compiler, connection)
            return "%s BETWEEN %%s AND %%s" % lhs, lhs_params + list(self.rhs)

    CharField.register_lookup(Within)
    try:
        return titles(Entry.objects.filter(title__within=("Dawn", "Dusk")))
    finally:
        CharField._unregister_lookup(Within)


# Aliases

@habit("str(Entry.objects.annotate(Calm=FilteredRelation(\"notes\", condition=Q(notes__title=\"mood calm\"))).values(\"Calm__title\").query)")
def filtered_relation_alias():
    from django.db.models import FilteredRelation, Q
    from journal.models import Entry

    calm = FilteredRelation("notes", condition=Q(notes__title="mood calm"))
    return str(Entry.objects.annotate(Calm=calm).values("Calm__title").query)


@habit("compiler.quote_name_unless_alias(\"T3\"), where T3 is the alias of a join")
def quote_name_unless_alias():
    from django.db import connection

    query = NOTE.objects.filter(entry__notes__title="no mood").query
    compiler = query.get_compiler(connection=connection)
    return repr(compiler.quote_name_unless_alias("T3"))


@habit("Entry.objects.annotate(**{\"share%\": Value(1)}).values_list(\"share%\", flat=True)")
def percent_alias():
    from django.db.models import Value
    from journal.models import Entry

    return repr(list(Entry.objects.annotate(**{"share%": Value(1)}).values_list("share%", flat=True)))


# Aggregates

@habit("[name for name in (\"StringAgg\", \"AnyValue\", \"BitAnd\", \"BitOr\", \"BitXor\", \"JSONNull\") if hasattr(django.db.models, name)]")
def names_in_models():
    from django.db import models

    return repr([name for name in ("StringAgg", "AnyValue", "BitAnd", "BitOr", "BitXor", "JSONNull") if hasattr(models, name)])


@habit("Entry.objects.aggregate(titles=StringAgg(\"title\", Value(\", \"), order_by=\"published\"))")
def string_agg_order_by():
    from django.db.models import StringAgg, Value
    from journal.models import Entry

    return repr(Entry.objects.aggregate(titles=StringAgg("title", Value(", "), order_by="published")))


@habit("Entry.objects.aggregate(first=Max(\"title\", order_by=\"published\")): an aggregate that takes no ordering")
def max_order_by():
    from django.db.models import Max
    from journal.models import Entry

    return repr(Entry.objects.aggregate(first=Max("title", order_by="published")))


@habit("Entry.objects.aggregate(titles=StringAgg(\"title\", Value(\",\"), distinct=True)), on SQLite: distinct, the delimiter a bare comma")
def string_agg_distinct():
    from django.db.models import StringAgg, Value
    from journal.models import Entry

    return repr(Entry.objects.aggregate(titles=StringAgg("title", Value(","), distinct=True)))


@habit("Entry.objects.aggregate(n=Total(\"id\", filter=Q(title=\"Dawn\"))): Total an Aggregate whose template is \"%(function)s(%(expressions)s)\"")
def custom_aggregate_filter():
    from django.db.models import Aggregate, Q
    from journal.models import Entry

    class Total(Aggregate):
        function = "COUNT"
        name = "Total"
        template = "%(function)s(%(expressions)s)"

    return repr(Entry.objects.aggregate(n=Total("id", filter=Q(title="Dawn"))))


@habit("Entry.objects.aggregate(n=Total(\"id\", filter=Q(published__lt=F(\"published\")))): Total an Aggregate whose template "
       "is \"%(function)s(%(expressions)s)\", and a filter no entry passes")
def custom_aggregate_filter_without_parameters():
    from django.db.models import Aggregate, F, Q
    from journal.models import Entry

    class Total(Aggregate):
        function = "COUNT"
        name = "Total"
        template = "%(function)s(%(expressions)s)"

    return repr(Entry.objects.aggregate(n=Total("id", filter=Q(published__lt=F("published")))))


@habit("Sum(\"id\", \"title\")")
def sum_arity():
    from django.db.models import Sum

    return repr(Sum("id", "title"))


@habit("Entry.objects.aggregate(n=Count(\"title\", \"published\"))")
def count_two_arguments():
    from django.db.models import Count
    from journal.models import Entry

    return repr(Entry.objects.aggregate(n=Count("title", "published")))


# JSON

@habit("Note.objects.filter(data=None): the notes that match")
def json_none():
    return titles(NOTE.objects.filter(data=None))


@habit("Note.objects.filter(data=JSONNull()): the notes that match")
def json_null():
    from django.db.models import JSONNull

    return titles(NOTE.objects.filter(data=JSONNull()))


@habit("Note.objects.filter(data__mood=None): the notes that match")
def json_key_none():
    return titles(NOTE.objects.filter(data__mood=None))


@habit("Note.objects.filter(data__mood__iexact=None): the notes that match")
def json_key_iexact_none():
    return titles(NOTE.objects.filter(data__mood__iexact=None))


@habit("Note.objects.filter(**{\"data__tags__-1\": \"sun\"}), on SQLite: the notes that match")
def json_negative_index():
    return titles(NOTE.objects.filter(**{"data__tags__-1": "sun"}))


@habit("from django.db.models.fields.json import compile_json_path")
def compile_json_path_import():
    from django.db.models.fields.json import compile_json_path

    return f"{compile_json_path.__module__}.{compile_json_path.__qualname__}"


@habit("JSONField().get_db_prep_value(\"[]\", connection)")
def json_string():
    from django.db import connection
    from django.db.models import JSONField

    return repr(JSONField().get_db_prep_value("[]", connection))


# The rest

@habit("Note._meta.get_field(\"entry\").get_joining_columns()")
def get_joining_columns():
    return repr(NOTE._meta.get_field("entry").get_joining_columns())


def lines(queryset) -> str:
    return repr(sorted((line.entry.title, line.number) for line in queryset))


@habit("Line.objects.filter(pk=Line.objects.filter(number=2).values(\"pk\")[:1]): a composite key equal to a subquery's")
def composite_key_exact_subquery():
    first = LINE.objects.filter(number=2).order_by("entry__published").values("pk")[:1]
    return lines(LINE.objects.filter(pk=first))


@habit("Line.objects.filter(pk__gt=Line.objects.filter(number=2).values(\"pk\")[:1]), on SQLite: a composite key greater than a subquery's")
def composite_key_greater_than_subquery():
    first = LINE.objects.filter(number=2).order_by("entry__published").values("pk")[:1]
    return lines(LINE.objects.filter(pk__gt=first))


@habit("Entry.objects.annotate(n=Value(1)).values(\"n\").query.annotation_select_mask")
def annotation_mask():
    from django.db.models import Value
    from journal.models import Entry

    return repr(Entry.objects.annotate(n=Value(1)).values("n").query.annotation_select_mask)


@habit("TruncDay(\"published\").deconstruct(): as a migration writes it, with no tzinfo and USE_TZ at its default, True")
def trunc_deconstruct():
    from django.db.models.functions import TruncDay

    return repr(TruncDay("published").deconstruct())


main()
