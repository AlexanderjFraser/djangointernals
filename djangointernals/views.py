"""The views: a page, robots.txt, and what stands in for a page that is not there.

Every page of the book is one view and one template. What differs between
a page, a department's landing page and the contents is in the page itself:
an index page has children, and the template lists them under its text.
"""
from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

from . import book as books


def site(request):
    """What every template is given: where the site lives and whether it may be indexed."""
    indexable = settings.BOOK_DIR.name == "pages"
    return {"site_url": settings.SITE_URL, "repository_url": settings.REPOSITORY_URL, "indexable": indexable}


def verified_against(page, tree) -> str:
    """The page's own `django` line, with the commit in it shortened and linked to the tree
    at that commit."""
    def link(match):
        return format_html('<a href="{}/tree/{}">{}</a>', tree["repository"], tree["commit"], match.group(0)[:12])
    # escaping leaves a run of hex digits as it was, so the commit is still there to be found
    return mark_safe(books.COMMIT.sub(link, escape(page.meta.get("django", ""))))


def page(request, id):
    book = books.current()
    found = book.pages.get(id)
    if found is None or not found.published:
        raise Http404(id)
    before, after = book.neighbours(found)
    grammar = book.root / found.department.id / "figures" / "figures.css" if found.department else None
    return render(request, "djangointernals/page.html", {
        "book": book,
        "page": found,
        "verified_against": verified_against(found, book.pin),
        "before": before,
        "after": after,
        "figure_grammar": mark_safe(grammar.read_text(encoding="utf-8")) if grammar and grammar.is_file() else "",
        "statuses": books.STATUSES.items(),
    })


def not_found(request, exception=None):
    return render(request, "djangointernals/404.html", {"book": books.current()}, status=404)


def robots(request):
    """Every crawler is allowed, the AI crawlers by name included: being read by them is the point."""
    return HttpResponse("User-agent: *\nAllow: /\n", content_type="text/plain; charset=utf-8")
