# The page

*The page spec of* How Django Works: *what a page of the book is, as a file
and as a thing a reader meets. The book's rules are in [CLAUDE.md](CLAUDE.md);
this is what they come to on a page. Three things hold a page to it. The
site's build refuses a page that breaks what a program can read
(`python manage.py bake`; each such rule is marked* **baked** *below,
section 12 lists them, and `python manage.py bake --probe` proves each
refusal). The two gates check its pointers and its names
(`tools/pointers.py`, `tools/names.py`), and the build runs them. The
rest is the writer's and the checker's: no program refuses a sentence for
what it says.
[specimen/](specimen/) is a small book written to these rules, with its
statuses set to show each one; bake it to see them. Section 13 has the
commands.*

## 1 · One corpus, two readers

A page is a markdown file. The file is the artefact: an agent reads it as
it is, from the repository or from a package, and will be able to fetch it
at the page's own address with `.md` after it. The site is a rendering of
the same file for a person. So nothing the rendering adds may carry a
fact, and nothing in the file may depend on being rendered: no raw HTML,
no image, no script (**baked**).

The two readers arrive differently. A person comes in at the contents and
reads down. An agent lands in the middle of a page, on the name it searched
for, and is often handed one section and nothing else. A page is written so
that both work: the head says in a few hundred tokens what the page is, and
every section can be read alone.

## 2 · Where a page lives

The book is the directory `pages/`. Its contents page is `pages/index.md`.
A page's **id** is its path under `pages/` without `.md`; the contents
page's id is empty.

| | for the page `pages/orm/queries.md` |
|---|---|
| id | `orm/queries` |
| address | `/orm/queries` |
| the same page as markdown, the file itself | `/orm/queries.md` |
| a section of it | `/orm/queries#how-is-a-lookup-compiled` |

A page that lists children is an **index**: `contents: queries, compiler`
in the head of `pages/orm.md` makes `pages/orm/queries.md` and
`pages/orm/compiler.md` its children, in that reading order. Adding a page
is writing its file and adding its name to its index's `contents`: nothing
else lists it. The pages directly under the contents page are the book's
front pages and its **departments**; a department's index is its landing
page. Every `.md` under `pages/` is a page and is named by exactly one
`contents` (**baked**). A page's name is lower-case letters and digits in
words joined by hyphens; it is never `index` or `404`, which the host
gives a meaning of its own at every depth, and directly under the
contents page it is not `static` (**baked**). A name is permanent: an
address is a promise.

## 3 · The head

A page opens with its front matter, then its title, its lede, and what it
asserts in brief. Together they are the page's **head**: what a reader
needs to decide whether this is the page they want, and the whole of a
page that is still in outline.

```
---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
status: verified
owns: "`BaseHandler.load_middleware`, `BaseHandler._middleware_chain`"
---

# The middleware chain

When is the middleware chain of a `WSGIHandler` built, and from what?

What the page asserts, in a paragraph or two, each claim with its pointer.

## The first section's question?
```

**The front matter** is one `key: value` to a line, a strict subset of
YAML, each key once and in any order (**baked**):

| key | | what it holds |
|---|---|---|
| `django` | required | the release and the commit the page was verified against, in words. It spells out the pinned commit of `pin.json`, twelve hex digits or more. Where the page points into a pinned library it names the library's release too (`; asgiref 3.12.1`). This is the book's rule 3: it is what lets a reader accept or reject the page at a glance |
| `status` | required | `outline`, `verified` or `read` (section 4) |
| `owns` | optional | the names this page is the home of, each in a code span, with commas between. A name has one home in the book, the page that explains it in full, and the build refuses a second (**baked**). Other pages say what their own story needs and link |
| `contents` | on an index | the names of its children, in reading order |

A value is plain text. It is written in double quotes when it begins with
anything but a letter or a digit, or holds a colon followed by a space, or
a space followed by `#`: so `owns`, which begins with a backtick, is
always quoted. Both gates read the front matter as prose: the commit there
is the one the pointer gate asks for, and a name in `owns` is checked.

