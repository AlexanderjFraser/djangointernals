from django.db import models


class Tree(models.Model):
    variety = models.CharField(max_length=40)
    row = models.PositiveSmallIntegerField()
