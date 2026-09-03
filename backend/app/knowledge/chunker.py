"""Forum post HTML → heading-aware chunks. Generic over GGG's PoE and PoE2 patch-note layouts.

PoE 1 posts: <h3>title</h3> then <strong>Section</strong> labels and <ul><li> bullets.
PoE 2 posts: <h2>title</h2>, <h3>Section</h3> boxes, <ul><li> bullets. Both handled the same way:
headings open a section, block elements contribute lines, sections are packed into chunks of at
most ``max_chars`` so a chunk never straddles two sections.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import html

_HEADING_TAGS = {"h1", "h2", "h3", "h4"}
_SKIP = {"script", "style", "form", "select", "textarea", "button", "input", "img"}


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    heading: str | None
    text: str


def _clean(s: str) -> str:
    return re.sub(r"[ \t\xa0]+", " ", re.sub(r"\s*\n\s*", "\n", s)).strip()


def first_post(doc: html.HtmlElement) -> html.HtmlElement | None:
    """The first post's body in a GGG forum thread page (news or staff post)."""
    for tr in doc.xpath('//table[contains(@class,"forumPostListTable")]//tr[td]'):
        content = tr.xpath('.//div[@class="content"]')
        if content:
            return content[0]
    return None


def _is_section_label(el: html.HtmlElement) -> bool:
    if el.tag in _HEADING_TAGS:
        return True
    if el.tag == "strong":
        parent = el.getparent()
        return parent is not None and parent.tag not in {"li", "p", "a"}
    return False


def sections(post: html.HtmlElement) -> list[tuple[str | None, list[str]]]:
    """Walk the post in document order: (heading, lines) per section."""
    out: list[tuple[str | None, list[str]]] = [(None, [])]
    for el in post.iter():
        if not isinstance(el.tag, str) or el.tag in _SKIP:
            continue
        if _is_section_label(el):
            title = _clean(el.text_content())
            if title and title.lower() != "table of contents":
                out.append((title, []))
            continue
        if el.tag == "li":
            if len(el) == 1 and el[0].tag == "a" and (el[0].get("href") or "").startswith("#"):
                continue  # table-of-contents entry
            line = _clean(el.text_content())
            if line:
                out[-1][1].append("• " + line)
        elif el.tag == "p" and not el.xpath(".//li"):
            line = _clean(el.text_content())
            if line:
                out[-1][1].append(line)
    return [(h, lines) for h, lines in out if lines]


def chunk_post(
    post: html.HtmlElement, max_chars: int = 1200, title: str | None = None
) -> list[Chunk]:
    """``title``: the thread title; a leading heading equal to it is not a section."""
    chunks: list[Chunk] = []
    for heading, lines in sections(post):
        if heading and title and heading.strip().lower() == title.strip().lower():
            heading = None
        buf: list[str] = []
        size = 0
        for line in lines:
            if buf and size + len(line) > max_chars:
                chunks.append(Chunk(len(chunks), heading, "\n".join(buf)))
                buf, size = [], 0
            buf.append(line)
            size += len(line) + 1
        if buf:
            chunks.append(Chunk(len(chunks), heading, "\n".join(buf)))
    seen: set[str] = set()
    unique: list[Chunk] = []
    for c in chunks:
        key = (c.heading or "") + "\x00" + c.text
        if key not in seen:
            seen.add(key)
            unique.append(Chunk(len(unique), c.heading, c.text))
    return unique
