"""A models module that fetches a model of an application entered after its own, while models
modules are still being imported, as get_user_model fetches the user model."""
from django.apps import apps
from django.db import models

Book = apps.get_model("catalogue", "Book", require_ready=False)


class Reservation(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE)
