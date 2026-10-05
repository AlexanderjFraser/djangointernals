from django.shortcuts import render

from .models import Entry


def by_year(request, year):
    entries = Entry.objects.filter(published__year=year).order_by("published")
    return render(request, "journal/entries.html", {"year": year, "entries": entries})
