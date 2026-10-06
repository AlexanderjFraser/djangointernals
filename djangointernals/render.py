"""One page's markdown as HTML, and everything SPEC.md asks of a page's body, enforced.

A page's body is read as CommonMark with tables. What comes out is the
page in the parts the templates lay out: the title (the one H1), the lede
(the first paragraph), the introduction (whatever else stands above the
first H2), and the sections (each H2 and what is under it).

What is refused here, each with its file and line: a page that does not
open with its H1 and a lede; a second H1; a heading below H3, or one
written by underlining; two headings on a page that come to the same
anchor, or a heading whose anchor begins `figure-`; raw HTML, a comment
included; an image; a link to another page that is not the relative path
of its `.md` file, that names no page of the book, or that names the book
by any of its hosts; a figure with no SVG beside it or no caption under
it, or whose SVG scripts, loads, moves or links out of itself; an empty
section on a written page.

What is changed on the way to HTML and nowhere else:

- Straight quotes in prose become curly, and a long name in a code span may
  break after a slash or a colon and before a dot.
- **A pointer becomes a link to the lines it lands on** at the pinned commit
  (gates.py), and is shown by its symbol, the file in the link's title. In a
  table it is shown with its file under it.
- **Pointers in parentheses leave the sentence.** A parenthesis that holds
  nothing but pointers, `(…)` after the words they support, is taken out of
  the paragraph and set beside it as its sources: in the margin where there
  is one, under the paragraph where there is not. The markdown keeps them
  where they were written, which is where an agent wants them.
- A quotation that opens with a phrase in bold is a note with that phrase
  as its label (`> **Why.** …`).
- A link to `other.md` becomes that page's address; a link to a page that
  is only planned becomes plain text.
- A figure's fenced source becomes the SVG drawn from it, numbered, with
  its caption; a table with an italic paragraph directly under it becomes a
  numbered table with that caption. The numbers are the book's (book.py).
- A `runtime-names` block is not shown: it declares names for the name
  gate, and a reader of the page has no use for it.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html import escape
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from django.conf import settings
from django.utils.text import slugify
from markdown_it import MarkdownIt
from markdown_it.token import Token

FIGURE = re.compile(r"\bfigure=(\S+)")
FIGURE_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
UNDRAWN = {"script", "style", "foreignObject", "image", "iframe", "feImage", "animate", "animateTransform", "animateMotion", "set"}
PAINTED = {"style", "fill", "stroke", "color", "font", "font-family", "font-size", "font-weight"}
ANCHOR_TAG = re.compile(r"</?a\b[^>]*>")
PROLOG = re.compile(r"\A\s*(?:(?:<\?xml.*?\?>|<!DOCTYPE.*?>|<!--.*?-->)\s*)*", re.S)
COLUMN = 646  # the text column in CSS pixels at the size the stylesheet sets: a wider figure uses the margin
UNBROKEN = 16  # a code span of this many characters or fewer is never broken across lines
BETWEEN = re.compile(r"\s*(?:[,;]|,?\s*and)?\s*")  # what may stand between two pointers of one parenthesis
SOURCED = {"paragraph_open", "bullet_list_open", "ordered_list_open", "blockquote_open"}  # blocks whose sources are set beside them


def breakable(code: str) -> str:
    """A code span's text, escaped, with the places a long name or pointer may break. A short
    one is given none: `settings.DEBUG` reads worse broken than it fits whole, and in the narrow
    first column of a table a browser breaks wherever it is allowed to."""
    text = escape(code, quote=False)
    if len(code) <= UNBROKEN:
        return text
    text = re.sub(r"([/:])(?=[^\s/:])", r"\1<wbr>", text)
    return re.sub(r"(?<=\w)\.(?=\w)", "<wbr>.", text)


def unlinked(html: str) -> str:
    """Inline HTML with its links' tags removed, for a place that is itself a link: a heading
    with a pointer in it inside the navigation, a title inside the contents."""
    return ANCHOR_TAG.sub("", html)


def book_host(href: str) -> bool:
    """Does a URL name the book's own site, by any of its hosts and either scheme?"""
    host = (urlsplit(href).hostname or "").lower()
    own = (urlsplit(settings.SITE_URL).hostname or "").lower()
    return bool(host) and host in {own, f"www.{own}", f"{settings.PAGES_PROJECT}.pages.dev"}


