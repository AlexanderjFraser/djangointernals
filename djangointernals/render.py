"""One page's markdown as HTML, and everything SPEC.md asks of a page's body, enforced.

A page's body is read as CommonMark with tables. What comes out is the
page in the parts the templates lay out: the title (the one H1), the lede
(the first paragraph), what the page asserts in brief (whatever else stands
above the first H2), and the sections (each H2 and what is under it).

What is refused here, each with its file and line: a page that does not
open with its H1 and a lede; a second H1; a heading below H3, or one
written by underlining; two headings on a page that come to the same
anchor; raw HTML, a comment included; an image; a link to another page that
is not the relative path of its `.md` file, or that names no page of the
book; a figure with no SVG beside it or no caption under it; an empty
section on a page that says it is written.

What is changed on the way to HTML and nowhere else: straight quotes in
prose become curly; a long name or pointer in a code span may break after a
slash or a colon and before a dot; a link to `other.md` becomes that page's
URL, and a link to a page still in outline becomes plain text marked as
unwritten; a figure's fenced source becomes the SVG drawn from it, with the
source folded away under it.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html import escape
from pathlib import PurePosixPath

from django.conf import settings
from django.utils.text import slugify
from markdown_it import MarkdownIt
from markdown_it.token import Token

FIGURE = re.compile(r"\bfigure=(\S+)")
FIGURE_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
UNDRAWN = {"script", "style", "foreignObject", "image", "iframe"}
PAINTED = {"style", "fill", "stroke", "color", "font", "font-family", "font-size", "font-weight"}
PROLOG = re.compile(r"\A\s*(?:(?:<\?xml.*?\?>|<!DOCTYPE.*?>|<!--.*?-->)\s*)*", re.S)
COLUMN = 646  # the text column in CSS pixels at the size the stylesheet sets: a wider figure uses the margins


def breakable(code: str) -> str:
    """A code span's text, escaped, with the places a long name or pointer may break."""
    text = escape(code, quote=False)
    text = re.sub(r"([/:])(?=[^\s/:])", r"\1<wbr>", text)
    return re.sub(r"(?<=\w)\.(?=\w)", "<wbr>.", text)


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


class Rules:
    """The render rules that differ from CommonMark's defaults. `env` carries the page being
    rendered, the book it is in, the line of the block being rendered, and the problems so far."""

    def code_inline(self, tokens, idx, options, env):
        return f"<code>{breakable(tokens[idx].content)}</code>"

    def fence(self, tokens, idx, options, env):
        token = tokens[idx]
        words = token.info.split()
        kind = f' data-kind="{escape(words[0])}"' if words else ""
        return f"<pre{kind}><code>{escape(token.content, quote=False)}</code></pre>\n"

    def table_open(self, tokens, idx, options, env):
        return '<div class="table"><table>\n'

    def table_close(self, tokens, idx, options, env):
        return "</table></div>\n"

    def heading_open(self, tokens, idx, options, env):
        token = tokens[idx]
        anchor = token.meta.get("id")
        return f'<{token.tag} id="{anchor}">' if anchor else f"<{token.tag}>"

    def link_open(self, tokens, idx, options, env):
        """A link to another page is written to its .md file, as it works on disk and on
        GitHub; here it becomes the page's URL, or plain text if the page is not written."""
        href = tokens[idx].attrGet("href") or ""
        opened = env.setdefault("links", [])
        page, book = env["page"], env["book"]
        where = f"{page.where}:{env['line']}"
        if SCHEME.match(href) or href.startswith("#"):
            if href.startswith("#"):
                env["fragments"].append((where, href, page, href[1:]))
            elif href.startswith(settings.SITE_URL):
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
            title = ' title="This page is outlined and not yet written."' if target is not None else ""
            return f'<span class="unwritten"{title}>'
        opened.append("a")
        return f'<a href="{escape(target.url + ("#" + fragment if fragment else ""))}">'

    def link_close(self, tokens, idx, options, env):
        return f"</{env['links'].pop()}>"


def markdown() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True, "typographer": True}).enable(["table", "smartquotes"])
    for name in ("code_inline", "fence", "table_open", "table_close", "heading_open", "link_open", "link_close"):
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


def inline(token: Token, env) -> str:
    return MD.renderer.renderInline(token.children or [], MD.options, env)


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
            return f"a figure carries no script and loads nothing: <{tag}>", None
        for attribute in element.attrib:
            attribute = attribute.rsplit("}", 1)[-1]
            if attribute.startswith("on"):
                return f"a figure carries no script and loads nothing: `{attribute}` on <{tag}>", None
            if attribute in PAINTED:
                return f"a figure carries classes and no colour or font of its own: `{attribute}` on <{tag}>", None
    try:
        return None, float(box[2])
    except ValueError:
        return "a figure is one <svg> element with a viewBox", None


