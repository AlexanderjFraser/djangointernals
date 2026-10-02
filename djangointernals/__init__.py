"""The site of *How Django Works*: a Django project that reads the corpus and bakes it.

    settings.py     the whole configuration: no database, one app, where the book is
    book.py         the corpus as the site sees it: every page's head, the tree, the order
    render.py       one page's markdown as HTML: the head, the sections, the figures
    views.py        a page, the contents, robots.txt
    urls.py         a page's id is its URL
    templates/      the apparatus that is the same on every page
    static/         the stylesheet, the typefaces
    management/     `bake`: every page requested through Django and written to a file

SPEC.md, at the repository's root, is the rule this code enforces.
"""
