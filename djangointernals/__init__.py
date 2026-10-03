"""The site of *How Django Works*: a Django project that reads the corpus and bakes it.

    settings.py     the whole configuration: no database, one app, where the book is, where it is published
    book.py         the corpus as the site sees it: every page's head, the tree, the order; the gates run on it
    render.py       one page's markdown as HTML: the head, the sections, the figures, a pointer as a link
    gates.py        the gates as the site calls them (tools/pointers.py, names.py, links.py), and a pointer's link
    doors.py        the agent's files, derived from the pages: the twin, llms.txt, index.json, names.json, the sitemap
    views.py        a page, its twin, the agent's files, robots.txt
    urls.py         a page's id is its URL; its twin is that with .md after it
    templates/      the apparatus that is the same on every page
    static/         the stylesheet, the typefaces
    management/     `bake`: the book requested through Django and written to files, then the link gate over them;
                    `preview`: the baked files served as Cloudflare Pages serves them;
                    `deploy`: the gates, the bake, the upload, and every page fetched back and compared

SPEC.md, at the repository's root, is the rule this code enforces.
"""
