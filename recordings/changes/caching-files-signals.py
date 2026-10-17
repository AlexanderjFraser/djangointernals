"""The habits of the section "What changed in caching, files, signals, serialization and
pagination", release by release: the keys of cached pages and fragments, what DatabaseCache reads
and when it culls, whether a File is true, the storage's old open flags and settings, how a signal
runs its coroutine receivers and what reaches the sender when they fail, what the serializers
write and read, and the paginators. Run by recordings/changes.py under each release; _run.py says
how a habit is written.

Two habits stop or wait on purpose. The overwriting storage's second save is stopped at the
tenth time it asks for a name, since a release that opens with O_EXCL would ask for ever, and
its line says so. The synchronous receiver of asend gives the coroutine half a second, a margin
and not a measurement: a coroutine that waits for it to return cannot have run in any time.
Each signal habit runs its own event loop (asyncio.run) over a Signal of its own, and no line
depends on which of two receivers the loop happens to run first.
"""
import asyncio
import binascii
import datetime
import os
import tempfile
import threading

from _run import configure, create, habit, main

configure()


# The keys of cached pages and fragments.

@habit("make_template_fragment_key(\"sidebar\", [\"a:b\", \"c\"]) == make_template_fragment_key(\"sidebar\", [\"a\", \"b:c\"])")
def fragment_keys_of_two_lists():
    from django.core.cache.utils import make_template_fragment_key
    return repr(make_template_fragment_key("sidebar", ["a:b", "c"]) == make_template_fragment_key("sidebar", ["a", "b:c"]))


@habit("make_template_fragment_key(\"sidebar\"): the key of a fragment that varies on nothing")
def fragment_key_without_vary_on():
    from django.core.cache.utils import make_template_fragment_key
    return repr(make_template_fragment_key("sidebar"))


@habit("learn_cache_key(request, response), Vary: Accept-Encoding, Cookie: one key for \"EU\" in either header?")
def page_keys_of_two_requests():
    from django.http import HttpResponse
    from django.test import RequestFactory, override_settings
    from django.utils.cache import learn_cache_key

    def key(**headers):
        response = HttpResponse()
        response.headers["Vary"] = "Accept-Encoding, Cookie"
        return learn_cache_key(RequestFactory().get("/", **headers), response)

    with override_settings(ALLOWED_HOSTS=["testserver"]):
        return repr(key(HTTP_ACCEPT_ENCODING="EU") == key(HTTP_COOKIE="EU"))


# DatabaseCache.

def database_cache(table, options=None):
    """A DatabaseCache over a table of its own, made by createcachetable."""
    from django.core.cache.backends.db import DatabaseCache
    from django.core.management import call_command
    from django.test import override_settings

    backend = "django.core.cache.backends.db.DatabaseCache"
    with override_settings(CACHES={"default": {"BACKEND": backend, "LOCATION": table}}):
        call_command("createcachetable", verbosity=0)
    return DatabaseCache(table, {"OPTIONS": options or {}})


@habit("cache.get(\"harbour\") from DatabaseCache, a newline put into the row's Base64")
def database_cache_loose_base64():
    from django.db import connection

    cache = database_cache("journal_cache")
    cache.set("harbour", "Leith")
    with connection.cursor() as cursor:
        cursor.execute("UPDATE journal_cache SET value = substr(value, 1, 8) || char(10) || substr(value, 9)")
    try:
        return repr(cache.get("harbour"))
    except binascii.Error as error:  # its class is named Error: the module is given with it
        return f"binascii.Error: {error}"


@habit("DatabaseCache with \"MAX_ENTRIES\": 2 and \"CULL_PROBABILITY\": 0: the rows after five writes")
def database_cache_cull_probability_zero():
    from django.db import connection

    cache = database_cache("journal_cull", {"MAX_ENTRIES": 2, "CULL_PROBABILITY": 0})
    for number in range(5):
        cache.set(f"entry{number}", number)
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM journal_cull")
        return repr(cursor.fetchone()[0])


# Files and storage.

@habit("bool(File(BytesIO(b\"Monday\"))): a File without a name")
def file_without_name():
    from io import BytesIO

    from django.core.files import File
    return repr(bool(File(BytesIO(b"Monday"))))


@habit("bool(ContentFile(b\"Monday\")): a ContentFile without a name")
def content_file_without_name():
    from django.core.files.base import ContentFile
    return repr(bool(ContentFile(b"Monday")))


