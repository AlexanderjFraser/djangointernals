"""The habits of the section "What changed in the admin", release by release: what
`ModelAdmin.get_actions` gives for an action, and what an override of it written before 6.1 is
offered on the change list and the change form; whose override of the deletion log is called, and
how many `post_save` signals a log of deletions sends; a change list's filter checked by an old
`lookup_allowed`, the joins a change list's query makes for a foreign key, for one that may be null
and for a path across a relation, its cell for a boolean across a relation, and
`list_select_related = True`; and what a staff user without permissions gets from the history page
and from "View on site", where the login page sends a user already signed in, and where
`NotRegistered` is defined. The habits run over an `AdminSite` served at /admin/ with journal's
Entry and a bulletin registered, two entries, a superuser and a staff user with no permissions, and
three models made for the change list's relations (a note, its author and its notebook), all made
before the first habit runs. A view is called as its URL resolves, with no middleware and no
handler around it: a request carries the host journal.example (valid by an ALLOWED_HOSTS the habit
overrides, and the domain of "View on site"'s redirect) and a message store, and an exception the
view raises is shown as raised, where the handler would answer PermissionDenied with a 403. The
boolean cell is drawn with STATIC_URL "/static/".
Run by recordings/changes.py under each release; _run.py says how a habit is written.
"""
import sys
import types

from _run import BASE, configure, create, habit, main, tables

configure(INSTALLED_APPS=[*BASE["INSTALLED_APPS"], "django.contrib.admin"], ROOT_URLCONF="journal_admin")

STATE = {}


def journal_admin():
    """The site and its rows, made once, before the habits run, so that nothing the setup warns
    of stands on a habit's line: an AdminSite with plain ModelAdmins of Entry and of Bulletin
    (a model whose get_absolute_url is /bulletins/<pk>/), served at /admin/ by the URLconf
    journal_admin; two entries; a superuser, editor, and a staff user with no permissions, reader;
    and Note, with a foreign key to an Author (a name and an active flag), one to a Notebook and a
    nullable one, editor, to an Author again, and one note."""
    import datetime

    from django.contrib import admin
    from django.contrib.auth.models import User
    from django.db import models
    from django.urls import path
    from journal.models import Entry

    tables()

    class Bulletin(models.Model):
        title = models.CharField(max_length=100)

        class Meta:
            app_label = "journal"

        def get_absolute_url(self):
            return f"/bulletins/{self.pk}/"

    class Author(models.Model):
        name = models.CharField(max_length=50)
        active = models.BooleanField(default=True)

        class Meta:
            app_label = "journal"

    class Notebook(models.Model):
        name = models.CharField(max_length=50)

        class Meta:
            app_label = "journal"

    class Note(models.Model):
        title = models.CharField(max_length=100)
        author = models.ForeignKey(Author, models.CASCADE)
        notebook = models.ForeignKey(Notebook, models.CASCADE)
        editor = models.ForeignKey(Author, models.SET_NULL, null=True, related_name="edited_notes")

        class Meta:
            app_label = "journal"

    create(Bulletin, Author, Notebook, Note)

    site = admin.AdminSite()
    site.register(Entry)
    site.register(Bulletin)
    urls = types.ModuleType("journal_admin")
    urls.urlpatterns = [path("admin/", site.urls)]
    sys.modules["journal_admin"] = urls

    Note.objects.create(
        title="Rain",
        author=Author.objects.create(name="Ada"),
        notebook=Notebook.objects.create(name="Autumn"),
    )
    STATE.update(
        site=site,
        entry_admin=site._registry[Entry],
        monday=Entry.objects.create(title="Monday", published=datetime.date(2026, 9, 21)),
        tuesday=Entry.objects.create(title="Tuesday", published=datetime.date(2026, 9, 22)),
        bulletin=Bulletin.objects.create(title="Closed on Monday"),
        Bulletin=Bulletin,
        Note=Note,
        editor=User.objects.create(username="editor", is_staff=True, is_superuser=True),
        reader=User.objects.create(username="reader", is_staff=True),
    )


journal_admin()

from django.contrib import admin as django_admin  # noqa: E402 - after configure; every release recorded has it


def request(path, user):
    """A GET of path by user, with a message store, as the admin's middleware would give it."""
    from django.contrib.messages.storage.cookie import CookieStorage
    from django.test import RequestFactory

    made = RequestFactory().get(path, HTTP_HOST="journal.example")
    made.user = user
    made._messages = CookieStorage(made)
    return made


