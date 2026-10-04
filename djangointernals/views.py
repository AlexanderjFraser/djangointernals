"""The views: a page, its twin, the agent's files, robots.txt, and what stands in for a page that is not there.

Every page of the book is one view and one template. What differs between
the front page, a chapter's opening page and a section is in the page
itself: where it stands in the tree and whether it has children, which the
template lists. The twin and the agent's files (doors.py) are views too, so
`runserver` serves them live and the bake writes what they answer.

Two things stand beside every page and are the site's, never a page's: the
book's contents as a navigation (`contents`), and the reader's choice of
colours (`COLOURS`, which names the palettes the stylesheet has).
"""
from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

from . import book as books
from . import doors


def indexable() -> bool:
    """May what is baked be indexed, and does it carry canonical URLs, a sitemap and the
    book in one file? Not until the book is published: settings.INDEXABLE."""
    return bool(settings.INDEXABLE)


def site(request):
    """What every template is given: where the site lives and whether it may be indexed."""
    return {"site_url": settings.SITE_URL, "repository_url": settings.REPOSITORY_URL, "indexable": indexable()}


def edition(page, tree) -> str:
    """The page's own `django` line, with the commit in it shortened and linked to the tree
    at that commit: which Django the page describes."""
    def link(match):
        return format_html('<a href="{}/tree/{}">{}</a>', tree["repository"], tree["commit"], match.group(0)[:7])
    # escaping leaves a run of hex digits as it was, so the commit is still there to be found
    return mark_safe(books.COMMIT.sub(link, escape(page.meta.get("django", ""))))


COLOURS = (
    # (the value kept in the reader's browser and set on the root element, the word shown).
    # The stylesheet has a palette for each value; the first is no value: the reader's system decides.
    ("", "Auto"),
    ("paper", "Paper"),
    ("white", "White"),
    ("sepia", "Sepia"),
    ("dusk", "Dusk"),
    ("night", "Night"),
)


def contents(book, here=None) -> list[dict]:
    """The book's contents as the navigation beside a page shows them: the parts, each with
    its chapters, and under the chapter that `here` is in, that chapter's sections, with the
    headings of the page being shown under it. A planned page is a line with no address."""
    branch = {*here.ancestors, here} if here is not None else set()

    def entry(page) -> dict:
        return {
            "page": page,
            "here": page is here,
            "children": [entry(child) for child in page.children] if page in branch else [],
            "sections": page.sections if page is here else [],
        }

    return [{"label": part["label"], "chapters": [entry(chapter) for chapter in part["chapters"]]} for part in book.parts]


def published(id: str):
    book = books.current()
    found = book.pages.get(id)
    if found is None or not found.published:
        raise Http404(id)
    return book, found


def page(request, id):
    book, found = published(id)
    before, after = book.neighbours(found)
    grammar = book.root / found.chapter.id / "figures" / "figures.css" if found.chapter else None
    return render(request, "djangointernals/page.html", {
        "book": book,
        "page": found,
        "nav": contents(book, found),
        "front": found is book.index,
        "colours": COLOURS,
        "edition": edition(found, book.pin),
        "twin": doors.twin_url(found),
        "before": before,
        "after": after,
        "figure_grammar": mark_safe(grammar.read_text(encoding="utf-8")) if grammar and grammar.is_file() else "",
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
    book = books.current()
    return render(request, "djangointernals/404.html", {"book": book, "nav": contents(book), "colours": COLOURS}, status=404)


def robots(request):
    """Every crawler is allowed, the AI crawlers by name included: being read by them is the point."""
    body = "User-agent: *\nAllow: /\n"
    if indexable():
        body += f"\nSitemap: {settings.SITE_URL.rstrip('/')}/sitemap.xml\n"
    return text(body)
