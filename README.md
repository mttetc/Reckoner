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
Modified-build recalculation runs through the real headless Path of Building when installed (tree allocation, config, gem level/quality); item edits are not exposed yet.

## Principles that are enforced in code

| Principle (SPEC § 3) | Where |
|---|---|
| Never a bare number — every value has provenance or is `unknown` with a reason | `Metric` validator, `backend/app/domain/provenance.py`; checked end-to-end in `frontend/e2e` |
| Nothing game-specific in the common domain | `tests/unit/test_domain_isolation.py` greps the domain package |
| Never simulate a modified calculation | `PoEAdapter.recalculate` runs the real headless Path of Building (pinned commit, `app/games/poe/engine/`) and returns a same-engine baseline next to the variant; without the engine the API returns 503, never a guess (ADR-008) |
| Build history never overwritten | `BuildSnapshot` is frozen; `Build` only appends snapshot ids |
| Knowledge is game-aware | `KnowledgeRepository.search(game, …)` refuses an empty game (422); the API requires `game` by type; `tests/corpus/test_knowledge_isolation.py` proves zero cross-game hits both ways, in CI (ADR-010) |
| The model is never the source of truth | `app/agent`: numbers come only from tools with `Evidence`; the final text is audited and untraceable numbers are shown as unverified (ADR-011) |
| Ingestion respects the source | `app/corpus/policy.py`: allowlist with stated terms, denylist (Maxroll, Mobalytics, undocumented endpoints), robots.txt, identified UA, rate limit — unit-tested |

## Layout

```
backend/            FastAPI · Python ≥ 3.12
  app/domain/       common domain: Build, BuildSnapshot, BuildVariant, Metric, Provenance, Knowledge
  app/games/        adapter registry + one package per game
    poe/            Path of Exile: PoB codec, XML parser (legacy + current layouts), tree URL decoder
      engine/       headless PoB: bridge.lua (JSON over stdio) + Python client; modifications validated by PoB itself
    poe2/           Phase 2: knowledge source only for now (patch notes) — 5 lines, nothing common touched
    diablo3/        Phase 3 placeholder
  app/corpus/       ingestion policy (allowlist, robots.txt, rate limit) + pipeline (validate, dedupe, persist)
  app/db/           PostgreSQL + pgvector: models, repository (search with unknown-last ordering)
  app/knowledge/    versioned knowledge: heading-aware chunker, local embeddings (fastembed / hash), game-filtered retrieval
  app/agent/        tool registry + evidence, LLM clients (Ollama/OpenAI-compatible, Anthropic, scripted), loop, number audit
  app/api/          /ask · /builds/analyze · /builds/recalculate · /builds · /builds/{id} · /corpus/stats · /knowledge/search · /knowledge/patches · /games
  scripts/first_light.py   SPEC § 15: decode a real code, print DPS and life with provenance
  scripts/ingest_forum.py  corpus ingestion from the official forums (policy-enforced; cron, not HTTP)
  scripts/ingest_files.py  dev seed / e2e fixtures into the corpus · scripts/db_init.py  schema bootstrap
  scripts/install_pob.sh   pinned, sparse Path of Building checkout into .engines/pob (≈650 MB)
  tests/            unit + integration + engine (pytest; engine tests skip without PoB, CI runs them for real)
frontend/           Next.js 16 · analyse page · Playwright e2e (drives backend + frontend)
docker-compose.yml  PostgreSQL 17 + pgvector (or `brew install postgresql@17 pgvector`)
```

## Run

```bash
# backend
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python scripts/first_light.py tests/fixtures/pob/slayer_lightning_strike_3_27.txt
.venv/bin/python -m pytest                        # engine tests skip until PoB is installed

# headless engine (recalculation) — needs a 2026 LuaJIT: brew install luajit (Linux: build from
# source, distro packages predate the compound-assignment syntax PoB uses; see ci.yml LUAJIT_COMMIT)
scripts/install_pob.sh                            # → .engines/pob, prints the two env vars
cp .env.example .env                              # RECKONER_POB_SRC, RECKONER_POB_SOURCE_COMMIT
.venv/bin/python -m pytest tests/engine -rs       # 12 tests against the real engine

# corpus (PostgreSQL + pgvector; docker compose up -d db, or a local server with a `reckoner` role)
.venv/bin/python scripts/db_init.py
.venv/bin/python scripts/ingest_files.py tests/fixtures/pob/*.txt      # dev seed
.venv/bin/python scripts/ingest_forum.py --threads-per-forum 5          # real ingestion, polite
.venv/bin/pip install -e ".[rag]"                                        # local ONNX embeddings (optional)
.venv/bin/python scripts/ingest_patch_notes.py --game poe --limit 5     # official patch notes → knowledge
.venv/bin/python scripts/ingest_patch_notes.py --game poe2 --limit 5

# agent (free, local): brew install ollama && ollama pull qwen2.5:7b && brew services start ollama
# then POST /api/v1/ask or open /ask. Without a reachable model the scripted policy answers and says so.
.venv/bin/python scripts/ask.py "Find me a tanky Duelist Lightning Strike build"   # terminal smoke test
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
