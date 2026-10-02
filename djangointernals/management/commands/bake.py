"""Bake the book: every page requested through Django and written to a file.

    python manage.py bake                    pages/ -> dist/
    python manage.py bake --book specimen    the specimen -> dist/
    python manage.py bake --out DIR          somewhere other than dist/
    python manage.py bake --probe            prove the bake refuses what it should

The book is read whole first (djangointernals/book.py), and a book with a
problem is refused whole: every problem is printed as `file:line: what is
wrong`, nothing is written, and the command fails. Then each written page
is requested with Django's test client, so that what is baked is what the
running site answers, and its response is written as `<id>.html`
(`index.html` for the contents). A page in outline gets no file: it is an
entry in the contents. Beside the pages go `404.html`, `robots.txt` and
the static files.

The output directory is emptied first. To be emptied it must be one this
command made (it holds the marker `.baked`) or be empty or absent: the
bake deletes nothing it did not write.

What a page's file is called is what Cloudflare Pages serves at the page's
URL: `orm/queries.html` at `/orm/queries`.
"""
import json
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.management.base import BaseCommand, CommandError
from django.test import Client, RequestFactory

from djangointernals import book as books
from djangointernals import views

MARKER = ".baked"


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
        written = self.write(book, out)
        outlined = sum(1 for page in book.order if not page.published)
        self.stdout.write(f"bake: ok, {written} page{'s' if written != 1 else ''} written to {books.shown(out)}"
                          + (f"; {outlined} in outline, as entries in the contents" if outlined else ""))

    def write(self, book, out: Path) -> int:
        """Write `book` to `out`. The views serve the book at settings.BOOK_DIR, so for as
        long as this runs that is `book`'s own directory."""
        before, settings.BOOK_DIR = settings.BOOK_DIR, book.root
        try:
            return self.written(book, out)
        finally:
            settings.BOOK_DIR = before

    def written(self, book, out: Path) -> int:
        if out.exists() and any(out.iterdir()) and not (out / MARKER).is_file():
            raise CommandError(f"bake: {out} is not empty and was not made by this command (it has no {MARKER}): not touched")
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        (out / MARKER).write_text("Made by `python manage.py bake`, and emptied by it before each bake.\n", encoding="utf-8")
        client = Client()
        written = 0
        for page in book.order:
            if not page.published:
                continue
            response = client.get(page.url)
            if response.status_code != 200:
                raise CommandError(f"bake: {page.url} answered {response.status_code}")
            target = out / f"{page.id or 'index'}.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.content)
            written += 1
        # Not requested like the pages: with DEBUG on, Django answers a missing page itself.
        (out / "404.html").write_bytes(views.not_found(RequestFactory().get("/404")).content)
        (out / "robots.txt").write_bytes(client.get("/robots.txt").content)
        # The static files, found as `runserver` finds them and copied beside the pages.
        # Not `collectstatic`: that writes to one directory fixed in the settings, not to `out`.
        for finder in finders.get_finders():
            for path, storage in finder.list([]):
                target = out / "static" / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(storage.path(path), target)
        return written

    # -- the probe -----------------------------------------------------------

    def probe(self):
        """Bake small books, each with one thing wrong, and check each is refused for it."""
        pin = json.loads(Path(settings.PIN_FILE).read_text(encoding="utf-8"))
        commit = pin["trees"][pin["subject"]]["commit"]
        head = f"---\ndjango: main at {commit}\nstatus: verified\n---\n"
        good = {
            "index.md": head.replace("---\n", "---\ncontents: a, b\n", 1) + "# A book\n\nIts lede.\n\n## One\n\nText, and [a link](a.md#first).\n",
            "a.md": head + "# A\n\nLede.\n\n## First\n\nText.\n",
            "b.md": head.replace("verified", "outline") + "# B\n\nLede.\n\n## A question?\n",
        }
        figure = good["a.md"] + "\n```text figure=one\nx\n```\n\n*A caption.*\n"
        svg = '<svg xmlns="http://www.w3.org/2000/svg" class="fig" viewBox="0 0 10 10"><rect class="box" width="5" height="5"/></svg>'
        with_figure = {**good, "a.md": figure, "figures/one.svg": svg}
        cases = [
            ("a page with no front matter", {"a.md": "# A\n\nLede.\n\n## First\n"}, "begins with its front matter"),
            ("a status that is not one of the three", {"a.md": good["a.md"].replace("status: verified", "status: done")}, "is not one of"),
            ("a key the front matter does not have", {"a.md": good["a.md"].replace("status:", "state: x\nstatus:")}, "is not a key"),
            ("a value a YAML reader would trip on", {"a.md": good["a.md"].replace(f"main at {commit}", f"`main` at {commit}")}, "in double quotes"),
            ("a `django` line without the pinned commit", {"a.md": good["a.md"].replace(commit, "0" * 40)}, "does not spell out the pinned commit"),
            ("a page with no title", {"a.md": head + "Lede.\n\n## First\n\nText.\n"}, "opens with its title"),
            ("a page with no lede", {"a.md": head + "# A\n\n## First\n\nText.\n"}, "has its lede"),
            ("two titles", {"a.md": good["a.md"] + "\n# Again\n"}, "a second # heading"),
            ("a heading below ###", {"a.md": good["a.md"] + "\n#### Deep\n\nText.\n"}, "nothing below ###"),
            ("two headings with one anchor", {"a.md": good["a.md"] + "\n## First\n\nText.\n"}, "come to the anchor"),
            ("raw HTML", {"a.md": good["a.md"] + "\n<div>x</div>\n"}, "raw HTML"),
            ("a comment", {"a.md": good["a.md"] + "\n<!-- later -->\n"}, "raw HTML"),
            ("an image", {"a.md": good["a.md"] + "\n![x](x.png)\n"}, "an image"),
            ("an empty section on a written page", {"a.md": good["a.md"] + "\n## Empty\n"}, "nothing under it"),
            ("a link to a page that is not there", {"a.md": good["a.md"] + "\n[x](c.md)\n"}, "no such page"),
            ("a link by URL to a page of the book", {"a.md": good["a.md"] + "\n[x](/b)\n"}, "the path of its .md file"),
            ("a link out of the book with no scheme", {"a.md": good["a.md"] + "\n[x](www.example.com)\n"}, "is a full URL"),
            ("a link written from the wrong directory", {"a.md": good["a.md"] + "\n[x](sub/b.md)\n"}, "this one comes to sub/b.md"),
            ("a link to an anchor its target lacks", {"index.md": good["index.md"].replace("#first", "#second")}, "has no heading or figure"),
            ("a child with no file", {"index.md": good["index.md"].replace("contents: a, b", "contents: a, b, c")}, "there is no"),
            ("a file in no contents", {"c.md": good["a.md"]}, "names this file"),
            ("a written page under an outlined index", {
                "b.md": good["b.md"].replace("---\n", "---\ncontents: c\n", 1), "b/c.md": good["a.md"]}, "still in outline"),
            ("a figure with no SVG", {"a.md": figure}, "there is no"),
            ("a figure with no caption", {"a.md": figure.replace("*A caption.*", "Not a caption."), "figures/one.svg": svg}, "its caption is"),
            ("a figure that is not one SVG with a viewBox", {"a.md": figure, "figures/one.svg": "<svg></svg>"}, "with a viewBox"),
            ("a figure of two elements", {"a.md": figure, "figures/one.svg": svg + "<p>more</p>"}, "not well-formed"),
            ("a figure with a script", {"a.md": figure, "figures/one.svg": svg.replace("<rect", "<script>x</script><rect")}, "carries no script"),
            ("a figure with a handler", {"a.md": figure, "figures/one.svg": svg.replace("<rect", '<rect onload="x"')}, "carries no script"),
            ("a figure that loads an image", {"a.md": figure, "figures/one.svg": svg.replace("<rect", '<image href="x.png"/><rect')}, "loads nothing"),
            ("a figure with a colour of its own", {"a.md": figure, "figures/one.svg": svg.replace("<rect", '<rect fill="red"')}, "no colour or font"),
            ("a figure without the class the stylesheet draws by", {"a.md": figure, "figures/one.svg": svg.replace(' class="fig"', "")}, 'class="fig"'),
            ("a figure named in capitals", {"a.md": figure.replace("figure=one", "figure=One"), "figures/One.svg": svg}, "a figure's name is"),
            ("two figures of one name", {"a.md": figure + figure.split("Text.\n", 1)[1], "figures/one.svg": svg}, "another of that name"),
            ("a figure inside a list", {"a.md": good["a.md"] + "\n- item\n\n  ```text figure=one\n  x\n  ```\n\n  *A caption.*\n",
                                        "figures/one.svg": svg}, "stands by itself"),
            ("a heading written by underlining", {"a.md": good["a.md"] + "\nSecond\n------\n\nText.\n"}, "not by underlining"),
            ("a heading with no words", {"a.md": good["a.md"] + "\n## ?\n\nText.\n"}, "no words in it"),
            ("a key given twice", {"a.md": good["a.md"].replace("status: verified", "status: verified\nstatus: verified")}, "given twice"),
            ("a quoted value that does not close", {"a.md": good["a.md"].replace("status: verified", 'status: verified\nowns: "`x`')}, "from end to end"),
            ("`owns` without code spans", {"a.md": good["a.md"].replace("status: verified", "status: verified\nowns: QuerySet")}, "each in a code span"),
            ("a name with two homes", {"a.md": good["a.md"].replace("status: verified", 'status: verified\nowns: "`QuerySet`"'),
                                       "index.md": good["index.md"].replace("status: verified", 'status: verified\nowns: "`QuerySet`"')}, "already the home of"),
            ("a child's name in capitals", {"index.md": good["index.md"].replace("contents: a, b", "contents: a, b, C")}, "lower-case words"),
            ("a child named for the site's own paths", {"index.md": good["index.md"].replace("contents: a, b", "contents: a, b, static")}, "not one of"),
            ("a child named twice", {"index.md": good["index.md"].replace("contents: a, b", "contents: a, b, a")}, "twice"),
            ("a contents page in outline", {"index.md": good["index.md"].replace("verified", "outline"),
                                            "a.md": good["a.md"].replace("verified", "outline")}, "nothing to publish"),
            ("a link to an anchor its own page lacks", {"a.md": good["a.md"] + "\n[x](#second)\n"}, "has no heading or figure"),
            ("a link to an anchor an outlined page lacks", {"a.md": good["a.md"] + "\n[x](b.md#second)\n"}, "has no heading or figure"),
            ("a link to the book by its address on the site", {"a.md": good["a.md"] + f"\n[x]({settings.SITE_URL}/b)\n"}, "not its address on the site"),
        ]
        failed = 0
        with tempfile.TemporaryDirectory() as scratch:
            def bake(name: str, files: dict) -> list[str]:
                root = Path(scratch) / name
                for path, text in files.items():
                    (root / path).parent.mkdir(parents=True, exist_ok=True)
                    (root / path).write_text(text, encoding="utf-8", newline="\n")
                try:
                    books.load(root)
                except books.Refused as refused:
                    return refused.problems
                return []

            for name, book in (("good", good), ("good-with-a-figure", with_figure)):
                problems = bake(name, book)
                if problems:
                    failed += 1
                    self.stderr.write(f"probe: the {name} book was refused: " + "; ".join(problems))
            written = Path(scratch) / "written"
            self.write(books.load(Path(scratch) / "good"), written)
            if not (written / "static" / "site.css").is_file() or not (written / "a.html").is_file() or (written / "b.html").exists():
                failed += 1
                self.stderr.write("probe: a bake to another directory did not hold its pages and its static files, and no outlined page")
            for n, (what, change, expected) in enumerate(cases):
                problems = bake(f"case{n}", {**good, **change})
                if len(problems) != 1 or expected not in problems[0]:
                    failed += 1
                    self.stderr.write(f"probe: {what}: expected one refusal holding `{expected}`, got: {problems or 'none'}")
            out = Path(scratch) / "not-ours"
            out.mkdir()
            (out / "keep.txt").write_text("someone's file\n", encoding="utf-8")
            try:
                self.write(books.load(Path(scratch) / "good"), out)
                failed += 1
                self.stderr.write("probe: a directory the bake did not make was emptied")
            except CommandError:
                if not (out / "keep.txt").is_file():
                    failed += 1
                    self.stderr.write("probe: the bake refused a directory it did not make, and emptied it anyway")
        if failed:
            raise CommandError(f"bake --probe: FAILED, {failed} of {len(cases) + 4}")
        self.stdout.write(f"bake --probe: ok. A good book is accepted, with a figure and without, and baked to a directory "
                          f"that then holds its written pages, its static files and no outlined page; {len(cases)} books with "
                          f"one thing wrong are each refused for it and for nothing else; a directory the bake did not make "
                          f"is not emptied.")
