# Decisions

Short architecture decision records. The spec (`SPEC.md`) says *what*; this file records the
*why* behind deviations and choices made while building.

## ADR-001 — Own the PoB export parser instead of depending on `pobapi` (2026-09-02)

**Context.** SPEC § 15 says "install `pobapi`, parse a real PoB code, display DPS and life".

**Verified.** `pobapi` 0.6.0 (last release 2021) does not import under Python 3.14: its dependency
`dataslots` removed `with_slots` in 1.1, and after pinning `dataslots==1.0.2` the second dependency
`unstdlib` fails on `unstdlib.six.moves`. The library is unmaintained and predates the current
PoB export layout (`SkillSet`, `ItemSet`, `ConfigSet`, `masteryEffects`).

**Decision.** The PoE adapter owns a small parser (`backend/app/games/poe/pob/`): the format is
`base64url(zlib(xml))`, and the values we need are attributes. Both the legacy (2019) and current
(3.27) layouts are covered by fixtures. Item *mod* interpretation, which was `pobapi`'s real
added value, is not needed for § 5 A and is deferred.

**Consequence.** One fewer dead dependency; the spec's "feasibility verified" claim about the PoB
*headless* path (`api-stdio` bridge, `pob-mcp`) is untouched and remains the plan for § 5 B.

## ADR-002 — PoB export values are `calculated`, engine version `None` (2026-09-02)

A PoB export embeds the numbers PoB computed on the author's machine but **not** PoB's own version.
Provenance therefore says `calculated · Path of Building · engine_version=None` and carries the
tree version (e.g. `3.27`) as `game_version`, plus the engine configuration inputs that condition
the numbers (boss, charges, …). Legacy exports without `treeVersion` yield `game_version=None`,
displayed as *patch unknown*. Nothing is inferred to fill these gaps (SPEC § 3.1, § 3.9).

## ADR-003 — `recalculate()` raises `EngineUnavailable` until the headless engine exists

The adapter contract exposes SPEC § 5 B as a method today so the API surface is stable, but the
PoE implementation refuses and the `/api/v1/games` endpoint reports
`recalculate_modified: false`. No approximation, no LLM estimate (SPEC § 3.15).

## ADR-004 — No database yet

Phase 1 A (analyse a pasted build) is stateless. `docker-compose.yml` ships PostgreSQL + pgvector
for the corpus and knowledge layers, but no table exists until the first feature needs one
(SPEC § 3.13: no infrastructure ahead of actual need).

## ADR-005 — Frontend styling is a placeholder

SPEC § 11 says the design is not to be generated. The current CSS only makes the prototype legible
and demonstrates the *rules* (numbers in monospace, provenance next to every value, unknown as a
first-class state, reduced-motion respected). The visual identity is to be authored by hand.

## ADR-006 — Fixtures are structured build codes, never guide prose

Test fixtures are PoB codes: two MIT-licensed ones from `ppoelzl/PathOfBuildingAPI` and one public
paste from pobb.in, kept with its URL for attribution. No third-party guide text is stored
(SPEC § 7).