def figure(page, fence: Token, under: Token | None, env) -> str:
    """A figure: the fenced block that holds its source, the SVG drawn from that source, and
    the italic paragraph under the block, which is its caption."""
    where = f"{page.where}:{env['line']}"
    name = FIGURE.search(fence.info).group(1)
    problems = env["problems"]
    if not FIGURE_NAME.fullmatch(name):
        problems.append(f"{where}: the figure `{name}`: a figure's name is lower-case words joined by hyphens")
        return ""
    file = page.source.parent / "figures" / f"{name}.svg"
    shown = f"{page.where.rsplit('/', 1)[0]}/figures/{name}.svg"
    svg, width = "", None
    if not file.is_file():
        problems.append(f"{where}: the figure `{name}`: there is no {shown}")
    else:
        svg = PROLOG.sub("", file.read_text(encoding="utf-8")).strip()
        wrong, width = drawn(svg)
        if wrong:
            problems.append(f"{shown}: {wrong}")
    children = (under.children or []) if under is not None else []
    whole = (len(children) >= 3 and children[0].type == "em_open" and children[-1].type == "em_close"
             and not any(c.type == "em_close" and c.level == children[0].level for c in children[1:-1]))
    if not whole:
        problems.append(f"{where}: the figure `{name}`: its caption is the paragraph under it, one italic run from end to end")
    caption = MD.renderer.renderInline(children[1:-1], MD.options, env) if whole else ""
    if name in env["figures"]:
        problems.append(f"{where}: the figure `{name}`: this page has another of that name")
    env["figures"].append(name)
    kind = fence.info.split()[0]
    wide = " wide" if width and width > COLUMN else ""
    size = f' style="--natural: {width:g}px"' if width else ""
    return (f'<figure class="figure{wide}" id="figure-{name}"{size}>\n<div class="art">{svg}</div>\n'
            f"<figcaption>{caption}</figcaption>\n"
            f'<details class="source"><summary>What this figure is drawn from</summary>'
            f'<pre data-kind="{escape(kind)}"><code>{escape(fence.content, quote=False)}</code></pre></details>\n'
            f"</figure>\n")


def body(page, tokens: list[Token], spans: list[tuple[int, int]], env) -> str:
    """Some of a page's top-level blocks as HTML, each figure put together from its two blocks."""
    out, i = [], 0
    while i < len(spans):
        first, last = spans[i]
        token = tokens[first]
        env["line"] = page.line + (token.map[0] if token.map else 0) + 1
        if is_figure(token):
            under = None
            if i + 1 < len(spans) and tokens[spans[i + 1][0]].type == "paragraph_open":
                under = tokens[spans[i + 1][0] + 1]
                i += 1
            out.append(figure(page, token, under, env))
        else:
            out.append(MD.renderer.render(tokens[first:last + 1], MD.options, env))
        i += 1
    return "".join(out)


def render(page, book, problems: list[str]) -> None:
    """Fill in `page` from its markdown: its title, lede, brief, sections, anchors and
    figures. What is wrong with it is added to `problems`."""
    env = {"page": page, "book": book, "problems": problems, "figures": [], "fragments": [], "line": page.line + 1}
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
                anchors.add(anchor)
                token.meta["id"] = anchor

    spans = blocks(tokens)
    kinds = [(tokens[a].type, tokens[a].tag) for a, _ in spans]
    page.title_html = page.title_text = page.lede_html = page.lede_text = page.brief_html = ""
    page.sections, page.anchors, page.figures, page.fragments = [], anchors, env["figures"], env["fragments"]
    if not kinds or kinds[0] != ("heading_open", "h1"):
        problems.append(f"{page.where}:{page.line + 1}: a page opens with its title, the one # heading")
        return
    title = tokens[spans[0][0] + 1]
    page.title_html, page.title_text = inline(title, env), plain(title)
    for kind, (a, _) in zip(kinds[1:], spans[1:]):
        if kind == ("heading_open", "h1"):
            problems.append(f"{at(tokens[a])}: a second # heading: a page has one title")
    if len(kinds) < 2 or kinds[1][0] != "paragraph_open":
        problems.append(f"{at(tokens[spans[0][0]])}: under its title a page has its lede, one paragraph")
        return
    lede = tokens[spans[1][0] + 1]
    env["line"] = page.line + lede.map[0] + 1
    page.lede_html, page.lede_text = inline(lede, env), plain(lede)

    starts = [i for i, kind in enumerate(kinds) if kind == ("heading_open", "h2")]
    page.brief_html = body(page, tokens, spans[2:starts[0] if starts else len(spans)], env)
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(spans)
        heading, words = tokens[spans[start][0]], tokens[spans[start][0] + 1]
        env["line"] = page.line + heading.map[0] + 1
        title_html = inline(words, env)
        html = body(page, tokens, spans[start + 1:end], env)
        if not html.strip() and page.published:
            problems.append(f"{at(heading)}: a section with nothing under it, on a page whose status is `{page.status}`")
        page.sections.append({"id": heading.meta.get("id", ""), "title_html": title_html, "title_text": plain(words), "html": html})