def served(path, user):
    """What the admin's view for path answers a GET by user: the status, and where a redirect goes."""
    from django.test.utils import override_settings
    from django.urls import resolve

    with override_settings(ALLOWED_HOSTS=["journal.example"]):
        match = resolve(path.split("?")[0])
        response = match.func(request(path, user), *match.args, **match.kwargs)
    if response.status_code in (301, 302):
        return f"{response.status_code} to {response['Location']}"
    return str(response.status_code)


def editing():
    return request("/admin/journal/entry/", STATE["editor"])


def archive():
    """An action offered on the change list and on the change form, with a description for each."""
    from django.contrib import admin
    from django.contrib.admin import ActionLocation

    @admin.action(
        description="Archive this entry",
        description_plural="Archive the selected entries",
        location=[ActionLocation.CHANGE_LIST, ActionLocation.CHANGE_FORM],
    )
    def archive(modeladmin, request, queryset):
        pass

    return archive


def old_actions_admin(actions=()):
    """A ModelAdmin of Entry whose get_actions, written before 6.1, takes no action_location."""
    from django.contrib import admin
    from journal.models import Entry

    class OldActionsEntryAdmin(admin.ModelAdmin):
        def get_actions(self, request):
            return super().get_actions(request)

    OldActionsEntryAdmin.actions = list(actions)
    return OldActionsEntryAdmin(Entry, STATE["site"])


@habit('entry_admin.get_actions(request)["delete_selected"]: the class of the value')
def action_value_class():
    return type(STATE["entry_admin"].get_actions(editing())["delete_selected"]).__name__


@habit('func, name, description = entry_admin.get_actions(request)["delete_selected"]')
def action_unpacked():
    func, name, description = STATE["entry_admin"].get_actions(editing())["delete_selected"]
    return repr(name)


@habit("old_admin.get_action_choices(request, default_choices=[]), get_actions(self, request) overridden: "
       "the actions offered")
def old_get_actions_on_the_change_list():
    choices = old_actions_admin().get_action_choices(editing(), default_choices=[])
    return repr([name for name, description in choices])


@habit("entry_admin.get_action_choices(request, default_choices=[], action_location=ActionLocation.CHANGE_FORM): "
       "an archive action declared for both locations")
def change_form_choices():
    from django.contrib import admin
    from django.contrib.admin import ActionLocation
    from journal.models import Entry

    class ArchivingEntryAdmin(admin.ModelAdmin):
        actions = [archive()]

    model_admin = ArchivingEntryAdmin(Entry, STATE["site"])
    return repr(model_admin.get_action_choices(
        editing(), default_choices=[], action_location=ActionLocation.CHANGE_FORM
    ))


@habit("old_admin.get_action_choices(request, default_choices=[], action_location=ActionLocation.CHANGE_FORM), "
       "get_actions(self, request) overridden: an archive action declared for both locations")
def old_get_actions_on_the_change_form():
    from django.contrib.admin import ActionLocation

    model_admin = old_actions_admin([archive()])
    return repr(model_admin.get_action_choices(
        editing(), default_choices=[], action_location=ActionLocation.CHANGE_FORM
    ))


def log_entries_saved(objects):
    """How many post_save signals for LogEntry entry_admin.log_deletions sends for these objects."""
    from django.contrib.admin.models import LogEntry
    from django.db.models.signals import post_save

    heard = []

    def receiver(sender, instance, **kwargs):
        heard.append(instance)

    post_save.connect(receiver, sender=LogEntry, weak=False)
    try:
        STATE["entry_admin"].log_deletions(editing(), objects)
    finally:
        post_save.disconnect(receiver, sender=LogEntry)
    return f"{len(heard)} post_save sent"


@habit("entry_admin.log_deletions(request, Entry.objects.all()), two entries: the post_save signals for LogEntry")
def log_of_two_deletions():
    from journal.models import Entry
    return log_entries_saved(Entry.objects.all())


@habit("entry_admin.log_deletions(request, [entry]): the post_save signals for LogEntry")
def log_of_one_deletion():
    return log_entries_saved([STATE["monday"]])


@habit("log_deletions(request, Entry.objects.all()), in a ModelAdmin that overrides log_deletion: "
       "the entries the override is called for")
def old_log_deletion():
    from django.contrib import admin
    from journal.models import Entry

    called = []

    class OldLogEntryAdmin(admin.ModelAdmin):
        def log_deletion(self, request, obj, object_repr):
            called.append(object_repr)

    OldLogEntryAdmin(Entry, STATE["site"]).log_deletions(editing(), Entry.objects.all())
    return repr(sorted(called))


