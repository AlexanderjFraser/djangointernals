from django.db import models

from library import probe


class Member(models.Model):
    name = models.CharField(max_length=100)


probe.ask("as library.members.models is imported, the last models module of phase 2")
