"""Bake the book: every page requested through Django and written to a file, with the agent's files beside it.

    python manage.py bake                    pages/ -> dist/
    python manage.py bake --book DIR         another directory of pages -> dist/
    python manage.py bake --out DIR          somewhere other than dist/
    python manage.py bake --probe            prove the bake refuses what it should, and writes what it should

The book is read whole first (djangointernals/book.py), the two gates run
on every page (gates.py), and a book with a problem is refused whole: every
problem is printed as `file:line: what is wrong`, nothing is written, and
the command fails. Then each written page is requested with Django's test
client, so that what is baked is what the running site answers, and its
response is written as `<id>.html` (`index.html` for the front page); beside
it its twin, `<id>.md`, the page's file as it is. A planned page (a title
and a line) gets no file: it is a line in the contents. Then the agent's
files (doors.py): `llms.txt`, `index.json`, `names.json`, and when the book
is indexable `llms-full.txt` and `sitemap.xml`; `404.html`; `robots.txt`;
Cloudflare Pages's `_headers`, and its `_redirects` when the book has a
file of that name (each address in it must lead to a page that was
written); and the static files (an editor's backup, a
hidden file and `CVS` left out, as `collectstatic` leaves them). Every page
carries the book's contents beside it and the choice of colours (views.py),
which the probe checks as it checks the rest of what a bake writes. Last, the
link gate (tools/links.py) runs over everything written, and the bake
fails if a link in it does not resolve.

The site is written beside the output directory first and moved into place
only when the link gate has passed, so a failed bake leaves no site behind.
The output directory must be one this command made (it holds the marker
`.baked`) or be empty or absent: the bake deletes nothing it did not write.

What a page's file is called is what Cloudflare Pages serves at the page's
URL: `orm/queries.html` at `/orm/queries`, `orm/queries.md` at `/orm/queries.md`.
"""
import json
import re
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.test import Client, RequestFactory

from djangointernals import book as books
from djangointernals import doors
from djangointernals import gates as gating
from djangointernals import views

MARKER = ".baked"
AGENT_FILES = ("llms.txt", "index.json", "names.json")
INDEXABLE_FILES = ("llms-full.txt", "sitemap.xml")
IGNORED_STATIC = ["CVS", ".*", "*~"]  # what collectstatic leaves out
PALETTE = re.compile(r':root\[data-colours="([a-z]+)"\]')  # a palette of the stylesheet, by the choice that puts it on
SECTION_SIGN = chr(0xA7)  # the site prints none, and the probe says so; written by its number so that this file holds none