@habit("OS_OPEN_FLAGS without os.O_EXCL and get_available_name returning the name, on a FileSystemStorage subclass: storage.save(\"notes.txt\", ...) when notes.txt exists")
def os_open_flags():
    from django.core.files.base import ContentFile
    from django.core.files.storage import FileSystemStorage

    asked = []

    class AskedAgain(Exception):
        pass

    # The overwriting storage as it was written before allow_overwrite: the name kept, and the
    # file opened without O_EXCL. Where _save opens with O_EXCL all the same, it asks for another
    # name after each refusal and is given the same one, without end; the habit stops it at the
    # tenth asking and says so.
    class OverwriteStorage(FileSystemStorage):
        OS_OPEN_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)

        def get_available_name(self, name, max_length=None):
            asked.append(name)
            if len(asked) == 10:
                raise AskedAgain
            return name

    with tempfile.TemporaryDirectory() as directory:
        storage = OverwriteStorage(location=directory)
        storage.save("notes.txt", ContentFile(b"first"))
        asked.clear()
        try:
            storage.save("notes.txt", ContentFile(b"second"))
        except AskedAgain:
            return "save() does not return: os.open refuses notes.txt, get_available_name gives the same name again (stopped at the tenth asking)"
        with open(os.path.join(directory, "notes.txt"), "rb") as written:
            return f"notes.txt holds {written.read()!r}"


@habit("DEFAULT_FILE_STORAGE = \"django.core.files.storage.InMemoryStorage\": the class of storages[\"default\"]")
def default_file_storage():
    from django.core.files.storage import storages
    from django.test import override_settings

    with override_settings(DEFAULT_FILE_STORAGE="django.core.files.storage.InMemoryStorage"):
        return type(storages["default"]).__name__


# Signals.

@habit("await signal.asend(None), a receiver of each kind: does the coroutine one wait for the synchronous one to return?")
def asend_sync_and_coroutine_receivers():
    from django.dispatch import Signal

    signal = Signal()
    coroutine_ran = threading.Event()
    seen = []

    # The synchronous receiver, in its thread, gives the coroutine half a second to have run;
    # a coroutine that waits for it to return cannot have run by then, however long it is given.
    def synchronous(**kwargs):
        seen.append(coroutine_ran.wait(0.5))

    async def coroutine(**kwargs):
        coroutine_ran.set()

    signal.connect(synchronous)
    signal.connect(coroutine)
    asyncio.run(signal.asend(None))
    return "no, it has run before the synchronous one returns" if seen[0] else "yes, it runs after the synchronous one returns"


@habit("await signal.asend(None), one coroutine receiver raising ValueError, another waiting: the waiting one when the ValueError reaches the sender")
def asend_waiting_receiver_after_a_failure():
    from django.dispatch import Signal

    signal = Signal()
    fate = []

    async def failing(**kwargs):
        raise ValueError("no berth")

    async def send():
        go_on = asyncio.Event()

        async def waiting(**kwargs):
            try:
                await go_on.wait()
            except asyncio.CancelledError:
                fate.append("cancelled")
                raise
            fate.append("runs to its end")

        signal.connect(failing)
        signal.connect(waiting)
        try:
            await signal.asend(None)
        except ValueError:
            # What has become of the waiting receiver is read as the error arrives, before the
            # sender does anything that could decide it; it is released only afterwards, so
            # that a receiver still waiting ends by itself and not by asyncio.run's cancelling.
            when_raised = fate[0] if fate else "still waiting"
        go_on.set()
        for _ in range(3):
            await asyncio.sleep(0)
        return when_raised

    return asyncio.run(send())


@habit("signal.send(None), two coroutine receivers raising ValueError: what reaches the sender")
def send_two_failing_coroutine_receivers():
    from django.dispatch import Signal

    signal = Signal()

    # The same message from each: which of two errors gather() passes on is the one whose task
    # the event loop finishes first, not anything Django chooses.
    async def first(**kwargs):
        raise ValueError("no berth")

    async def second(**kwargs):
        raise ValueError("no berth")

    signal.connect(first)
    signal.connect(second)
    signal.send(None)


@habit("await signal.asend(None), two coroutine receivers each adding 1 to a ContextVar the sender set to 1: what the sender reads after")
def asend_context_variable():
    import contextvars

    from django.dispatch import Signal

    signal = Signal()
    count = contextvars.ContextVar("count")

    async def adding(**kwargs):
        count.set(count.get() + 1)

    async def again(**kwargs):
        count.set(count.get() + 1)

    async def send():
        count.set(1)
        await signal.asend(None)
        return count.get()

    signal.connect(adding)
    signal.connect(again)
    return repr(asyncio.run(send()))


