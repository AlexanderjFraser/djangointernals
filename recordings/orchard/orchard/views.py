import os

from django.http import HttpResponse


def index(request):
    return HttpResponse("The orchard.\n")


def stop(request):
    """Ends the process that serves this request, at once, with status 7. The recording asks
    for it to show what the reloader's first process does when its child ends with a status
    other than the one that asks for a restart."""
    os._exit(7)