class EntryAdmin(django_admin.ModelAdmin):
    """Entry's ModelAdmin as a project wrote it before 5.0, its lookup_allowed taking no request;
    defined at the module's top level, as a project's admin module defines it, so that an error
    names it as it would name a project's."""

    def lookup_allowed(self, lookup, value):
        return True


@habit('The change list for "?title=Monday", in a ModelAdmin whose lookup_allowed(self, lookup, value) '
       "takes no request: the entries listed")
def old_lookup_allowed():
    from journal.models import Entry

    model_admin = EntryAdmin(Entry, STATE["site"])
    changelist = model_admin.get_changelist_instance(request("/admin/journal/entry/?title=Monday", STATE["editor"]))
    return repr([entry.title for entry in changelist.result_list])


def joined(list_display):
    """The joins of the change list's query of Note, with this list_display: each join's kind, the
    table it joins and the column of Note it joins on (author and editor both join journal_author),
    in the query's order."""
    import re

    from django.contrib import admin

    NoteAdmin = type("NoteAdmin", (admin.ModelAdmin,), {"list_display": list_display})
    model_admin = NoteAdmin(STATE["Note"], STATE["site"])
    changelist = model_admin.get_changelist_instance(request("/admin/journal/note/", STATE["editor"]))
    joins = re.findall(r'((?:INNER|LEFT OUTER) JOIN "\w+")(?: "\w+")? ON \("journal_note"\."(\w+)"',
                       str(changelist.queryset.query))
    return ", ".join(f"{join} ON {column}" for join, column in joins) if joins else "no join"


@habit('list_display = ("title", "author"), on a Note with foreign keys author and notebook, and editor, '
       "which may be null: the change list's joins")
def joins_for_a_foreign_key():
    return joined(("title", "author"))


@habit('list_display = ("title", "editor"), editor the foreign key that may be null: the change list\'s joins')
def joins_for_a_nullable_foreign_key():
    return joined(("title", "editor"))


@habit('list_display = ("title", "author__name"): the change list\'s joins')
def joins_for_a_path():
    return joined(("title", "author__name"))


@habit("class NoteAdmin(admin.ModelAdmin): list_select_related = True")
def list_select_related_true():
    from django.contrib import admin

    class NoteAdmin(admin.ModelAdmin):
        list_select_related = True

    return "the class is made"


@habit('list_display = ("title", "author__active"): the cell drawn for a note whose author is active')
def boolean_across_a_relation():
    from django.contrib import admin
    from django.contrib.admin.templatetags.admin_list import items_for_result
    from django.test.utils import override_settings

    NoteAdmin = type("NoteAdmin", (admin.ModelAdmin,), {
        "list_display": ("title", "author__active"), "list_display_links": None, "actions": None,
    })
    model_admin = NoteAdmin(STATE["Note"], STATE["site"])
    with override_settings(STATIC_URL="/static/"):
        changelist = model_admin.get_changelist_instance(request("/admin/journal/note/", STATE["editor"]))
        cells = list(items_for_result(changelist, changelist.result_list[0], None))
    return next(cell for cell in cells if "field-author__active" in cell)


@habit("GET /admin/journal/entry/999/history/ by a staff user without permissions: entry 999 does not exist")
def history_of_a_missing_entry():
    return served("/admin/journal/entry/999/history/", STATE["reader"])


@habit("GET /admin/journal/entry/1/history/ by a staff user without permissions: entry 1 exists")
def history_of_an_entry():
    assert STATE["monday"].pk == 1
    return served("/admin/journal/entry/1/history/", STATE["reader"])


@habit('"View on site" for a bulletin whose get_absolute_url is "/bulletins/1/", followed by a staff user '
       "without permissions")
def view_on_site_without_permission():
    from django.contrib.contenttypes.models import ContentType

    assert STATE["bulletin"].get_absolute_url() == "/bulletins/1/"
    content_type = ContentType.objects.get_for_model(STATE["Bulletin"])
    return served(f"/admin/r/{content_type.pk}/1/", STATE["reader"])


@habit("GET /admin/login/?next=/admin/journal/entry/ by a staff user already signed in")
def login_when_signed_in():
    return served("/admin/login/?next=/admin/journal/entry/", STATE["editor"])


@habit("from django.contrib.admin.sites import NotRegistered: the module that defines the class")
def not_registered_from_sites():
    from django.contrib.admin.sites import NotRegistered
    return NotRegistered.__module__


main()
