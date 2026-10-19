from django.db import models


class Wish(models.Model):
    # Two references by string that never resolve: catalogue is installed, and its model is
    # Book; no application with the label periodicals is installed.
    book = models.ForeignKey("catalogue.Bok", on_delete=models.CASCADE)
    issue = models.ForeignKey("periodicals.Issue", on_delete=models.CASCADE)
