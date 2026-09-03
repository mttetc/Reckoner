import pytest

from app.corpus.pipeline import FetchedCode, ingest_code, ingest_many
from app.db.repository import BuildQuery, CorpusRepository, SourceRef
from app.domain.provenance import MetricKey

pytestmark = pytest.mark.asyncio


def _src(url="https://pobb.in/abc", title="A build"):
    return SourceRef(
        kind="paste",
        url=url,
        game="poe",
        title=title,
        parent_url="https://www.pathofexile.com/forum/view-thread/1",
        terms="test",
    )


async def test_ingest_persists_document_and_projections(session, code_modern):
    snapshot, status = await ingest_code(session, code_modern, _src())
    assert status == "ingested"
    await session.commit()
    repo = CorpusRepository(session)
    back = await repo.get_snapshot(snapshot.id)
    assert back == snapshot  # full round trip through JSONB, provenance included
    row = await repo.find_by_hash("poe", snapshot.raw.sha256)
    assert row.dps_total == snapshot.metric(MetricKey.DPS_TOTAL).value
    assert row.class_name == "Duelist" and row.subclass == "Slayer"
    assert row.metric_source == "pob:export"
    assert (await repo.get_source_of(snapshot.id)).url == "https://pobb.in/abc"


async def test_same_code_is_a_duplicate_not_a_second_row(session, code_modern):
    fetched = [
        FetchedCode(code_modern, _src()),
        FetchedCode(code_modern, _src("https://pobb.in/dup")),
    ]
    report = await ingest_many(session, fetched)
    assert report.ingested == 1 and report.duplicates == 1 and report.rejected == []
    assert (await CorpusRepository(session).stats())["snapshots"] == 1


async def test_garbage_is_rejected_with_a_reason_and_does_not_poison_the_batch(
    session, code_modern
):
    fetched = [
        FetchedCode("not a build code at all", _src("https://pobb.in/bad")),
        FetchedCode(code_modern, _src("https://pobb.in/good")),
    ]
    report = await ingest_many(session, fetched)
    assert report.ingested == 1
    assert len(report.rejected) == 1
    assert report.rejected[0][0] == "https://pobb.in/bad"
    assert "invalid_build_code" in report.rejected[0][1]


async def test_unknown_metrics_are_null_and_sort_last(session, all_codes):
    fetched = [FetchedCode(code, _src(f"https://pobb.in/{name}", name)) for name, code in all_codes]
    report = await ingest_many(session, fetched)
    assert report.ingested == len(all_codes), report.rejected
    repo = CorpusRepository(session)
    res = await repo.search(BuildQuery(game="poe", sort="dps_total", limit=50))
    assert res.total == len(all_codes)
    known = [s.metric(MetricKey.DPS_TOTAL).value for s in res.items]
    nulls = [v for v in known if v is None]
    assert nulls, "the ballista fixture has no TotalDPS and must be present as unknown"
    assert known[-len(nulls) :] == nulls  # unknown never outranks a number
    assert known[: len(known) - len(nulls)] == sorted(
        known[: len(known) - len(nulls)], reverse=True
    )


async def test_filters(session, all_codes):
    await ingest_many(
        session, [FetchedCode(c, _src(f"https://pobb.in/{n}", n)) for n, c in all_codes]
    )
    repo = CorpusRepository(session)
    r = await repo.search(BuildQuery(game="poe", class_name="duelist"))
    assert r.total == 1 and r.items[0].character.subclass == "Slayer"
    r = await repo.search(BuildQuery(game="poe", main_skill="lightning strike"))
    assert r.total == 1
    r = await repo.search(BuildQuery(game="poe", min_dps=1_000_000))
    assert r.total == 1  # only the slayer has a known TotalDPS above 1M
    r = await repo.search(BuildQuery(game="poe", game_version="3.29"))
    assert r.total == 2  # void sphere + ballista
    r = await repo.search(BuildQuery(game="poe2"))
    assert r.total == 0 and r.items == []
    assert (await repo.stats())["per_game"] == {"poe": len(all_codes)}
