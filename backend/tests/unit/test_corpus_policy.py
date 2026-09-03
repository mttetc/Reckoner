"""SPEC § 7 ingestion rules, enforced in code (no network)."""

import pytest

from app.corpus.policy import ALLOWED_HOSTS, SourceNotPermitted, parse_robots, rule_for


@pytest.mark.parametrize(
    "url",
    [
        "https://maxroll.gg/poe/build-guides/x",
        "https://mobalytics.gg/poe/builds/y",
        "https://pastebin.com/raw/abc123",
        "https://poe.ninja/pob/raw/abc",
        "https://www.poe.ninja/pob/abc",
        "https://example.com/anything",
        "https://www.pathofexile.com.evil.example/forum/view-thread/1",
    ],
)
def test_denied_or_unlisted_hosts_are_refused(url):
    with pytest.raises(SourceNotPermitted):
        rule_for(url)


def test_allowlisted_hosts_carry_the_reason():
    assert "robots.txt" in rule_for("https://www.pathofexile.com/forum/view-forum/40").terms
    pobb = rule_for("https://pobb.in/abc123/raw")
    assert "documented public API" in pobb.terms
    assert pobb.honour_robots is False


def test_robots_parsing_matches_real_forum_rules():
    rp = parse_robots(
        "user-agent: *\ndisallow: /search/\ndisallow: /api/\ndisallow: /forum/view-post/\n"
    )
    ua = "Reckoner/0.1"
    assert rp.can_fetch(ua, "https://www.pathofexile.com/forum/view-thread/123")
    assert rp.can_fetch(ua, "https://www.pathofexile.com/forum/view-forum/40")
    assert not rp.can_fetch(ua, "https://www.pathofexile.com/api/whatever")
    assert not rp.can_fetch(ua, "https://www.pathofexile.com/forum/view-post/9")


def test_every_allowlisted_host_states_its_terms():
    for rule in ALLOWED_HOSTS.values():
        assert rule.terms and len(rule.terms) > 10
