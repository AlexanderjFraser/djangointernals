#!/usr/bin/env python3
"""The link gate: every link in a baked site resolves.

    python tools/links.py DIST [--site URL]   check the site baked at DIST
    python tools/links.py --probe             prove the gate fails on what it should

DIST is a directory as `python manage.py bake` writes it and Cloudflare Pages serves it:
`a/b.html` at `/a/b`, `index.html` at `/`, every other file at its own path. The gate reads
every page (.html), every markdown twin (.md), `llms.txt`, `llms-full.txt` and `sitemap.xml`
under DIST and checks each link in them:

- In a page: every `href` and `src` of every element. An address resolves when a file answers
  for it as Pages would: `/a/b` by `a/b.html`, by `a/b/index.html` or by a file `a/b`; `/` by
  `index.html`; `/a/` by `a/index.html` or `a.html` (Pages answers it with a redirect to `/a`);
  a relative address against the page's own; a query string is not part of the address. A
  file answers only under its exact name: a difference of case or a trailing dot, which this
  machine's file system forgives, is a 404 on Pages. A fragment, `/a/b#x` or `#x`, must be the
  `id` of an element in the file it names; `#` alone is the top of the page.
- In a twin: every `[text](target)` outside fenced blocks and code spans (a destination may be
  written in angle brackets), as the page spec writes a link: a relative path to a twin;
  `#fragment` to an anchor of the target. A twin's anchors are the ids of the page baked
  beside it (`a/b.html` beside `a/b.md`), which is what the site made of its headings and
  figures; for a twin with no page beside it they are made from its headings as the site
  makes them (the heading's words, lower-cased, spaces as hyphens, punctuation dropped; a
  code span's underscores kept) and from its `figure=<name>` fences.
- In `llms.txt`: every `[text](target)`, which must be a full URL, and every bare URL in its
  text (sentence punctuation after it is not part of it); in `llms-full.txt` only the bare
  URLs (its relative links are the twins' own, relative to pages it is not); in `sitemap.xml`
  every `<loc>`. A URL under the site's own address resolves as an address does; one with
  another host is external. The site's address is `--site`, or the `<link rel="canonical">`
  of `index.html` with its path cut, or else none.
- A link to a planned page is counted apart and is no fault, though nothing answers at its
  address: the page spec allows the link and gives the page no file until it is written. Which
  pages are planned the gate reads from `index.json` beside the pages, where the bake lists
  every page and says of each whether it is written.

External links (another host, a protocol-relative `//host`, or `mailto:` and the like) are
counted and not fetched: the build must work without the network. A stylesheet's own `url()`
references are not read, nor `srcset`, nor `_headers`, `_redirects` or a `.baked` marker.
Nothing is written. One line per fault, `file: the link TARGET: why`, and a last line: `links:
ok, N links in M files; E external not fetched`, or `FAILED` with how many did not resolve.

Vendored: the copy in a book's repository is written by a command and is not edited there.
"""
from __future__ import annotations

import json
import os
import posixpath
import re
import sys
import unicodedata
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
ELSEWHERE = ("mailto:", "tel:", "data:", "javascript:")  # no address of the site at all
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
CODE = re.compile(r"(`+)(.+?)\1")  # a code span, by CommonMark's rule for one run of backticks
LINK = re.compile(r"\]\((<[^>]*>|[^)\s]+)\)")  # a markdown link's target, in angle brackets or not
URL = re.compile(r"https?://[^\s<>\"')\]]+")  # a bare URL in text
HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
QUOTED_OR_LISTED = re.compile(r"^\s*(?:>\s?|(?:[-*+]|\d+[.)])\s+)")
FIGURE = re.compile(r"\bfigure=([^\s`]+)")
LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
CANONICAL = re.compile(r'<link[^>]*rel="canonical"[^>]*href="([^"]+)"')
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
AGENT_FILES = ("llms.txt", "llms-full.txt", "sitemap.xml")
PUNCTUATION = ".,;:!?)"  # what a sentence may end a bare URL with


