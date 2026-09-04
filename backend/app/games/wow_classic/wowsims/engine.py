"""WoWSims Classic as a headless engine: ``wowsimcli sim --infile <RaidSimRequest>`` per run.

The DPS is read from WoWSims' own ``RaidSimResult``; its version (the build's git revision) travels
with every number. Nothing here derives a value.
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
from app.games.wow_classic.wowsims.settings import to_raid_sim_request


class WowSimsFailed(Exception):
    """WoWSims ran and rejected the input (unknown item, bad rotation, …)."""


@dataclass(frozen=True)
class WowSimsResult:
    version: str | None
    iterations: int
    dps_avg: float | None
    dps_stdev: float | None
    hps_avg: float | None
    dtps_avg: float | None
    duration: float | None
    raw: dict


class WowSimsEngine:
    def __init__(self, binary: str | None = None, iterations: int | None = None) -> None:
        self.binary = binary or settings.wowsims_bin
        self.iterations = iterations or settings.wowsims_iterations

    def available(self) -> bool:
        return bool(self.binary) and shutil.which(self.binary) is not None

    def unavailable_reason(self) -> str:
        if not self.binary:
            return "RECKONER_WOWSIMS_BIN is not set (wowsimcli path)"
        return f"'{self.binary}' not found on PATH"

    def version(self) -> str | None:
        if not self.available():
            return None
        key = self.binary or ""
        if key not in _VERSIONS:
            try:
                proc = subprocess.run([key, "version"], capture_output=True, text=True, timeout=30)
                _VERSIONS[key] = (
                    (proc.stdout or "").strip().splitlines()[0] if proc.stdout else None
                )
            except (OSError, subprocess.TimeoutExpired):
                _VERSIONS[key] = None
        return _VERSIONS[key]

    def simulate(self, data: dict) -> WowSimsResult:
        if not self.available():
            raise EngineUnavailable(self.unavailable_reason())
        request = to_raid_sim_request(data, self.iterations)
        with tempfile.TemporaryDirectory(prefix="reckoner-wowsims-") as tmp:
            Path(tmp, "input.json").write_text(json.dumps(request))
            try:
                proc = subprocess.run(
                    [self.binary, "sim", "--infile", "input.json"],
                    cwd=tmp,
                    capture_output=True,
                    text=True,
                    timeout=settings.engine_timeout_s,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise EngineUnavailable(f"WoWSims did not run: {exc}") from exc
        if proc.returncode != 0 or not proc.stdout.strip().startswith("{"):
            tail = (proc.stderr or proc.stdout or "").strip()[-600:]
            raise WowSimsFailed(f"WoWSims refused the export (exit {proc.returncode}): {tail}")
        raw = json.loads(proc.stdout)
        if raw.get("error"):
            message = str(raw["error"].get("message", "")).split("\n")[0]
            raise WowSimsFailed(f"WoWSims refused the export: {message}")
        return _parse(raw, self.iterations, self.version(), request)


_VERSIONS: dict[str, str | None] = {}


def _avg(d: dict, key: str) -> float | None:
    v = d.get(key)
    if isinstance(v, dict) and isinstance(v.get("avg"), int | float):
        return float(v["avg"])
    return None


def _parse(raw: dict, iterations: int, version: str | None, request: dict) -> WowSimsResult:
    parties = (raw.get("raidMetrics") or {}).get("parties") or [{}]
    player = (parties[0].get("players") or [{}])[0]
    dps = player.get("dps") or {}
    return WowSimsResult(
        version=version,
        iterations=int(raw.get("iterationsDone") or iterations),
        dps_avg=_avg(player, "dps"),
        dps_stdev=float(dps["stdev"]) if isinstance(dps.get("stdev"), int | float) else None,
        hps_avg=_avg(player, "hps"),
        dtps_avg=_avg(player, "dtps"),
        duration=(request.get("encounter") or {}).get("duration"),
        raw=raw,
    )
