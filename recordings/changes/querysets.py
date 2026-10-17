"""The habits of the section "What changed in querysets", release by release: what reading a
related object costs under the fetch modes of 6.1, and what the releases before do with their
names; the deprecations beside them; the orderings of first() and of combined querysets (6.1);
values_list(flat=True) and in_bulk() after values() (6.0, 6.1); aiterator() after
prefetch_related() (6.2); prefetching's old methods removed and raw() over a composite key (6.0);
a related filter by an instance never saved (5.0).
Run by recordings/changes.py under each release; _run.py says how a habit is written.

The rows: the journal's two entries, Spring and Autumn, ids 1 and 2. The models most habits
share are defined here, in the application journal, with their rows:
four reporters, two to each of two papers, each paper of its own publisher; two letters,
ordered by title; a notice, made by a from_db() of its model's own. They are defined at module
level because a model defined in a function carries the function in its qualified name, which
FETCH_RAISE's message prints.
"""
import datetime

from _run import configure, create, habit, main, tables

configure()

from django.db import models  # noqa: E402 - after configure(), as every model import is


class Publisher(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "journal"


class Paper(models.Model):
    name = models.CharField(max_length=100)
    publisher = models.ForeignKey(Publisher, models.CASCADE)

    class Meta:
        app_label = "journal"


class Reporter(models.Model):
    name = models.CharField(max_length=100)
    paper = models.ForeignKey(Paper, models.CASCADE)

    class Meta:
        app_label = "journal"


class Letter(models.Model):
    title = models.CharField(max_length=100)
    pages = models.IntegerField()

    class Meta:
        app_label = "journal"
        ordering = ["title"]


class Notice(models.Model):
    title = models.CharField(max_length=100)

    class Meta:
        app_label = "journal"

    @classmethod
    def from_db(cls, db, field_names, values):  # written before 6.1: no fetch_mode
        return super().from_db(db, field_names, values)


tables()


def rows():
    from journal.models import Entry

    Entry.objects.create(title="Spring", published=datetime.date(2026, 3, 1))
    Entry.objects.create(title="Autumn", published=datetime.date(2026, 9, 1))
    harbour = Publisher.objects.create(name="Harbour Press")
    northern = Publisher.objects.create(name="Northern Press")
    gazette = Paper.objects.create(name="Gazette", publisher=harbour)
    courier = Paper.objects.create(name="Courier", publisher=northern)
    for name, paper in [("Ada", gazette), ("Ben", gazette), ("Cy", courier), ("Di", courier)]:
        Reporter.objects.create(name=name, paper=paper)
    Letter.objects.create(title="Reply", pages=3)
    Letter.objects.create(title="Answer", pages=12)
    Notice.objects.create(title="Closed on Monday")


rows()


def statements(function) -> str:
    """How many statements a call runs, as the line of a habit."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as captured:
        function()
    return f"{len(captured)} statements"


# Fetch modes (6.1)

@habit("[r.paper.name for r in Reporter.objects.all()]: the statements it runs, four reporters on two papers")
def related_object_read_on_demand():
    return statements(lambda: [r.paper.name for r in Reporter.objects.all()])


@habit("[r.paper.name for r in Reporter.objects.fetch_mode(FETCH_PEERS)]: the statements it runs")
def fetch_peers():
    from django.db.models import FETCH_PEERS

    return statements(lambda: [r.paper.name for r in Reporter.objects.fetch_mode(FETCH_PEERS)])


@habit("Reporter.objects.fetch_mode(FETCH_RAISE).first().paper")
def fetch_raise():
    from django.db.models import FETCH_RAISE

    return repr(Reporter.objects.fetch_mode(FETCH_RAISE).first().paper)


@habit("[r.paper.publisher.name for r in Reporter.objects.select_related(\"paper\").fetch_mode(FETCH_PEERS)]: "
       "the statements it runs")
def fetch_peers_after_select_related():
    from django.db.models import FETCH_PEERS

    queryset = Reporter.objects.select_related("paper").fetch_mode(FETCH_PEERS)
    return statements(lambda: [r.paper.publisher.name for r in queryset])


@habit("[n.title for n in Notice.objects.all()]: a model whose own from_db() takes no fetch_mode")
def from_db_without_fetch_mode():
    return repr([n.title for n in Notice.objects.all()])


@habit("Entry.objects.select_related(), with no field named")
def select_related_with_no_arguments():
    from journal.models import Entry
    return str(Entry.objects.select_related().query)


# Orderings (6.1)

@habit("Entry.objects.order_by().first(): the statement it runs")
def first_after_ordering_cleared():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    from journal.models import Entry

    with CaptureQueriesContext(connection) as captured:
        Entry.objects.order_by().first()
    return captured[0]["sql"]


@habit("Entry.objects.order_by(\"title\").totally_ordered")
def totally_ordered():
    from journal.models import Entry

    return repr(Entry.objects.order_by("title").totally_ordered)


@habit("titles.union(titles): its statement, with titles = Letter.objects.order_by().values(\"title\") "
       "and Letter ordered by title")
def union_statement():
    titles = Letter.objects.order_by().values("title")
    return str(titles.union(titles).query)


@habit("list(pages.union(pages)), with pages = Letter.objects.order_by().values(\"pages\") and Letter ordered by title")
def union_of_a_model_with_an_ordering():
    pages = Letter.objects.order_by().values("pages")
    return repr(list(pages.union(pages)))


@habit("list(pages.union(pages).order_by()), with the same pages")
def union_with_its_ordering_cleared():
    pages = Letter.objects.order_by().values("pages")
    return repr(list(pages.union(pages).order_by()))


# values(), values_list() and in_bulk()

@habit("Entry.objects.values_list(flat=True), with no field named")
def values_list_flat_with_no_field():
    from journal.models import Entry
    return str(Entry.objects.values_list(flat=True).query)


@habit("list(Entry.objects.values_list(flat=True)), with no field named")
def values_list_flat_with_no_field_values():
    from journal.models import Entry

    return repr(list(Entry.objects.values_list(flat=True)))


@habit("Entry.objects.values(\"title\").in_bulk()")
def in_bulk_after_values():
    from journal.models import Entry

    return repr(Entry.objects.values("title").in_bulk())


# Iterating and prefetching

@habit("[r.paper.name async for r in Reporter.objects.prefetch_related(\"paper\").aiterator()]")
def aiterator_after_prefetch_related():
    from asgiref.sync import async_to_sync

    async def names():
        return [r.paper.name async for r in Reporter.objects.prefetch_related("paper").aiterator()]

    return repr(async_to_sync(names)())


@habit("Prefetch(\"paper\").get_current_queryset(0)")
def prefetch_get_current_queryset():
    from django.db.models import Prefetch

    return repr(Prefetch("paper").get_current_queryset(0))


@habit("prefetch_related_objects(clippings, \"earlier\"): a descriptor that defines get_prefetch_queryset() alone")
def prefetch_through_get_prefetch_queryset():
    from django.db.models import prefetch_related_objects
    from journal.models import Entry

    called = []

    class Earlier:
        """A descriptor of a library written before 5.0, for an object prefetched by hand."""

        def __get__(self, instance, owner=None):
            return self if instance is None else instance._state.fields_cache.get("earlier")

        def is_cached(self, instance):
            return "earlier" in instance._state.fields_cache

        def get_prefetch_queryset(self, instances, queryset=None):
            called.append(len(instances))
            return Entry.objects.none(), (lambda entry: entry.pk), (lambda clipping: clipping.pk), True, "earlier", False

    class Clipping(models.Model):
        title = models.CharField(max_length=100)
        earlier = Earlier()

        class Meta:
            app_label = "journal"

    prefetch_related_objects([Clipping(id=1, title="Spring"), Clipping(id=2, title="Autumn")], "earlier")
    return f"get_prefetch_queryset() called for {called[0]} instances" if called else "get_prefetch_queryset() not called"


@habit("[e.pk for e in Edition.objects.raw('SELECT * FROM journal_edition')]: a composite primary key")
def raw_with_a_composite_primary_key():
    class Edition(models.Model):
        pk = models.CompositePrimaryKey("volume", "number")
        volume = models.IntegerField()
        number = models.IntegerField()

        class Meta:
            app_label = "journal"

    create(Edition)
    Edition.objects.create(volume=1, number=2)
    return repr([e.pk for e in Edition.objects.raw("SELECT * FROM journal_edition")])


@habit("Reporter.objects.filter(paper=Paper(id=1)).count(): an instance given a key and never saved")
def filter_by_an_instance_never_saved():
    return repr(Reporter.objects.filter(paper=Paper(id=1)).count())


main()