**The title** is the page's one `#` heading, and names the thing, not the
page's place in the book. It may hold a name in a code span.

**The lede** is the first paragraph: one or two sentences. For a page it
is the question the page answers. For a landing page it is the
department's claim, a sentence someone could dispute. It is what the
contents and the book's map for agents say about the page, so it carries
the names a reader would search for. A question presupposes: a lede is
checked for what it takes for granted, like any claim.

**In brief** is whatever else stands above the first `##`: what the page
asserts, in a paragraph or two, as claims with their pointers. It is
written first and it stays. On a page in outline it is the plan; on a
written page it is the summary, checked after the sections it summarises.
It is the one place a page says twice what a section says, and it says it
in the section's own words.

## 4 · Status

A page's status says how far it has come, in three words the site reads.

| status | what the file holds | what the site publishes |
|---|---|---|
| `outline` | the head, and the sections as questions | an entry in the contents: the title, the lede, the status. No page, and no address |
| `verified` | the page, written from claims that were each checked against the source | the page |
| `read` | the page, read together with the pages around it and revised after a reader's read | the page |

- **A page never claims a status it has not reached.** `verified` means
  each claim was put to a checker who had the source and not the writer's
  reasoning, and what the checker found was settled. `read` means the page
  was read in one sitting with the rest of its department, and a person
  who did not write it read it and what they said was answered.
- **There is no status for written and not yet checked.** A page stays
  `outline` while it is being written, and the site publishes nothing of
  its body. The status moves when the checking is done, not when the prose
  exists.
- **No page says of itself how far it has come**, nor how far another page
  has. The site says it, on the page and in the contents, from the status.
  A sentence in a page about a page's state would have to be edited when
  the state changed.
- **An outline is the page's own head.** Under each section's question an
  outline may hold the writer's orders for that section: what it must
  assert, what its figure must show, the why it must answer. Writing the
  section replaces them. A written section holds no order, no note and no
  "later".
- A written page cannot stand under an index that is still in outline, a
  written page has no empty section, and the contents page is written
  (**baked**).

## 5 · Sections

- **A section answers one question, and its heading says which.** Most
  headings are the question itself. Where a model's wrong belief has an
  error message, the message is the heading: that is what gets searched.
- **Its first sentence names its subject**, by the subject's own name. Not
  "it", not "this method", not "as above".
- **It stands alone.** It never leans on the section before it. A name
  that more than one module defines is given with its module inside the
  section that uses it (section 7). A reader handed this section and no
  other must be able to check every claim in it.
- **One fact, one home.** A fact is stated in full by the section that
  owns it. Another section that needs it says what its own story requires
  and links to the owner.
- **A section's address** is its heading in lower case, with spaces as
  hyphens and punctuation dropped: a dot goes, an underscore stays, so
  *Who calls `BaseHandler.get_response`?* is
  `#who-calls-basehandlerget_response`. A heading has words (**baked**),
  two headings on a page may not come to the same address (**baked**), and
  rewording a heading moves every link that lands on it.
- A page has a title, sections (`##`) and subsections (`###`), written
  with `#` and nothing deeper (**baked**).

How many sections a page has, in what order, and what shape the page
takes, are not ruled here. A department decides its own (section 11), and
a page takes the shape of what it explains.

## 6 · Claims and pointers

- **Every claim about the source carries a pointer**: the file and symbol,
  at the pinned commit, where the source does what the sentence says. How
  a pointer is written is the book's rule 6 and the head of
  `tools/pointers.py`.
- **One claim to a sentence**, as far as the prose bears it, so that a
  window of the page is a list of things that can be checked.
- **The pointer closes its sentence**, in parentheses before the full
  stop, unless it is the sentence's own subject or object:

  > `BaseHandler._middleware_chain` is `None` on the class (`django/core/handlers/base.py:BaseHandler._middleware_chain`).

  Two sentences that are one claim may share the pointer that closes the
  second. In a table, a row's pointer has a cell of its own.
