from django.db import models
from django.db.models import F

from harbour import serials


class Licence(models.Model):
    """A sailor may pilot ships into a port. The table between `Sailor.pilots_into` and Port."""

    sailor = models.ForeignKey("crew.Sailor", on_delete=models.CASCADE)
    port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)
    granted = models.DateField()


class Manifest(models.Model):
    """What a voyage carried."""

    serial = models.CharField(max_length=8, primary_key=True, default=serials.next_serial)
    voyage = models.ForeignKey("fleet.Voyage", on_delete=models.CASCADE)
    crates = models.PositiveIntegerField()
    kilos_each = models.PositiveIntegerField()
    kilos = models.GeneratedField(expression=F("crates") * F("kilos_each"), output_field=models.PositiveIntegerField(), db_persist=True)
    stamped = models.BooleanField(db_default=False)
    scan = models.FileField(upload_to="manifests/", blank=True)


class Berth(models.Model):
    """A place to tie up, known by its port and its number there."""

    pk = models.CompositePrimaryKey("port_id", "number")
    port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)
    number = models.PositiveSmallIntegerField()
    metres = models.PositiveSmallIntegerField()


class Logbook(models.Model):
    title = models.CharField(max_length=60)


class LogEntry(models.Model):
    """A line of a logbook. When a logbook is deleted the database deletes its lines."""

    book = models.ForeignKey(Logbook, on_delete=models.DB_CASCADE)
    line = models.CharField(max_length=200)
