"""SPEC § 15 — first concrete action: parse a real PoB code, print DPS and life, with provenance.

python scripts/first_light.py tests/fixtures/pob/slayer_lightning_strike_3_27.txt
pbpaste | python scripts/first_light.py -
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.provenance import MetricKey  # noqa: E402
from app.services.analyze import analyze_code  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    code = sys.stdin.read() if argv[1] == "-" else Path(argv[1]).read_text()
    snap = analyze_code(code)
    c = snap.character
    print(f"{c.class_name} / {c.subclass}  level {c.level}   main skill: {snap.main_skill}")
    print(
        f"game={snap.game.value}  patch={snap.game_version or 'unknown'}  "
        f"tree nodes={len(snap.tree.node_ids)}"
    )
    print()
    keys = [MetricKey.DPS_TOTAL, MetricKey.DPS_FULL, MetricKey.LIFE_MAX, MetricKey.EHP_TOTAL]
    if snap.metric(MetricKey.MINION_DPS_TOTAL.value) is not None:
        keys.insert(2, MetricKey.MINION_DPS_TOTAL)  # optional: only when the export has minion rows
    for key in keys:
        m = snap.metric(key.value)
        if m is None or not m.known:
            print(f"{key.value:<16} unknown  — {m.unknown_reason if m else 'no metric'}")
            continue
        p = m.provenance
        print(
            f"{key.value:<16} {m.value:>16,.1f}  {p.status.value} · {p.engine} "
            f"(version {p.engine_version or 'not embedded'}) · patch {p.game_version or 'unknown'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