- **A pointer names a symbol, not a line**: the smallest symbol that holds
  the statement the sentence is about. Several claims about several
  statements of one function carry the same pointer. A statement at a
  module's top level has no symbol of its own: point at the file.
- **A pointer names the place that does the thing**, not a place nearby:
  not the caller, not the subclass that inherits it, not the code that
  reads what another place sets. A pointer may land on an import only
  under a sentence that is about the import.
- **Say what the line does, in the code's own terms.** A claim survives
  checking by saying less. "A `WSGIHandler`" means every instance of every
  subclass; if the sentence is true of the class itself, it says "an
  instance of `WSGIHandler` itself". No "always", "only", "never", "every"
  or "by default" without the search that shows the whole population; no
  "otherwise" that was not read to the end of; no "so" the code does not
  bear out.
- **A page states no count that a tool can derive**: how many files,
  classes, lines or modules. Generated tables own the numbers. A numbered
  step in a table is not a count.
- **The book points and does not quote.** A page carries no excerpt of
  Django's source: the pointer is one step from the lines, a quoted line
  is a second copy that goes stale without anything failing, and prose
  that walks through quoted code is the line-by-line reading the book is
  not. What a page may show in a fenced block is what a reader would type
  (a scenario's few lines), what a run produced (a recording, the SQL a
  queryset came to), a figure's source, and the declaration of names made
  at runtime. A comment's reasoning is said in the page's words, with its
  pointer.
- **Newest version only.** The past is told in one place, the chapter of
  what a reader probably believes that is no longer true.
- **A correction to what a section asserts is made by rewriting the
  section** from its corrected claims with the source open, never by
  editing a sentence in place. A name, a pointer or a spelling is
  corrected where it stands.

**On the site a pointer is a link to the lines it lands on** at the
pinned commit, in the tree's own repository:
`.../blob/<commit>/<path>#L<first>-L<last>`, from a definition's first
decorator to its last line; a whole file links to the file, a directory
to the tree, and a name bound more than once (a property and its setter,
overloads before a definition) to the span from its first binding to its
last, each named in the link's title. The range is the pointer gate's
resolution, derived at the bake and written by hand nowhere. The
pointers in a `runtime-names` block are linked the same way. **In the
page's markdown twin a pointer stands as it is written**: the file is the
artefact, and an agent with the tree resolves a pointer in one step.

**The pointer gate's report of a page**, `<page>.pointers.json`, is
written beside the page by `python tools/pointers.py pages/` and
committed with it: generated, never edited. It is what a re-pin compares
(`python tools/pointers.py --check pages/`) to tell a symbol whose body
changed from one that only kept its name. The build reads the `.md` files,
the figures' `.svg` and a department's `figures/figures.css`, and nothing
else, so the reports do not disturb the book.

## 7 · Names and code spans

A code span holds a pointer, a name of the source, or code. This is the
book's rule 5 and the head of `tools/names.py`; what it comes to on a
page:

- A member is written on the class that declares it: `BaseHandler.load_middleware`,
  never `WSGIHandler.load_middleware`, and never a bare `load_middleware`.
  Where the code calls a method on an object whose class it does not fix,
  the sentence says which class's method runs, and why.
- A literal keeps its quotes inside the span: `"text/html"`, `"_meta"`,
  `"admin/base_site.html"`. Without them the gates take it for a pointer
  or a name. About three in a hundred of the code spans in Django's own
  documentation hold a slash and would be refused here; that is the price
  of no pointer going unchecked.
- **A word that is not a name of the source is not put in a code span.**
  That covers a parameter, a local variable, and an attribute that some
  code sets on an object from outside and no class declares: say it in
  words, write the call or the keyword (`is_async=True`), or quote it as
  a literal (the attribute named `"_has_been_logged"`). The gate cannot
  enforce all of this: a bare lower-case word passes when some module
  happens to define it at its top, as `request` does.
  `tools/names.py --spans` shows what each name was taken for.
