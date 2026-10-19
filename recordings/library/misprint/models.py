"""A models module with a mistake in it, of the kind a development server meets while code is
being written: a field class misspelt, which raises AttributeError as the module is imported."""
from django.db import models


class Erratum(models.Model):
    text = models.TextFeld()
