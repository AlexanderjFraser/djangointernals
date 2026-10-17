"""The habits of the section "Security fixes: SQL injection", release by release: a hostile name
given where the ORM writes a name into a statement (an alias of annotate or values, a JSON key
named in values, the name of a FilteredRelation, the connector of a Q, and the flag _negated
that When hands on to Q), and the values Oracle's JSON lookups write into one. Each patch
release recorded is the newest of its series and carries every fix, so most lines say that all
four refuse alike; the lines that differ are the guards 6.1 changed again. Run by
recordings/changes.py under each release; _run.py says how a habit is written.

The journal's three entries, Dawn, Dusk and Noon, published in that order, each have a remark,
a model of the module's own with a JSON document. PostgreSQL's and Oracle's backends are asked
without a server: a connection made from settings alone compiles the statement, no line asks
the server's version, and nothing is sent. In Oracle's statements U+FFFF, the delimiter of a
literal, is written <U+FFFF>.

Q.create is tree.Node.create, a classmethod the documentation does not name, which Django calls
itself only with AND, OR or a node's own connector; the documented ways a crafted dictionary
reaches a connector are the keyword arguments of filter and of Q (When hands its own to Q),
which the two habits before it ask.
"""
import warnings

from _run import configure, create, habit, main, tables

configure()

REMARK = None


def _setup():
    """The entries and their remarks, made before any habit runs, with their warnings silenced."""
    global REMARK
    import datetime

    from django.db import models
    from journal.models import Entry

    tables()

    class Remark(models.Model):
        title = models.CharField(max_length=100)
        entry = models.ForeignKey(Entry, models.CASCADE, related_name="remarks")
        data = models.JSONField(null=True)

        class Meta:
            app_label = "journal"

    create(Remark)
    for day, title in ((5, "Dawn"), (6, "Dusk"), (7, "Noon")):
        entry = Entry.objects.create(title=title, published=datetime.date(2026, 1, day))
        Remark.objects.create(title=f"on {title}", entry=entry, data={"mood": "calm"})
    REMARK = Remark


with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    _setup()


def without_server(engine):
    """A connection of another backend made from settings alone; nothing opens it."""
    from django.db.utils import ConnectionHandler

    return ConnectionHandler({
        "default": {"ENGINE": "django.db.backends.dummy"},
        "server": {"ENGINE": engine, "NAME": "journal", "USER": "editor", "HOST": "db.journal.example"},
    })["server"]


def where(queryset, connection=None) -> tuple[str, tuple]:
    """The WHERE clause of a queryset's statement as its compiler writes it, placeholders kept,
    and the statement's parameters. U+FFFF, the delimiter of Oracle's literals, is written
    <U+FFFF>, so that it is told apart from the six characters \\uffff."""
    from django.db import connection as default

    sql, params = queryset.query.get_compiler(connection=connection or default).as_sql()
    return sql.split(" WHERE ", 1)[1].replace("￿", "<U+FFFF>"), tuple(params)


# Aliases

@habit("Entry.objects.annotate(**{\"total\\x01\": Count(\"remarks\")}): a control character in an alias")
def alias_control_character():
    from django.db.models import Count
    from journal.models import Entry

    return repr(list(Entry.objects.annotate(**{"total\x01": Count("remarks")}).values_list("title", flat=True)))


@habit("Entry.objects.annotate(**{\"total#\": Count(\"remarks\")}): a hash in an alias")
def alias_hash():
    from django.db.models import Count
    from journal.models import Entry

    return repr(list(Entry.objects.annotate(**{"total#": Count("remarks")}).values_list("title", flat=True)))


@habit("Remark.objects.values('data__mood\" FROM journal_remark --'): a crafted JSON key named in values")
def values_json_key():
    return repr(list(REMARK.objects.values('data__mood" FROM journal_remark --')))


@habit("Remark.objects.values(\"data__first name\"): a JSON key with a space named in values")
def values_json_key_with_space():
    return repr(list(REMARK.objects.values("data__first name")))