- **A name that more than one module defines** is given with its module
  first, by a pointer or by writing it from its module, **in the section
  that uses it**: a pointer in another section does not bind it, and
  what stands above the first `##` is a section of its own. The build
  runs the name gate so (`tools/names.py --sections`; **baked**). A
  heading cannot be bound by what is under it, so such a name in a
  heading is written from its module
  (`django.db.backends.postgresql.base.DatabaseWrapper`), which the
  gate checks; only where the heading asks about the spelling itself is
  it quoted as a string (`"DatabaseWrapper"`), which no gate checks. A
  section is a top-level `##`: one inside a quotation or a list begins
  none.
- **A name made at runtime** is in no file's syntax tree: a metaclass, a
  descriptor or `setattr` makes it as the code runs, or it is a setting
  the defaults do not define. It is declared, with the pointer to code
  that makes it, in a fenced block:

  ````
  ```runtime-names
  Model._meta    django/db/models/options.py:Options.contribute_to_class    # after the #, anything
  ```
  ````

  One entry to a line: the name, on the class a reader knows it by; the
  pointer; then a remark. A block in `map/runtime-names.md` declares for
  the whole book. A block on a page declares for that page only, so while
  the book's list does not hold a name, every page that uses it declares
  it; the block may stand anywhere on the page, except that an entry on a
  class several modules define stands where that class is bound: in the
  section of a pointer into its file, or written from its module. Where
  more than one place makes the name, the entry points at one and its
  remark says so. Nothing can be checked after such a name: a member
  reached through it is written on its own class.
- **Names go in headings, ledes and first sentences**, not only in the
  body. Exact names are what an agent searches with.

## 8 · Figures

A figure is drawn before the bake and is a file. The site draws nothing in
the reader's browser.

````
```text figure=building-the-chain
WSGIHandler.__init__, when an instance of WSGIHandler itself is made
    calls BaseHandler.load_middleware
        ...
```

*What happens when an instance of `WSGIHandler` itself is made: the loop, and the assignment after it.*
````

- **In the markdown, a figure is its source**: a fenced block whose first
  word says what the source is (`text`, `mermaid`, `csv`, `json`) and
  which names the figure, `figure=<name>`. The source is what the figure
  was drawn from: the mermaid, the table, the rows of a recording. An
  agent reads the source; it is the figure, for that reader. The block
  stands by itself in its section, not inside a list or a quotation
  (**baked**), and its name is lower-case words joined by hyphens, once on
  its page (**baked**).
- **On the site, the figure is the SVG** at `figures/<name>.svg`, beside
  the page's file, put into the page in place of the block, with the
  source folded away under it. Its address is `#figure-<name>`.
- **The file is one well-formed `<svg>` element** with a `viewBox` and
  `class="fig"`, and it is held to what a page is held to: no script, no
  event handler, no `<style>`, `<image>`, `<iframe>` or `<foreignObject>`;
  nothing that moves (`<animate>` and its kin, `<set>`); no `href` that
  leaves the file, so a `<use>` or an `<a>` points at `#id` within it
  (**baked**).
- **A figure carries classes and no colour**: no `style`, `fill`,
  `stroke`, `color` or font attribute anywhere in the file (**baked**).
  The book's classes are in the site's stylesheet (`box`, `line`, `head`,
  `name`, `quiet`, `mark`, `mark-line`), so a figure follows the colours
  the reader has chosen, as the page does: the site has five palettes, and
  a figure is looked at in a light one and a dark one before its page is
  called written. A department adds its own classes (section 11).
- **The caption** is the paragraph directly under the block, one italic
  run from end to end (**baked**). It says what the picture shows, in the
  present tense, and never points at its own figure. A name in it is in a
  code span inside the italics. It is a claim, and is checked like one.
- **A figure never carries a fact the text does not.** Every label, arrow
  and number in it is said in the section it stands in, and what is drawn
  inside what agrees with what the section says happens inside what.
- **A figure answers one question** and shows what words carry badly: an
  order, a branch, a boundary, a containment, a quantity. If a table says
  it, it is a table.
