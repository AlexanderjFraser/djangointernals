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
3. **Every page names its version.** The first line of a page states the
   release and the commit it was verified against. Newest version only; the
   one place the past appears is the delta chapter — what a reader, or a
   model, probably believes that is no longer true.
4. **Every section stands alone.** A section answers one question; its
   heading says which; its first sentence names its subject; it never leans
   on the section before it.
5. **Verified names.** Every backticked identifier exists in the pinned
   clone, written `Class.member` on the declaring class; a page that fails
   does not publish.
6. **Every claim carries a pointer**: file and symbol at the pinned commit,
   as a link into GitHub at that commit. The gate checks that the pointer
   resolves and the symbol is where it says; line numbers are derived at
   build, never written by hand. Django's licence permits quoting its source;
   whether the corpus quotes or only points is to be ruled, and until then
   pages point.
7. **Trace-driven, and recorded.** A trace page's spine is a recording from
   a running system — Django's test suite under a tracer, a request through
   the test client — explained against the code, never a trace inferred from
   reading.
8. **Figures render and are legible where they stand**, and a figure never
   carries a fact the text does not: the figure's source (the mermaid, the
   table an SVG was drawn from) is in the markdown.
9. **Links resolve.**
10. **Every rule has a gate, every gate has a `--probe`** that proves it
    fails on the construct it should, and the build refuses to publish on a
    failure.
11. **Commit your own files by name, never `add -A`.** Two sessions are
    often open.

## The source

`reference/django/` is a shallow clone of `main` at
`4fab678a0739d54401ccee7eb587553657c9f76e` (2026-09-26; 6.2 alpha, 6.1 the
current release), gitignored; refetch with
`git clone --depth 1 https://github.com/django/django reference/django`.
Django is BSD-licensed: its source may be quoted, linked at a commit and
redistributed, so a claim can point at the line. Measured 2026-09-16 at
`8cbdd4a`: `django/` without contrib 121k lines, of which `django/db` 55k in
123 files; contrib 44k; `tests/` 357k in 2,010 files; `docs/` 173k lines of
reStructuredText. The whole codebase is about 1.5M tokens; `django/db`
alone, about half a million, fits one context and is the pilot's unit.

## The site

To be built; the stack is ruled, the skeleton is not. Django as the
generator, baked to static files and hosted on Cloudflare Pages; `pagefind`
for the human's search; figures as SVG; the gates before every build. Four
doors for an agent, all built from the one corpus: the `.md` URL and
`llms.txt`; a pip package that ships the corpus beside Django in
`site-packages` with a CLI; the same package serving MCP tools (`search`,
`section`, `names`, `report`) over stdio; a Claude Code skill and an
`AGENTS.md` line that say when to consult it. `robots.txt` allows the AI
crawlers. A reader's correction arrives as a GitHub issue carrying the
pointer that shows the claim false.

## Conventions

- Django's own names throughout, as the source spells them; `Class.member`
  for every member, on the declaring class, never a bare member.
- A page states no count a tool can derive; generated tables own the
  numbers.
- On this machine: never edit files through PowerShell; a script with
  backslashes in it, or over about a hundred lines, goes through the Write
  tool and runs from a file.
