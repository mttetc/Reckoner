# Reckoner

> Understand what makes a build work, how strong it really is, and what to change.
>
> *reckon* — to calculate, to count, to judge from evidence. The system reckons; the model only talks.

An AI system that understands ARPG builds by combining structured game data, deterministic
game-specific calculation engines, versioned knowledge retrieval, tool-calling agents and
provenance — behind a natural-language interface. The full specification is in
[`docs/SPEC.md`](docs/SPEC.md); decisions taken while building are in
[`docs/DECISIONS.md`](docs/DECISIONS.md).

**Status: Phase 1, slice A.** Paste a Path of Building export → normalised build snapshot where every
number carries its provenance and every gap is an explicit `unknown`. No corpus, knowledge layer or
agent yet. Modified-build recalculation runs through the real headless Path of Building when installed (tree allocation, config, gem level/quality); item edits are not exposed yet.

## Principles that are enforced in code

| Principle (SPEC § 3) | Where |
|---|---|
| Never a bare number — every value has provenance or is `unknown` with a reason | `Metric` validator, `backend/app/domain/provenance.py`; checked end-to-end in `frontend/e2e` |
| Nothing game-specific in the common domain | `tests/unit/test_domain_isolation.py` greps the domain package |
| Never simulate a modified calculation | `PoEAdapter.recalculate` runs the real headless Path of Building (pinned commit, `app/games/poe/engine/`) and returns a same-engine baseline next to the variant; without the engine the API returns 503, never a guess (ADR-008) |
| Build history never overwritten | `BuildSnapshot` is frozen; `Build` only appends snapshot ids |
| Knowledge is game-aware | `KnowledgeMetadata.game` is mandatory (retrieval filter to come with the RAG layer) |

## Layout

```
backend/            FastAPI · Python ≥ 3.12
  app/domain/       common domain: Build, BuildSnapshot, BuildVariant, Metric, Provenance, Knowledge
  app/games/        adapter registry + one package per game
    poe/            Path of Exile: PoB codec, XML parser (legacy + current layouts), tree URL decoder
      engine/       headless PoB: bridge.lua (JSON over stdio) + Python client; modifications validated by PoB itself
    poe2/ diablo3/  Phase 2 / 3 placeholders
  app/api/          /api/v1/builds/analyze · /api/v1/builds/recalculate · /api/v1/games · /health
  scripts/first_light.py   SPEC § 15: decode a real code, print DPS and life with provenance
  scripts/harvest_forum_codes.py  collect recent codes linked from the official forums (robustness pass, § 7 seed)
  scripts/install_pob.sh   pinned, sparse Path of Building checkout into .engines/pob (≈650 MB)
  tests/            unit + integration + engine (pytest; engine tests skip without PoB, CI runs them for real)
frontend/           Next.js 16 · analyse page · Playwright e2e (drives backend + frontend)
docker-compose.yml  PostgreSQL 17 + pgvector (not used yet — see ADR-004)
```

## Run

```bash
# backend
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python scripts/first_light.py tests/fixtures/pob/slayer_lightning_strike_3_27.txt
.venv/bin/python -m pytest                        # engine tests skip until PoB is installed

# headless engine (recalculation) — needs luajit: brew install luajit / apt install luajit
scripts/install_pob.sh                            # → .engines/pob, prints the two env vars
cp .env.example .env                              # RECKONER_POB_SRC, RECKONER_POB_SOURCE_COMMIT
.venv/bin/python -m pytest tests/engine -rs       # 12 tests against the real engine
.venv/bin/uvicorn app.main:app --reload --port 8000

# frontend
cd frontend && pnpm install && pnpm dev          # http://localhost:3000
pnpm test:e2e                                     # starts both servers itself
```

## Adding a game (the metric that matters — SPEC § 8)

Create `backend/app/games/<game>/` implementing `GameAdapter`, register it in
`backend/app/games/__init__.py`, add the id to `GameId`. Nothing else in `app/domain` should change;
`test_domain_isolation.py` and the diff size are the measure.

## Data & legal

Fixtures are PoB codes (two MIT-licensed, one public pobb.in paste with attribution). No guide
prose is stored, no commercial build sites are scraped, no private APIs are used (SPEC § 7).
