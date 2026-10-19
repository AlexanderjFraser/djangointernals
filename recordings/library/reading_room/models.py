from django.db import models


class Seat(models.Model):
    number = models.PositiveIntegerField()
