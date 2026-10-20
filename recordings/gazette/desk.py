"""Views for the later blocks of the recording, and the URLconf that routes to them.

A block that requests one of these sets ROOT_URLCONF to this module for its requests, and puts
the setting back after them; `gazette.urls` is not changed, so that the earlier blocks' URLs and
the names they reverse stay as they were. The URLconf holds the views below but `forged` and the
error views (`development_urls.py` routes the first, and the recording makes URLconfs of its own
for the others), the coroutine view `views.wire` under `non_atomic_requests`, the class with two
decorators given as a list, from `listed.py`, and two RedirectViews that preserve the request.
"""
from django.core.exceptions import SuspiciousOperation
from django.db.transaction import non_atomic_requests
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.template.response import TemplateResponse
from django.urls import path
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import condition
from django.views.decorators.vary import vary_on_cookie
from django.views.generic import RedirectView

from . import views
from .listed import Corrections
from .stamp import stamped

# A coroutine view under a decorator whose wrapper is an ordinary function.
wire_outside = non_atomic_requests(views.wire)


# A middleware made into a decorator, around a coroutine view.

@stamped
async def wire_notices(request):
    return HttpResponse("notices from the wire")


# CSRF: a view under csrf_protect that uses the token, as a form's template does.

@csrf_protect
def subscribe(request):
    get_token(request)
    return HttpResponse("subscribed")


# A decorator that sets Vary, below condition and above it; the tag is the edition's, as
# views.edition_tag gives it.

def edition_tag(request):
    return "edition-7"


@condition(etag_func=edition_tag)
@vary_on_cookie
def vary_below(request):
    return HttpResponse("today's edition")


@vary_on_cookie
@condition(etag_func=edition_tag)
def vary_above(request):
    return HttpResponse("today's edition")


# Error views of the project's own, for handler404.

def not_found_unrendered(request, exception):
    return TemplateResponse(request, "gazette/not_found.html", {"path": request.path}, status=404)


def not_found_ok(request, exception):
    return HttpResponse(f"no page at {request.path}")


def not_found_misnamed(request, exc):
    return HttpResponse(f"no page at {request.path}", status=404)


# A view that finds something wrong with the request.

def forged(request):
    raise SuspiciousOperation("the edition's date has been altered")


urlpatterns = [
    path("wire/outside/", wire_outside, name="wire-outside"),
    path("notices/wire/", wire_notices, name="wire-notices"),
    path("subscribe/", subscribe, name="subscribe"),
    path("corrections/", Corrections.as_view(), name="corrections"),
    path("edition/vary-below/", vary_below, name="vary-below"),
    path("edition/vary-above/", vary_above, name="vary-above"),
    path("news/kept/", RedirectView.as_view(url="/articles/", preserve_request=True), name="news-kept"),
    path("news/kept/moved/", RedirectView.as_view(url="/articles/", permanent=True, preserve_request=True), name="news-kept-moved"),
]