def plain(inline: Token) -> str:
    """An inline token's text with no markup, code spans included."""
    out = []
    for child in inline.children or []:
        if child.type in ("text", "code_inline"):
            out.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            out.append(" ")
    return "".join(out).strip()


def is_figure(token: Token) -> bool:
    return token.type == "fence" and bool(FIGURE.search(token.info))


def shown(body: str, gates) -> tuple[str, str]:
    """A pointer as a reader is shown it: (what it names, where that is). A symbol and its
    file; a file and its directory; a directory and what it is in. A library's tree is named."""
    tree, path, symbol = gates.world.parse(body)
    prefix = "" if tree == gates.world.subject else f"{tree}: "
    if symbol:
        return symbol, prefix + path
    head, _, tail = path.rstrip("/").rpartition("/")
    return tail + ("/" if path.endswith("/") else ""), prefix + (head + "/" if head else "")


def pointer(body: str, gates, full: bool = False) -> str:
    """A code span's HTML. A pointer is a link to the lines it lands on at the pin (gates.py),
    shown by its symbol; `full` adds the file under it, as the margin and a table show it.
    Anything else, and a pointer that does not resolve (the gate refuses the page), is code."""
    linked = gates.link(body) if gates is not None and gates.is_pointer(body) else None
    if linked is None:
        return f"<code>{breakable(body)}</code>"
    href, title = linked
    what, where = shown(body, gates)
    link = f'href="{escape(href, quote=True)}" title="{escape(title, quote=True)}"'
    if full:
        return f'<a class="src" {link}><code>{breakable(what)}</code> <span class="in">{breakable(where)}</span></a>'
    symbol = gates.world.parse(body)[2]
    return f'<a class="pointer" {link}><code>{breakable(what if symbol else where + what)}</code></a>'


def sources(tokens: list[Token], gates) -> list[str]:
    """Take out of a block's inline text every parenthesis that holds only pointers, and
    return the pointers, each once, in the order they were written."""
    found: list[str] = []
    if gates is None:
        return found
    for token in tokens:
        kids = token.children if token.type == "inline" else None
        if not kids:
            continue
        kept, i = [], 0
        while i < len(kids):
            kid = kids[i]
            kept.append(kid)
            if kid.type != "text" or not kid.content.endswith("("):
                i += 1
                continue
            group, j = [], i + 1
            while j < len(kids):
                if kids[j].type == "code_inline" and gates.is_pointer(kids[j].content) and gates.link(kids[j].content):
                    group.append(kids[j].content)
                    j += 1
                    if j < len(kids) and kids[j].type == "text" and kids[j].content.startswith(")"):
                        break
                    while j < len(kids) and (kids[j].type == "softbreak" or (kids[j].type == "text" and BETWEEN.fullmatch(kids[j].content))):
                        j += 1
                    continue
                group = []
                break
            closes = j < len(kids) and kids[j].type == "text" and kids[j].content.startswith(")")
            if group and closes:
                kid.content = kid.content[:-1].rstrip()
                kids[j].content = kids[j].content[1:]
                found += [body for body in group if body not in found]
                i = j
            else:
                i += 1
        token.children = kept
    return found


def beside(found: list[str], gates) -> str:
    """A block's sources, set beside it."""
    if not found:
        return ""
    return '<aside class="sources" aria-label="In the source">' + "".join(pointer(body, gates, full=True) for body in found) + "</aside>\n"


