# The page

*What a page of* Django Internals *is: as a file, and as something a reader
meets. The book's rules are in [CLAUDE.md](CLAUDE.md); this is what they
come to on a page. The site's build holds a page to everything here that a
program can read (`python manage.py bake`; the last section but one lists
what it refuses). The rest is the writer's and the checker's.*

## Two readers, one file

A page is a markdown file, and the file is the book. The site renders it
for a person; an agent reads the file itself, served at the page's address
with `.md` after it. So nothing the rendering adds may carry a fact, and
nothing in the file may depend on being rendered: no raw HTML, no image, no
script.

A person comes in at the contents and reads down. An agent lands in the
middle of a page, on the name it searched for, and is often handed one
section and nothing else. A page is written so that both work.

**A page is about Django and nothing else.** It says nothing about how the
book is made or how far it has got, nothing about the site, and nothing
about its own conventions: no status, no note to a later writer, no "to be
written", no instructions for reading the book.

## Where a page lives

The book is the directory `pages/`. `pages/index.md` is its front page. The
pages directly under it are the **chapters**; the pages under a chapter are
its **sections**; there is nothing deeper.

| | for `pages/handlers/chain.md` |
|---|---|
| id | `handlers/chain` |
| address | `/handlers/chain` |
| the file itself, as markdown | `/handlers/chain.md` |
| a heading on it | `/handlers/chain#the-loop` |

A page lists its children in its front matter: `contents: entry, chain` in
`pages/handlers.md` makes `pages/handlers/entry.md` and
`pages/handlers/chain.md` its sections, in that order. Adding a page is
writing its file and adding its name there; nothing else lists it. A name
is lower-case words joined by hyphens, and once a page is published its
name is permanent: an address is a promise. Where a page has to move all
the same, its old address is listed in `pages/_redirects` with the new one,
and the site answers the old with a redirect.

**A page that is only its title and one paragraph is planned, not
written.** It has a line in the contents, and no page and no address until
it has more. A chapter's opening page must be written before any of its
sections is.

The numbers are the site's: a chapter's from its place in the book, a
section's from its place in its chapter (`4.2`), a figure's and a captioned
table's from their place in their chapter (`Figure 4.3`). No page writes a
number, and a page refers to another by its title.

## The head

```
---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The request cycle
contents: entry, chain, view, exceptions, async
---

# Handlers and middleware

One paragraph: what this page is about.

The introduction, down to the first heading.

## The first heading
```

**The front matter** is one `key: value` to a line.

| key | | |
|---|---|---|
| `django` | required | which Django the page describes: the release in words, and the pinned commit of `pin.json` spelt out. A page that points into a pinned library names its release too (`; asgiref 3.12.1`) |
| `part` | on a chapter | the part of the book the chapter is in. Chapters that follow one another with the same part are shown under it |
| `contents` | on a page with children | their names, in reading order |

A value is plain text, written in double quotes when it begins with
anything but a letter or a digit, or holds a colon followed by a space.

**The title** is the page's one `#` heading. It names the subject. It is
also the text of every link to the page, so it holds no name that several
modules define (`Field`, `Options`): the name gate would ask for a pointer
beside each link.

**The lede** is the first paragraph: one to three sentences that say what
the page is about, with the names a reader would search for. It is what the
contents, the chapter's outline and `llms.txt` say of the page.

**The introduction** is whatever else stands above the first `##`.

## How a page is written

The standard is a university textbook. A page explains.

- **Start from what the system has to do**, give the model before the
  detail, tell things in the order that makes them understood, and say why.
  A paragraph that restates a function line by line has explained nothing
  the source does not say better.
- **A chapter's opening page gives a working model of the whole system**:
  what it is for, the few objects that carry it, its main flow in order,
  and where it meets its neighbours. A reader who stops there should be
  able to say how the system works. The sections go deeper, one subject
  each.
- **A heading names its subject**, in plain words, with the exact name of
  a class or a function where that is what a reader would search for. A
  question is a heading only when the question is the best title.
- **A section can be read alone.** Its first sentence names its subject by
  name, not "it" or "this method", because a reader may be handed that
  section and no other.
- **Prose first.** A list is for parallel items or a true sequence, a
  table for something a reader looks up. No device appears on every page:
  a page takes the shape of what it explains.
- **A term is defined where it is first used**, in bold.
- **A note** is a quotation that opens with its label in bold:
  `> **Changed in 6.2.** …`, `> **Why.** …`. It is for what stands beside
  the main line: what changed between releases, the reason behind a
  design, a trap. Used sparingly.
- **Newest version only.** What a reader may believe from an older release
  is corrected in a note where it matters, and collected in the last
  chapter.
