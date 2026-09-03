"""Collect PoB codes linked from the official Path of Exile class forums (dev tool).

Purpose: feed the parser with real, recent exports to find format cases the fixtures miss
(SPEC § 7 names the official forum as the legitimate build-code source). It reads public listing
and thread pages, follows the first PoB links of each thread to their *raw* endpoints
(pobb.in / pastebin / poe.ninja), and stores whatever decodes as a build code. No scraping of
third-party guide sites, no private APIs, a clear user agent, and a pause between requests.

    .venv/bin/python scripts/harvest_forum_codes.py OUT_DIR [--per-forum 8]

Then: ``.venv/bin/python scripts/first_light.py OUT_DIR/*.txt`` or your own loop.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx
from lxml import html

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.games.poe.pob import codec  # noqa: E402

FORUMS = {
    "duelist": 40,
    "marauder": 23,
    "ranger": 24,
    "shadow": 303,
    "templar": 41,
    "witch": 22,
    "scion": 436,
}
USER_AGENT = "Reckoner-dev/0.1 (+https://github.com/mttetc/Reckoner; parser robustness pass)"
LINK_RE = re.compile(
    r"https?://(?:pobb\.in/[A-Za-z0-9_-]+|pastebin\.com/(?:raw/)?[A-Za-z0-9]+"
    r"|poe\.ninja/pob/[A-Za-z0-9]+)"
)
PAUSE_S = 0.6


def _threads(client: httpx.Client, forum_id: int) -> list[tuple[str, str]]:
    doc = html.fromstring(
        client.get(f"https://www.pathofexile.com/forum/view-forum/{forum_id}").text
    )
    out: list[tuple[str, str]] = []
    for a in doc.xpath('//div[@class="thread_title"]//a[@href]'):
        m = re.search(r"view-thread/(\d+)", a.get("href", ""))
        if m and m.group(1) != "1457463":  # pinned code of conduct
            out.append((m.group(1), a.text_content().strip()))
    return out


def _first_post_links(client: httpx.Client, thread_id: str) -> list[str]:
    doc = html.fromstring(
        client.get(f"https://www.pathofexile.com/forum/view-thread/{thread_id}").text
    )
    posts = doc.xpath('//div[@class="content"]')
    if not posts:
        return []
    text = posts[0].text_content()
    hrefs = [a.get("href", "") for a in posts[0].xpath(".//a[@href]")]
    return sorted(set(LINK_RE.findall(text)) | {h for h in hrefs if LINK_RE.match(h)})


def _raw_url(link: str) -> str:
    if "pobb.in" in link:
        return link.rstrip("/") + "/raw"
    if "pastebin.com" in link and "/raw/" not in link:
        return link.replace("pastebin.com/", "pastebin.com/raw/")
    if "poe.ninja/pob/" in link:
        return link.replace("poe.ninja/pob/", "poe.ninja/pob/raw/")
    return link


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--per-forum", type=int, default=8)
    ap.add_argument("--links-per-thread", type=int, default=2)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    meta: list[dict[str, str]] = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30) as c:
        for forum, fid in FORUMS.items():
            for tid, title in _threads(c, fid)[: args.per_forum]:
                for i, link in enumerate(_first_post_links(c, tid)[: args.links_per_thread]):
                    time.sleep(PAUSE_S)
                    try:
                        body = c.get(_raw_url(link)).text.strip()
                    except httpx.HTTPError as exc:
                        print(f"ERR  {link}: {exc}")
                        continue
                    if not codec.looks_like_code(body):
                        print(f"skip {link} (not a build code)")
                        continue
                    slug = re.sub(r"[^a-z0-9]+", "_", title.lower())[:40].strip("_")
                    name = f"{forum}_{tid}_{i}_{slug}.txt"
                    (args.out_dir / name).write_text(body)
                    meta.append(
                        {"forum": forum, "thread": tid, "title": title, "link": link, "file": name}
                    )
                    print(f"ok   {name}  <- {link}")
                time.sleep(PAUSE_S)
    (args.out_dir / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(f"{len(meta)} codes written to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