# The name of a filtered relation

@habit("Entry.objects.annotate(**{'on\" ON 1=1 --': FilteredRelation(\"remarks\")}): a crafted name for a filtered relation")
def filtered_relation_quote():
    from django.db.models import FilteredRelation
    from journal.models import Entry

    return repr(list(Entry.objects.annotate(**{'on" ON 1=1 --': FilteredRelation("remarks")}).values_list("title", flat=True)))


@habit("Entry.objects.annotate(**{\"remarks.title\": FilteredRelation(\"remarks\")}): a period in the name of a filtered relation")
def filtered_relation_period():
    from django.db.models import FilteredRelation
    from journal.models import Entry

    return repr(list(Entry.objects.annotate(**{"remarks.title": FilteredRelation("remarks")}).values_list("title", flat=True)))


@habit("Entry.objects.annotate(**{\"remark$\": FilteredRelation(\"remarks\")}).values(\"remark$__title\"), compiled for "
       "PostgreSQL: a dollar sign in the name of a filtered relation")
def filtered_relation_dollar_postgresql():
    from django.db.models import FilteredRelation
    from journal.models import Entry

    queryset = Entry.objects.annotate(**{"remark$": FilteredRelation("remarks")}).values("remark$__title")
    sql, params = queryset.query.get_compiler(connection=without_server("django.db.backends.postgresql")).as_sql()
    return sql


# The connector of a Q

@habit("Entry.objects.filter(**{\"title\": \"Dawn\", \"_connector\": \"OR\"})")
def filter_connector():
    from journal.models import Entry

    return repr(list(Entry.objects.filter(**{"title": "Dawn", "_connector": "OR"}).values_list("title", flat=True)))


@habit("Q(**{\"title\": \"Dawn\", \"_connector\": \"OR 1=1 OR\"})")
def q_connector():
    from django.db.models import Q

    return repr(Q(**{"title": "Dawn", "_connector": "OR 1=1 OR"}))


@habit("Entry.objects.filter(Q.create([(\"title\", \"Dawn\"), (\"title\", \"Noon\")], connector=\"OR 1=1 OR\")), by the "
       "undocumented Q.create: the WHERE clause")
def q_create_connector():
    from django.db.models import Q
    from journal.models import Entry

    return where(Entry.objects.filter(Q.create([("title", "Dawn"), ("title", "Noon")], connector="OR 1=1 OR")))[0]


@habit("Case(When(**{\"title\": \"Dawn\", \"_negated\": True}, then=Value(1)), default=Value(0)): the entries given 1")
def when_negated():
    from django.db.models import Case, Value, When
    from journal.models import Entry

    marked = Entry.objects.annotate(mark=Case(When(**{"title": "Dawn", "_negated": True}, then=Value(1)), default=Value(0)))
    return repr(sorted(marked.filter(mark=1).values_list("title", flat=True)))


# Values written into the statement on Oracle

@habit("Remark.objects.filter(HasKey(Value(\"') OR 1=1 --\", JSONField()), \"mood\")), compiled for Oracle: the "
       "WHERE clause and its parameter, a left-hand side given directly")
def oracle_has_key_lhs():
    from django.db.models import JSONField, Value
    from django.db.models.fields.json import HasKey

    queryset = REMARK.objects.filter(HasKey(Value("') OR 1=1 --", JSONField()), "mood"))
    clause, params = where(queryset, without_server("django.db.backends.oracle"))
    return f"{clause}, the parameter {', '.join(params)}"


@habit("Remark.objects.filter(data__has_key=\"mood\\uffff') OR 1=1 --\"), compiled for Oracle: the WHERE clause, "
       "U+FFFF written <U+FFFF>")
def oracle_has_key_delimiter():
    queryset = REMARK.objects.filter(data__has_key="mood￿') OR 1=1 --")
    clause, params = where(queryset, without_server("django.db.backends.oracle"))
    return clause


main()
