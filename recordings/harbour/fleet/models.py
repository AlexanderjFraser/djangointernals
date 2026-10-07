from django.db import models


class Named(models.Model):
    """What a port and a ship have in common. Abstract: it has no table of its own."""

    name = models.CharField(max_length=60)

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return self.name


class Port(Named):
    country = models.CharField(max_length=40)


class Ship(Named):
    tonnage = models.PositiveIntegerField()
    home = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="ships")
    captain = models.OneToOneField("crew.Sailor", null=True, blank=True, on_delete=models.SET_NULL, related_name="command")

    class Meta(Named.Meta):
        constraints = [
            models.CheckConstraint(condition=models.Q(tonnage__gt=0), name="%(class)s_has_tonnage"),
            models.UniqueConstraint(fields=["name", "home"], name="one_name_to_a_port"),
        ]
        indexes = [models.Index(fields=["home", "tonnage"])]


class Voyage(models.Model):
    ship = models.ForeignKey(Ship, on_delete=models.CASCADE)
    sailed = models.DateField()
    calls = models.ManyToManyField(Port)
