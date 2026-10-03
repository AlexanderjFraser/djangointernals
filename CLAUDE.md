# How Django Works — djangointernals.dev

**What this is.** A textbook of *how Django works* — the codebase, not the
API: what each part owns, when it runs, how a request becomes a response and
a queryset becomes SQL, and why it is the way it is. It is written for two
readers at once: the person who needs a model of the system to direct an
agent well, and the agent that reads the whole corpus and needs to know how
everything fits. The official documentation owns *how to use Django* and is
the best in the industry at it; this book never competes with it. The book
is not affiliated with or endorsed by the Django Software Foundation.

**Status: planning (2026-10-01).** No page is written. The title is *How
Django Works*; the site is `djangointernals.dev`. The production process
this book is built with is the owner's and is not in this repository; what
is here is what a reader or a contributor to this book needs: the corpus,
the site build, the gates, the tools configured for Django, the page spec,
the licences.

**Owner:** Alexander Fraser (`AlexanderjFraser`). The owner judges what
lands and is also the book's *student*: the human who reads a page, tries to
use it, and says where it lost them. Nothing is recorded that the owner
hasn't understood.

**The predecessor:** [MinecraftDocs](https://github.com/AlexanderjFraser/MinecraftDocs)
(minecraftdocs.dev), one full production of a codebase textbook. Its rules
are assumed here until a ruling replaces one.

## The rules so far

1. **How it works, never how to use it.** Object-level: what a class owns,
   when it runs, on what thread, in what order, and why — not a line-by-line
   walkthrough.
2. **One corpus, two faces.** Markdown is the artefact; the HTML is a
   rendering. Every page is also served at its `.md` URL; `llms.txt` maps the
   book for routing; a JSON index and a reverse index by name are built from
   the same files.
3. **Every page names its version.** The first entry of a page's head
   states the release and the commit it was verified against. Newest version only; the
   one place the past appears is the delta chapter — what a reader, or a
   model, probably believes that is no longer true.
4. **Every section stands alone.** A section answers one question; its
   heading says which; its first sentence names its subject; it never leans
   on the section before it.
5. **Verified names.** Every name in a code span exists in the pinned
   trees, written `Class.member` on the class whose own body declares the
   member, never on a subclass that inherits it. A name that exists only at
   runtime (made by a metaclass, a descriptor, `setattr`, a module's
   `__getattr__`) is admitted only where it is declared with the pointer to
   the code in the clone that makes it: in the page, or in
   `map/runtime-names.md`. A name more than one module defines is given
   with its module first, in the section that uses it. `python
   tools/names.py` is the gate; a page that fails does not publish.
6. **Every claim carries a pointer**, written in a code span as
   `path:Symbol`: the path from the clone's root, a colon, the symbol dotted
   from module level, as in `django/db/models/query.py:QuerySet._fetch_all`.
   A bare path is a whole file; a final slash, a directory; a library's
   tree is named first (`asgiref:asgiref/sync.py:SyncToAsync`). The commit
   is named once, at the head of the page, and never inside a pointer.
   `python tools/pointers.py` is the gate: it resolves every pointer by the
   syntax tree at the pinned commit and writes, for each, the lines it
   lands on and a fingerprint of them, so that a re-pin can tell a symbol
   whose body changed from one that only kept its name. Line numbers are
   derived, never written by hand. On the site a pointer becomes a link
   into GitHub at the commit. Django's licence permits quoting its source,
   and the book does not: a page points, and carries no excerpt of the
   source (`SPEC.md`, section 6).
7. **Trace-driven, and recorded.** A trace page's spine is a recording from
   a running system — Django's test suite under a tracer, a request through
   the test client — explained against the code, never a trace inferred from
   reading.
8. **Figures render and are legible where they stand**, and a figure never
   carries a fact the text does not: the figure's source (the mermaid, the
   table an SVG was drawn from) is in the markdown. A figure is drawn
   before the build and put into the page as SVG; nothing is drawn in the
   reader's browser.
9. **Links resolve.** A link between pages is the path of the target's
   `.md` file from the page it is written in, and the build refuses one
   that lands on no page, section or figure. `python tools/links.py dist`
   is the gate over what the build wrote: every address, fragment and
   twin link in the baked site resolves as the host serves it, and the
   build fails if one does not.
10. **Every rule has a gate, every gate has a `--probe`** that proves it
    fails on the construct it should, and the build refuses to publish on a
    failure.
11. **Commit your own files by name, never `add -A`.** Two sessions are
    often open.

## The source