- **No count that a tool can derive**: how many files, classes or lines.

## Names and code spans

A code span holds a name of the source, a pointer, or code.

- **A name exists at the pin.** `python tools/names.py` checks every one.
- **A member is written on the class that declares it** where a section
  first names it: `BaseHandler.load_middleware`, never
  `WSGIHandler.load_middleware`, which only inherits it. After that the
  section may write it bare, `load_middleware`. The gate checks that a
  qualified name is declared by that very class, and that a bare one is a
  member some class declares.
- **A literal keeps its quotes inside the span**: `"text/html"`,
  `"ATOMIC_REQUESTS"`. Without them the gates take it for a name or a
  pointer.
- **A word that is not a name of the source is not put in a code span**: a
  parameter, a local variable, the made-up names of an example. An
  attribute is written on its class or bare (`WSGIRequest.GET`, `GET`),
  not on a variable that holds an instance.
- **An HTTP header's name of one word is a literal**, `"Host"`,
  `"Cookie"`, as is a method, `"POST"`. A name with a hyphen cannot be
  taken for a name of the source and is written plain: `Content-Type`.
- **A name that several modules define** (`DatabaseWrapper`) is given with
  its module, or after a pointer into its file, in the section that uses
  it.
- **A name that exists only as the code runs** (made by a metaclass, a
  descriptor, `setattr`, or looked up by `getattr` and declared by no
  class) is listed in `map/runtime-names.md` with a pointer to the code
  that makes or reads it.

## Pointers

A pointer says where in the source a passage's subject is. It is written in
a code span as `path:Symbol`: the path from the tree's root, a colon, the
symbol dotted from module level. A bare path is a whole file; a final
slash, a directory; a library's tree is named first.

```
django/core/handlers/base.py:BaseHandler.load_middleware
django/conf/global_settings.py
django/core/handlers/
asgiref:asgiref/sync.py:sync_to_async
```

- **A pointer follows what it supports, in parentheses**, before the full
  stop or after the paragraph's last sentence. On the site the parenthesis
  leaves the sentence: the pointers of a paragraph stand beside it, in the
  margin, each a link to its lines at the pinned commit. In the markdown
  they stay where they were written.
- **Every mechanism a page describes has a pointer near it.** The grain is
  where a reader would go to look: usually one or two to a paragraph, not
  one to a sentence.
- **A pointer names the place that does the thing**, not the caller, not a
  subclass that inherits it, not a place nearby.
- **The book points and does not quote.** A page carries no excerpt of
  Django's source: the pointer is one step from the lines, and a quoted
  line goes stale without anything failing. A fenced block holds what a
  reader would type, what a run produced, or a figure's source.
- `python tools/pointers.py pages/` checks every pointer and writes
  `<page>.pointers.json` beside each page: the lines each lands on and a
  fingerprint of them, which is what a re-pin compares. The reports are
  committed with the pages and never edited.

## Recordings

Where the order of calls is the point, the page shows a recording from a
running Django, not an order inferred by reading. A chapter's recordings
are made by a script, `recordings/<chapter>.py`, whose output is committed
beside it as `recordings/<chapter>.txt`; a recording that needs a project
keeps it in a directory beside the script. The output is blocks: a title
at the left margin, and the lines recorded under it, indented, to the next
blank line.

A page quotes the output in a fenced block that names the recording,
`recording=<chapter>` after the block's kind, and the quote is held to the
output (`python tools/recordings.py`): its lines are the lines of one
block, in the block's order and with the block's nesting, and nothing is
altered, added or moved. A quote may leave lines out, and says so: in the
prose beside it, or with a line of three dots where they were. An excerpt
from inside a block may be shifted left as a whole.

````
```text recording=handlers
WSGI, GET /plain/: a view that returns a response
    signal: request_started
    A.process_request
```
````

## Figures

A figure shows what words carry badly: an order, a nesting, a boundary, a
crossing. If a table says it, it is a table.

````
```text figure=the-chain
MIDDLEWARE = [A, B, C]
request  ->  A  ->  B  ->  C  ->  the view
```

*With three middleware, a request enters at A and reaches the view through B and C.*
````

- **In the markdown a figure is its source**: a fenced block that says
  what kind of text it holds and names the figure, `figure=<name>`. An
  agent reads the source; for that reader it is the figure. So the source
  says everything the drawing does.
- **On the site the figure is the SVG** `pages/<chapter>/figures/<name>.svg`
  (`pages/figures/` for the front page), put into the page in place of the
  block. Its address is `#figure-<name>`.
- **The caption** is the paragraph directly under the block, one italic
  run. It says what the picture shows.
