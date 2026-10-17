"""The habits of the section "What changed in models and fields", release by release: what a save
reads back from the database, a delete left to the database, unsaved instances compared, the
checks a model is given, choices, the exception of an update that matches no row, the
constraints, and the smaller changes to saving and to the field classes. Each habit asks what an
older release did with code a reader of it would write. The database is SQLite in memory, as
_run.py configures it: the statements the delete habits show are SQLite's, and what a save reads
back is what a backend with RETURNING reads (MySQL's is not run). Run by recordings/changes.py
under each release; _run.py says how a habit is written.
"""
import datetime

from _run import configure, create, habit, main, tables

configure()

PUBLISHED = datetime.date(2026, 9, 26)
MADE = {}


def model(name):
    """A model several habits share, defined the first time one asks. A model whose habits need
    no rows is unmanaged, so that the tables() of a later habit does not make its table."""
    if name not in MADE:
        from django.db import models
        from django.db.models import F

        if name == "Square":
            class Square(models.Model):
                side = models.IntegerField()
                area = models.GeneratedField(
                    expression=F("side") * F("side"), output_field=models.IntegerField(), db_persist=True
                )

                class Meta:
                    app_label = "journal"

            create(Square)
            MADE[name] = Square
        elif name == "Berth":
            class Berth(models.Model):
                pk = models.CompositePrimaryKey("quay", "number")
                quay = models.CharField(max_length=20)
                number = models.IntegerField()

                class Meta:
                    app_label = "journal"
                    managed = False

            MADE[name] = Berth
        elif name == "Ticket":
            class Ticket(models.Model):
                number = models.IntegerField(primary_key=True, db_default=1)

                class Meta:
                    app_label = "journal"
                    managed = False

            MADE[name] = Ticket
    return MADE[name]


def check_ids(messages):
    return ", ".join(sorted(message.id for message in messages)) or "no messages"


# What a save reads back from the database.

@habit("Square.objects.create(side=3).area: a generated field, after the insert")
def generated_field_after_insert():
    Square = model("Square")
    return repr(Square.objects.create(side=3).area)


@habit("square.side = 4; square.save(); square.area: a generated field, after an update")
def generated_field_after_update():
    Square = model("Square")
    square = Square.objects.create(side=3)
    square.side = 4
    square.save()
    return repr(square.area)


@habit("tally.count = F(\"count\") + 1; tally.save(); tally.count: a field assigned an expression, after the save")
def expression_after_save():
    from django.db import models
    from django.db.models import F

    class Tally(models.Model):
        count = models.IntegerField(default=0)

        class Meta:
            app_label = "journal"

    create(Tally)
    tally = Tally.objects.create()
    tally.count = F("count") + 1
    tally.save()
    return repr(tally.count)


@habit("Log(line=\"moored\").save(): the add of each call of the field's pre_save, on an insert")
def pre_save_calls():
    from django.db import models

    calls = []

    class CountingField(models.CharField):
        def pre_save(self, model_instance, add):
            calls.append(add)
            return super().pre_save(model_instance, add)

    class Log(models.Model):
        line = CountingField(max_length=20)

        class Meta:
            app_label = "journal"

    create(Log)
    Log(line="moored").save()
    return repr(calls)


# A delete left to the database.

def deleted(parent, child, on_delete):
    """Delete a parent with one child whose key to it has this on_delete, while a receiver of
    post_delete listens for the child, as a project's own code may: the statements sent."""
    from django.db import connection, models
    from django.db.models.signals import post_delete
    from django.test.utils import CaptureQueriesContext

    Parent = type(parent, (models.Model,), {
        "__module__": __name__,
        "name": models.CharField(max_length=20),
        "Meta": type("Meta", (), {"app_label": "journal"}),
    })
    Child = type(child, (models.Model,), {
        "__module__": __name__,
        parent.lower(): models.ForeignKey(Parent, on_delete=on_delete),
        "Meta": type("Meta", (), {"app_label": "journal"}),
    })
    create(Parent, Child)
    row = Parent.objects.create(name="Leith")
    Child.objects.create(**{parent.lower(): row})

    def receiver(sender, instance, **kwargs):
        pass

    post_delete.connect(receiver, sender=Child)
    try:
        with CaptureQueriesContext(connection) as queries:
            row.delete()
    finally:
        post_delete.disconnect(receiver, sender=Child)
    return "\n".join(query["sql"] for query in queries.captured_queries)


