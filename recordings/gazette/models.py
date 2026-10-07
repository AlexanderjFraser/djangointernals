from django.db import models
from django.urls import reverse


class Article(models.Model):
    slug = models.SlugField(unique=True)
    headline = models.CharField(max_length=100)
    published = models.DateTimeField()

    def __str__(self):
        return self.headline

    def get_absolute_url(self):
        return reverse("article", kwargs={"slug": self.slug})
