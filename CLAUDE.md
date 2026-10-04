# Django Internals — djangointernals.dev

**What this is.** A textbook of how Django works: the codebase, not the
API. What each part owns, when it runs, how a request becomes a response
and a queryset becomes SQL, and why it is built the way it is. It is
written for two readers at once: the person who needs a working model of
the system, and the agent that needs a fact it can check. The official
documentation owns *how to use Django* and is the best in the industry at
it; this book never competes with it. It is not affiliated with or
endorsed by the Django Software Foundation.

**The standard** is a textbook a university press would publish: it
explains, it is correct, and it is good to look at. A reader meets nothing
on the site but the book.

**Owner:** Alexander Fraser (`AlexanderjFraser`). The predecessor is
[MinecraftDocs](https://github.com/AlexanderjFraser/MinecraftDocs)
(minecraftdocs.dev).

## The rules

1. **How it works, never how to use it.** What a class owns, when it runs,
   in what order, and why. Not a line-by-line walkthrough.
2. **A page explains.** It starts from what the system has to do, gives
   the model before the detail, and takes the shape of its subject.
   `SPEC.md` says what a page is.
3. **Nothing about the book's making reaches a page**: no status, no notes,
   no account of the site or of the method.
4. **One corpus, two faces.** Markdown is the book; the HTML is a
   rendering of it. Every page is also served at its `.md` address;
   `llms.txt` maps the book; `index.json` and `names.json` (every name,
   and the sections that mention it) are built from the same files.
5. **Every page names its version**: the first line of its head states the
   release and the commit it describes. Newest version only.
6. **Verified names.** Every name in a code span exists in the pinned
   trees; a member written on a class is declared by that class.
   `python tools/names.py` is the gate.
7. **Pointers.** Every mechanism a page describes has a pointer near it,
   written `path:Symbol`, as in
   `django/db/models/query.py:QuerySet._fetch_all`. `python
   tools/pointers.py` resolves each by the syntax tree at the pinned
   commit and records the lines it lands on and a fingerprint of them, so
   that a re-pin can tell a symbol whose body changed. On the site a
   pointer is a link to its lines. The book points and does not quote
   Django's source.
8. **Recorded, not inferred.** Where the order of calls is the point, the
   page shows a recording from a running Django (`recordings/`).
9. **Figures are drawn for the page, looked at rendered, and legible where
   they stand.** A figure's source is in the markdown, and it carries no
   fact the text does not.
10. **Links resolve**, and the build refuses one that does not.
11. **Every rule a program can check has a gate, and every gate a
    `--probe`** that proves it fails on what it should.
12. **Commit your own files by name, never `add -A`.** Two sessions are
    often open.

## The source

`pin.json` names what the book describes, and every tool reads it:
Django's `main` at `4fab678a0739d54401ccee7eb587553657c9f76e` (2026-09-26;
on its way to 6.2, the next long-term-support release; 6.1.1 is the newest
release at that commit), and beside it the two libraries Django requires,
`asgiref` 3.12.1 and `sqlparse` 0.6.0, each at its release's commit. The
trees live under `reference/`, gitignored. `python tools/pin.py fetch`
fetches each at its commit; `python tools/pin.py check` fails unless every
file on disk is the commit's, byte for byte, and this file names the pin.

This is not the Django a model remembers. Read the file before writing
about it: at this commit `MiddlewareMixin` lives in `django/middleware/`,
deprecation warnings are named by year, and much else has moved.

## What is here

- `pages/`: the book. `pages/index.md` is the front page; each chapter is
  a file and a directory of its sections and figures. Beside each page,
  its pointer report, `<page>.pointers.json`: generated, committed, never
  edited.
- `SPEC.md`: what a page is, and what the build refuses.
- `recordings/`: for each chapter that has one, a script that runs Django
  and writes down what happens, and its output.
- `map/`: the source by chapter. `map/chapters.json` says which part of
  Django each chapter explains (written by hand); `map/generated/` has
  the sizes, every file with what it defines and imports, and each
  chapter's files in reading order; `map/inventory/` has every place the
  source cites a ticket or names a deprecation warning, by chapter. Both
  are generated (`tools/map_source.py`, `tools/inventory.py`) and never
  edited. `map/runtime-names.md` lists the names that exist only as the
  code runs.
- `tools/` (MIT): the pin, the map and the three gates. Each has a
  `--probe`.
- `djangointernals/` and `manage.py`: the site, a Django project baked to
  static files for Cloudflare Pages. `djangointernals/__init__.py` says
  what each file is.

## The site

**`python manage.py bake` is the whole build.** It reads the book, runs
the gates on every page, refuses the book whole with each problem as
`file:line: what is wrong`, and otherwise writes to `dist/` every page
with its `.md` twin, `llms.txt`, `index.json`, `names.json`, and then runs
the link gate over what it wrote. `python manage.py bake --probe` proves
the refusals. `python manage.py preview` serves `dist/` as Cloudflare
Pages will; `python manage.py deploy` checks the committed pointer
reports, bakes, uploads, and fetches every file back.

The site is live as it is built, and `noindex` until the book is
published (`INDEXABLE` in `djangointernals/settings.py`).

## Conventions

- Django's own names, as the source spells them. A member is written on
  its declaring class where a section first names it.
- A code span holds a name of the source, a pointer, or code. A literal
  keeps its quotes inside the span (`"text/html"`).
- On this machine: never edit files through PowerShell; a script goes in a
  file and is run with `.venv/Scripts/python.exe`, never through a
  heredoc. The `python` on PATH is 3.11, which cannot parse the pin.
