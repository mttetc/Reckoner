"""Corpus repository: snapshots in, filtered snapshots out. No game-specific code here."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BuildRow, SnapshotRow, SourceRow
from app.domain.build import BuildSnapshot
from app.domain.provenance import MetricKey


@dataclass(frozen=True)
class SourceRef:
    kind: str
    url: str
    game: str
    title: str | None = None
    parent_url: str | None = None
    terms: str | None = None


@dataclass(frozen=True)
class BuildQuery:
    game: str | None = None
    class_name: str | None = None
    subclass: str | None = None
    main_skill: str | None = None  # case-insensitive substring
    game_version: str | None = None
    min_dps: float | None = None
    min_life: float | None = None
    min_ehp: float | None = None
    sort: str = "dps_total"  # dps_total · life_max · ehp_total · created_at
    limit: int = 20
    offset: int = 0


@dataclass
class SearchResult:
    total: int
    items: list[BuildSnapshot] = field(default_factory=list)
    sources: dict[uuid.UUID, SourceRef] = field(default_factory=dict)


_SORTABLE = {
    "dps_total": SnapshotRow.dps_total,
    "dps_full": SnapshotRow.dps_full,
    "life_max": SnapshotRow.life_max,
    "ehp_total": SnapshotRow.ehp_total,
    "created_at": SnapshotRow.created_at,
}


def _metric_value(snapshot: BuildSnapshot, key: MetricKey) -> float | None:
    m = snapshot.metric(key.value)
    return None if m is None else m.value


def _row_from_snapshot(
    snapshot: BuildSnapshot, build_id: uuid.UUID, source_id: uuid.UUID | None
) -> SnapshotRow:
    metric_source = next((m.provenance.source for m in snapshot.metrics if m.provenance), None)
    return SnapshotRow(
        id=snapshot.id,
        build_id=build_id,
        source_id=source_id,
        game=snapshot.game.value,
        game_version=snapshot.game_version,
        class_name=snapshot.character.class_name,
        subclass=snapshot.character.subclass,
        level=snapshot.character.level,
        main_skill=snapshot.main_skill,
        raw_sha256=snapshot.raw.sha256,
        metric_source=metric_source,
        dps_total=_metric_value(snapshot, MetricKey.DPS_TOTAL),
        dps_full=_metric_value(snapshot, MetricKey.DPS_FULL),
        minion_dps_total=_metric_value(snapshot, MetricKey.MINION_DPS_TOTAL),
        life_max=_metric_value(snapshot, MetricKey.LIFE_MAX),
        energy_shield_max=_metric_value(snapshot, MetricKey.ENERGY_SHIELD_MAX),
        ehp_total=_metric_value(snapshot, MetricKey.EHP_TOTAL),
        node_count=len(snapshot.tree.node_ids) if snapshot.tree.node_ids else None,
        document=snapshot.model_dump(mode="json"),
    )


class CorpusRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    # ------------------------------------------------------------------ sources

    async def upsert_source(self, ref: SourceRef) -> SourceRow:
        stmt = (
            insert(SourceRow)
            .values(
                kind=ref.kind,
                url=ref.url,
                game=ref.game,
                title=ref.title,
                parent_url=ref.parent_url,
                terms=ref.terms,
            )
            .on_conflict_do_update(
                index_elements=[SourceRow.url],
                set_={"title": ref.title, "parent_url": ref.parent_url, "fetched_at": func.now()},
            )
            .returning(SourceRow)
        )
        return (await self.s.execute(stmt)).scalar_one()

    # ------------------------------------------------------------------ snapshots

    async def find_by_hash(self, game: str, raw_sha256: str) -> SnapshotRow | None:
        stmt = select(SnapshotRow).where(
            SnapshotRow.game == game, SnapshotRow.raw_sha256 == raw_sha256
        )
        return (await self.s.execute(stmt)).scalar_one_or_none()

    async def add_snapshot(
        self,
        snapshot: BuildSnapshot,
        source: SourceRow | None = None,
        build_id: uuid.UUID | None = None,
        name: str | None = None,
    ) -> SnapshotRow:
        """Append a snapshot. A new ``Build`` is created unless ``build_id`` is given (history)."""
        if build_id is None:
            build = BuildRow(game=snapshot.game.value, name=name)
            self.s.add(build)
            await self.s.flush()
            build_id = build.id
        row = _row_from_snapshot(snapshot, build_id, source.id if source else None)
        self.s.add(row)
        await self.s.flush()
        return row

    async def get_snapshot(self, snapshot_id: uuid.UUID) -> BuildSnapshot | None:
        row = await self.s.get(SnapshotRow, snapshot_id)
        return BuildSnapshot.model_validate(row.document) if row else None

    async def get_source_of(self, snapshot_id: uuid.UUID) -> SourceRef | None:
        stmt = (
            select(SourceRow)
            .join(SnapshotRow, SnapshotRow.source_id == SourceRow.id)
            .where(SnapshotRow.id == snapshot_id)
        )
        row = (await self.s.execute(stmt)).scalar_one_or_none()
        return _ref(row) if row else None

    def _apply_filters(self, stmt: Select, q: BuildQuery) -> Select:
        if q.game:
            stmt = stmt.where(SnapshotRow.game == q.game)
        if q.class_name:
            stmt = stmt.where(func.lower(SnapshotRow.class_name) == q.class_name.lower())
        if q.subclass:
            stmt = stmt.where(func.lower(SnapshotRow.subclass) == q.subclass.lower())
        if q.main_skill:
            stmt = stmt.where(SnapshotRow.main_skill.ilike(f"%{q.main_skill}%"))
        if q.game_version:
            stmt = stmt.where(SnapshotRow.game_version == q.game_version)
        if q.min_dps is not None:
            stmt = stmt.where(SnapshotRow.dps_total >= q.min_dps)
        if q.min_life is not None:
            stmt = stmt.where(SnapshotRow.life_max >= q.min_life)
        if q.min_ehp is not None:
            stmt = stmt.where(SnapshotRow.ehp_total >= q.min_ehp)
        return stmt

    async def search(self, q: BuildQuery) -> SearchResult:
        base = self._apply_filters(select(SnapshotRow), q)
        total = (
            await self.s.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        order = _SORTABLE.get(q.sort, SnapshotRow.dps_total)
        # Unknown metrics (NULL) sort last: a build without a number never outranks one with.
        stmt = base.order_by(order.desc().nulls_last(), SnapshotRow.created_at.desc())
        stmt = stmt.limit(min(q.limit, 100)).offset(q.offset)
        rows = (await self.s.execute(stmt)).scalars().all()
        result = SearchResult(total=total)
        for row in rows:
            result.items.append(BuildSnapshot.model_validate(row.document))
        source_ids = {r.source_id for r in rows if r.source_id}
        if source_ids:
            srcs = (
                await self.s.execute(select(SourceRow).where(SourceRow.id.in_(source_ids)))
            ).scalars()
            by_id = {s.id: _ref(s) for s in srcs}
            for row in rows:
                if row.source_id in by_id:
                    result.sources[row.id] = by_id[row.source_id]
        return result

    async def stats(self) -> dict:
        total = (await self.s.execute(select(func.count(SnapshotRow.id)))).scalar_one()
        per_game = (
            await self.s.execute(select(SnapshotRow.game, func.count()).group_by(SnapshotRow.game))
        ).all()
        per_version = (
            await self.s.execute(
                select(SnapshotRow.game, SnapshotRow.game_version, func.count())
                .group_by(SnapshotRow.game, SnapshotRow.game_version)
                .order_by(SnapshotRow.game, SnapshotRow.game_version)
            )
        ).all()
        sources = (await self.s.execute(select(func.count(SourceRow.id)))).scalar_one()
        return {
            "snapshots": total,
            "sources": sources,
            "per_game": {g: n for g, n in per_game},
            "per_version": [{"game": g, "game_version": v, "count": n} for g, v, n in per_version],
        }


def _ref(row: SourceRow) -> SourceRef:
    return SourceRef(
        kind=row.kind,
        url=row.url,
        game=row.game,
        title=row.title,
        parent_url=row.parent_url,
        terms=row.terms,
    )
