from django.db import models


class Rank(models.TextChoices):
    MASTER = "master"
    MATE = "mate", "First mate"
    ENGINEER = "engineer"


class SailorQuerySet(models.QuerySet):
    def aboard(self, ship):
        return self.filter(ship=ship)


class Sailor(models.Model):
    name = models.CharField(max_length=60)
    ship = models.ForeignKey("fleet.Ship", on_delete=models.CASCADE, related_name="crew")
    signed_on = models.DateTimeField(auto_now_add=True)
    pilots_into = models.ManyToManyField("fleet.Port", through="office.Licence", related_name="pilots")

    objects = SailorQuerySet.as_manager()

    def __str__(self):
        return self.name


class Officer(Sailor):
    """A sailor with a rank. A child with a table of its own: the rank is kept there."""

    rank = models.CharField(max_length=10, choices=Rank)


class VeteranManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(signed_on__year__lt=2020)


class Veteran(Sailor):
    """The sailors who signed on before 2020. A proxy: the same table, another class."""

    objects = VeteranManager()

    class Meta:
        proxy = True
