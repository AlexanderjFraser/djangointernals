from django.db import models

from library import probe

probe.ask("as library.loans.models is imported, the first models module of phase 2")


class Loan(models.Model):
    # Both models are named by a string, and both belong to applications listed after this one.
    book = models.ForeignKey("catalogue.Book", on_delete=models.CASCADE)
    member = models.ForeignKey("members.Member", on_delete=models.CASCADE)
    due = models.DateField()
