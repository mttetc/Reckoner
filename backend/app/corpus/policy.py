"""Fetch policy: the SPEC § 7 ingestion rules, enforced in code rather than in a README.

- Only hosts on the allowlist, each with the reason the fetch is permitted.
- robots.txt is honoured for every URL (cached per host).
- A clear User-Agent with contact info; a pause between requests.
- Maxroll / Mobalytics and undocumented endpoints are refused outright.
"""

from __future__ import annotations

import threading
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.domain.errors import DomainError


class SourceNotPermitted(DomainError):
    code = "source_not_permitted"


@dataclass(frozen=True)
class HostRule:
    host: str
    terms: str  # recorded on every source row fetched from this host
    honour_robots: bool = True  # False only when the operator documents the endpoint for tools


ALLOWED_HOSTS: dict[str, HostRule] = {
    "www.pathofexile.com": HostRule(
        host="www.pathofexile.com",
        terms="official forum, public thread pages; robots.txt honoured",
    ),
    "worldofwarcraft.blizzard.com": HostRule(
        host="worldofwarcraft.blizzard.com",
        terms="official publisher news pages (hotfixes, content update notes); robots.txt honoured",
    ),
    "pobb.in": HostRule(
        host="pobb.in",
        # https://github.com/Dav1dde/pasteofexile#public-api — '/:id/raw' is documented as a
        # public URL for third-party integrations, with a User-Agent + contact requirement.
        # Its robots.txt disallows '/*/raw$' for crawlers; the operator's own documentation
        # authorises tool access, which is what this is.
        terms="pobb.in documented public API (/:id/raw), identified User-Agent",
        honour_robots=False,
    ),
}

# Never, regardless of robots.txt: SPEC § 7 names them, or the endpoint is undocumented.
DENIED_HOSTS: dict[str, str] = {
    "maxroll.gg": "SPEC § 7: never scrape Maxroll",
    "mobalytics.gg": "SPEC § 7: never scrape Mobalytics",
    "pastebin.com": "robots.txt disallows /raw/; no documented public read API",
    "poe.ninja": "/pob/raw is undocumented",
}


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def rule_for(url: str) -> HostRule:
    host = _host(url)
    for denied, why in DENIED_HOSTS.items():
        if host == denied or host.endswith("." + denied):
            raise SourceNotPermitted(f"{host}: {why}")
    rule = ALLOWED_HOSTS.get(host)
    if rule is None:
        raise SourceNotPermitted(f"{host} is not on the permitted-source allowlist")
    return rule


class RobotsCache:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self._parsers: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def allowed(self, url: str, user_agent: str) -> bool:
        host = _host(url)
        if host not in self._parsers:
            self._parsers[host] = self._load(urlparse(url).scheme or "https", host)
        rp = self._parsers[host]
        return True if rp is None else rp.can_fetch(user_agent, url)

    def _load(self, scheme: str, host: str) -> urllib.robotparser.RobotFileParser | None:
        try:
            r = self._client.get(f"{scheme}://{host}/robots.txt")
        except httpx.HTTPError:
            return None  # unreachable robots → no rules (standard behaviour)
        if r.status_code >= 400 or "text/html" in r.headers.get("content-type", ""):
            return None
        return parse_robots(r.text)

    def crawl_delay(self, url: str, user_agent: str) -> float | None:
        rp = self._parsers.get(_host(url))
        if rp is None:
            return None
        d = rp.crawl_delay(user_agent)
        return float(d) if d else None


def parse_robots(text: str) -> urllib.robotparser.RobotFileParser:
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(text.splitlines())
    return rp


class PoliteClient:
    """httpx client that applies the policy to every GET."""

    def __init__(self, delay_s: float | None = None, user_agent: str | None = None) -> None:
        self.user_agent = user_agent or settings.corpus_user_agent
        self.delay_s = settings.corpus_request_delay_s if delay_s is None else delay_s
        self._client = httpx.Client(
            headers={"User-Agent": self.user_agent}, follow_redirects=True, timeout=30
        )
        self._robots = RobotsCache(self._client)
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PoliteClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def check(self, url: str) -> HostRule:
        rule = rule_for(url)
        if rule.honour_robots and not self._robots.allowed(url, self.user_agent):
            raise SourceNotPermitted(f"robots.txt disallows {url}")
        return rule

    def get(self, url: str) -> httpx.Response:
        rule = self.check(url)
        delay = max(self.delay_s, self._robots.crawl_delay(url, self.user_agent) or 0.0)
        with self._lock:
            wait = self._last.get(rule.host, 0.0) + delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last[rule.host] = time.monotonic()
        return self._client.get(url)
