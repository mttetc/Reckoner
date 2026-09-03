"""Official Path of Exile forum → PoB codes.

Authors publish their builds as links to pobb.in (documented public raw endpoint) — in a sample
of 24 recent threads, none embedded the code inline. So: list a class sub-forum (allowed by
robots.txt), open each thread's first post, follow pobb.in links only, and keep the thread URL
and title as attribution. Pastebin / poe.ninja links are recorded as skipped, never fetched.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from lxml import html

from app.corpus.pipeline import FetchedCode
from app.corpus.policy import PoliteClient, SourceNotPermitted
from app.db.repository import SourceRef
from app.games.poe.pob import codec

FORUM_BASE = "https://www.pathofexile.com/forum"
CLASS_FORUMS: dict[str, int] = {
    "duelist": 40,
    "marauder": 23,
    "ranger": 24,
    "shadow": 303,
    "templar": 41,
    "witch": 22,
    "scion": 436,
}
PINNED_THREADS = {"1457463"}  # code of conduct
_LINK_RE = re.compile(r"https?://pobb\.in/(?:u/[A-Za-z0-9_-]+/)?[A-Za-z0-9_-]+")
_OTHER_PASTE_RE = re.compile(r"https?://(?:pastebin\.com|poe\.ninja/pob)/\S+")


@dataclass
class ForumFetcher:
    forums: dict[str, int] = field(default_factory=lambda: dict(CLASS_FORUMS))
    threads_per_forum: int = 10
    links_per_thread: int = 2
    client: PoliteClient | None = None
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (url, reason)

    def __iter__(self) -> Iterator[FetchedCode]:
        client = self.client or PoliteClient()
        try:
            for _forum, fid in self.forums.items():
                for tid, title in self.list_threads(client, fid)[: self.threads_per_forum]:
                    thread_url = f"{FORUM_BASE}/view-thread/{tid}"
                    links, others = self.first_post_links(client, thread_url)
                    for other in others:
                        self.skipped.append((other, "paste service not permitted (policy)"))
                    for link in links[: self.links_per_thread]:
                        raw_url = link.rstrip("/") + "/raw"
                        try:
                            r = client.get(raw_url)
                        except SourceNotPermitted as exc:
                            self.skipped.append((raw_url, str(exc)))
                            continue
                        body = r.text.strip()
                        if r.status_code != 200 or not codec.looks_like_code(body):
                            self.skipped.append((raw_url, f"HTTP {r.status_code} / not a code"))
                            continue
                        yield FetchedCode(
                            code=body,
                            source=SourceRef(
                                kind="paste",
                                url=link,
                                game="poe",
                                title=title,
                                parent_url=thread_url,
                                terms=client.check(raw_url).terms,
                            ),
                        )
        finally:
            if self.client is None:
                client.close()

    @staticmethod
    def list_threads(client: PoliteClient, forum_id: int) -> list[tuple[str, str]]:
        doc = html.fromstring(client.get(f"{FORUM_BASE}/view-forum/{forum_id}").text)
        out: list[tuple[str, str]] = []
        for a in doc.xpath('//div[@class="thread_title"]//a[@href]'):
            m = re.search(r"view-thread/(\d+)", a.get("href", ""))
            if m and m.group(1) not in PINNED_THREADS:
                out.append((m.group(1), a.text_content().strip()))
        return out

    @staticmethod
    def first_post_links(client: PoliteClient, thread_url: str) -> tuple[list[str], list[str]]:
        doc = html.fromstring(client.get(thread_url).text)
        posts = doc.xpath('//div[@class="content"]')
        if not posts:
            return [], []
        text = posts[0].text_content()
        hrefs = [a.get("href", "") for a in posts[0].xpath(".//a[@href]")]
        pobb = sorted(set(_LINK_RE.findall(text)) | {h for h in hrefs if _LINK_RE.match(h)})
        others = sorted(
            set(_OTHER_PASTE_RE.findall(text)) | {h for h in hrefs if _OTHER_PASTE_RE.match(h)}
        )
        return pobb, others