# Serialization.

@habit("serialize(\"json\", []): no indent")
def json_serializer_end():
    from django.core.serializers import serialize
    return repr(serialize("json", []))


@habit("DjangoJSONEncoder().encode(datetime.datetime(2000, 1, 1, 0, 0, 0, 1)): one microsecond")
def json_encoder_milliseconds():
    from django.core.serializers.json import DjangoJSONEncoder
    return DjangoJSONEncoder().encode(datetime.datetime(2000, 1, 1, 0, 0, 0, 1))


MADE = {}


def opted_out():
    """A Wharf whose natural_key returns (), and a Lighter with a key to it, defined the first time
    a habit asks; neither has a table. Unsaved instances of each, the lighter's key the wharf."""
    from django.db import models

    if MADE:
        return MADE["Wharf"](pk=1, name="Leith"), MADE["Lighter"]

    class Wharf(models.Model):
        name = models.CharField(max_length=20)

        class Meta:
            app_label = "journal"
            managed = False

        def natural_key(self):
            return ()

    class Lighter(models.Model):
        wharf = models.ForeignKey(Wharf, on_delete=models.CASCADE)

        class Meta:
            app_label = "journal"
            managed = False

    MADE.update(Wharf=Wharf, Lighter=Lighter)
    return Wharf(pk=1, name="Leith"), Lighter


@habit("serialize(\"python\", [wharf], use_natural_primary_keys=True), Wharf.natural_key() returning ()")
def natural_primary_key_opted_out():
    from django.core.serializers import serialize

    wharf, _ = opted_out()
    return repr(serialize("python", [wharf], use_natural_primary_keys=True))


@habit("serialize(\"python\", [lighter], use_natural_foreign_keys=True): its key to a Wharf whose natural_key() returns ()")
def natural_foreign_key_opted_out():
    from django.core.serializers import serialize

    wharf, Lighter = opted_out()
    lighter = Lighter(pk=1, wharf=wharf)
    return repr(serialize("python", [lighter], use_natural_foreign_keys=True)[0]["fields"]["wharf"])


@habit("deserialize(\"xml\", ...): an Entry whose title is written <b>Valletta</b>")
def xml_nested_element():
    from django.core.serializers import deserialize

    text = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<django-objects version="1.0"><object model="journal.entry" pk="1">'
        '<field name="title" type="CharField"><b>Valletta</b></field>'
        '<field name="published" type="DateField">2026-09-26</field>'
        "</object></django-objects>"
    )
    return repr(next(deserialize("xml", text)).object.title)


@habit("DeserializedObject.save(), a Hold with a crate: the raw that m2m_changed's receivers are given")
def deserialized_many_to_many_raw():
    from django.core.serializers import deserialize
    from django.db import models
    from django.db.models.signals import m2m_changed

    class Crate(models.Model):
        name = models.CharField(max_length=20)

        class Meta:
            app_label = "journal"

    class Hold(models.Model):
        crates = models.ManyToManyField(Crate)

        class Meta:
            app_label = "journal"

    create(Crate, Hold)
    received = []

    def receiver(**kwargs):
        received.append(kwargs.get("raw", "none given"))

    data = [
        {"model": "journal.crate", "pk": 1, "fields": {"name": "tea"}},
        {"model": "journal.hold", "pk": 1, "fields": {"crates": [1]}},
    ]
    m2m_changed.connect(receiver, sender=Hold.crates.through)
    try:
        for deserialized in deserialize("python", data):
            deserialized.save()
    finally:
        m2m_changed.disconnect(receiver, sender=Hold.crates.through)
    return f"raw: {received[0]!r}" if received[0] != "none given" else "no raw argument"


# Pagination.

@habit("Paginator(range(10), 2, orphans=2).num_pages: orphans not fewer than the page")
def paginator_orphans():
    from django.core.paginator import Paginator
    return repr(Paginator(range(10), 2, orphans=2).num_pages)


@habit("len(await AsyncPaginator(range(10), 2).apage(1)): before aget_object_list")
def async_page_length():
    from django.core.paginator import AsyncPaginator

    page = asyncio.run(AsyncPaginator(range(10), 2).apage(1))
    return repr(len(page))


main()