class Command(BaseCommand):
    help = "Bake the book to static files, or refuse it and say why."

    def add_arguments(self, parser):
        parser.add_argument("--book", help="the directory of pages to bake (default: pages)")
        parser.add_argument("--out", help="where to write (default: dist)")
        parser.add_argument("--probe", action="store_true", help="prove the bake refuses what it should")

    def handle(self, *args, **options):
        if options["probe"]:
            return self.probe()
        if options["book"]:
            settings.BOOK_DIR = (settings.BASE_DIR / options["book"]).resolve()
        out = (settings.BASE_DIR / (options["out"] or settings.DIST_DIR)).resolve()
        try:
            book = books.load(settings.BOOK_DIR)
        except books.Refused as refused:
            for problem in refused.problems:
                self.stderr.write(problem)
            raise CommandError(f"bake: REFUSED, {len(refused.problems)} problem{'s' if len(refused.problems) != 1 else ''}; nothing was written")
        written, counts = self.write(book, out)
        planned = sum(1 for page in book.order if not page.published)
        self.stdout.write(f"bake: ok, {written} page{'s' if written != 1 else ''} written to {books.shown(out)} with their twins, "
                          f"{', '.join(AGENT_FILES + (INDEXABLE_FILES if views.indexable() else ()))}, and every one of {counts['links']} "
                          f"links resolving" + (f" ({counts['outlined']} to a planned page)" if counts["outlined"] else "")
                          + (f"; {planned} planned, as lines in the contents" if planned else ""))

    def write(self, book, out: Path) -> tuple[int, dict]:
        """Write `book` beside `out`, gate it, and move it into `out`: -> (pages written, the
        link gate's counts). The views serve the book at settings.BOOK_DIR, so for as long as
        this runs that is `book`'s own directory."""
        if out.exists() and any(out.iterdir()) and not (out / MARKER).is_file():
            raise CommandError(f"bake: {out} is not empty and was not made by this command (it has no {MARKER}): not touched")
        baking = out.parent / f"{out.name}.baking"
        if baking.exists():
            shutil.rmtree(baking)
        before, settings.BOOK_DIR = settings.BOOK_DIR, book.root
        try:
            written = self.written(book, baking)
            counts = self.gate(baking)
        except BaseException:
            shutil.rmtree(baking, ignore_errors=True)
            raise
        finally:
            settings.BOOK_DIR = before
        if out.exists():
            shutil.rmtree(out)
        baking.rename(out)
        return written, counts

    def written(self, book, out: Path) -> int:
        out.mkdir(parents=True)
        (out / MARKER).write_text("Made by `python manage.py bake`, and emptied by it before each bake.\n", encoding="utf-8")
        client = Client()

        def fetch(url: str, target: Path) -> None:
            response = client.get(url)
            if response.status_code != 200:
                raise CommandError(f"bake: {url} answered {response.status_code}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.content)

        written = 0
        for page in book.order:
            if not page.published:
                continue
            fetch(page.url, out / f"{page.id or 'index'}.html")
            fetch(doors.twin_url(page), out / doors.twin_path(page))
            written += 1
        for name in AGENT_FILES + (INDEXABLE_FILES if views.indexable() else ()):
            fetch(f"/{name}", out / name)
        fetch("/robots.txt", out / "robots.txt")
        # Not requested like the pages: with DEBUG on, Django answers a missing page itself.
        (out / "404.html").write_bytes(views.not_found(RequestFactory().get("/404")).content)
        (out / "_headers").write_text(doors.headers(views.indexable()), encoding="utf-8", newline="\n")
        # The addresses that have moved: each must lead to a page or a twin that was just written.
        moved = doors.redirects(book)
        for old, new in moved:
            target = out / (new.lstrip("/") if new.endswith(".md") else f"{new.strip('/') or 'index'}.html")
            if not old.startswith("/") or not new.startswith("/") or not target.is_file():
                raise CommandError(f"bake: {books.shown(book.root / '_redirects')}: `{old}` is sent to `{new}`, and "
                                   f"that is no page of this book (a line is `/old /new 301`)")
        if moved:
            shutil.copyfile(book.root / "_redirects", out / "_redirects")
        # The static files, found as `runserver` finds them and copied beside the pages.
        # Not `collectstatic`: that writes to one directory fixed in the settings, not to `out`.
        for finder in finders.get_finders():
            for path, storage in finder.list(IGNORED_STATIC):
                target = out / "static" / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(storage.path(path), target)
        return written

    def gate(self, out: Path) -> dict:
        """The link gate over what was written: a link that does not resolve fails the bake."""
        faults, counts = gating.links.check(str(out), settings.SITE_URL)
        for fault in faults:
            self.stderr.write(f"{books.shown(out)}/{fault}")
        if faults:
            raise CommandError(f"bake: the link gate FAILED on what was written: {len(faults)} link"
                               f"{'s' if len(faults) != 1 else ''} in it do{'es' if len(faults) == 1 else ''} not resolve; nothing was kept")
        return counts

    # -- the probe -----------------------------------------------------------

    def probe(self):
        """Bake small books, each with one thing wrong, and check each is refused for it; bake
        a good one and check what is written."""
        pin = json.loads(Path(settings.PIN_FILE).read_text(encoding="utf-8"))
        commit = pin["trees"][pin["subject"]]["commit"]
        head = f"---\ndjango: main at {commit}; asgiref 3.12.1\n---\n"

        def headed(**keys) -> str:
            return head.replace("---\n", "---\n" + "".join(f"{key}: {value}\n" for key, value in keys.items()), 1)

        pointer = "django/core/handlers/base.py:BaseHandler.load_middleware"
        written_page = "# D\n\nLede.\n\n## Section\n\nText.\n"
        good = {
            "index.md": headed(contents="a, b, p")
                        + "# A book\n\nIts lede, which links [A](a.md).\n\nA preface.\n\n## One\n\nText, [a link](a.md#first) and [one to a planned page](b.md).\n",
            "a.md": headed(part="First")
                    + f"# A\n\nLede.\n\n## First\n\nHow the chain is built (`{pointer}`). A call, `import_string(\"x\")`; a library's, "
                      f"`asgiref:asgiref/sync.py:SyncToAsync`; a directory, `django/core/handlers/`; a file, `django/core/handlers/wsgi.py`; "
                      f"a member by itself, `load_middleware`.\n\n"
                      "```runtime-names\nModel._meta  django/db/models/options.py:Options.contribute_to_class\n```\n",
            "b.md": head + "# B\n\nLede of B.\n",
            "p.md": headed(part="Second", contents="c") + "# P\n\nLede of P.\n\n## Only\n\nText.\n",
            "p/c.md": head + "# C\n\nLede of C.\n\n## What `django/core/handlers/base.py:BaseHandler.get_response` does, and [A](../a.md)?\n\nText.\n",
            "_redirects": "# addresses that have moved\n/old /a 301\n/old.md /a.md 301\n/old/* /p/c 301\n/first / 301\n",
        }
        figure = good["a.md"] + "\n```text figure=one\nx\n```\n\n*A caption.*\n"
        svg = '<svg xmlns="http://www.w3.org/2000/svg" class="fig" viewBox="0 0 10 10"><rect class="box" width="5" height="5"/></svg>'
        drawn = "a/figures/one.svg"
        with_figure = {**good, "a.md": figure + "\n| x | y |\n|---|---|\n| 1 | 2 |\n\n*What the table shows.*\n\n> **Why.** A reason.\n\n> Somebody's words.\n",
                       drawn: svg}
        plain = head + "# A\n\nLede.\n\n## First\n\nText.\n"
        cases = [
            ("a page with no front matter", {"a.md": "# A\n\nLede.\n\n## First\n\nText.\n"}, "begins with its front matter"),
            ("a key the front matter does not have", {"a.md": good["a.md"].replace("django:", "status: verified\ndjango:")}, "is not a key"),
            ("a value a YAML reader would trip on", {"a.md": good["a.md"].replace(f"main at {commit}", f"`main` at {commit}")}, "in double quotes"),
            ("a `django` line without the pinned commit", {"a.md": plain.replace(commit, "0" * 40)}, "does not spell out the pinned commit"),
            ("a page with no title", {"a.md": head + "Lede.\n\n## First\n\nText.\n"}, "opens with its title"),
            ("a page with no lede", {"a.md": head + "# A\n\n## First\n\nText.\n"}, "has its lede"),
            ("two titles", {"a.md": good["a.md"] + "\n# Again\n"}, "a second # heading"),
            ("a heading below ###", {"a.md": good["a.md"] + "\n#### Deep\n\nText.\n"}, "nothing below ###"),
            ("two headings with one anchor", {"a.md": good["a.md"] + "\n## First\n\nText.\n"}, "come to the anchor"),
            ("a heading whose address is a figure's", {"a.md": figure + "\n## Figure one\n\nText.\n", drawn: svg}, "begins `figure-`"),
            ("raw HTML", {"a.md": good["a.md"] + "\n<div>x</div>\n"}, "raw HTML"),
            ("a comment", {"a.md": good["a.md"] + "\n<!-- later -->\n"}, "raw HTML"),
            ("an image", {"a.md": good["a.md"] + "\n![x](x.png)\n"}, "an image"),
            ("an empty section", {"a.md": good["a.md"] + "\n## Empty\n"}, "nothing under it"),
            ("a link to a page that is not there", {"a.md": good["a.md"] + "\n[x](d.md)\n"}, "no such page"),
            ("a link by URL to a page of the book", {"a.md": good["a.md"] + "\n[x](/b)\n"}, "the path of its .md file"),
            ("a link out of the book with no scheme", {"a.md": good["a.md"] + "\n[x](www.example.com)\n"}, "is a full URL"),
            ("a link written from the wrong directory", {"a.md": good["a.md"] + "\n[x](sub/b.md)\n"}, "this one comes to sub/b.md"),
            ("a link to an anchor its target lacks", {"index.md": good["index.md"].replace("#first", "#second")}, "has no heading or figure"),
            ("a child with no file", {"index.md": good["index.md"].replace("contents: a, b", "contents: a, b, d")}, "there is no"),
            ("a file in no contents", {"d.md": head + written_page}, "names this file"),
            ("a written page under a planned one", {"b.md": headed(contents="d") + "# B\n\nLede of B.\n", "b/d.md": head + written_page},
             "only a title and a line"),
            ("`part` on a page that is not a chapter", {"p/c.md": good["p/c.md"].replace("django:", "part: Third\ndjango:")}, "`part` is a chapter's"),
            ("a page under a section", {"p/c.md": good["p/c.md"].replace("django:", "contents: e\ndjango:"), "p/c/e.md": head + written_page},
             "nothing deeper"),
            ("a figure with no SVG", {"a.md": figure}, "there is no"),
            ("a figure with no caption", {"a.md": figure.replace("*A caption.*", "Not a caption."), drawn: svg}, "its caption is"),
            ("a figure that is not one SVG with a viewBox", {"a.md": figure, drawn: "<svg></svg>"}, "with a viewBox"),
            ("a figure of two elements", {"a.md": figure, drawn: svg + "<p>more</p>"}, "not well-formed"),
            ("a figure with a script", {"a.md": figure, drawn: svg.replace("<rect", "<script>x</script><rect")}, "carries no script"),
            ("a figure with a handler", {"a.md": figure, drawn: svg.replace("<rect", '<rect onload="x"')}, "carries no script"),
            ("a figure that loads an image", {"a.md": figure, drawn: svg.replace("<rect", '<image href="x.png"/><rect')}, "loads nothing"),
            ("a figure that moves", {"a.md": figure, drawn: svg.replace("<rect", '<animate attributeName="x"/><rect')}, "does not move"),
            ("a figure with a frame in it", {"a.md": figure, drawn: svg.replace("<rect", '<iframe/><rect')}, "loads nothing"),
            ("a figure that links out of itself", {"a.md": figure, drawn: svg.replace("<rect", '<a href="javascript:alert(1)"><rect/></a><rect')},
             "links nowhere outside itself"),
            ("a figure whose <use> loads from elsewhere", {"a.md": figure, drawn: svg.replace("<rect", '<use href="https://example.org/x.svg#a"/><rect')},
             "links nowhere outside itself"),
            ("a figure with a colour of its own", {"a.md": figure, drawn: svg.replace("<rect", '<rect fill="red"')}, "no colour or font"),
            ("a figure without the class the stylesheet draws by", {"a.md": figure, drawn: svg.replace(' class="fig"', "")}, 'class="fig"'),
            ("a figure named in capitals", {"a.md": figure.replace("figure=one", "figure=One"), "a/figures/One.svg": svg}, "a figure's name is"),
            ("two figures of one name", {"a.md": figure + "\n```text figure=one\ny\n```\n\n*Another caption.*\n", drawn: svg}, "another of that name"),
            ("a figure inside a list", {"a.md": good["a.md"] + "\n- item\n\n  ```text figure=one\n  x\n  ```\n\n  *A caption.*\n", drawn: svg},
             "stands by itself"),
            ("a chapter's figure stylesheet with a script in it", {"a/figures/figures.css": ".fig .x {}\n</style><script>alert(1)</script>\n"},
             "classes and nothing else"),
            ("a heading written by underlining", {"a.md": good["a.md"] + "\nSecond\n------\n\nText.\n"}, "not by underlining"),
            ("a heading with no words", {"a.md": good["a.md"] + "\n## ?\n\nText.\n"}, "no words in it"),
            ("a key given twice", {"a.md": good["a.md"].replace("part: First", "part: First\npart: First")}, "given twice"),
            ("a quoted value that does not close", {"a.md": good["a.md"].replace("part: First", 'part: "First')}, "from end to end"),
            ("a child's name in capitals", {"index.md": good["index.md"].replace("contents: a, b", "contents: a, b, C")}, "lower-case words"),
            ("a child named for the site's own paths", {"index.md": good["index.md"].replace("contents: a, b", "contents: a, b, static")}, "not static"),
            ("a child named index, in a chapter", {"p.md": good["p.md"].replace("contents: c", "contents: c, index")}, "never 404 or index"),
            ("a child named 404, in a chapter", {"p.md": good["p.md"].replace("contents: c", "contents: c, 404")}, "never 404 or index"),
            ("a child named twice", {"index.md": good["index.md"].replace("contents: a, b", "contents: a, b, a")}, "twice"),
            ("a front page with nothing on it", {"index.md": headed(contents="a, b") + "# A book\n\nIts lede.\n", "a.md": head + "# A\n\nLede.\n",
                                                 "p.md": None, "p/c.md": None}, "nothing to publish"),
            ("a link to an anchor its own page lacks", {"a.md": good["a.md"] + "\n[x](#second)\n"}, "has no heading or figure"),
            ("a link to an anchor a planned page lacks", {"a.md": good["a.md"] + "\n[x](b.md#second)\n"}, "has no heading or figure"),
            ("a link to the book by its address on the site", {"a.md": good["a.md"] + f"\n[x]({settings.SITE_URL}/b)\n"}, "not its address on the site"),
            ("a link to the book by its www address", {"a.md": good["a.md"] + f"\n[x]({settings.SITE_URL.replace('://', '://www.')}/b)\n"}, "not its address on the site"),
            ("a link to the book by http", {"a.md": good["a.md"] + f"\n[x]({settings.SITE_URL.replace('https://', 'http://')}/b)\n"}, "not its address on the site"),
            ("a link to the book by its pages.dev address", {"a.md": good["a.md"] + f"\n[x](https://{settings.PAGES_PROJECT}.pages.dev/b)\n"},
             "not its address on the site"),
            # the gates, run by the loader on every page
            ("a pointer that does not resolve", {"a.md": good["a.md"].replace("A call,", "And `django/nope.py:Nope`. A call,")}, "holds no file"),
            ("a name that does not exist", {"a.md": good["a.md"] + "\n`QuerySet._fetch_al`\n"}, "binds no"),
            ("a member by itself that no class declares", {"a.md": good["a.md"] + "\n`load_middlewares`\n"}, "no module of"),
            ("a name several files define, bound by a pointer in an earlier section only", {
                "a.md": good["a.md"] + "\n`django/db/backends/sqlite3/base.py:DatabaseWrapper`\n\n## Second\n\n`DatabaseWrapper.get_new_connection`\n"},
             "in this section"),
            ("a name that does not exist, in a planned page's line", {"b.md": head + "# B\n\nLede of `QuerySet._fetch_al`.\n"}, "binds no"),
        ]
        failed = 0
        with tempfile.TemporaryDirectory() as scratch:
            def put(root: Path, files: dict) -> None:
                for path, text in files.items():
                    if text is None:
                        continue  # a case that takes a file of the good book away
                    (root / path).parent.mkdir(parents=True, exist_ok=True)
                    (root / path).write_text(text, encoding="utf-8", newline="\n")

            def bake(name: str, files: dict) -> list[str]:
                root = Path(scratch) / name
                put(root, files)
                try:
                    books.load(root)
                except books.Refused as refused:
                    return refused.problems
                return []

            def fail(what: str) -> None:
                nonlocal failed
                failed += 1
                self.stderr.write(f"probe: {what}")

            for name, book in (("good", good), ("good-with-a-figure", with_figure)):
                problems = bake(name, book)
                if problems:
                    fail(f"the {name} book was refused: " + "; ".join(problems))
            for n, (what, change, expected) in enumerate(cases):
                problems = bake(f"case{n}", {**good, **change})
                if len(problems) != 1 or expected not in problems[0]:
                    fail(f"{what}: expected one refusal holding `{expected}`, got: {problems or 'none'}")
                elif not problems[0].startswith(books.shown(Path(scratch) / f"case{n}")):
                    fail(f"{what}: the refusal does not begin with the page's path in the book: {problems[0]}")

            # what a bake writes: the pages and their twins, the agent's files, and nothing for a planned page;
            # a second static directory, with what collectstatic would leave out, to see the copy leave it out too
            written = Path(scratch) / "written"
            good_root = Path(scratch) / "good"
            extra = Path(scratch) / "extra-static"
            put(extra, {"extra.txt": "kept\n", "site.css~": "an editor's backup\n", ".hidden": "hidden\n", "CVS/Entries": "cvs\n"})
            before_dirs, settings.STATICFILES_DIRS = settings.STATICFILES_DIRS, [str(extra)]
            before_indexable, settings.INDEXABLE = settings.INDEXABLE, False
            finders.get_finder.cache_clear()
            try:
                count, counts = self.write(books.load(good_root), written)
            finally:
                settings.STATICFILES_DIRS = before_dirs
                finders.get_finder.cache_clear()
            if not (written / "static" / "extra.txt").is_file() or any((written / "static" / name).exists() for name in ("site.css~", ".hidden", "CVS")):
                fail("the static files were copied with an editor's backup, a hidden file or CVS, or without a plain file")
            if count != 4 or counts.get("links", 0) < 10 or counts != gating.links.check(str(written), settings.SITE_URL)[1]:
                fail(f"a bake of four written pages reported {count} pages and {counts} through the gate, which counts "
                     f"{gating.links.check(str(written), settings.SITE_URL)[1]}")
            if (written.parent / "written.baking").exists():
                fail("the bake left its working directory behind")
            for name in ("index.html", "a.html", "p.html", "p/c.html", "index.md", "a.md", "p/c.md", "llms.txt", "index.json", "names.json",
                         "robots.txt", "404.html", "_headers", "static/site.css"):
                if not (written / name).is_file():
                    fail(f"a bake did not write {name}")
            for name in ("b.html", "b.md", "llms-full.txt", "sitemap.xml"):
                if (written / name).exists():
                    fail(f"a bake wrote {name}: a planned page has no file, and a book that is not indexable no sitemap and no whole")
            if (written / "a.md").read_bytes() != (good_root / "a.md").read_bytes():
                fail("the twin is not the page's file byte for byte")
            page = (written / "a.html").read_text(encoding="utf-8")
            section_page = (written / "p/c.html").read_text(encoding="utf-8")
            index_html = (written / "index.html").read_text(encoding="utf-8")
            missing = (written / "404.html").read_text(encoding="utf-8")
            world = gating.current().world
            records = {r["pointer"]: r for r in gating.pointers.examine(world, str(good_root / "a.md"))[0]}
            lines = records[pointer]["lines"]
            # a pointer in parentheses leaves its sentence and stands beside the paragraph, linked to its lines at the pin
            beside_text = page.split('<aside class="sources"', 1)[-1].split("</aside>", 1)[0] if '<aside class="sources"' in page else ""
            lands = f'href="https://github.com/django/django/blob/{commit}/django/core/handlers/base.py#L{lines[0]}-L{lines[1]}"'
            if lands not in beside_text or "<code>BaseHandler<wbr>.load_middleware</code>" not in beside_text or "django/<wbr>core/<wbr>handlers/<wbr>base<wbr>.py" not in beside_text:
                fail("a pointer in parentheses is not set beside its paragraph, shown by its symbol and its file, linked to its lines at the pin")
            if "is built (" in page or "is built." not in page:
                fail("a parenthesis that held only a pointer was left in the sentence")
            if f'href="https://github.com/django/django/tree/{commit}/django/core/handlers"' not in page:
                fail("a directory pointer is not a link to the tree at the pin")
            if f'href="https://github.com/django/django/blob/{commit}/django/core/handlers/wsgi.py"' not in page:
                fail("a file pointer is not a link to the file at the pin")
            asgiref = world.pinned["trees"]["asgiref"]
            if f'href="{asgiref["repository"]}/blob/{asgiref["commit"]}/asgiref/sync.py#L' not in page or "<code>SyncToAsync</code>" not in page:
                fail("a pointer into a library is not a link into the library's repository at its own commit, shown by its symbol")
            if "runtime-names" in page or "Model._meta" in page:
                fail("a runtime-names block is shown on the page: it declares names for the gate, and is the twin's alone")
            if 'rel="alternate" type="text/markdown" href="/a.md"' not in page or '<a href="/a.md">' not in page.split('<footer class="colophon', 1)[-1]:
                fail("a page does not name its twin in its head and at its foot")
            if 'rel="canonical"' in page:
                fail("a book that is not indexable carries a canonical URL")
            if 'class="planned"' not in index_html or 'href="/b"' in index_html:
                fail("a link to a planned page is not shown as plain text")
            # the numbers: a chapter's on its opening page, a section's in its title, the parts in the contents
            if '<p class="numeral" aria-hidden="true">1</p>' not in page or '<span class="no">3.1</span> C</h1>' not in section_page:
                fail("a chapter's opening page does not carry its number, or a section's title its own")
            if "Part I · First" not in index_html or "Part II · Second" not in index_html or "Part I · First" not in page:
                fail("the parts are not numbered in the contents, or a chapter's opening page does not say which part it is in")
            for name in ("index.html", "a.html", "p.html", "p/c.html", "404.html"):
                if SECTION_SIGN in (written / name).read_text(encoding="utf-8"):
                    fail(f"{name} prints a section sign")
            if "<dl" in page or "Verified against" in page or 'class="status' in page:
                fail("a page carries a block about itself: what it was verified against, or how far it has come")
            # the book's contents beside every page: the page shown marked, its chapter open and no other
            def beside(html: str) -> str:
                return html.split('<nav class="booknav"', 1)[-1].split("</nav>", 1)[0] if '<nav class="booknav"' in html else ""
            nav_a, nav_c = beside(page), beside(section_page)
            if ('<a href="/a" aria-current="page">' not in nav_a or '<a href="/p">' not in nav_a or 'href="/p/c"' in nav_a
                    or '<a href="#first">' not in nav_a or nav_a.count("aria-current") != 1):
                fail("the navigation beside a page does not mark that page and no other, list its headings, and keep the other chapters closed")
            if '<a href="/p/c" aria-current="page">' not in nav_c or '<a href="/p">' not in nav_c or "#first" in nav_c:
                fail("the navigation beside a section does not open its chapter, or lists another page's headings")
            unlinked = re.sub(r"<a [^>]*>.*?</a>", "", nav_c, flags=re.S)  # what is left when every link is taken out whole
            if "<a " in unlinked or "</a>" in unlinked:
                fail("a heading with a link in it nests a link inside the navigation")
            if 'class="planned"' not in nav_a or 'href="/b"' in nav_a:
                fail("the navigation gives a planned page an address, or leaves it out")
            if "Part I · First" not in nav_a or "aria-current" in beside(index_html):
                fail("the navigation does not name the parts, or marks a page beside the front page")
            if '<a href="/a">' not in beside(missing) or "aria-current" in missing:
                fail("the page for a missing address carries no navigation, or marks a page as the one shown")
            # what the site itself gives an id begins with an underscore, which no heading's address can
            # (a heading's address is its slug, and a slug never begins with one): `## Contents` cannot collide
            own_ids = set(re.findall(r'\bid="([^"]*)"', index_html)) - {"one"}
            if not own_ids or any(not i.startswith("_") for i in own_ids):
                fail(f"the site gives an element of a page an id a heading could also come to: {sorted(own_ids)}")
            # the reader's colours: put on before the stylesheet is read, and a palette in the stylesheet for each one offered
            head_html = page.split("</head>", 1)[0]
            if not 0 <= head_html.find('localStorage.getItem("colours")') < head_html.find('rel="stylesheet"'):
                fail("a page does not put on the reader's colours before its stylesheet is read")
            if not (written / "static" / "site.js").is_file() or 'src="/static/site.js"' not in head_html:
                fail("the script that keeps the reader's colours is not written, or a page does not load it")
            stylesheet = (written / "static" / "site.css").read_text(encoding="utf-8")
            offered = {value for value, _word in views.COLOURS if value}
            for value, word in views.COLOURS:
                if f'<option value="{value}">{word}</option>' not in page:
                    fail(f"the colours a page offers do not include {word}")
            if offered != set(PALETTE.findall(stylesheet)) or "" not in dict(views.COLOURS):
                fail(f"the colours offered and the stylesheet's palettes are not the same set: {sorted(offered)} against "
                     f"{sorted(set(PALETTE.findall(stylesheet)))}; or the reader's system is not among the choices")
            llms = (written / "llms.txt").read_text(encoding="utf-8")
            if (f"- [A]({settings.SITE_URL}/a.md): Lede." not in llms or "\n## 1. A\n" not in llms or "b.md" in llms or "\n## 3. P\n" not in llms
                    or f"- [C]({settings.SITE_URL}/p/c.md): Lede of C." not in llms or f"> Its lede, which links [A]({settings.SITE_URL}/a.md)." not in llms):
                fail("llms.txt does not list the written pages' twins with their ledes under their chapters, links made absolute")
            data = json.loads((written / "index.json").read_text(encoding="utf-8"))
            by_id = {entry["id"]: entry for entry in data["pages"]}
            if ([entry["id"] for entry in data["pages"]] != ["", "a", "b", "p", "p/c"] or by_id["b"]["url"] is not None
                    or by_id["b"]["written"] is not False or by_id["a"]["written"] is not True
                    or by_id["a"]["sections"] != [{"anchor": "first", "heading": "First"}]
                    or by_id["a"]["number"] != "1" or by_id["p/c"]["number"] != "3.1" or by_id["a"]["part"] != "First"
                    or "django" not in data["verified_against"]
                    or by_id["p/c"]["chapter"] != "p" or by_id["p/c"]["parent"] != "p" or by_id["a"]["chapter"] is not None):
                fail("index.json does not carry every page in reading order with its number, its part and whether it is written")
            names = json.loads((written / "names.json").read_text(encoding="utf-8"))
            entry = names["names"].get("BaseHandler.load_middleware")
            c_section = "/p/c#what-djangocorehandlersbasepybasehandlerget_response-does-and-a"
            if entry != {"home": None, "where": ["/a#first"]} or names["paths"].get("django/core/handlers/base.py") != ["/a#first", c_section]:
                fail(f"names.json does not say where a name is mentioned: {entry}, {names['paths'].get('django/core/handlers/base.py')}")
            if names["names"].get("BaseHandler.get_response", {}).get("home") != c_section:
                fail("names.json does not give a name the section whose heading names it as its home")
            if ("import_string" not in names["names"] or "asgiref:asgiref/sync.py" not in names["paths"]
                    or f"{pointer}" not in names["names"] or "QuerySet._fetch_all" in names["names"]
                    or not names["names"][pointer].get("url", "").endswith(f"/django/core/handlers/base.py#L{lines[0]}-L{lines[1]}")):
                fail("names.json does not index a call, a library's path and a whole pointer with the link to its lines")
            headers = (written / "_headers").read_text(encoding="utf-8")
            if "X-Robots-Tag: noindex" not in headers or "/*.md\n  Content-Type: text/markdown" not in headers:
                fail("the headers do not keep a book that is not indexable out of the index, or do not give the twins their type")
            if self.faults(written):
                fail("the link gate failed on a good bake: " + "; ".join(self.faults(written)))
            # the addresses that have moved: copied for the host as they are, and refused when one leads nowhere
            if not (written / "_redirects").is_file() or (written / "_redirects").read_bytes() != (good_root / "_redirects").read_bytes():
                fail("the book's _redirects was not written beside the pages as it is")
            astray = Path(scratch) / "astray"
            put(astray, {**good, "_redirects": "/old /nowhere 301\n"})
            try:
                self.write(books.load(astray), Path(scratch) / "astray-out")
                fail("a redirect that leads to no page of the book was let through")
            except CommandError as refused:
                if "is no page of this book" not in str(refused) or (Path(scratch) / "astray-out").exists():
                    fail(f"a redirect that leads nowhere was refused in other words, or something was written: {refused}")
            # the link gate stops a bake whose output holds a link that does not resolve
            (written / "stray.html").write_text('<a href="/nowhere">x</a>', encoding="utf-8")
            try:
                self.gate(written)
                fail("the link gate let a link to nowhere through")
            except CommandError:
                pass
            # a figure and a captioned table are numbered through their chapter
            figured = Path(scratch) / "figured"
            self.write(books.load(Path(scratch) / "good-with-a-figure"), figured)
            with_numbers = (figured / "a.html").read_text(encoding="utf-8")
            if '<span class="no">Figure 1.1</span> A caption.' not in with_numbers or '<span class="no">Table 1.1</span> What the table shows.' not in with_numbers:
                fail("a figure or a captioned table is not numbered by its chapter and its place in it")
            if '<figure class="figure" id="figure-one"' not in with_numbers or "<svg" not in with_numbers or "figure=one" in with_numbers:
                fail("a figure is not put into the page as its SVG, or its source is shown beside it")
            if with_numbers.count('<aside class="note">') != 1 or with_numbers.count("<blockquote>") != 1:
                fail("a quotation that opens with a label in bold is not a note, or one that does not is")
            # the book published: indexable, with its sitemap and its whole
            settings.INDEXABLE = True
            try:
                indexed = Path(scratch) / "indexed"
                self.write(books.load(good_root), indexed)
            finally:
                settings.INDEXABLE = before_indexable
            if not (indexed / "sitemap.xml").is_file() or not (indexed / "llms-full.txt").is_file():
                fail("an indexable book was baked without its sitemap and its whole")
            if "/b<" in (indexed / "sitemap.xml").read_text(encoding="utf-8") or f"<!-- {settings.SITE_URL}/index.md -->" not in (indexed / "llms-full.txt").read_text(encoding="utf-8"):
                fail("the sitemap lists a planned page, or the whole leaves out the front page")
            if "noindex" in (indexed / "_headers").read_text(encoding="utf-8") or "Sitemap:" not in (indexed / "robots.txt").read_text(encoding="utf-8"):
                fail("an indexable book is kept out of the index, or its robots.txt does not name the sitemap")
            if f'<link rel="canonical" href="{settings.SITE_URL}/a">' not in (indexed / "a.html").read_text(encoding="utf-8"):
                fail("a page of an indexable book carries no canonical URL")
            if 'name="robots"' in (indexed / "a.html").read_text(encoding="utf-8"):
                fail("a page of an indexable book says noindex")
            if self.faults(indexed):
                fail("the link gate failed on an indexable book: " + "; ".join(self.faults(indexed)))
            # the command itself: it runs the gate and says what it wrote
            from io import StringIO
            printed = StringIO()
            call_command("bake", book=str(good_root), out=str(Path(scratch) / "by-command"), stdout=printed)
            if "links resolving" not in printed.getvalue() or "4 pages" not in printed.getvalue() or "1 planned" not in printed.getvalue():
                fail(f"the command did not report its pages, the planned one and the link gate's count: {printed.getvalue()!r}")
            # a directory the bake did not make is not emptied
            out = Path(scratch) / "not-ours"
            out.mkdir()
            (out / "keep.txt").write_text("someone's file\n", encoding="utf-8")
            try:
                self.write(books.load(good_root), out)
                fail("a directory the bake did not make was emptied")
            except CommandError:
                if not (out / "keep.txt").is_file():
                    fail("the bake refused a directory it did not make, and emptied it anyway")
        if failed:
            raise CommandError(f"bake --probe: FAILED, {failed} expectation{'s' if failed != 1 else ''} not met")
        self.stdout.write(f"bake --probe: ok. A good book is accepted, with a figure and without; {len(cases)} books with one thing wrong "
                          f"are each refused for it and for nothing else, with the page's path, a pointer that does not resolve, a name that "
                          f"does not exist and a name bound only in another section among them; a bake writes the pages, their twins (the "
                          f"files themselves), llms.txt, index.json and names.json as the head says; a planned page gets a line in the "
                          f"contents and no file; a pointer in parentheses stands beside its paragraph and every pointer links to the pin; "
                          f"chapters, sections, parts, figures and captioned tables carry their numbers; no page prints a section sign or "
                          f"a block about itself; the book's contents stand beside every page (the page shown marked, its chapter open) "
                          f"with the colours the stylesheet has palettes for, put on before it is read; the sitemap, the whole and a "
                          f"canonical URL are written for an indexable book alone; the book's list of addresses that have moved is "
                          f"copied for the host, and refused when one leads to no page; the link gate stops a bake with a link to "
                          f"nowhere and the command reports its count; a directory the bake did not make is not emptied.")

    @staticmethod
    def faults(out: Path) -> list[str]:
        return gating.links.check(str(out), settings.SITE_URL)[0]
