"""Official Blizzard World of Warcraft news → patch-note documents (hotfixes, content update notes).

One site serves Retail and Classic: hotfix posts carry sections headed "Mists of Pandaria Classic",
"Season of Discovery", … next to Retail ones. Each fetcher yields only its game's sections, so the
knowledge base stays game-aware (SPEC § 6) without the model ever deciding what belongs where.
Politeness and permissions: ``app.corpus.policy`` (allowlist, robots.txt, identified UA, delay).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime

from lxml import html

from app.corpus.policy import PoliteClient
from app.knowledge.chunker import Chunk
from app.knowledge.sources.ggg_forum import PatchNoteDocument

NEWS_BASE = "https://worldofwarcraft.blizzard.com/en-us/news"
SOURCE = "blizzard:news"
_NOTE_SLUGS = ("hotfixes", "content-update-notes", "patch-notes")
_LINK_RE = re.compile(
    r'href="(?:https?://worldofwarcraft\.blizzard\.com/en-us)?(/news/(\d+)/([^"]+))"'
)
_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r" (\d{1,2}), (\d{4})\b"
)
_VERSION_RE = re.compile(r"\b(\d{1,2}\.\d\.\d)\b")
# Section headings that belong to the Classic games; everything else is Retail.
_CLASSIC_RE = re.compile(
    r"classic|season of discovery|hardcore|\bera\b|burning crusade|pandaria|cataclysm|wrath of",
    re.I,
)


def _clean(s: str) -> str:
    return re.sub(r"[ \t\xa0]+", " ", s).strip()


def parse_listing(page_html: str) -> list[tuple[str, str, str]]:
    """(article id, slug, absolute url) for every patch-note-like article on a listing page."""
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for path, article_id, slug in _LINK_RE.findall(page_html):
        if article_id in seen or not any(k in slug for k in _NOTE_SLUGS):
            continue
        seen.add(article_id)
        out.append((article_id, slug, f"https://worldofwarcraft.blizzard.com/en-us{path}"))
    return out


def parse_date(text: str) -> datetime | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    try:
        return datetime.strptime(" ".join(m.groups()), "%B %d %Y").replace(tzinfo=UTC)
    except ValueError:
        return None


def _li_lines(li: html.HtmlElement, prefix: str) -> list[str]:
    """Hotfix bullets nest class › spec › change; leaves keep their path as a prefix."""
    own = _clean(" ".join(t for t in li.xpath("text()|*[not(self::ul)]//text()")))
    nested = li.xpath("./ul/li")
    if not nested:
        return [f"{prefix}{own}"] if own else []
    head = f"{prefix}{own} › " if own else prefix
    lines: list[str] = []
    for child in nested:
        lines.extend(_li_lines(child, head))
    return lines


def sections(detail: html.HtmlElement) -> list[tuple[str, list[str]]]:
    """Walk the article body: a lone bold paragraph or a heading opens a section; bullets and
    paragraphs are lines. Hotfix posts are dated blocks — the date joins the heading."""
    out: list[tuple[str, list[str]]] = []
    date: str | None = None
    current = ""

    def open_section(title: str) -> None:
        nonlocal current
        current = f"{date} · {title}" if date and title != date else title
        out.append((current, []))

    for el in detail:
        if not isinstance(el.tag, str):
            continue
        text = _clean(" ".join(el.text_content().split()))
        if el.tag in ("h2", "h3", "h4"):
            if text:
                open_section(text)
        elif el.tag == "p":
            strong = el.xpath("./strong")
            if strong and _clean(" ".join(strong[0].text_content().split())) == text and text:
                if _DATE_RE.fullmatch(text):
                    date = text
                    continue
                open_section(text)
            elif text:
                if not out:
                    out.append(("", []))
                out[-1][1].append(text)
        elif el.tag == "ul":
            if not out:
                out.append(("", []))
            for li in el.xpath("./li"):
                out[-1][1].extend("• " + line for line in _li_lines(li, ""))
    return [(h, lines) for h, lines in out if lines]


def pack(secs: list[tuple[str, list[str]]], max_chars: int = 1200) -> list[Chunk]:
    chunks: list[Chunk] = []
    for heading, lines in secs:
        buf: list[str] = []
        size = 0
        for line in lines:
            if buf and size + len(line) > max_chars:
                chunks.append(Chunk(len(chunks), heading or None, "\n".join(buf)))
                buf, size = [], 0
            buf.append(line)
            size += len(line) + 1
        if buf:
            chunks.append(Chunk(len(chunks), heading or None, "\n".join(buf)))
    return chunks


def is_classic_heading(heading: str) -> bool:
    return bool(_CLASSIC_RE.search(heading))


def parse_article(page_html: str, url: str, game: str) -> PatchNoteDocument | None:
    """The document for one game, or None when the article has nothing for it."""
    doc = html.fromstring(page_html)
    details = doc.xpath('//div[contains(concat(" ", normalize-space(@class), " "), " detail ")]')
    titles = doc.xpath("//h1/text()") or doc.xpath("//title/text()")
    if not details or not titles:
        return None
    title = _clean(titles[0]).removesuffix(" - WoW")
    secs = sections(details[0])
    mine = [(h, lines) for h, lines in secs if is_classic_heading(h) == (game == "wow_classic")]
    chunks = pack(mine)
    if not chunks:
        return None
    body = " ".join(line for _, lines in mine for line in lines)
    versions = _VERSION_RE.findall(body) or _VERSION_RE.findall(title)
    version = max(set(versions), key=versions.count) if versions else None
    kind = "hotfixes" if "hotfix" in title.lower() else "notes"
    return PatchNoteDocument(
        game=game,
        source=SOURCE,
        source_url=url,
        title=title,
        version=version or kind,
        patch=".".join(version.split(".")[:2]) if version else None,
        published_at=parse_date(title) or parse_date(body),
        chunks=chunks,
    )


class BlizzardNewsFetcher:
    """Iterable of PatchNoteDocument for one game (``wow`` or ``wow_classic``)."""

    def __init__(
        self, game: str, limit: int = 10, pages: int = 2, client: PoliteClient | None = None
    ):
        self.game = game
        self.limit = limit
        self.pages = pages
        self.client = client

    def list_articles(self, client: PoliteClient) -> list[tuple[str, str, str]]:
        found: list[tuple[str, str, str]] = []
        for page in range(1, self.pages + 1):
            url = NEWS_BASE if page == 1 else f"{NEWS_BASE}?page={page}"
            found.extend(a for a in parse_listing(client.get(url).text) if a not in found)
            if len(found) >= self.limit:
                break
        return found[: self.limit]

    def __iter__(self) -> Iterator[PatchNoteDocument]:
        client = self.client or PoliteClient()
        for _id, _slug, url in self.list_articles(client):
            doc = parse_article(client.get(url).text, url, self.game)
            if doc is not None:
                yield doc