- **It is legible where it stands.** One unit of the `viewBox` is one CSS
  pixel at the size it was drawn for. The stylesheet sets a figure's type
  at 14 pixels, and its names at 13: a figure is drawn so that its labels
  fit at that size. The text column is 646 pixels wide; a figure wider
  than that takes the margins, up to 988. On a narrow screen a figure
  shrinks to three quarters of its size and then scrolls sideways.
- A figure of a trace is drawn from a recording, never from reading.

The tools that draw figures and check the names inside them are not yet
built: nothing yet checks a name in a figure's source or in its SVG.
Until they are, a figure is drawn by hand to these rules and looked at
rendered, at the column's width and on a phone's, before its page is
called written.

## 9 · Tables and lists

A table is a figure in its own right here: Django is registries, option
tables and lookups, and a table is what both readers read best. It may be
wider than the text. A list holds parallel items; anything that explains
is prose.

## 10 · Links

- **A link to another page is the path of its `.md` file from the file
  the link is written in**, with the section's address after `#` where
  the answer is a section. From `pages/orm.md` the page
  `pages/orm/queries.md` is `orm/queries.md`; from `pages/orm/compiler.md`
  it is `queries.md`. So a link works in the repository and on disk as
  written, and the site turns it into the page's address (**baked**: the
  page exists, and so does the section or the figure, also for a link
  within one page and for a link to a page in outline).
- A link points from the page that assumes to the page that explains.
- A link to a page still in outline is allowed, and is shown as plain
  text marked as not yet written.
- A link out of the book is a full URL. A page of the book is never
  linked by its address on the site (**baked**).

## 11 · What is the same everywhere, and what is a department's own

