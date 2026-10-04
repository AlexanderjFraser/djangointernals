"""The files an agent reads, each derived from the pages and nothing else.

    /<id>.md         the twin: the page's markdown file, byte for byte (`/index.md` for the front page)
    /llms.txt        the book's map, llmstxt.org's index form: one line per written page, linking
                     its twin, with its lede, under its chapter
    /llms-full.txt   every written page in reading order, in one file (only when the book is indexable)
    /index.json      the book as data: the pin, every page's number, title, lede and headings,
                     planned pages included (a planned page has no address)
    /names.json      the reverse index by name: every name and pointer in a code span on a written
                     page, with the sections that mention it and, where a heading names it, the
                     section that is its home. A name is keyed as it is written, so a name several
                     modules define merges its mentions; a pointer is also keyed whole
                     (`path:Symbol`), which tells them apart
    /sitemap.xml     every written page's address (only when the book is indexable)

And two files for the host, Cloudflare Pages: `_headers` (the twins' media type; `noindex`
while the book is not indexable) and `_redirects` (the addresses that have moved, which the
book lists in a file of that name at its root).

One fact, one home: the title, the lede, the sections and the numbers are
read from the pages, so nothing here can drift from them. No dates and no
machine paths, so a bake is the same bytes on every machine. The views in
views.py serve these; the bake writes what the views answer.
"""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

from django.conf import settings

from . import gates as gating

GENERATED = {"by": "python manage.py bake", "spec": "SPEC.md"}


def site_url() -> str:
    return settings.SITE_URL.rstrip("/")


def twin_path(page) -> str:
    """The twin's file under the baked site, and its address without the leading slash."""
    return f"{page.id}.md" if page.id else "index.md"


def twin_url(page) -> str:
    return "/" + twin_path(page)


def pin() -> dict:
    return json.loads(Path(settings.PIN_FILE).read_text(encoding="utf-8"))


def verified_against() -> dict:
    """Every tree of pin.json: what the book's pointers resolve in."""
    out = {}
    for name, entry in pin()["trees"].items():
        out[name] = {key: entry[key] for key in ("repository", "commit", "version", "describes") if key in entry}
    return out


RELATIVE_LINK = re.compile(r"\]\(([^)\s#]+\.md)(#[^)]*)?\)")


def absolute(markdown: str, page, book) -> str:
    """A head's markdown with its relative links to other pages made full URLs of their twins,
    so that a lede quoted in llms.txt sends an agent to the page and not to a path."""
    site = site_url()

    def twin(match):
        parts = list(PurePosixPath(page.id).parent.parts) if page.id else []
        for part in PurePosixPath(match.group(1)).parts:
            if part == "..":
                parts = parts[:-1]
            elif part != ".":
                parts.append(part)
        target = "/".join(parts)[:-len(".md")]
        found = book.pages.get("" if target == "index" else target)
        if found is None:
            return match.group(0)
        return f"]({site}{twin_url(found)}{match.group(2) or ''})"
    return RELATIVE_LINK.sub(twin, markdown)


def llms(book, indexable: bool) -> str:
    """llms.txt: the index form of https://llmstxt.org, from the heads."""
    index = book.index
    site = site_url()
    lines = [f"# {absolute(index.title_md, index, book)}", "", f"> {absolute(index.lede_md, index, book)}", ""]
    lines.append(
        f"Describes Django {index.meta.get('django', '')}: every name in a code span exists in the source at that "
        f"commit, and a pointer, `path:Symbol`, names the file and symbol there that a passage is about. Every link "
        f"below is a page as markdown, the page's address with `.md` after it; drop the `.md` for the rendered page, "
        f"where each pointer is a link to its lines at that commit. The book as data: {site}/index.json. Every name, "
        f"the sections that mention it, and for a pointer the link to its lines: {site}/names.json."
        + (f" The whole book in one file: {site}/llms-full.txt." if indexable else ""))
    lines.append("")
    for chapter in book.index.children:
        written = [page for page in [chapter] + chapter.descendants if page.published]
        if not written:
            continue
        lines += [f"## {chapter.number}. {absolute(chapter.title_md, chapter, book)}", ""]
        lines += [f"- [{absolute(page.title_md, page, book)}]({site}{twin_url(page)}): {absolute(page.lede_md, page, book)}"
                  for page in written]
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def whole(book) -> str:
    """llms-full.txt: every written page's file, in reading order."""
    site = site_url()
    parts = [f"# {book.index.title_md}\n\nOne file, every written page of the book in reading order, each as its "
             f"markdown twin. The book's map, a line a page: {site}/llms.txt\n"]
    for page in book.order:
        if page.published:
            parts.append(f"\n\n<!-- {site}{twin_url(page)} -->\n\n" + page.source.read_bytes().decode("utf-8").replace("\r\n", "\n").rstrip("\n") + "\n")
    return "".join(parts)


