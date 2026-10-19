from django.db import models


class Box(models.Model):
    shelfmark = models.CharField(max_length=20)