class Rules:
    """The render rules that differ from CommonMark's defaults. `env` carries the page being
    rendered, the book it is in, the line of the block being rendered, and the problems so far."""

    def code_inline(self, tokens, idx, options, env):
        return pointer(tokens[idx].content, env.get("gates"), full=bool(env.get("in_table")))

    def fence(self, tokens, idx, options, env):
        token = tokens[idx]
        words = token.info.split()
        if words and words[0] == "runtime-names":
            return ""
        kind = f' data-kind="{escape(words[0])}"' if words else ""
        return f"<pre{kind}><code>{escape(token.content, quote=False)}</code></pre>\n"

    def table_open(self, tokens, idx, options, env):
        env["in_table"] = True
        return '<div class="table"><table>\n'

    def table_close(self, tokens, idx, options, env):
        env["in_table"] = False
        return "</table></div>\n"

    def blockquote_open(self, tokens, idx, options, env):
        """A quotation that opens with a phrase in bold is a note, and the phrase its label."""
        first = tokens[idx + 2] if idx + 2 < len(tokens) and tokens[idx + 1].type == "paragraph_open" else None
        opening = [child for child in (first.children or []) if not (child.type == "text" and not child.content)] if first is not None else []
        note = bool(opening) and opening[0].type == "strong_open"
        env.setdefault("quotes", []).append("aside" if note else "blockquote")
        return '<aside class="note">\n' if note else "<blockquote>\n"

    def blockquote_close(self, tokens, idx, options, env):
        return f"</{env['quotes'].pop()}>\n"

    def heading_open(self, tokens, idx, options, env):
        token = tokens[idx]
        anchor = token.meta.get("id")
        return f'<{token.tag} id="{anchor}">' if anchor else f"<{token.tag}>"

    def link_open(self, tokens, idx, options, env):
        """A link to another page is written to its .md file, as it works on disk and on
        GitHub; here it becomes the page's address, or plain text if the page is not written."""
        href = tokens[idx].attrGet("href") or ""
        opened = env.setdefault("links", [])
        page, book = env["page"], env["book"]
        where = f"{page.where}:{env['line']}"
        if SCHEME.match(href) or href.startswith("#") or href.startswith("//"):
            if href.startswith("#"):
                env["fragments"].append((where, href, page, href[1:]))
            elif book_host(href):
                env["problems"].append(f"{where}: the link `{href}`: a link to a page of the book is the relative path of "
                                       f"its .md file, not its address on the site")
            opened.append("a")
            return self.renderToken(tokens, idx, options, env)
        path, _, fragment = href.partition("#")
        target = None
        if href.startswith("/") or not path.endswith(".md"):
            env["problems"].append(f"{where}: the link `{href}`: a link to another page is the path of its .md file from "
                                   f"this file, and a link out of the book is a full URL")
        else:
            parts = list(PurePosixPath(page.id).parent.parts) if page.id else []
            for part in PurePosixPath(path).parts:
                if part == "..":
                    if not parts:
                        parts = None
                        break
                    parts.pop()
                elif part != ".":
                    parts.append(part)
            wanted = "/".join(parts)[: -len(".md")] if parts is not None else None
            if wanted is not None:
                target = book.pages.get("" if wanted == "index" else wanted)
            if target is None:
                came_to = f"{wanted}.md" if wanted is not None else "a place above the book"
                env["problems"].append(f"{where}: the link `{href}`: there is no such page in this book (a link is "
                                       f"relative to the file it is written in: this one comes to {came_to})")
        if target is not None and fragment:
            env["fragments"].append((where, href, target, fragment))
        if target is None or not target.published:
            opened.append("span")
            return '<span class="planned">'
        opened.append("a")
        return f'<a href="{escape(target.url + ("#" + fragment if fragment else ""))}">'

    def link_close(self, tokens, idx, options, env):
        return f"</{env['links'].pop()}>"


def markdown() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True, "typographer": True}).enable(["table", "smartquotes"])
    for name in ("code_inline", "fence", "table_open", "table_close", "blockquote_open", "blockquote_close", "heading_open",
                 "link_open", "link_close"):
        md.add_render_rule(name, getattr(Rules, name))
    return md


MD = markdown()


def blocks(tokens: list[Token]) -> list[tuple[int, int]]:
    """The top-level blocks of a document, each as (its first token, its last)."""
    out, start = [], 0
    for i, token in enumerate(tokens):
        if token.level != 0:
            continue
        if token.nesting == 1:
            start = i
        elif token.nesting == -1:
            out.append((start, i))
        else:
            out.append((i, i))
    return out


def stub(body: str) -> bool:
    """Is this page only its title and one paragraph? Then it is planned and not written:
    it has a line in the contents, and no page of its own."""
    return len(blocks(MD.parse(body, {}))) <= 2


def inline(token: Token, env) -> str:
    return MD.renderer.renderInline(token.children or [], MD.options, env)


def caption(under: Token | None) -> list[Token] | None:
    """The tokens of a caption: a paragraph that is one italic run from end to end."""
    children = (under.children or []) if under is not None else []
    whole = (len(children) >= 3 and children[0].type == "em_open" and children[-1].type == "em_close"
             and not any(c.type == "em_close" and c.level == children[0].level for c in children[1:-1]))
    return children[1:-1] if whole else None


