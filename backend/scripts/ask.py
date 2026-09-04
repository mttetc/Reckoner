"""Ask Reckoner from the terminal with the configured provider (dev smoke test for real models).

    .venv/bin/python scripts/ask.py "Find me a tanky Duelist Lightning Strike build"
    .venv/bin/python scripts/ask.py --code tests/fixtures/pob/slayer_lightning_strike_3_27.txt \
        "How strong is this?"

Prints the answer, then the tool trace, the number audit and the degraded states — the same
things the /ask page shows. Nothing here is hidden from the user in the UI either.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.runner import ask  # noqa: E402
from app.api.deps import build_store, knowledge_store  # noqa: E402
from app.db.engine import dispose, session_factory  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--game", default=None)
    ap.add_argument("--code", default=None, help="path to a file holding a build code")
    args = ap.parse_args()
    code = Path(args.code).read_text() if args.code else None

    async with session_factory()() as session:
        a = await ask(
            build_store(session), knowledge_store(session), args.question, game=args.game, code=code
        )
    await dispose()

    print(a.text)
    print()
    print(
        f"— model {a.model} · {len(a.steps)} tool call(s) · {a.duration_ms} ms"
        f" · tokens {a.input_tokens}+{a.output_tokens}"
    )
    for s in a.steps:
        status = "ok " if s.ok else "ERR"
        detail = s.summary if s.ok else s.error
        print(f"  {status} {s.tool}({s.args}) → {detail} [{s.duration_ms} ms]")
    if a.audit.clean:
        print(f"— audit: {a.audit.checked} number(s), all traceable")
    else:
        print(f"— audit: UNVERIFIED {a.audit.unverified} ({a.audit.checked} checked)")
    for d in a.degraded:
        print(f"— degraded: {d}")
    print(f"— evidence: {len(a.evidence)} item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
