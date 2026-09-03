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

## ADR-007 — The main skill is whatever the export has selected; minion and aggregate DPS are separate facts (2026-09-03)

**Context.** A robustness pass over 37 unique exports linked from the official class forums
(patches 3.22 → 3.29) parsed without a single failure but surfaced three honest-but-confusing
situations: (a) the author left a movement or utility skill selected as PoB's main socket group,
so `TotalDPS` is 0 while `FullDPS` is in the millions; (b) minion builds report player `TotalDPS`
0 and carry their real numbers in `<MinionStat>` rows; (c) one export had no `TotalDPS` row at all.

**Decision.**
- `main_skill` stays the export's selection. Guessing a "better" main skill from `includeInFullDPS`
  flags or from DPS magnitude would be an inference presented as a fact. The provenance context
  carries `main_skill_source = "socket group selected in the export"` and the UI says so on hover.
- `dps.full` keeps PoB's number and its provenance context lists the `<FullDPSSkill>` rows it
  aggregates (`aggregates`), so a reader can see that 19.4M is poison + culling + two skills.
  The full breakdown lives in `extra["poe.full_dps_breakdown"]`.
- New canonical keys `minion.dps.total` and `minion.life.max` are emitted **only when the export
  carries `<MinionStat>` rows**. Absence is not an unknown: a build without minions has nothing to
  measure. This is the one place where a metric is optional rather than unknown-with-reason.
- A missing `TotalDPS` row stays `unknown` with the reason "not present in this export". Never 0.

**Consequences.** Six fixtures now cover both layouts, multi-set exports, minions, utility-selected
main skill and absent DPS. `scripts/harvest_forum_codes.py` reproduces the pass; it is also the
seed of the § 7 corpus ingestion (official forum → build codes), rate-limited and identified.

## ADR-008 — Headless Path of Building through our own stdio bridge, pinned by commit (2026-09-03)

**Context.** SPEC § 5 B forbids approximating a modified build: only a real engine may produce
the numbers. Upstream PoB ships `HeadlessWrapper.lua` (used by its own test-suite) which exposes
`loadBuildFromXML` and the full `build` object, but no API. A JSON-RPC layer exists only as an
open upstream PR (#9505, used by the various `pob-mcp` servers).

**Decision.**
- Run upstream PoB unmodified under LuaJIT, at a **pinned commit** installed by
  `backend/scripts/install_pob.sh` into `.engines/pob` (sparse checkout, no tree sprites: 646 MB).
- Talk to it through **our own** 240-line `bridge.lua` (newline-delimited JSON on stdio), not the
  unmerged PR: fewer moving parts, no dependency on a fork, and every refusal rule is ours to test.
- The only PoB dependency we shim is `lua-utf8`, which PoB uses solely to format thousands
  separators for display. The shim is byte-wise `string.*`; we never read formatted strings.
- Supported modifications: `tree.allocate`, `tree.deallocate`, `config.set`, `gem.set_level`,
  `gem.set_quality`. Each is validated against PoB's own data (node exists, node reachable,
  config value in PoB's list — case-insensitive, canonicalised) and refused with a precise message
  (`InvalidModification`, HTTP 422). Unknown kinds are refused, never ignored.
- `recalculate()` returns the variant **and a baseline recomputed by the same engine**. The export's
  own numbers may come from a different PoB version and game-data patch (the 3.27 fixture drifts
  by ~0.4 % DPS and −19 life on current data), so like-for-like deltas need a same-engine baseline.
- Engine metrics carry `source=pob:headless`, the real `engine_version` (e.g. 2.67.2), the pinned
  commit and the engine's data version in `context`, plus the list of modifications PoB applied.
- No engine configured → capability `recalculate_modified=false` and HTTP 503 with the install hint.
  The default `backend` CI job runs in that mode on purpose; the `engine` job runs with PoB and
  fails if the engine tests skip.

**Consequences.** One persistent LuaJIT process per API worker, requests serialised, a fresh
`load` before every modification set (no state leaks). ~2 s cold start, ~0.3–0.8 s per request.
`RawSource` still keeps only a hash: the recalculation endpoint takes the code again (stateless
until ADR-004 is revisited). Item edits and mastery selection are not yet exposed.