def drawn(svg: str) -> tuple[str | None, float | None]:
    """What is wrong with a figure's SVG, if anything, and the width it was drawn at. The
    file is put into the page as it is, so it is held to what a page is held to: no script,
    nothing that loads, and classes where a colour or a font would be."""
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as why:
        return f"a figure is one <svg> element with a viewBox, and this is not well-formed ({why})", None
    box = (root.get("viewBox") or "").replace(",", " ").split()
    if root.tag.rsplit("}", 1)[-1] != "svg" or len(box) != 4:
        return "a figure is one <svg> element with a viewBox", None
    if "fig" not in (root.get("class") or "").split():
        return 'a figure\'s <svg> has class="fig", which is what the stylesheet draws it by', None
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag in UNDRAWN:
            return f"a figure carries no script, loads nothing and does not move: <{tag}>", None
        for attribute, value in element.attrib.items():
            attribute = attribute.rsplit("}", 1)[-1]
            if attribute.startswith("on"):
                return f"a figure carries no script and loads nothing: `{attribute}` on <{tag}>", None
            if attribute in PAINTED:
                return f"a figure carries classes and no colour or font of its own: `{attribute}` on <{tag}>", None
            if attribute == "href" and not value.startswith("#"):
                return f"a figure links nowhere outside itself: `href` on <{tag}> is `{value}`, not `#id`", None
    try:
        return None, float(box[2])
    except ValueError:
        return "a figure is one <svg> element with a viewBox", None


def figure(page, fence: Token, under: Token | None, env) -> str:
    """A figure: the SVG drawn from the fenced block's source, and the italic paragraph under
    the block, which is its caption. The source stays in the markdown, for the reader of that."""
    where = f"{page.where}:{env['line']}"
    name = FIGURE.search(fence.info).group(1)
    problems = env["problems"]
    if not FIGURE_NAME.fullmatch(name):
        problems.append(f"{where}: the figure `{name}`: a figure's name is lower-case words joined by hyphens")
        return ""
    # a chapter's figures are in one directory, beside its sections: pages/<chapter>/figures/
    home = env["book"].root / page.chapter.id if page.chapter is not None else env["book"].root
    file = home / "figures" / f"{name}.svg"
    try:
        shown_at = file.relative_to(settings.BASE_DIR).as_posix()
    except ValueError:
        shown_at = file.as_posix()
    svg, width = "", None
    if not file.is_file():
        problems.append(f"{where}: the figure `{name}`: there is no {shown_at}")
    else:
        svg = PROLOG.sub("", file.read_text(encoding="utf-8")).strip()
        wrong, width = drawn(svg)
        if wrong:
            problems.append(f"{shown_at}: {wrong}")
    words = caption(under)
    if words is None:
        problems.append(f"{where}: the figure `{name}`: its caption is the paragraph under it, one italic run from end to end")
    said = MD.renderer.renderInline(words, MD.options, env) if words else ""
    if name in env["figures"]:
        problems.append(f"{where}: the figure `{name}`: this page has another of that name")
    env["figures"].append(name)
    wide = " wide" if width and width > COLUMN else ""
    size = f' style="--natural: {width:g}px"' if width else ""
    label = escape(" ".join(plain(under).split()), quote=True) if under is not None else ""
    return (f'<figure class="figure{wide}" id="figure-{name}"{size}>\n<div class="art" role="img" aria-label="{label}">{svg}</div>\n'
            f'<figcaption><span class="no">Figure \x02F{len(env["figures"])}\x03</span> {said}</figcaption>\n</figure>\n')


def body(page, tokens: list[Token], spans: list[tuple[int, int]], env) -> str:
    """Some of a page's top-level blocks as HTML: each figure put together from its two
    blocks, each captioned table from its two, and each block's sources set beside it."""
    out, i = [], 0
    gates = env.get("gates")
    while i < len(spans):
        first, last = spans[i]
        token = tokens[first]
        env["line"] = page.line + (token.map[0] if token.map else 0) + 1
        under = tokens[spans[i + 1][0] + 1] if i + 1 < len(spans) and tokens[spans[i + 1][0]].type == "paragraph_open" else None
        if is_figure(token):
            out.append(figure(page, token, under, env))
            i += 1 if under is not None else 0
        elif token.type == "table_open" and caption(under) is not None:
            env["tables"] += 1
            table = MD.renderer.render(tokens[first:last + 1], MD.options, env)
            said = MD.renderer.renderInline(caption(under), MD.options, env)
            out.append(f'<figure class="tabular">\n<figcaption><span class="no">Table \x02T{env["tables"]}\x03</span> {said}</figcaption>\n{table}</figure>\n')
            i += 1
        else:
            found = sources(tokens[first:last + 1], gates) if token.type in SOURCED else []
            out.append(MD.renderer.render(tokens[first:last + 1], MD.options, env))
            out.append(beside(found, gates))
        i += 1
    return "".join(out)


