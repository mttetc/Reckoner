"""SimulationCraft as a headless engine: a subprocess per simulation, JSON report back.

``simc <profile> iterations=N json2=<out>``. Nothing here derives a number: the DPS is read from
SimulationCraft's own report, and its version travels with it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.domain.errors import EngineUnavailable


@dataclass(frozen=True)
class SimcResult:
    version: str | None
    iterations: int
    dps_mean: float | None
    dps_error: float | None
    hps_mean: float | None
    dtps_mean: float | None
    fight_length: float | None
    raw: dict


class SimcEngine:
    def __init__(self, binary: str | None = None, iterations: int | None = None) -> None:
        self.binary = binary or settings.simc_bin
        self.iterations = iterations or settings.simc_iterations

    def available(self) -> bool:
        return bool(self.binary) and shutil.which(self.binary) is not None

    def unavailable_reason(self) -> str:
        if not self.binary:
            return "RECKONER_SIMC_BIN is not set (SimulationCraft CLI path)"
        return f"'{self.binary}' not found on PATH"

    def simulate(self, profile_text: str) -> SimcResult:
        if not self.available():
            raise EngineUnavailable(self.unavailable_reason())
        with tempfile.TemporaryDirectory(prefix="reckoner-simc-") as tmp:
            profile = Path(tmp) / "profile.simc"
            out = Path(tmp) / "report.json"
            profile.write_text(profile_text)
            cmd = [self.binary, str(profile), f"iterations={self.iterations}", f"json2={out}"]
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=settings.engine_timeout_s
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise EngineUnavailable(f"SimulationCraft did not run: {exc}") from exc
            if proc.returncode != 0 or not out.exists():
                tail = (proc.stderr or proc.stdout or "").strip()[-400:]
                raise EngineUnavailable(f"SimulationCraft failed (exit {proc.returncode}): {tail}")
            raw = json.loads(out.read_text())
        return _parse(raw, self.iterations)


def _num(d: dict, *path: str) -> float | None:
    cur: object = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return float(cur) if isinstance(cur, int | float) else None


def _parse(raw: dict, iterations: int) -> SimcResult:
    sim = raw.get("sim", raw)
    players = sim.get("players") or []
    p0 = players[0] if players else {}
    cd = p0.get("collected_data", {})
    return SimcResult(
        version=raw.get("version") or sim.get("version"),
        iterations=int(_num(sim, "options", "iterations") or iterations),
        dps_mean=_num(cd, "dps", "mean"),
        dps_error=_num(cd, "dps", "mean_std_dev"),
        hps_mean=_num(cd, "hps", "mean"),
        dtps_mean=_num(cd, "dtps", "mean"),
        fight_length=_num(sim, "options", "max_time"),
        raw=raw,
    )