def plain(markdown: str) -> str:
    """A heading's words as the site reads them before making its anchor: a code span's text
    as it is, emphasis marks gone, a link's text without its target."""
    out = []
    for i, piece in enumerate(CODE.split(markdown)):
        if i % 3 == 2:
            out.append(piece)  # the code span's text
        elif i % 3 == 0:
            piece = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", piece)
            out.append(re.sub(r"(?<!\w)[*_]{1,2}(?=\S)|(?<=\S)[*_]{1,2}(?!\w)", "", piece))
    return " ".join("".join(out).split())


def slugify(value: str) -> str:
    """Django's slugify, which is how the site makes a heading's anchor."""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-_")


def without_code(line: str) -> str:
    """A line of markdown with its code spans blanked, so that `](` inside one is no link."""
    return CODE.sub(lambda m: " " * len(m.group(0)), line)


class Page(HTMLParser):
    """The links and the ids of one HTML file."""

    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if value is None:
                continue
            if name == "id":
                self.ids.add(value)
            elif name in ("href", "src"):
                self.links.append(value)

    handle_startendtag = handle_starttag


def read(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n")


def outside_fences(text: str):
    """(line number, line) for every line of a markdown file that is not inside a fence."""
    fence = None
    for number, line in enumerate(text.split("\n"), 1):
        opened = FENCE.match(line)
        if fence:
            if opened and opened.group(1)[0] == fence[0] and len(opened.group(1)) >= len(fence):
                fence = None
            continue
        if opened:
            fence = opened.group(1)
            continue
        yield number, line


class Site:
    """A baked site: what file answers for an address, and what a file holds."""

    def __init__(self, dist: str, site: str | None = None):
        self.dist = os.path.abspath(dist)
        self.site = (site or self.canonical() or "").rstrip("/")
        self.outlined = self.in_outline()
        self._pages: dict[str, Page] = {}
        self._anchors: dict[str, set[str]] = {}
        self._listings: dict[str, set[str]] = {}

    def canonical(self) -> str | None:
        index = os.path.join(self.dist, "index.html")
        if os.path.isfile(index):
            found = CANONICAL.search(read(index))
            if found:
                parts = urlsplit(found.group(1))
                return f"{parts.scheme}://{parts.netloc}"
        return None

    def in_outline(self) -> set[str]:
        """The ids of the pages index.json says are not written: lines in the contents, with no file."""
        index = os.path.join(self.dist, "index.json")
        if not os.path.isfile(index):
            return set()
        try:
            pages = json.loads(read(index)).get("pages", [])
            return {page["id"] for page in pages if page.get("written") is False}
        except (ValueError, TypeError, KeyError, AttributeError):
            return set()

    def outlined_at(self, address: str) -> bool:
        path = unquote(address.split("?", 1)[0]).strip("/")
        return (path[:-len(".md")] if path.endswith(".md") else path) in self.outlined

    def files(self) -> list[str]:
        out = []
        for dp, dirs, names in os.walk(self.dist):
            dirs.sort()
            for name in sorted(names):
                rel = os.path.relpath(os.path.join(dp, name), self.dist).replace(os.sep, "/")
                if name.endswith((".html", ".md")) or rel in AGENT_FILES:
                    out.append(rel)
        return out

    def listing(self, directory: str) -> set[str]:
        if directory not in self._listings:
            try:
                self._listings[directory] = set(os.listdir(directory))
            except OSError:
                self._listings[directory] = set()
        return self._listings[directory]

    def exact(self, candidate: str) -> bool:
        """Is `candidate` a file under dist, each part of its path spelt exactly as the file
        system lists it? A case or a trailing-dot difference that this machine forgives
        would be a 404 on the host."""
        parts = [p for p in candidate.split("/") if p]
        if not parts or any(p in (".", "..") for p in parts):
            return False
        here = self.dist
        for part in parts:
            if part not in self.listing(here):
                return False
            here = os.path.join(here, part)
        return os.path.isfile(here)

    def file_for(self, address: str) -> str | None:
        """The file Pages serves at an absolute address, relative to dist, or None."""
        path = unquote(address.split("?", 1)[0]).lstrip("/")
        if path == "" or path.endswith("/"):
            candidates = [path + "index.html"] + ([path.rstrip("/") + ".html"] if path else [])
        else:
            candidates = [path, path + ".html", path + "/index.html"]
        for candidate in candidates:
            if self.exact(candidate):
                return candidate
        return None

    def page(self, rel: str) -> Page:
        if rel not in self._pages:
            parsed = Page()
            parsed.feed(read(os.path.join(self.dist, *rel.split("/"))))
            self._pages[rel] = parsed
        return self._pages[rel]

    def anchors(self, rel: str) -> set[str]:
        """A twin's anchors: the ids of the page baked beside it; failing that, its headings'
        addresses as the site makes them and its figures' `figure-<name>`."""
        if rel not in self._anchors:
            beside = rel[:-len(".md")] + ".html"
            if self.exact(beside):
                self._anchors[rel] = set(self.page(beside).ids)
                return self._anchors[rel]
            found = set()
            text = read(os.path.join(self.dist, *rel.split("/")))
            for _number, line in outside_fences(text):
                stripped = line
                while QUOTED_OR_LISTED.match(stripped):
                    stripped = QUOTED_OR_LISTED.sub("", stripped, 1)
                heading = HEADING.match(stripped)
                if heading:
                    found.add(slugify(plain(heading.group(2))))
            for line in text.split("\n"):
                if FENCE.match(line):
                    figure = FIGURE.search(line)
                    if figure:
                        found.add(f"figure-{figure.group(1)}")
            self._anchors[rel] = found
        return self._anchors[rel]

    def fragment_missing(self, rel: str, fragment: str) -> str | None:
        """Why a fragment is not in the file that answers, or None."""
        if not fragment:
            return None  # `#` alone: the top of the page
        if rel.endswith(".html"):
            return None if fragment in self.page(rel).ids else f"{rel} has no element with the id `{fragment}`"
        if rel.endswith(".md"):
            return None if fragment in self.anchors(rel) else f"{rel} has no heading or figure whose address is `#{fragment}`"
        return f"{rel} is not a page: a fragment cannot be checked in it"


def check(dist: str, site: str | None = None) -> tuple[list[str], dict]:
    """Every fault, as `file: the link TARGET: why`, and the counts."""
    held = Site(dist, site)
    faults: list[str] = []
    counts = {"files": 0, "links": 0, "external": 0, "outlined": 0}

    def missing(address: str) -> str | None:
        """Why nothing answers at an address, or None when a planned page is linked."""
        if held.outlined_at(address):
            counts["outlined"] += 1
            return None
        return f"nothing is served at {address}"

    def address_of(url: str) -> str | None:
        """An absolute address of the site for a full URL under it, else None (external)."""
        if held.site and (url == held.site or url.startswith(held.site + "/")):
            return url[len(held.site):] or "/"
        return None

    def resolve(rel: str, target: str, base_address: str, relative_to_file: bool) -> str | None:
        """Why a link does not resolve, or None. `relative_to_file`: a twin's link is a path
        relative to the twin's directory; a page's is an address relative to the page's."""
        counts["links"] += 1
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        lowered = target.lower()
        if lowered.startswith(ELSEWHERE) or lowered.startswith("//") or SCHEME.match(target):
            url, _, fragment = target.partition("#")
            address = address_of(url) if SCHEME.match(url) else None
            if address is None:
                counts["external"] += 1
                return None
            found = held.file_for(address)
            if found is None:
                return missing(address)
            return held.fragment_missing(found, fragment) if fragment or target.endswith("#") else None
        path, hash_, fragment = target.partition("#")
        if not path:
            return held.fragment_missing(rel, fragment) if hash_ else "an empty link"
        if path.startswith("/"):
            address = path
        elif relative_to_file:
            address = "/" + posixpath.normpath(posixpath.join(posixpath.dirname(rel), path))
        else:
            address = posixpath.normpath(posixpath.join(posixpath.dirname(base_address) or "/", path))
            if path.endswith("/") and not address.endswith("/"):
                address += "/"
        found = held.file_for(address)
        if found is None:
            return missing(address)
        return held.fragment_missing(found, fragment) if hash_ else None

    for rel in held.files():
        counts["files"] += 1
        full = os.path.join(held.dist, *rel.split("/"))
        found: list[tuple[str, str | None]] = []
        if rel.endswith(".html"):
            base = "/" if rel == "index.html" else "/" + rel[:-len(".html")]
            found = [(link, resolve(rel, link, base, False)) for link in held.page(rel).links]
        elif rel.endswith(".md"):
            text = read(full)
            found = [(link, resolve(rel, link, "", True))
                     for _n, line in outside_fences(text) for link in LINK.findall(without_code(line))]
        elif rel == "llms.txt":
            text = read(full)
            linked = [link.strip("<>") for link in LINK.findall(text)]
            for link in linked:
                if not SCHEME.match(link):
                    counts["links"] += 1
                    found.append((link, "a link in llms.txt is a full URL"))
                else:
                    found.append((link, resolve(rel, link, "/", False)))
            bare = [url.rstrip(PUNCTUATION) for url in URL.findall(text)]
            found += [(url, resolve(rel, url, "/", False)) for url in bare if url not in linked]
        elif rel == "llms-full.txt":
            found = [(url, resolve(rel, url, "/", False)) for url in (u.rstrip(PUNCTUATION) for u in URL.findall(read(full)))]
        elif rel == "sitemap.xml":
            found = [(url, resolve(rel, url, "/", False)) for url in LOC.findall(read(full))]
        faults += [f"{rel}: the link `{link}`: {why}" for link, why in found if why]
    return faults, counts


def count(n: int, what: str) -> str:
    return f"{n} {what}" + ("" if n == 1 else "s")


def run(dist: str, site: str | None) -> int:
    if not os.path.isdir(dist):
        raise SystemExit(f"{dist}: no such directory")
    faults, counts = check(dist, site)
    for line in faults:
        print(line)
    print(f"links: {'FAILED' if faults else 'ok'}, {count(counts['links'], 'link')} in {count(counts['files'], 'file')}; "
          f"{counts['external']} external not fetched"
          + (f"; {counts['outlined']} to a planned page, which has a line in the contents and no file" if counts["outlined"] else "")
          + (f"; {count(len(faults), 'link')} did not resolve" if faults else ""))
    return 1 if faults else 0


# ----------------------------------------------------------------------------
# the probe

PROBE_GOOD = {  # a baked site whose every link resolves
    "index.html": '<!doctype html><html><head><link rel="canonical" href="https://example.test/">\n'
                  '<link rel="stylesheet" href="/static/site.css"><link rel="alternate" type="text/markdown" href="/index.md"></head>\n'
                  '<body id="top"><h2 id="what-does-each-status-publish">What?</h2><a href="/a/b">a page</a> <a href="/a/b#one">an id</a> <a href="https://example.org/x">external</a>\n'
                  '<a href="mailto:x@y.test">mail</a> <a href="#top">own id</a> <a href="#">the top</a> <a href="/a">a.html beside a/</a>\n'
                  '<a href="/a/">redirected</a> <a href="a/b.md">relative</a> <a href="/">the root</a> <a href="/index.json">a file</a>\n'
                  '<a href="/a/b.html">the html itself</a> <a href="/a/b?x=1">a query string</a> <a href="/d">a directory</a>\n'
                  '<a href="/d/">its index</a> <a href="//example.org/x">protocol-relative, external</a>\n'
                  '<a href="HTTPS://example.org/y">a scheme in capitals</a> <a href="/a/d">in outline</a></body></html>\n',
    "a.html": '<html><body><h1 id="a">A</h1></body></html>\n',
    "a/b.html": '<html><body><section id="one"></section><h2 id="one-set_count-under-two">One</h2><figure id="figure-one"></figure>\n'
                '<a href="../a">up</a> <a href="b.md#one-set_count-under-two">a twin\'s heading</a> <a href="../d/">a slash kept</a>\n'
                '</body></html>\n',
    "a/b.md": "---\nstatus: verified\n---\n\n# B\n\nSee [the index](../index.md), [its contents](../index.md#what-does-each-status-publish), "
              "[the figure](#figure-one), [external](https://example.org/), [a page in outline](d.md), [in angle brackets](<../index.md>), "
              "and `handlers[0](request)`, which is no link, nor is `` a `](x.md)` inside two backticks ``.\n\n"
              "## One `set_count` under *two*\n\n[own heading](#one-set_count-under-two) [the lone twin](alone.md#where-is-_meta-kept)\n\n"
              "```text figure=one\n[not read](zzz.md)\n```\n\n*A caption.*\n",
    "a/alone.md": "# Alone, with no page beside it\n\n## Where is `_meta` kept?\n\n> ## A quoted heading\n\n- ## In a list\n\n"
                  "    ## indented four: a code block\n\n## See [the index](../index.md)\n\n[q](#a-quoted-heading) [l](#in-a-list) "
                  "[s](#see-the-index) [d](#where-is-_meta-kept) [f](#figure-lone)\n\n```text figure=lone\nx\n```\n\n*A caption.*\n",
    "d/index.html": "<html><body>d</body></html>\n",
    "index.md": "# Index\n\n## What does each status publish?\n\n[in outline](a/d.md) [a section's id, which only the page beside the twin has](a/b.md#one)\n",
    "index.json": '{"pages": [{"id": "", "written": true}, {"id": "a/b", "written": true}, {"id": "a/d", "written": false}, '
                  '{"id": "a/gone", "written": true}]}\n',
    "static/site.css": "@import url(nope.css);\n",
    "llms.txt": "# Index\n\n> A lede.\n\nThe data: https://example.test/index.json. And https://example.test/a/b#one, with a fragment.\n\n"
                "## B\n\n- [B](https://example.test/a/b.md): lede\n- [ext](https://other.test/x.md): external\n",
    "llms-full.txt": "<!-- https://example.test/a/b.md -->\n[relative, not read](zzz.md)\n",
    "sitemap.xml": '<?xml version="1.0"?><urlset><url><loc>https://example.test/a/b</loc></url></urlset>\n',
    ".baked": "not read\n",
}
PROBE_BAD = {  # appended to the good site: every one a link that does not resolve
    "index.html": '<a href="/a/b#nope">x</a><a href="/missing">x</a><a href="#gone">x</a><img src="/static/nope.png">\n'
                  '<a href="/A/B">x</a><a href="/a/b.html.">x</a><a href="/Index.json">x</a>\n',
    "a/b.html": '<a href="../../x">x</a><a href="c">x</a>\n',
    "a/b.md": "\n[a missing section](../index.md#nope), [a missing twin](c.md), [no figure](#figure-two), "
              "[a page listed as written and not baked](gone.md), [out of the site](../../outside.txt), "
              "[a lone twin's missing heading](alone.md#indented-four-a-code-block), [a bracketed miss](<nope.md>).\n",
    "llms.txt": "- [Z](https://example.test/zz.md): z\n- [rel](a/b.md): r\n\nAnd https://example.test/names.json too, "
                "and https://example.test/a/b#nope.\n",
    "llms-full.txt": "https://example.test/nothing.md\n",
    "sitemap.xml": "<url><loc>https://example.test/zz</loc></url>\n",
}
PROBE_FAULTS = {
    ("index.html", "/a/b#nope"), ("index.html", "/missing"), ("index.html", "#gone"), ("index.html", "/static/nope.png"),
    ("index.html", "/A/B"), ("index.html", "/a/b.html."), ("index.html", "/Index.json"),
    ("a/b.html", "../../x"), ("a/b.html", "c"),
    ("a/b.md", "../index.md#nope"), ("a/b.md", "c.md"), ("a/b.md", "#figure-two"), ("a/b.md", "gone.md"),
    ("a/b.md", "../../outside.txt"), ("a/b.md", "alone.md#indented-four-a-code-block"), ("a/b.md", "<nope.md>"),
    ("llms.txt", "https://example.test/zz.md"), ("llms.txt", "a/b.md"), ("llms.txt", "https://example.test/names.json"),
    ("llms.txt", "https://example.test/a/b#nope"),
    ("llms-full.txt", "https://example.test/nothing.md"), ("sitemap.xml", "https://example.test/zz"),
}


def probe() -> int:
    import shutil
    import tempfile
    work = tempfile.mkdtemp(prefix="linksprobe-")
    failed = []

    def expect(label: str, got, want) -> None:
        if got != want:
            failed.append(f"{label}: got {got!r}, wanted {want!r}")

    try:
        def write(root: str, files: dict) -> None:
            for path, text in files.items():
                full = os.path.join(root, *path.split("/"))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "a", encoding="utf-8", newline="\n") as f:
                    f.write(text)

        good, dist = os.path.join(work, "good"), os.path.join(work, "dist")
        write(good, PROBE_GOOD)
        write(dist, PROBE_GOOD)
        write(dist, PROBE_BAD)
        write(work, {"outside.txt": "a file above the site\n"})  # a link that climbs out must not find it
        good_faults, good_counts = check(good, "https://example.test")
        expect("a site whose every link resolves passes", good_faults, [])
        expect("external links counted, not fetched", good_counts["external"], 6)  # example.org three times, the mail, the protocol-relative, other.test
        expect("links to a planned page counted apart", good_counts["outlined"], 3)  # from index.html, a/b.md and index.md
        expect("files read", good_counts["files"], 10)  # four pages, three twins, llms.txt, llms-full.txt, sitemap.xml; not the css or .baked
        faults, counts = check(dist, "https://example.test")
        found = {(line.split(": the link `", 1)[0], line.split("`")[1]) for line in faults}
        expect("the faults, and only the faults", found, PROBE_FAULTS)
        expect("every fault says why", all(line.count(": ") >= 2 for line in faults), True)
        expect("a fault counts no external link", counts["external"], good_counts["external"])
        faults_by_canonical, _counts = check(dist)
        expect("the site's address read from the canonical link", faults_by_canonical, faults)
        faults_no_site, _counts = check(dist, "https://nowhere.test")
        expect("under another site every URL is external", {f for f in faults_no_site if "://" in f.split("`")[1]}, set())
        expect("an anchor is made as the site makes one, a code span's underscores kept, a link's text alone",
               [slugify(plain(h)) for h in ("Who calls `BaseHandler.get_response`?", "Where is `BaseHandler._middleware_chain` kept?",
                                            "What does `WSGIHandler.__init__` call?", "See [the index](../index.md), *now*")],
               ["who-calls-basehandlerget_response", "where-is-basehandler_middleware_chain-kept", "what-does-wsgihandler__init__-call",
                "see-the-index-now"])
        expect("a twin's anchors are its page's ids when the page is beside it", Site(good).anchors("a/b.md"),
               {"one", "one-set_count-under-two", "figure-one"})
        expect("and its headings' addresses, quoted and listed ones included, and its figures', when it has no page",
               Site(good).anchors("a/alone.md"),
               {"alone-with-no-page-beside-it", "where-is-_meta-kept", "a-quoted-heading", "in-a-list", "see-the-index", "figure-lone"})
        expect("a file answers only under its exact name", [Site(good).exact(c) for c in ("a/b.html", "A/b.html", "a/b.html.", "a/B.HTML")],
               [True, False, False, False])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if failed:
        print("PROBE FAILED:\n  " + "\n  ".join(failed))
        return 1
    print("probe ok: an address resolves as Pages serves it (a page by its .html, the root by index.html, a directory by its "
          "index or its redirect, a file by itself under its exact name, a relative address against the page's own, a query "
          "string set aside); a fragment must be an id in the page it names, or an anchor of the twin, taken from the page "
          "baked beside it or made as the site makes them; a twin's links are read outside its fences and code spans, in angle "
          "brackets too; llms.txt's links are full URLs, its and llms-full.txt's bare URLs (sentence punctuation set aside) and "
          "the sitemap's locations resolve under the site's address, read from the flag or the canonical link; a link to a "
          "planned page is counted apart; external links are counted and not fetched; a link cannot leave the site; a site whose "
          "every link resolves passes")
    return 0


def main(argv: list[str]) -> int:
    args = list(argv)
    site = None
    while "--site" in args:
        at = args.index("--site")
        if at + 1 >= len(args):
            raise SystemExit("--site needs a URL")
        site = args[at + 1]
        del args[at:at + 2]
    if "--probe" in args:
        return probe()
    flags = [a for a in args if a.startswith("--")]
    rest = [a for a in args if not a.startswith("--")]
    if flags or len(rest) != 1:
        raise SystemExit(__doc__)
    return run(rest[0], site)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
