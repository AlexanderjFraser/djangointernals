"""The gazette's views.

`RECEIVED` is where the letters view puts what a valid form held, so that the recording
script can show it arrived.
"""
from functools import wraps

from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import condition, require_GET
from django.views.decorators.vary import vary_on_cookie
from django.views.generic import (
    CreateView, DeleteView, DetailView, FormView, ListView, MonthArchiveView, UpdateView, YearArchiveView,
)

from .forms import LetterForm
from .models import Article
from .stamp import announced, shut, stamped

RECEIVED = []


# Functions.

def front(request):
    return HttpResponse("the front page")


def nothing(request):
    pass


def headline(request):
    return "Harbour wall to be rebuilt"


@require_GET
@never_cache
@vary_on_cookie
def masthead(request):
    return HttpResponse("The Gazette")


def edition_tag(request):
    return "edition-7"


@condition(etag_func=edition_tag)
def edition(request):
    return HttpResponse("today's edition")


@stamped
def notices(request):
    return HttpResponse("public notices")


@stamped
def notices_page(request):
    return TemplateResponse(request, "gazette/notices.html", {"count": 3})


@stamped
def notices_lost(request):
    raise LookupError("the notices are lost")


@shut
def notices_shut(request):
    return HttpResponse("public notices")


def missing(request, year):
    # Each value is put together as the function runs, so that a search of an error report for
    # the whole text finds the variable and not a line of this file.
    password = " ".join(["open", "sesame"])
    shelf = " ".join(["the", "attic"])
    raise LookupError(f"no edition for {year}")


def till(request, year):
    posted = request.POST
    raise LookupError("the till is shut")


def tide(request, port):
    return HttpResponse(f"high water at {port}: noon")


class Almanac:
    """A view that is neither a function nor made by as_view(): an object that can be called."""

    def __init__(self, text):
        self.text = text

    def __call__(self, request):
        if self.text:
            return HttpResponse(self.text)


# Functions that are coroutines.

async def wire(request):
    return HttpResponse("from the wire")


def bare(view):
    """A decorator of the project's own that copies nothing from the view to its wrapper."""
    def wrapper(request, *args, **kwargs):
        return view(request, *args, **kwargs)
    return wrapper


def counted(view):
    """A decorator of the project's own, written for functions that are not coroutines."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        return view(request, *args, **kwargs)
    return wrapper


@counted
async def wire_counted(request):
    return HttpResponse("from the wire")


# Classes.

class Colophon(View):
    """Who prints the paper, and in what type."""

    type_size = 9

    def get(self, request):
        return HttpResponse(f"set in {self.type_size} point")


class Blank(View):
    def get(self, request):
        pass


@method_decorator(announced, name="dispatch")
class Births(View):
    def get(self, request):
        return HttpResponse("births, marriages and deaths")


@method_decorator(stamped, name="dispatch")
class Crossword(View):
    def get(self, request):
        return HttpResponse("today's crossword")


@method_decorator(csrf_exempt, name="dispatch")
class Tips(View):
    def post(self, request):
        return HttpResponse("thank you")


class TipsMarkedOnPost(View):
    @method_decorator(csrf_exempt)
    def post(self, request):
        return HttpResponse("thank you")


class Wire(View):
    async def get(self, request):
        return HttpResponse("from the wire")


class Muddle(View):
    def get(self, request):
        return HttpResponse("a list")

    async def post(self, request):
        return HttpResponse("added")


# Subclasses of the generic views.

class ArticleDetail(DetailView):
    model = Article


class ArticleList(ListView):
    model = Article
    paginate_by = 3
    ordering = "-published"


class ArticleYear(YearArchiveView):
    model = Article
    date_field = "published"


class ArticleMonth(MonthArchiveView):
    model = Article
    date_field = "published"
    month_format = "%m"


class Letters(FormView):
    form_class = LetterForm
    template_name = "gazette/letters.html"
    success_url = reverse_lazy("thanks")

    def form_valid(self, form):
        RECEIVED.append(form.cleaned_data["name"])
        return super().form_valid(form)


class ArticleCreate(CreateView):
    model = Article
    fields = ["slug", "headline", "published"]


class ArticleUpdate(UpdateView):
    model = Article
    fields = ["headline"]


class ArticleDelete(DeleteView):
    model = Article
    success_url = reverse_lazy("articles")