- **A figure never carries a fact the text does not**, and a figure of a
  flow is drawn from a recording.
- **The file is one `<svg>` element** with a `viewBox` and `class="fig"`:
  no script, nothing that loads or moves, no link out of itself.
- **It carries classes and no colour or font of its own**, so that it
  follows the reader's palette with the page. The site's stylesheet has
  the classes (`box`, `ground`, `mark-box`, `line`, `dashed`, `mark-line`,
  `head`, `mark`, `name`, `quiet`, `strong`, `small`); a chapter may add
  its own in `pages/<chapter>/figures/figures.css`.
- **It is legible where it stands.** One unit of the `viewBox` is one CSS
  pixel. The text column is 646 pixels wide; a wider figure runs into the
  margin, up to about 940. Type in a figure is 14 pixels, names 13.
- **It is looked at rendered**, in a light palette and a dark one, at a
  desktop's width and a phone's, before its page is published.

## Tables

A table is ruled above and below and may run into the margin. An italic
paragraph directly under a table is its caption, and gives it a number. A
pointer in a table cell is shown with its file under it.

A narrow screen has no room for a table of three columns or more, and sets
it row by row: a row's first cell stands alone as the row's name, and each
cell after it beside the heading of its column. So a row's first cell says
what the row is about, and a heading reads sensibly beside one cell.

## Links

- A link to another page is the path of its `.md` file from the file the
  link is written in, with `#` and a heading's address where the answer is
  a section. It works in the repository as written, and the site turns it
  into the page's address.
- A heading's address is its text in lower case, spaces as hyphens,
  punctuation dropped. Rewording a heading moves every link that lands on
  it, and the build refuses a link that lands on nothing.
- A link to a planned page is allowed, and is shown as plain text until
  the page is written.
- A link out of the book is a full URL.

## What the build refuses

`python manage.py bake` reads the whole book and refuses it whole, with
each problem as `file:line: what is wrong`. `python manage.py bake --probe`
proves each refusal.

- *The front matter*: none; a line that is not `key: value`; a key that is
  not one of the three, or given twice; a value that needs quotes and has
  none; no `django`, or one without the pinned commit; `part` on a page
  that is not a chapter.
- *The tree*: no front page, or one with nothing on it; a child with no
  file, named twice, or with a name that is not lower-case words (or is
  `index`, `404`, or at the top `static`); a file no `contents` names; a
  page under a section; a written page under a planned one.
- *The body*: no title, no lede, or two titles; a heading below `###`,
  written by underlining, or with no words; two headings with one address;
  raw HTML, a comment included; an image; a section with nothing in it.
- *Links*: to a page that is not there; not by the path of its file; to
  the book by its address on the site; to a heading or a figure its target
  lacks.
- *Figures*: no SVG; an SVG that is not one well-formed element with a
  `viewBox` and `class="fig"`; a script, a handler, something that loads
  or moves, a link out; a colour or a font of its own; no caption; a name
  that is not lower-case words, or used twice on a page; a figure inside a
  list or a quotation.
- *The gates*, on every page: a pointer that does not resolve at the pin
  (`tools/pointers.py`); a name no pinned tree declares, or written on a
  class that does not declare it, or defined by several modules and bound
  by nothing in its section (`tools/names.py --sections`); a quote of a
  recording that names one there is no output for, or whose lines are not
  one block's in its order and nesting (`tools/recordings.py`).
- *What was written*: a link in a baked page, a twin, `llms.txt` or the
  sitemap that resolves to no file or no heading (`tools/links.py`).

It does not check what a sentence means: whether a page is right, whether
a pointer names the place that does what its passage says, whether a page
explains. Those are the writer's and the checker's.

## Checking a page

With the project's Python (`.venv`; on Windows `.venv/Scripts/python.exe`
in place of `python`):

```
python manage.py bake                        the build: refuses, or bakes pages/ to dist/
python manage.py bake --probe                proves every refusal, and what a bake writes
python manage.py runserver                   the book as it stands, read again at each save
python manage.py preview                     dist/ served as Cloudflare Pages serves it
python manage.py deploy [--dry-run]          the reports checked, the bake, the upload, every file fetched back
python tools/pointers.py pages/              every pointer resolves; a report written beside each page
python tools/pointers.py --check pages/      the committed reports are what the gate writes now
python tools/names.py --sections pages/      every name in a code span exists
python tools/names.py --spans PAGE.md        what each code span was taken for
python tools/recordings.py pages/            every quote of a recording is one block's lines, in order, nesting kept
python recordings/handlers.py                a chapter's recording, to compare with the committed output
```

All of them need the pinned trees on disk (`python tools/pin.py fetch`).