@habit("harbour.delete(), a Mooring's key to it on_delete=DB_CASCADE, post_delete heard on Mooring: the statements sent")
def delete_with_db_cascade():
    from django.db.models import DB_CASCADE
    return deleted("Harbour", "Mooring", DB_CASCADE)


@habit("dock.delete(), a Pontoon's key to it on_delete=DB_CASCADE: what it returns")
def delete_with_db_cascade_returns():
    from django.db import models
    from django.db.models import DB_CASCADE

    class Dock(models.Model):
        name = models.CharField(max_length=20)

        class Meta:
            app_label = "journal"

    class Pontoon(models.Model):
        dock = models.ForeignKey(Dock, on_delete=DB_CASCADE)

        class Meta:
            app_label = "journal"

    create(Dock, Pontoon)
    dock = Dock.objects.create(name="Leith")
    Pontoon.objects.create(dock=dock)
    return repr(dock.delete())


@habit("port.delete(), a Slip's key to it on_delete=CASCADE, post_delete heard on Slip: the statements sent")
def delete_with_cascade():
    from django.db.models import CASCADE
    return deleted("Port", "Slip", CASCADE)


# Keys: a composite key, a key the database supplies, and what an unsaved instance equals.

@habit("Berth(quay=\"North\") == Berth(quay=\"North\"): unsaved, a part of the composite key unset")
def composite_key_part_unset_equal():
    Berth = model("Berth")
    return repr(Berth(quay="North") == Berth(quay="North"))


@habit("Berth(quay=\"North\", number=1) == Berth(quay=\"North\", number=1): unsaved, the composite key whole")
def composite_key_whole_equal():
    Berth = model("Berth")
    return repr(Berth(quay="North", number=1) == Berth(quay="North", number=1))


@habit("Ticket()._is_pk_set(): unsaved, the key one the database supplies (db_default=1)")
def database_default_key_is_set():
    Ticket = model("Ticket")
    return repr(Ticket()._is_pk_set())


@habit("Ticket() == Ticket(): unsaved, the key one the database supplies (db_default=1)")
def database_default_key_equal():
    Ticket = model("Ticket")
    return repr(Ticket() == Ticket())


@habit("Index(fields=[\"quay\"]), quay a ForeignObject of two from_fields: the model's checks")
def index_on_foreign_object_of_two_fields():
    from django.db import models

    class Quay(models.Model):
        id = models.AutoField(primary_key=True)
        harbour = models.CharField(max_length=20)
        number = models.IntegerField()

        class Meta:
            app_label = "journal"
            managed = False
            unique_together = [("harbour", "number")]

    class Hull(models.Model):
        id = models.AutoField(primary_key=True)
        harbour = models.CharField(max_length=20)
        number = models.IntegerField()
        quay = models.ForeignObject(
            Quay, on_delete=models.CASCADE, from_fields=["harbour", "number"], to_fields=["harbour", "number"]
        )

        class Meta:
            app_label = "journal"
            managed = False
            indexes = [models.Index(fields=["quay"], name="hull_quay")]

    return check_ids(Hull.check(databases=["default"]))


@habit("Entry.check(): the checks of a model given its automatic key by default")
def automatic_key_check():
    from journal.models import Entry
    return check_ids(Entry.check())


# Choices.

@habit("from django.db.models.enums import ChoicesMeta")
def choices_meta():
    from django.db.models.enums import ChoicesMeta
    return ChoicesMeta.__name__


@habit("models.CharField(choices=[(\"gale\", \"Gale\")]).get_choices(): the blank choice put first")
def blank_choice():
    from django.db import models
    value, label = list(models.CharField(choices=[("gale", "Gale")]).get_choices())[0]
    return repr((value, str(label)))


# An update that matches no row.

@habit("entry.save(force_update=True), no row with its key: what except DatabaseError catches")
def forced_update_of_no_row():
    from django.db import DatabaseError
    from journal.models import Entry

    tables()
    entry = Entry(pk=999, title="Leith", published=PUBLISHED)
    try:
        entry.save(force_update=True)
    except DatabaseError as error:
        return f"{type(error).__qualname__}: {error}"
    return "nothing raised"


# Constraints.

