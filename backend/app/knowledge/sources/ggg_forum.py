"""Official GGG forum → patch-note documents. Shared by PoE (forum 'patch-notes') and PoE2 (2212):
same site, same markup family, different game tag. Politeness and permissions come from
``app.corpus.policy`` (allowlist, robots.txt, identified UA, delay).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from lxml import html

from app.corpus.policy import PoliteClient
from app.knowledge.chunker import Chunk, chunk_post, first_post

FORUM_BASE = "https://www.pathofexile.com/forum"
_VERSION = re.compile(r"\b(\d+\.\d+(?:\.\d+)?[a-z]?)\b")
_DATE_FORMATS = ("%b %d, %Y, %I:%M:%S %p", "%b %d, %Y %I:%M:%S %p")


@dataclass(frozen=True)
class PatchNoteDocument:
    game: str
    source: str
    source_url: str
    title: str
    version: str  # as printed, e.g. "3.29.0b"
    patch: str  # major.minor, aligned with tree versions on snapshots, e.g. "3.29"
    published_at: datetime | None
    chunks: list[Chunk]


def parse_version(title: str) -> tuple[str, str] | None:
    """'3.29.0b Patch Notes' → ('3.29.0b', '3.29'); '0.5.4f Hotfix' → ('0.5.4f', '0.5').
    None when the title carries no version (server maintenance, announcements)."""
    m = _VERSION.search(title)
    if not m:
        return None
    version = m.group(1)
    parts = version.split(".")
    return version, ".".join(parts[:2])


def parse_post_date(text: str) -> datetime | None:
    text = text.strip().lstrip(",").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


@dataclass
class GggPatchNotesFetcher:
    game: str
    forum: str  # slug or numeric id, e.g. "patch-notes" or "2212"
    source: str = "ggg:patch-notes"
    limit: int = 10
    client: PoliteClient | None = None

    def list_threads(self, client: PoliteClient) -> list[tuple[str, str]]:
        doc = html.fromstring(client.get(f"{FORUM_BASE}/view-forum/{self.forum}").text)
        out: list[tuple[str, str]] = []
        for a in doc.xpath('//div[@class="thread_title"]//a[@href]'):
            m = re.search(r"view-thread/(\d+)", a.get("href", ""))
            title = a.text_content().strip()
            if m and parse_version(title):
                out.append((m.group(1), title))
        return out

    def fetch_thread(
        self, client: PoliteClient, thread_id: str, title: str
    ) -> PatchNoteDocument | None:
        url = f"{FORUM_BASE}/view-thread/{thread_id}"
        doc = html.fromstring(client.get(url).text)
        post = first_post(doc)
        parsed = parse_version(title)
        if post is None or parsed is None:
            return None
        dates = doc.xpath('//*[contains(@class,"post_date")]')
        published = parse_post_date(dates[0].text_content()) if dates else None
        version, patch = parsed
        return PatchNoteDocument(
            game=self.game,
            source=self.source,
            source_url=url,
            title=title,
            version=version,
            patch=patch,
            published_at=published,
            chunks=chunk_post(post, title=title),
        )

    def __iter__(self) -> Iterator[PatchNoteDocument]:
        client = self.client or PoliteClient()
        try:
            for tid, title in self.list_threads(client)[: self.limit]:
                doc = self.fetch_thread(client, tid, title)
                if doc is not None:
                    yield doc
        finally:
            if self.client is None:
                client.close()
