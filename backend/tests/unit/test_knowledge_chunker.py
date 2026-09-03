from pathlib import Path

from lxml import html

from app.knowledge.chunker import chunk_post, first_post
from app.knowledge.embedder import DIMS, HashEmbedder
from app.knowledge.sources.ggg_forum import parse_post_date, parse_version

FIX = Path(__file__).parents[1] / "fixtures" / "forum"


def _chunks(name):
    doc = html.fromstring((FIX / name).read_text())
    post = first_post(doc)
    assert post is not None
    return chunk_post(post)


def test_poe1_layout_sections_and_only_first_post():
    chunks = _chunks("poe1_patch_notes.html")
    headings = [c.heading for c in chunks]
    assert headings == ["League", "General Fixes"]
    assert "Lightning Strike projectiles" in chunks[0].text
    assert "Spectral Throw" in chunks[1].text
    assert all("must not be ingested" not in c.text for c in chunks)


def test_poe2_layout_skips_table_of_contents():
    chunks = _chunks("poe2_patch_notes.html")
    assert [c.heading for c in chunks] == ["Skill Changes", "Bug Fixes"]
    assert all("Table of Contents" not in (c.heading or "") for c in chunks)
    assert not any(c.text.strip() in ("• Skill Changes", "• Bug Fixes") for c in chunks)
    assert "chains to nearby enemies" in chunks[0].text


def test_long_sections_split_without_straddling():
    doc = html.fromstring(
        "<table class='forumPostListTable'><tr><td><div class='content'><h3>Big</h3><ul>"
        + "".join(f"<li>line {i} " + "x" * 200 + "</li>" for i in range(20))
        + "</ul><h3>Next</h3><ul><li>tail</li></ul></div></td></tr></table>"
    )
    chunks = chunk_post(first_post(doc), max_chars=1000)
    assert len(chunks) > 3
    assert all(len(c.text) <= 1000 + 210 for c in chunks)
    assert {c.heading for c in chunks} == {"Big", "Next"}
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_version_parsing():
    assert parse_version("3.29.0b Patch Notes") == ("3.29.0b", "3.29")
    assert parse_version("3.29.3 Hotfix 7") == ("3.29.3", "3.29")
    assert parse_version("0.5.4f Patch Notes") == ("0.5.4f", "0.5")
    assert parse_version("Content Update 0.5.5 — Path of Exile 2") == ("0.5.5", "0.5")
    assert parse_version("Server Maintenance") is None


def test_post_date_parsing():
    d = parse_post_date(", Aug 31, 2026, 6:56:21 AM")
    assert d is not None and (d.year, d.month, d.day, d.hour) == (2026, 8, 31, 6)
    assert parse_post_date("yesterday") is None


def test_hash_embedder_is_deterministic_unit_norm_and_fixed_dims():
    e = HashEmbedder()
    [a], [b] = e.embed(["Lightning Strike damage"]), e.embed(["Lightning Strike damage"])
    assert a == b and len(a) == DIMS
    assert abs(sum(x * x for x in a) - 1.0) < 1e-6
    [c] = e.embed(["Herald of Ash reservation"])
    dot = sum(x * y for x, y in zip(a, c, strict=True))
    assert dot < 0.5


def test_heading_equal_to_thread_title_is_not_a_section():
    doc = html.fromstring(
        "<table class='forumPostListTable'><tr><td><div class='content'><h3>3.29.3 Hotfix 7</h3>"
        "<ul><li>Fixed a thing.</li></ul></div></td></tr></table>"
    )
    post = first_post(doc)
    assert chunk_post(post)[0].heading == "3.29.3 Hotfix 7"
    assert chunk_post(post, title="3.29.3 Hotfix 7")[0].heading is None
