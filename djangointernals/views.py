"""The views: a page, its twin, the agent's files, robots.txt, and what stands in for a page that is not there.

Every page of the book is one view and one template. What differs between
a page, a department's landing page and the contents is in the page itself:
an index page has children, and the template lists them under its text. The
twin and the agent's files (doors.py) are views too, so `runserver` serves
them live and the bake writes what they answer.
"""
from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

from . import book as books
from . import doors


def indexable() -> bool:
    """Only the book itself may be indexed and carries canonical URLs: never the specimen."""
    return settings.BOOK_DIR.name == "pages"


def site(request):
    """What every template is given: where the site lives and whether it may be indexed."""
    return {"site_url": settings.SITE_URL, "repository_url": settings.REPOSITORY_URL, "indexable": indexable()}


def verified_against(page, tree) -> str:
    """The page's own `django` line, with the commit in it shortened and linked to the tree
    at that commit."""
    def link(match):
        return format_html('<a href="{}/tree/{}">{}</a>', tree["repository"], tree["commit"], match.group(0)[:12])
    # escaping leaves a run of hex digits as it was, so the commit is still there to be found
    return mark_safe(books.COMMIT.sub(link, escape(page.meta.get("django", ""))))


def published(id: str):
    book = books.current()
    found = book.pages.get(id)
    if found is None or not found.published:
        raise Http404(id)
    return book, found


def page(request, id):
    book, found = published(id)
    before, after = book.neighbours(found)
    grammar = book.root / found.department.id / "figures" / "figures.css" if found.department else None
    return render(request, "djangointernals/page.html", {
        "book": book,
        "page": found,
        "verified_against": verified_against(found, book.pin),
        "twin": doors.twin_url(found),
        "before": before,
        "after": after,
        "figure_grammar": mark_safe(grammar.read_text(encoding="utf-8")) if grammar and grammar.is_file() else "",
        "statuses": books.STATUSES.items(),
    })


def twin(request, id):
    """The page's markdown file, as it is: the artefact the site is a rendering of."""
    _book, found = published(id)
    return HttpResponse(found.source.read_bytes(), content_type="text/markdown; charset=utf-8")


def text(body: str, kind: str = "text/plain") -> HttpResponse:
    return HttpResponse(body, content_type=f"{kind}; charset=utf-8")


def llms(request):
    return text(doors.llms(books.current(), indexable()))


def llms_full(request):
    if not indexable():
        raise Http404("llms-full.txt")
    return text(doors.whole(books.current()))


def index_json(request):
    return text(doors.dumps(doors.index(books.current(), indexable())), "application/json")


def names_json(request):
    return text(doors.dumps(doors.names(books.current())), "application/json")


def sitemap(request):
    if not indexable():
        raise Http404("sitemap.xml")
    return text(doors.sitemap(books.current()), "application/xml")


def not_found(request, exception=None):
    return render(request, "djangointernals/404.html", {"book": books.current()}, status=404)


def robots(request):
    """Every crawler is allowed, the AI crawlers by name included: being read by them is the point."""
    body = "User-agent: *\nAllow: /\n"
    if indexable():
        body += f"\nSitemap: {settings.SITE_URL.rstrip('/')}/sitemap.xml\n"
    return text(body)