@habit("CheckConstraint(check=Q(title__gt=\"\"), name=\"titled\").condition")
def check_constraint_check_keyword():
    from django.db.models import CheckConstraint, Q
    return repr(CheckConstraint(check=Q(title__gt=""), name="titled").condition)


@habit("CheckConstraint(condition=Q(title__gt=\"\"), name=\"titled\").check: what the name check is")
def check_constraint_check_name():
    from django.db.models import CheckConstraint, Q
    return repr(CheckConstraint(condition=Q(title__gt=""), name="titled").check)


@habit("BaseConstraint(\"titled\", \"Every entry needs a title.\").name: the name and message by position")
def base_constraint_positional():
    from django.db.models import BaseConstraint
    return repr(BaseConstraint("titled", "Every entry needs a title.").name)


@habit("UniqueConstraint(fields=[\"name\"], ..., violation_error_code=\"taken\"), no message: the code for a second row")
def unique_constraint_code_without_message():
    from django.core.exceptions import ValidationError
    from django.db import models

    constraint = models.UniqueConstraint(fields=["name"], name="one_callsign", violation_error_code="taken")

    class Callsign(models.Model):
        name = models.CharField(max_length=20)

        class Meta:
            app_label = "journal"
            constraints = [constraint]

    create(Callsign)
    Callsign.objects.create(name="Petrel")
    try:
        constraint.validate(Callsign, Callsign(name="Petrel"))
    except ValidationError as error:
        return repr(error.code)
    return "no error"


# Smaller changes to saving and to the field classes.

@habit("entry.save(True): force_insert given by position")
def save_positional():
    from journal.models import Entry

    tables()
    Entry(title="Leith", published=PUBLISHED).save(True)
    return "saved"


@habit("models.DecimalField(), neither size given: its checks on SQLite")
def decimal_field_without_sizes():
    from django.db import models

    class Price(models.Model):
        amount = models.DecimalField()

        class Meta:
            app_label = "journal"
            managed = False

    return check_ids(Price._meta.get_field("amount").check(databases=["default"]))


@habit("models.BinaryField().to_python(\"am91*cm5hbA==\"): Base64 with a character outside its alphabet")
def binary_field_loose_base64():
    from django.db import models
    return repr(bytes(models.BinaryField().to_python("am91*cm5hbA==")))


@habit("models.GenericIPAddressField().get_prep_value(\"2001:db8::zz\"): not an address, as a save or a filter prepares it")
def generic_ip_address_invalid():
    from django.db import models
    return repr(models.GenericIPAddressField().get_prep_value("2001:db8::zz"))


@habit("models.GenericIPAddressField().get_prep_value(\" 2001:DB8::1 \"): an address with spaces around it")
def generic_ip_address_spaces():
    from django.db import models
    return repr(models.GenericIPAddressField().get_prep_value(" 2001:DB8::1 "))


@habit("note.tags.add(tag): the arguments a receiver of m2m_changed is given")
def m2m_changed_arguments():
    from django.db import models
    from django.db.models.signals import m2m_changed

    class Tag(models.Model):
        name = models.CharField(max_length=20)

        class Meta:
            app_label = "journal"

    class Note(models.Model):
        tags = models.ManyToManyField(Tag)

        class Meta:
            app_label = "journal"

    create(Tag, Note)
    received = []

    def receiver(**kwargs):  # every argument, sender among them, is sent by keyword
        received.append(sorted(kwargs))

    m2m_changed.connect(receiver, sender=Note.tags.through)
    try:
        Note.objects.create().tags.add(Tag.objects.create(name="gale"))
    finally:
        m2m_changed.disconnect(receiver, sender=Note.tags.through)
    return ", ".join(received[0])


@habit("def get_placeholder(self, value, compiler, connection), on a subclass of a field")
def field_get_placeholder():
    from django.db import models

    class UpperCaseField(models.CharField):
        def get_placeholder(self, value, compiler, connection):
            return "UPPER(%s)"

    return "the class is made"


@habit("def get_cache_name(self): return \"home\", on a FieldCacheMixin subclass: its cache_name")
def field_cache_get_cache_name():
    from django.db.models.fields.mixins import FieldCacheMixin

    class Home(FieldCacheMixin):
        def get_cache_name(self):
            return "home"

    return repr(Home().cache_name)


main()