def index(book, indexable: bool) -> dict:
    """index.json: the book as data."""
    site = site_url()
    files = {"page": "/<id>", "markdown": "/<id>.md", "map": "/llms.txt", "names": "/names.json", "this": "/index.json"}
    if indexable:
        files.update(whole="/llms-full.txt", sitemap="/sitemap.xml")
    pages = []
    for page in book.order:
        pages.append({
            "id": page.id,
            "number": page.number,
            "url": f"{site}{page.url}" if page.published else None,
            "markdown": f"{site}{twin_url(page)}" if page.published else None,
            "title": page.title_text,
            "lede": page.lede_text,
            "written": page.published,
            "django": page.meta.get("django", ""),
            "part": page.chapter.part if page.chapter is not None else "",
            "parent": page.parent.id if page.parent is not None else None,
            "chapter": page.chapter.id if page.chapter is not None and page.chapter is not page else None,
            "contents": [child.id for child in page.children],
            "sections": [{"anchor": section["id"], "heading": section["title_text"]} for section in page.sections],
            "figures": list(page.figures),
        })
    return {
        "book": {"title": book.index.title_text, "lede": book.index.lede_text, "site": site,
                 "repository": settings.REPOSITORY_URL, "licence": "CC BY 4.0", "indexable": indexable},
        "generated": GENERATED,
        "verified_against": verified_against(),
        "files": files,
        "pages": pages,
    }


def names(book) -> dict:
    """names.json: for every name and pointer in a code span on a written page, the sections
    that mention it, and its home: the first section, in reading order, whose heading names
    it. A pointer is indexed by its symbol and by its path."""
    gates = gating.current()
    found: dict[str, dict] = {}
    paths: dict[str, set] = {}

    def entry(name: str) -> dict:
        return found.setdefault(name, {"home": None, "where": set()})

    for page in book.order:
        if not page.published:
            continue
        starts = {section["line"]: section["id"] for section in page.sections}
        spans, _lines = gating.pointers.read(str(page.source))
        for span in spans:
            if span.line <= page.line:
                continue  # the front matter
            where = page.url + (f"#{starts[span.section]}" if span.section in starts else "")
            heading = span.line == span.section and span.section in starts
            if gates.is_pointer(span.body):
                try:
                    tree, path, symbol = gates.world.parse(span.body)
                except gating.pointers.Unresolved:
                    continue
                shown_path = path if tree == gates.world.subject else f"{tree}:{path}"
                paths.setdefault(shown_path, set()).add(where)
                if symbol:
                    keyed = [entry(symbol), entry(f"{shown_path}:{symbol}")]
                    linked = gates.link(span.body)
                    if linked:
                        keyed[1]["url"] = linked[0]  # the lines it lands on at the pin, which a twin does not carry
                else:
                    keyed = []
            else:
                kind, name = gating.names.take(span.body)
                keyed = [entry(name)] if kind in ("name", "call") and name else []
            for one in keyed:
                one["where"].add(where)
                if heading and one["home"] is None:
                    one["home"] = where
    return {
        "generated": GENERATED,
        "site": site_url(),
        "about": "For a name, `where` is every section that mentions it, as the page's address and the section's "
                 "anchor; an address with no anchor is the page's opening, above its first heading. `home` is the "
                 "first section in reading order whose heading names it, or null. A name is keyed as written, so one "
                 "that several modules define merges its mentions; a pointer is keyed whole too (`path:Symbol`), which "
                 "tells them apart, and that entry's `url` is the lines it lands on at the pinned commit, which the "
                 "markdown twins do not carry. Under `paths`, for a file of the source, the sections that point into it.",
        "names": {name: {"home": one["home"], "where": sorted(one["where"]), **({"url": one["url"]} if "url" in one else {})}
                  for name, one in sorted(found.items())},
        "paths": {path: sorted(where) for path, where in sorted(paths.items())},
    }


def sitemap(book) -> str:
    site = site_url()
    rows = [f"  <url><loc>{site}{page.url}</loc></url>" for page in book.order if page.published]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(rows) + "\n</urlset>\n")


def headers(indexable: bool) -> str:
    """Cloudflare Pages's `_headers`: the twins as markdown, and nothing indexed when the book is not."""
    out = "/*.md\n  Content-Type: text/markdown; charset=utf-8\n"
    if not indexable:
        out += "\n/*\n  X-Robots-Tag: noindex\n"
    return out


def redirects(book) -> list[tuple[str, str]]:
    """The addresses that have moved, as (the old address, where its page is now): the lines of
    the book's own `_redirects` file, which is Cloudflare Pages's format (`/old /new 301`, a
    `#` beginning a comment, an old address ending in `/*` taking everything under it). An
    address is a promise, and this is how one is kept when a page is renamed. The bake checks
    that each leads to a page it wrote, and copies the file beside the pages."""
    file = book.root / "_redirects"
    if not file.is_file():
        return []
    moved = []
    for line in file.read_text(encoding="utf-8").splitlines():
        words = line.split("#", 1)[0].split()
        if words:
            moved.append((words[0], words[1] if len(words) > 1 else ""))
    return moved


def dumps(data: dict) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"