**The pin.** `pin.json` names what the book is verified against, and every
tool reads it: Django's `main` at
`4fab678a0739d54401ccee7eb587553657c9f76e` (2026-09-26; on its way to 6.2,
the next long-term-support release; 6.1.1 is the newest release at that
commit), and beside it the two libraries Django's own `pyproject.toml`
requires, `asgiref` 3.12.1 and `sqlparse` 0.6.0, each at its release's
commit. The trees live under `reference/`, gitignored.
`python tools/pin.py fetch` fetches each at its commit, never a branch as
it stands that day, and as the commit's own bytes (no line-ending
conversion, a symbolic link as the file git stores), so that sizes and
fingerprints are the same on every machine. `python tools/pin.py check`
fails unless every file on disk is the commit's, byte for byte, and this
file names the pin. Django is BSD-licensed: its source may be quoted,
linked at a commit and redistributed, so a claim can point at the line.

**The tools** are in `tools/` (MIT), each with a `--probe` that proves it
fails on what it should. They need Python 3.12 or later, because Django at
the pin does: run them with the project's virtual environment, `.venv`
(Python 3.14, with Django installed from the pinned clone).

**The map.** `map/map.json` (what is mapped and how it is counted) and
`map/slices.json` (which paths make which slice) are written by hand.
`map/generated/` is written by `python tools/map_source.py` and
`map/inventory/` by `python tools/inventory.py`; each is checked by its
tool's `--check` and never edited, and each has a `README.md`. In the
first: sizes by package and the imports between packages (`packages.md`);
every file with what it defines and imports (`files.json`); the slices the
first pass reads the source in, each with its files in reading order
(`slices.md`, `slices/`). In the second: every comment and string that
cites a ticket, and every place a deprecation warning class is named, by
slice. At the pin, `django/` holds 736 Python files outside locale
directories, 162k lines; as an agent reads it, it is about 2.4M tokens, of
which `django/db` is 0.8M, so no one context holds the ORM, let alone the
tree. Those numbers are the generated tables'; where this paragraph and
the tables differ, the tables are right.

**The gates.** `python tools/pointers.py DOC` and `python tools/names.py
DOC` check a markdown document against the pinned trees (rules 6 and 5);
each tool's head says exactly what is a pointer, what is a name, and what
the gate does not check. The pointer gate writes `DOC.pointers.json` beside
the document (a page's report is committed beside the page), or under
`--report DIR`: generated, never edited, and checked by `--check`, which
after a re-pin says which pointers land on changed bytes. The name gate
run with `--sections`, as the build runs it on a page, binds a name
several modules define only within the section that uses it.
`map/map.json`'s `names` says which file holds the settings' defaults,
and names `map/runtime-names.md`, the book's list of names made at
runtime, each with the pointer to the code that makes it.

## The site

**The repository is a Django project**, and the site is that project baked
to static files for Cloudflare Pages. `manage.py` is at the root; the
package `djangointernals/` is the whole site (its `__init__.py` says what
each file is); the corpus is `pages/`, of which `pages/index.md` is the
contents; `SPEC.md` is the page spec: what a page's head holds, the three
statuses and what each publishes, what a section is, how a figure is
written. **`python manage.py bake` is the whole build**: it reads the book
whole, runs both gates on every page, refuses it whole with each problem
as `file:line: what is wrong`, and otherwise writes to `dist/` (ignored)
every page with its `.md` twin, `llms.txt`, `index.json` (the book as
data), `names.json` (every name and where it is explained), and for the
book itself `llms-full.txt` and `sitemap.xml`, then runs the link gate
over what it wrote; `python manage.py bake --probe` proves the refusals.
On the site a pointer is a link to its lines at the pinned commit; in the
twin it is as written. `python manage.py preview` serves `dist/` on this
machine as Cloudflare Pages serves it; `python manage.py deploy` runs the
gates, bakes, uploads to Pages and fetches every file back, stopping at
the first failure. `specimen/` is a small book that follows the spec and
is never part of the book: `python manage.py bake --book specimen`. The
site needs `requirements.txt` beside Django, and the pinned trees on disk.

**The site is live as it is built** (the owner's word, 2026-10-02):
djangointernals.dev serves what exists, `noindex` until the book is
published; today that is the specimen. **Still to be built**: `pagefind`
for the human's search; a pip package that ships the corpus beside Django
in `site-packages` with a CLI; the same package serving MCP tools
(`search`, `section`, `names`, `report`) over stdio; a Claude Code skill
and an `AGENTS.md` line that say when to consult it. `robots.txt` allows
the AI crawlers. A reader's correction arrives as a GitHub issue carrying
the pointer that shows the claim false.

## Conventions

- Django's own names throughout, as the source spells them; `Class.member`
  for every member, on the declaring class, never a bare member.
- A code span holds a pointer, a name of the source, or code. A string or
  other literal text keeps its quotes inside the span (`"text/html"`,
  `"_meta"`): without them the gates take it for a pointer or a name.
- A page states no count a tool can derive; generated tables own the
  numbers.
- On this machine: never edit files through PowerShell; a script with
  backslashes in it, or over about a hundred lines, goes through the Write
  tool and runs from a file. Run the tools as
  `.venv/Scripts/python.exe tools/<tool>.py`, and the site as
  `.venv/Scripts/python.exe manage.py <command>`: the `python` on PATH is
  3.11, which cannot parse the pin.
