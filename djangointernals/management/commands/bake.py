"""Bake the book: every page requested through Django and written to a file, with the agent's files beside it.

    python manage.py bake                    pages/ -> dist/
    python manage.py bake --book specimen    the specimen -> dist/
    python manage.py bake --out DIR          somewhere other than dist/
    python manage.py bake --probe            prove the bake refuses what it should, and writes what it should

The book is read whole first (djangointernals/book.py), the two gates run
on every page (gates.py), and a book with a problem is refused whole: every
problem is printed as `file:line: what is wrong`, nothing is written, and
the command fails. Then each written page is requested with Django's test
client, so that what is baked is what the running site answers, and its
response is written as `<id>.html` (`index.html` for the contents); beside
it its twin, `<id>.md`, the page's file as it is. A page in outline gets
no file: it is an entry in the contents. Then the agent's files (doors.py):
`llms.txt`, `index.json`, `names.json`, and for the book itself (never the
specimen) `llms-full.txt` and `sitemap.xml`; `404.html`; `robots.txt`;
Cloudflare Pages's `_headers`; and the static files (an editor's backup, a
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
        outlined = sum(1 for page in book.order if not page.published)
        self.stdout.write(f"bake: ok, {written} page{'s' if written != 1 else ''} written to {books.shown(out)} with their twins, "
                          f"{', '.join(AGENT_FILES + (INDEXABLE_FILES if views.indexable() else ()))}, and every one of {counts['links']} "
                          f"links resolving" + (f" ({counts['outlined']} to a page in outline)" if counts["outlined"] else "")
                          + (f"; {outlined} in outline, as entries in the contents" if outlined else ""))

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
        head = f"---\ndjango: main at {commit}; asgiref 3.12.1\nstatus: verified\n---\n"
        pointer = "django/core/handlers/base.py:BaseHandler.load_middleware"
        good = {
            "index.md": head.replace("---\n", "---\ncontents: a, b, p\n", 1)
                        + "# A book\n\nIts lede, which links [A](a.md).\n\n## One\n\nText, [a link](a.md#first) and [one to a page in outline](b.md).\n",
            "a.md": head.replace("status: verified", 'status: verified\nowns: "`BaseHandler.load_middleware`"')
                    + f"# A\n\nLede.\n\n## First\n\nText, and `{pointer}`; a call, `import_string(\"x\")`; a library's, "
                      f"`asgiref:asgiref/sync.py:SyncToAsync`; a directory, `django/core/handlers/`; a file, `django/core/handlers/wsgi.py`.\n\n"
                      "```runtime-names\nModel._meta  django/db/models/options.py:Options.contribute_to_class\n```\n",
            "b.md": head.replace("verified", "outline") + "# B\n\nLede.\n\n## A question?\n\n- To assert: what `QuerySet._fetch_all` does.\n",
            "p.md": head.replace("status: verified", "status: verified\ncontents: c") + "# P\n\nLede of P.\n\n## Only\n\nText.\n",
            "p/c.md": head + "# C\n\nLede of C.\n\n## What `django/core/handlers/base.py:BaseHandler.get_response` does, and [A](../a.md)?\n\nText.\n",
        }
        figure = good["a.md"] + "\n```text figure=one\nx\n```\n\n*A caption.*\n"
        svg = '<svg xmlns="http://www.w3.org/2000/svg" class="fig" viewBox="0 0 10 10"><rect class="box" width="5" height="5"/></svg>'
        with_figure = {**good, "a.md": figure, "figures/one.svg": svg}
        no_owns = good["a.md"].replace('\nowns: "`BaseHandler.load_middleware`"', "")
        cases = [
            ("a page with no front matter", {"a.md": "# A\n\nLede.\n\n## First\n"}, "begins with its front matter"),
            ("a status that is not one of the three", {"a.md": good["a.md"].replace("status: verified", "status: done")}, "is not one of"),
            ("a key the front matter does not have", {"a.md": good["a.md"].replace("status:", "state: x\nstatus:")}, "is not a key"),
            ("a value a YAML reader would trip on", {"a.md": good["a.md"].replace(f"main at {commit}", f"`main` at {commit}")}, "in double quotes"),
            ("a `django` line without the pinned commit", {"a.md": no_owns.replace(commit, "0" * 40).replace("```runtime-names", "```text")
                                                            .replace(f"`{pointer}`", "nothing").replace("`asgiref:asgiref/sync.py:SyncToAsync`", "x")
                                                            .replace("`django/core/handlers/`", "y").replace("`django/core/handlers/wsgi.py`", "z")},
             "does not spell out the pinned commit"),
            ("a page with no title", {"a.md": head + "Lede.\n\n## First\n\nText.\n"}, "opens with its title"),
            ("a page with no lede", {"a.md": head + "# A\n\n## First\n\nText.\n"}, "has its lede"),
            ("two titles", {"a.md": good["a.md"] + "\n# Again\n"}, "a second # heading"),
            ("a heading below ###", {"a.md": good["a.md"] + "\n#### Deep\n\nText.\n"}, "nothing below ###"),
            ("two headings with one anchor", {"a.md": good["a.md"] + "\n## First\n\nText.\n"}, "come to the anchor"),
            ("a heading whose address is a figure's", {"a.md": figure + "\n## Figure one\n\nText.\n", "figures/one.svg": svg}, "begins `figure-`"),
            ("raw HTML", {"a.md": good["a.md"] + "\n<div>x</div>\n"}, "raw HTML"),
            ("a comment", {"a.md": good["a.md"] + "\n<!-- later -->\n"}, "raw HTML"),
            ("an image", {"a.md": good["a.md"] + "\n![x](x.png)\n"}, "an image"),
            ("an empty section on a written page", {"a.md": good["a.md"] + "\n## Empty\n"}, "nothing under it"),
            ("a link to a page that is not there", {"a.md": good["a.md"] + "\n[x](d.md)\n"}, "no such page"),
            ("a link by URL to a page of the book", {"a.md": good["a.md"] + "\n[x](/b)\n"}, "the path of its .md file"),
            ("a link out of the book with no scheme", {"a.md": good["a.md"] + "\n[x](www.example.com)\n"}, "is a full URL"),
            ("a link written from the wrong directory", {"a.md": good["a.md"] + "\n[x](sub/b.md)\n"}, "this one comes to sub/b.md"),
            ("a link to an anchor its target lacks", {"index.md": good["index.md"].replace("#first", "#second")}, "has no heading or figure"),
            ("a child with no file", {"index.md": good["index.md"].replace("contents: a, b", "contents: a, b, d")}, "there is no"),
            ("a file in no contents", {"d.md": no_owns}, "names this file"),
            ("a written page under an outlined index", {
                "b.md": good["b.md"].replace("---\n", "---\ncontents: d\n", 1), "b/d.md": no_owns}, "still in outline"),
            ("a figure with no SVG", {"a.md": figure}, "there is no"),
            ("a figure with no caption", {"a.md": figure.replace("*A caption.*", "Not a caption."), "figures/one.svg": svg}, "its caption is"),
            ("a figure that is not one SVG with a viewBox", {"a.md": figure, "figures/one.svg": "<svg></svg>"}, "with a viewBox"),
            ("a figure of two elements", {"a.md": figure, "figures/one.svg": svg + "<p>more</p>"}, "not well-formed"),
            ("a figure with a script", {"a.md": figure, "figures/one.svg": svg.replace("<rect", "<script>x</script><rect")}, "carries no script"),
            ("a figure with a handler", {"a.md": figure, "figures/one.svg": svg.replace("<rect", '<rect onload="x"')}, "carries no script"),
            ("a figure that loads an image", {"a.md": figure, "figures/one.svg": svg.replace("<rect", '<image href="x.png"/><rect')}, "loads nothing"),
            ("a figure that moves", {"a.md": figure, "figures/one.svg": svg.replace("<rect", '<animate attributeName="x"/><rect')}, "does not move"),
            ("a figure with a frame in it", {"a.md": figure, "figures/one.svg": svg.replace("<rect", '<iframe/><rect')}, "loads nothing"),
            ("a figure that links out of itself", {"a.md": figure, "figures/one.svg": svg.replace("<rect", '<a href="javascript:alert(1)"><rect/></a><rect')},
             "links nowhere outside itself"),
            ("a figure whose <use> loads from elsewhere", {"a.md": figure, "figures/one.svg": svg.replace("<rect", '<use href="https://example.org/x.svg#a"/><rect')},
             "links nowhere outside itself"),
            ("a figure with a colour of its own", {"a.md": figure, "figures/one.svg": svg.replace("<rect", '<rect fill="red"')}, "no colour or font"),
            ("a figure without the class the stylesheet draws by", {"a.md": figure, "figures/one.svg": svg.replace(' class="fig"', "")}, 'class="fig"'),
            ("a figure named in capitals", {"a.md": figure.replace("figure=one", "figure=One"), "figures/One.svg": svg}, "a figure's name is"),
            ("two figures of one name", {"a.md": figure + "\n```text figure=one\ny\n```\n\n*Another caption.*\n", "figures/one.svg": svg}, "another of that name"),
            ("a figure inside a list", {"a.md": good["a.md"] + "\n- item\n\n  ```text figure=one\n  x\n  ```\n\n  *A caption.*\n",
                                        "figures/one.svg": svg}, "stands by itself"),
            ("a department's figure stylesheet with a script in it", {"a/figures/figures.css": ".fig .x {}\n</style><script>alert(1)</script>\n"},
             "classes and nothing else"),
            ("a heading written by underlining", {"a.md": good["a.md"] + "\nSecond\n------\n\nText.\n"}, "not by underlining"),
            ("a heading with no words", {"a.md": good["a.md"] + "\n## ?\n\nText.\n"}, "no words in it"),
            ("a key given twice", {"a.md": good["a.md"].replace("status: verified", "status: verified\nstatus: verified")}, "given twice"),
            ("a quoted value that does not close", {"a.md": good["a.md"].replace('owns: "`BaseHandler.load_middleware`"', 'owns: "`BaseHandler.load_middleware`')},
             "from end to end"),
            ("`owns` without code spans", {"a.md": good["a.md"].replace('owns: "`BaseHandler.load_middleware`"', "owns: QuerySet")}, "each in a code span"),
            ("a name with two homes", {"index.md": good["index.md"].replace("status: verified", 'status: verified\nowns: "`BaseHandler.load_middleware`"')},
             "already the home of"),
            ("a child's name in capitals", {"index.md": good["index.md"].replace("contents: a, b", "contents: a, b, C")}, "lower-case words"),
            ("a child named for the site's own paths", {"index.md": good["index.md"].replace("contents: a, b", "contents: a, b, static")}, "not static"),
            ("a child named index, in a department", {"p.md": good["p.md"].replace("contents: c", "contents: c, index")}, "never 404 or index"),
            ("a child named 404, in a department", {"p.md": good["p.md"].replace("contents: c", "contents: c, 404")}, "never 404 or index"),
            ("a child named twice", {"index.md": good["index.md"].replace("contents: a, b", "contents: a, b, a")}, "twice"),
            ("a contents page in outline", {"index.md": good["index.md"].replace("verified", "outline"),
                                            "a.md": good["a.md"].replace("verified", "outline"), "p.md": good["p.md"].replace("verified", "outline"),
                                            "p/c.md": good["p/c.md"].replace("verified", "outline")},
             "nothing to publish"),
            ("a link to an anchor its own page lacks", {"a.md": good["a.md"] + "\n[x](#second)\n"}, "has no heading or figure"),
            ("a link to an anchor an outlined page lacks", {"a.md": good["a.md"] + "\n[x](b.md#second)\n"}, "has no heading or figure"),
            ("a link to the book by its address on the site", {"a.md": good["a.md"] + f"\n[x]({settings.SITE_URL}/b)\n"}, "not its address on the site"),
            ("a link to the book by its www address", {"a.md": good["a.md"] + f"\n[x]({settings.SITE_URL.replace('://', '://www.')}/b)\n"}, "not its address on the site"),
            ("a link to the book by http", {"a.md": good["a.md"] + f"\n[x]({settings.SITE_URL.replace('https://', 'http://')}/b)\n"}, "not its address on the site"),
            ("a link to the book by its pages.dev address", {"a.md": good["a.md"] + f"\n[x](https://{settings.PAGES_PROJECT}.pages.dev/b)\n"},
             "not its address on the site"),
            # the gates, run by the loader on every page
            ("a pointer that does not resolve", {"a.md": good["a.md"].replace("Text, and", "Text, `django/nope.py:Nope`, and")}, "holds no file"),
            ("a name that does not exist", {"a.md": good["a.md"] + "\n`QuerySet._fetch_al`\n"}, "binds no"),
            ("a name several files define, bound by a pointer in an earlier section only", {
                "a.md": good["a.md"] + "\n`django/db/backends/sqlite3/base.py:DatabaseWrapper`\n\n## Second\n\n`DatabaseWrapper.get_new_connection`\n"},
             "in this section"),
            ("a name in an outlined page's orders", {"b.md": good["b.md"] + "\n- To assert: what `QuerySet._fetch_al` does.\n"}, "binds no"),
        ]
        failed = 0
        with tempfile.TemporaryDirectory() as scratch:
            def put(root: Path, files: dict) -> None:
                for path, text in files.items():
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

            # what a bake writes: the pages and their twins, the agent's files, and nothing for an outlined page;
            # a second static directory, with what collectstatic would leave out, to see the copy leave it out too
            written = Path(scratch) / "written"
            good_root = Path(scratch) / "good"
            extra = Path(scratch) / "extra-static"
            put(extra, {"extra.txt": "kept\n", "site.css~": "an editor's backup\n", ".hidden": "hidden\n", "CVS/Entries": "cvs\n"})
            before_dirs, settings.STATICFILES_DIRS = settings.STATICFILES_DIRS, [str(extra)]
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
                    fail(f"a bake wrote {name}: an outlined page has no file, and a book that is not indexable no sitemap and no whole")
            if (written / "a.md").read_bytes() != (good_root / "a.md").read_bytes():
                fail("the twin is not the page's file byte for byte")
            page = (written / "a.html").read_text(encoding="utf-8")
            world = gating.current().world
            records = {r["pointer"]: r for r in gating.pointers.examine(world, str(good_root / "a.md"))[0]}
            lines = records[pointer]["lines"]
            if f'class="pointer" href="https://github.com/django/django/blob/{commit}/django/core/handlers/base.py#L{lines[0]}-L{lines[1]}"' not in page:
                fail("a pointer is not a link to the lines the gate resolves it to, at the pin")
            if f'href="https://github.com/django/django/tree/{commit}/django/core/handlers"' not in page:
                fail("a directory pointer is not a link to the tree at the pin")
            if f'href="https://github.com/django/django/blob/{commit}/django/core/handlers/wsgi.py"' not in page:
                fail("a file pointer is not a link to the file at the pin")
            asgiref = world.pinned["trees"]["asgiref"]
            if f'href="{asgiref["repository"]}/blob/{asgiref["commit"]}/asgiref/sync.py#L' not in page:
                fail("a pointer into a library is not a link into the library's repository at its own commit")
            block = page.split('<pre data-kind="runtime-names">', 1)[-1].split("</pre>", 1)[0]
            if 'class="pointer"' not in block:
                fail("a runtime-names entry's pointer is not linked")
            if 'rel="alternate" type="text/markdown" href="/a.md"' not in page or "/a.md" not in page.split('<dt>For an agent</dt>', 1)[-1]:
                fail("a page does not name its twin in its head and its apparatus")
            if 'rel="canonical"' in page:
                fail("a book that is not indexable carries a canonical URL")
            index_html = (written / "index.html").read_text(encoding="utf-8")
            if 'class="unwritten"' not in index_html or 'href="/b"' in index_html:
                fail("a link to a page in outline is not shown as unwritten text")
            answers = (written / "p/c.html").read_text(encoding="utf-8").split('<nav class="answers"', 1)[-1].split("</nav>", 1)[0]
            if answers.count("<a ") != 1:
                fail("a heading with a link in it nests a link inside the list of a page's questions")
            # the book's contents beside every page: the page shown marked, its branch open and no other
            def beside(html: str) -> str:
                return html.split('<nav class="booknav"', 1)[-1].split("</nav>", 1)[0] if '<nav class="booknav"' in html else ""
            nav_a, nav_c = beside(page), beside((written / "p/c.html").read_text(encoding="utf-8"))
            if ('<a href="/a" aria-current="page">' not in nav_a or '<a href="/p">' not in nav_a or 'href="/p/c"' in nav_a
                    or '<a href="#first">' not in nav_a or nav_a.count("aria-current") != 1):
                fail("the navigation beside a page does not mark that page and no other, list its sections, and keep the other branches closed")
            if '<a href="/p/c" aria-current="page">' not in nav_c or '<a href="/p">' not in nav_c or "#first" in nav_c:
                fail("the navigation beside a page under a department does not open that department's branch, or lists another page's sections")
            if 'class="outlined"' not in nav_a or 'href="/b"' in nav_a:
                fail("the navigation gives a page in outline an address, or leaves it out")
            if '<a href="/" aria-current="page">Contents</a>' not in beside(index_html):
                fail("the navigation beside the contents page does not mark it")
            missing = (written / "404.html").read_text(encoding="utf-8")
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
            if (f"- [A]({settings.SITE_URL}/a.md): Lede." not in llms or "\n## A\n" not in llms or "b.md" in llms or "\n## P\n" not in llms
                    or f"- [C]({settings.SITE_URL}/p/c.md): Lede of C." not in llms or f"> Its lede, which links [A]({settings.SITE_URL}/a.md)." not in llms):
                fail("llms.txt does not list the written pages' twins with their ledes under the top-level pages, links made absolute")
            data = json.loads((written / "index.json").read_text(encoding="utf-8"))
            by_id = {entry["id"]: entry for entry in data["pages"]}
            if ([entry["id"] for entry in data["pages"]] != ["", "a", "b", "p", "p/c"] or by_id["b"]["url"] is not None
                    or by_id["b"]["status"] != "outline" or by_id["a"]["sections"] != [{"anchor": "first", "heading": "First"}]
                    or by_id["a"]["owns"] != ["BaseHandler.load_middleware"] or "django" not in data["verified_against"]
                    or by_id["p/c"]["department"] != "p" or by_id["p/c"]["parent"] != "p" or by_id["a"]["department"] is not None):
                fail("index.json does not carry every page's head in reading order, outlined pages included")
            names = json.loads((written / "names.json").read_text(encoding="utf-8"))
            entry = names["names"].get("BaseHandler.load_middleware")
            c_section = "/p/c#what-djangocorehandlersbasepybasehandlerget_response-does-and-a"
            if entry != {"home": "/a", "where": ["/a#first"]} or names["paths"].get("django/core/handlers/base.py") != ["/a#first", c_section]:
                fail(f"names.json does not say where a name is explained and where it is mentioned: {entry}, {names['paths'].get('django/core/handlers/base.py')}")
            if ("import_string" not in names["names"] or "asgiref:asgiref/sync.py" not in names["paths"]
                    or f"{pointer}" not in names["names"] or "QuerySet._fetch_all" in names["names"]
                    or not names["names"][pointer].get("url", "").endswith(f"/django/core/handlers/base.py#L{lines[0]}-L{lines[1]}")):
                fail("names.json does not index a call, a library's path and a whole pointer with the link to its lines, or indexes an outlined page")
            headers = (written / "_headers").read_text(encoding="utf-8")
            if "X-Robots-Tag: noindex" not in headers or "/*.md\n  Content-Type: text/markdown" not in headers:
                fail("the headers do not keep a book that is not indexable out of the index, or do not give the twins their type")
            if self.faults(written):
                fail("the link gate failed on a good bake: " + "; ".join(self.faults(written)))
            # the link gate stops a bake whose output holds a link that does not resolve
            (written / "stray.html").write_text('<a href="/nowhere">x</a>', encoding="utf-8")
            try:
                self.gate(written)
                fail("the link gate let a link to nowhere through")
            except CommandError:
                pass
            # the book itself, baked from a directory called pages: indexable, with its sitemap and its whole
            put(Path(scratch) / "pages", good)
            indexed = Path(scratch) / "indexed"
            self.write(books.load(Path(scratch) / "pages"), indexed)
            if not (indexed / "sitemap.xml").is_file() or not (indexed / "llms-full.txt").is_file():
                fail("the book itself was baked without its sitemap and its whole")
            if "/b<" in (indexed / "sitemap.xml").read_text(encoding="utf-8") or f"<!-- {settings.SITE_URL}/index.md -->" not in (indexed / "llms-full.txt").read_text(encoding="utf-8"):
                fail("the sitemap lists an outlined page, or the whole leaves out the contents page")
            if "noindex" in (indexed / "_headers").read_text(encoding="utf-8") or "Sitemap:" not in (indexed / "robots.txt").read_text(encoding="utf-8"):
                fail("the book itself is kept out of the index, or its robots.txt does not name the sitemap")
            if f'<link rel="canonical" href="{settings.SITE_URL}/a">' not in (indexed / "a.html").read_text(encoding="utf-8"):
                fail("a page of the book itself carries no canonical URL")
            if self.faults(indexed):
                fail("the link gate failed on the book itself: " + "; ".join(self.faults(indexed)))
            # the command itself: it runs the gate and says what it wrote
            from io import StringIO
            printed = StringIO()
            call_command("bake", book=str(good_root), out=str(Path(scratch) / "by-command"), stdout=printed)
            if "links resolving" not in printed.getvalue() or "4 pages" not in printed.getvalue():
                fail(f"the command did not report its pages and the link gate's count: {printed.getvalue()!r}")
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
                          f"files themselves), llms.txt, index.json and names.json as the head says, links each pointer (a symbol, a file, a "
                          f"directory, a library's) to the pin, names the twin on the page, nests no link in the list of questions, puts "
                          f"the book's contents beside every page (the page shown marked, its branch open, a page in outline without an "
                          f"address) and offers the colours the stylesheet has palettes for, put on before it is read; it "
                          f"writes the sitemap, the whole and a canonical URL for the book alone; the link gate stops a bake with a link to "
                          f"nowhere and the command reports its count; a directory the bake did not make is not emptied.")

    @staticmethod
    def faults(out: Path) -> list[str]:
        return gating.links.check(str(out), settings.SITE_URL)[0]
