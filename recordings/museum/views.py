"""The museum's views. Each answers with a line of text that says what it was called with.

`ON_VIEW` is for the recording script: it adds callables to the list, and every view calls
each with the request before it answers. That is how the script asks its questions from
inside a request.
"""
from django.http import HttpResponse
from django.views import View

ON_VIEW = []


def answer(request, text):
    for ask in ON_VIEW:
        ask(request)
    return HttpResponse(text)


def entrance(request):
    return answer(request, "the entrance")


def tickets(request, year, month=None):
    return answer(request, f"tickets for {year}" + (f", month {month}" if month else ""))


def wing(request, wing):
    return answer(request, f"the {wing} wing")


def room(request, wing, room):
    return answer(request, f"room {room} of the {wing} wing")


def track(request, wing, room, track):
    return answer(request, f"the audio track {track} for room {room} of the {wing} wing")


def shop(request):
    return answer(request, "the shop")


def item(request, item):
    return answer(request, f"the shop's {item}")


def plan(request, floor, format="html"):
    return answer(request, f"the plan of floor {floor}, as {format}")


def download(request, name):
    return answer(request, f"the file {name}")


def feed(request, kind):
    return answer(request, f"the {kind} feed")


def hours(request):
    return answer(request, "the opening hours")


def members(request):
    return answer(request, "the members' entrance")


class Tour(View):
    def get(self, request):
        return answer(request, "the tour")


def lost(request):
    """An error view of the wrong shape for 403: it takes the request and nothing else."""
    return HttpResponse("lost", status=403)