def render(page, book, problems: list[str]) -> None:
    """Fill in `page` from its markdown: its title, lede, introduction, sections, anchors and
    figures. What is wrong with it is added to `problems`."""
    env = {"page": page, "book": book, "problems": problems, "figures": [], "tables": 0, "fragments": [], "line": page.line + 1,
           "gates": getattr(book, "gates", None)}
    tokens = MD.parse(page.body, env)

    def at(token: Token) -> str:
        return f"{page.where}:{page.line + (token.map[0] if token.map else 0) + 1}"

    anchors: set[str] = set()
    for i, token in enumerate(tokens):
        for one in [token] + (token.children or []):
            if one.type in ("html_block", "html_inline"):
                problems.append(f"{at(token)}: raw HTML, a comment included, is not written in a page")
            elif one.type == "image":
                problems.append(f"{at(token)}: an image: a figure is a fenced block with `figure=name`, drawn as SVG")
        if is_figure(token) and token.level:
            problems.append(f"{at(token)}: a figure stands by itself in its section, not inside a list or a quotation")
        if token.type == "heading_open":
            if token.markup[:1] != "#":
                problems.append(f"{at(token)}: a heading is written with #, not by underlining")
            if token.tag in ("h4", "h5", "h6"):
                problems.append(f"{at(token)}: a page has a title, sections and subsections: nothing below ###")
            if token.tag in ("h2", "h3"):
                anchor = slugify(plain(tokens[i + 1]))
                if not anchor:
                    problems.append(f"{at(token)}: a heading with no words in it has no anchor")
                elif anchor in anchors:
                    problems.append(f"{at(token)}: two headings on this page come to the anchor `{anchor}`")
                elif anchor.startswith("figure-"):
                    problems.append(f"{at(token)}: a heading whose address begins `figure-`: that is a figure's address")
                anchors.add(anchor)
                token.meta["id"] = anchor

    spans = blocks(tokens)
    kinds = [(tokens[a].type, tokens[a].tag) for a, _ in spans]
    page.title_html = page.title_html_unlinked = page.title_text = page.title_md = page.brief_html = ""
    page.lede_html = page.lede_text = page.lede_md = ""
    page.sections, page.anchors, page.figures, page.fragments, page.tables = [], anchors, env["figures"], env["fragments"], 0
    if not kinds or kinds[0] != ("heading_open", "h1"):
        problems.append(f"{page.where}:{page.line + 1}: a page opens with its title, the one # heading")
        return
    title = tokens[spans[0][0] + 1]
    page.title_html, page.title_text, page.title_md = inline(title, env), plain(title), " ".join(title.content.split())
    page.title_html_unlinked = unlinked(page.title_html)
    for kind, (a, _) in zip(kinds[1:], spans[1:]):
        if kind == ("heading_open", "h1"):
            problems.append(f"{at(tokens[a])}: a second # heading: a page has one title")
    if len(kinds) < 2 or kinds[1][0] != "paragraph_open":
        problems.append(f"{at(tokens[spans[0][0]])}: under its title a page has its lede, one paragraph")
        return
    lede = tokens[spans[1][0] + 1]
    env["line"] = page.line + lede.map[0] + 1
    page.lede_html, page.lede_text, page.lede_md = inline(lede, env), plain(lede), " ".join(lede.content.split())

    starts = [i for i, kind in enumerate(kinds) if kind == ("heading_open", "h2")]
    page.brief_html = body(page, tokens, spans[2:starts[0] if starts else len(spans)], env)
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(spans)
        heading, words = tokens[spans[start][0]], tokens[spans[start][0] + 1]
        env["line"] = page.line + heading.map[0] + 1
        title_html = inline(words, env)
        html = body(page, tokens, spans[start + 1:end], env)
        if not html.strip():
            problems.append(f"{at(heading)}: a section with nothing under it")
        # `line` is the heading's line in the file, which is how a code span is placed in its section (doors.py)
        page.sections.append({"id": heading.meta.get("id", ""), "title_html": title_html, "title_html_unlinked": unlinked(title_html),
                              "title_text": plain(words), "html": html, "line": page.line + heading.map[0] + 1})
    page.tables = env["tables"]
