"""Tables. The snapshot *document* (full ``BuildSnapshot`` JSON) is the truth; scalar columns are
search projections derived from it at write time, never edited on their own.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SourceRow(Base):
    """Where a corpus build came from. Attribution is the URL (+ title); no author handles."""

    __tablename__ = "corpus_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(32))  # forum_thread · paste · file · user_paste
    url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str | None] = mapped_column(Text)
    game: Mapped[str] = mapped_column(String(16), index=True)
    parent_url: Mapped[str | None] = mapped_column(
        Text, comment="Page that linked to this source (e.g. the forum thread for a paste)."
    )
    terms: Mapped[str | None] = mapped_column(
        Text,
        comment="Why this fetch was permitted: robots.txt / documented public API / user upload.",
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    snapshots: Mapped[list[SnapshotRow]] = relationship(back_populates="source")


class BuildRow(Base):
    __tablename__ = "builds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    snapshots: Mapped[list[SnapshotRow]] = relationship(
        back_populates="build", order_by="SnapshotRow.created_at"
    )


class SnapshotRow(Base):
    __tablename__ = "build_snapshots"
    __table_args__ = (
        UniqueConstraint("game", "raw_sha256", name="uq_snapshot_game_raw"),
        Index("ix_snapshot_search", "game", "class_name", "subclass", "main_skill"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    build_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("builds.id"), index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("corpus_sources.id"), index=True)

    game: Mapped[str] = mapped_column(String(16))
    game_version: Mapped[str | None] = mapped_column(String(16), index=True)
    class_name: Mapped[str | None] = mapped_column(String(64))
    subclass: Mapped[str | None] = mapped_column(String(64))
    level: Mapped[int | None] = mapped_column(Integer)
    main_skill: Mapped[str | None] = mapped_column(String(128))
    raw_sha256: Mapped[str] = mapped_column(String(64))
    metric_source: Mapped[str | None] = mapped_column(
        String(32), comment="Provenance source of the metrics, e.g. pob:export / pob:headless."
    )

    # Search projections (None when the metric is unknown — never 0).
    dps_total: Mapped[float | None] = mapped_column(Float)
    dps_full: Mapped[float | None] = mapped_column(Float)
    minion_dps_total: Mapped[float | None] = mapped_column(Float)
    life_max: Mapped[float | None] = mapped_column(Float)
    energy_shield_max: Mapped[float | None] = mapped_column(Float)
    ehp_total: Mapped[float | None] = mapped_column(Float)
    node_count: Mapped[int | None] = mapped_column(Integer)

    document: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    build: Mapped[BuildRow] = relationship(back_populates="snapshots")
    source: Mapped[SourceRow | None] = relationship(back_populates="snapshots")


class KnowledgeChunkRow(Base):
    """One retrievable passage. ``game`` is mandatory and indexed: filtering on it precedes any
    similarity ranking (SPEC § 6)."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("source_url", "ordinal", name="uq_chunk_source_ordinal"),
        Index("ix_chunk_game_patch", "game", "patch"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game: Mapped[str] = mapped_column(String(16), index=True)
    version: Mapped[str | None] = mapped_column(String(32))
    patch: Mapped[str | None] = mapped_column(String(32))
    season: Mapped[str | None] = mapped_column(String(64))
    class_name: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(64))  # e.g. ggg:patch-notes
    source_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    heading: Mapped[str | None] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    embedder: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float]] = mapped_column(Vector(384))


class FeedbackRow(Base):
    """A thumbs up / down on one answer. Read by humans; never fed back to any model."""

    __tablename__ = "answer_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[str] = mapped_column(String(128), index=True)
    rating: Mapped[str] = mapped_column(String(16))
    question: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
