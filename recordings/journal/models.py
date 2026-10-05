from django.db import models


class Entry(models.Model):
    title = models.CharField(max_length=100)
    published = models.DateField()

    def __str__(self):
        return self.title
