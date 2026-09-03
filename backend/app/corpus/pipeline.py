"""Fetcher output → validated, deduplicated, persisted snapshots."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import CorpusRepository, SourceRef
from app.domain.build import BuildSnapshot, GameId
from app.domain.errors import DomainError
from app.games import detect_adapter, get_adapter


@dataclass(frozen=True)
class FetchedCode:
    code: str
    source: SourceRef


class Fetcher(Protocol):
    """Yields build codes with their attribution. Implemented per game, per permitted source."""

    def __iter__(self) -> Iterable[FetchedCode]: ...


@dataclass
class IngestReport:
    ingested: int = 0
    duplicates: int = 0
    rejected: list[tuple[str, str]] = field(default_factory=list)  # (source url, reason)
    snapshot_ids: list[str] = field(default_factory=list)


class ValidationFailed(DomainError):
    code = "build_validation_failed"


def validate(snapshot: BuildSnapshot) -> None:
    """Minimal structural validation: enough to be searchable, honest about the rest."""
    if not snapshot.character.class_name:
        raise ValidationFailed("no character class")
    if not snapshot.metrics:
        raise ValidationFailed("no metrics at all")
    if snapshot.tree.unknown_reason and not snapshot.items and not snapshot.skills:
        raise ValidationFailed("neither tree, items nor skills — empty build")


async def ingest_code(
    session: AsyncSession, code: str, source: SourceRef, game: GameId | str | None = None
) -> tuple[BuildSnapshot | None, str]:
    """Returns (snapshot, status) with status in {'ingested', 'duplicate'}; raises DomainError."""
    adapter = get_adapter(game) if game else detect_adapter(code)
    snapshot = adapter.parse_build(code)
    validate(snapshot)
    repo = CorpusRepository(session)
    existing = await repo.find_by_hash(snapshot.game.value, snapshot.raw.sha256)
    if existing is not None:
        return None, "duplicate"
    src = await repo.upsert_source(source)
    await repo.add_snapshot(snapshot, source=src, name=source.title)
    return snapshot, "ingested"


async def ingest_many(
    session: AsyncSession, fetched: Iterable[FetchedCode], game: GameId | str | None = None
) -> IngestReport:
    report = IngestReport()
    for item in fetched:
        try:
            snapshot, status = await ingest_code(session, item.code, item.source, game)
        except DomainError as exc:
            await session.rollback()
            report.rejected.append((item.source.url, f"{exc.code}: {exc}"))
            continue
        except Exception as exc:  # one bad code must never abort the batch
            await session.rollback()
            report.rejected.append((item.source.url, f"unexpected: {type(exc).__name__}: {exc}"))
            continue
        await session.commit()
        if status == "duplicate":
            report.duplicates += 1
        else:
            report.ingested += 1
            assert snapshot is not None
            report.snapshot_ids.append(str(snapshot.id))
    return report