**The apparatus is the site's, and identical on every page**: where the
page is in the book; the book's contents beside the page, with the page
marked and its own sections under it; the title and the lede; what it was
verified against; its status, in the site's words; what it is the home
of; the questions it answers; and at the foot, the pages before and
after, the licence, the disclaimer, and where to report an error. No page
writes any of it. The contents beside a page are derived from the heads,
like the contents page itself: a page in outline is there by its title,
with no address. The colours are the reader's choice among the site's
palettes (the reader's system decides until they choose), kept in their
browser by the site's one script; nothing a page says may depend on a
colour.

**A department has its own voice and its own figures.** Each part of
Django reads as a discipline a reader may already know: a database, a
compiler, a protocol, a state machine. Its pages are written in that
discipline's terms and drawn in its figures. What is a department's own,
and where it lives:

| | where |
|---|---|
| its claim | the lede of its landing page |
| the bridge: the version of this a reader of the discipline already knows, and what differs here | a section of its landing page |
| the names it owns at its edges | a section of its landing page |
| its figure grammar: the classes its figures use beyond the book's, and what each means | `figures/figures.css` in the department's directory, which the site adds to the department's pages; and a section of its landing page saying how to read its figures |
| its page shapes and its voice | decided when the department is planned, and visible in its first written page, which the rest are read against |

A department does not restyle the apparatus and has no colour of its own:
the book has one accent.

**A landing page** answers, for its department: what it asserts; what
discipline it reads as, and the bridge; which names it owns; how its
figures are read; where one request through the whole system enters it and
leaves it; which scenarios its pages follow. **The list of its pages is
not written on it**, in a table or in prose: the site derives it from
`contents` and the pages' own heads, and a list written by hand is stale
the day a page is added. (The specimen's landing pages are short: a claim
and how to read the figures. They are not departments.)

**A collection**, such as the chapter of what a reader probably believes
that is no longer true, closes entry by entry. Each entry is a section
that states the belief, the truth at the pin, the pointer, and since which
release.

## 12 · What the build refuses, in one place

`python manage.py bake` reads the whole book and refuses it whole, with
each problem as `file:line: what is wrong`.

- *The front matter*: none; a line that is not `key: value`; a key that
  is not one of the four, or given twice; a value that needs quotes and
  has none, or whose quotes do not close; no `django` or no `status`; a
  `django` line without the pinned commit; a status that is not one of
  the three; `owns` that is not names in code spans; a name with two
  homes.
- *The tree*: no contents page, or one in outline; a child in `contents`
  with no file, named twice, or with a name that is not lower-case words,
  is `index` or `404` anywhere, or is `static` at the top; a file in no
  `contents`; a written page under an outlined index; a department's
  `figures/figures.css` that holds anything but classes (`<`, `url(`,
  `@import`).
- *The body*: no title, no lede, or two titles; a heading below `###`,
  written by underlining, or with no words; two headings with one
  address, or a heading whose address begins `figure-`; raw HTML, a
  comment included; an image; an empty section on a written page.
- *Links*: to a page that is not there; not by the path of its file; to
  the book by its address on the site, under any of the site's hosts; to
  a section or a figure its target lacks.
- *Figures*: no SVG; an SVG that is not one well-formed element with a
  `viewBox` and `class="fig"`; a script, a handler, something that loads
  or moves, or an `href` that leaves the file; a colour or a font of its
  own; no caption, or one that is not one italic run; a name that is not
  lower-case words, or used twice on a page; a figure inside a list or a
  quotation.
- *The gates*, run on every page, outlined pages included, each refusal
  in the gate's own words: a pointer that is not well formed or does not
  resolve at the pin (`tools/pointers.py`); a name no pinned tree
  declares, written on a class that does not declare it, or defined by
  several modules and bound by no pointer in its section; a declaration
  of a runtime-made name whose pointer does not resolve, or of a name
  the source declares (`tools/names.py --sections`).
- *What was written*, after the pages are baked: a link in a page, a
  twin, `llms.txt`, `llms-full.txt` or `sitemap.xml` that resolves to no
  file as the host serves the directory, or to no id, heading or figure
  in its target (`tools/links.py`). The bake fails after writing.

It does not check anything about what a sentence means: a page's
status, a section's first sentence, a count, a quoted excerpt of source,
an order left in a written section, or whether a pointer names the place
that does what the sentence says. Those are the writer's and the
checker's.

## 13 · Checking a page

With the project's Python (`.venv`; on this book's machine
`.venv/Scripts/python.exe` in place of `python`):

```
python manage.py bake --book specimen        the build: refuses, or bakes to dist/ the pages, their twins,
                                             llms.txt, index.json, names.json, 404.html, robots.txt, _headers
                                             and the static files (for pages/ also llms-full.txt and
                                             sitemap.xml), then runs the link gate over what it wrote
python manage.py bake --book DIR --out DIR   another book, to another place
python manage.py preview                     dist/ served on this machine as Cloudflare Pages serves it
python manage.py deploy [--book DIR] [--branch B] [--dry-run]
                                             the committed reports checked, the bake, the upload, and every
                                             file fetched back and compared; it stops at the first failure
python tools/pointers.py pages/              every pointer resolves at the pin; a report written beside each page
python tools/pointers.py --check pages/      the committed reports are what the gate writes now
python tools/names.py --sections pages/      every name in a code span exists, bound within its section
python tools/names.py --spans PAGE.md        what each code span was taken for
python tools/links.py --site https://djangointernals.dev dist
                                             every link in the baked site resolves (the bake runs it; by hand,
                                             give it the site's address, which the specimen's pages do not carry)
python manage.py runserver                   the book as it stands, read again at each save: the pages, the
                                             twins and the agent's files alike
```

`python manage.py bake` with no `--book` bakes `pages/`, and refuses until
`pages/index.md` exists. `runserver` serves `pages/` too; to serve another
book, set `BOOK` in the environment to its directory (`BOOK=specimen`).
Both need the pinned trees on disk (`python tools/pin.py fetch`): the
gates run inside the build. The baked site is static files, laid out for a
host that serves `orm/queries.html` at `/orm/queries` and
`orm/queries.md` beside it, which is what `preview` does on this machine.
