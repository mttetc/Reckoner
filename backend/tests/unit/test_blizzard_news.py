"""Blizzard's official notes: read as sections, split by game, never mixed."""

from pathlib import Path

from app.corpus.policy import SourceNotPermitted, rule_for
from app.knowledge.sources.blizzard_news import parse_article, parse_listing

FIX = Path(__file__).parents[1] / "fixtures" / "wow"
URL = "https://worldofwarcraft.blizzard.com/en-us/news/24296142/hotfixes-september-3-2026"


def test_listing_keeps_only_patch_note_articles():
    found = parse_listing((FIX / "blizzard_news_listing.html").read_text())
    slugs = [slug for _, slug, _ in found]
    assert slugs == [
        "hotfixes-july-28-2026",
        "curse-of-ulatek-content-update-notes",
        "hotfixes-september-3-2026",
    ]
    assert found[0][2].startswith("https://worldofwarcraft.blizzard.com/en-us/news/24287397/")


def test_retail_hotfixes_become_dated_sections_with_nested_paths():
    doc = parse_article((FIX / "blizzard_hotfixes_2026-09-03.html").read_text(), URL, "wow")
    assert doc is not None and doc.game == "wow" and doc.source == "blizzard:news"
    assert doc.title == "Hotfixes: September 3, 2026"
    assert doc.published_at is not None and doc.published_at.date().isoformat() == "2026-09-03"
    headings = [c.heading for c in doc.chunks]
    assert "September 3, 2026 · Classes" in headings
    classes = next(c for c in doc.chunks if c.heading == "September 3, 2026 · Classes")
    assert "• Priest › Holy › Fixed an issue" in classes.text
    assert all(len(c.text) <= 1400 for c in doc.chunks)


def test_the_same_article_yields_classic_sections_only_to_classic():
    page = (FIX / "blizzard_hotfixes_2026-07-28.html").read_text()
    retail = parse_article(page, URL, "wow")
    classic = parse_article(page, URL, "wow_classic")
    assert retail is not None and classic is not None
    assert all("Classic" in c.heading or "Discovery" in c.heading for c in classic.chunks)
    assert not any(
        "Classic" in (c.heading or "") or "Discovery" in (c.heading or "") for c in retail.chunks
    )
    assert "Mists of Pandaria Classic" in " ".join(c.heading for c in classic.chunks)


def test_an_article_with_nothing_for_classic_yields_no_classic_document():
    page = (FIX / "blizzard_hotfixes_2026-09-03.html").read_text()
    assert parse_article(page, URL, "wow_classic") is None


def test_content_update_notes_take_their_version_from_the_text():
    page = (FIX / "blizzard_content_update_notes_ulatek.html").read_text()
    doc = parse_article(page, URL, "wow")
    assert doc is not None and doc.title == "Curse of Ula'tek Content Update Notes"
    assert any(c.heading for c in doc.chunks)  # headings come from the article's own h2s


def test_blizzard_news_is_a_permitted_source_and_fan_sites_are_not():
    assert rule_for("https://worldofwarcraft.blizzard.com/en-us/news").honour_robots
    try:
        rule_for("https://www.wowhead.com/news")
    except SourceNotPermitted:
        return
    raise AssertionError("wowhead is not on the allowlist and must be refused")
