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
from app.games.wow.simc.talents import (
    TalentNode,
    TalentTable,
    parse_spell_query,
    parse_talent_tables,
)


class SimcFailed(Exception):
    """SimulationCraft ran and rejected the input (bad talent string, unknown item…)."""


@dataclass(frozen=True)
class SimcGearItem:
    slot: str
    name: str | None
    ilevel: int | None
    encoded: str | None
    stats: dict[str, float]


@dataclass(frozen=True)
class SimcResult:
    version: str | None
    game_version: str | None  # e.g. 12.1.0.69587, from the report's dbc block
    iterations: int
    fight_style: str | None
    dps_mean: float | None
    dps_error: float | None
    hps_mean: float | None
    dtps_mean: float | None
    fight_length: float | None
    talents: str | None
    talent_tables: tuple[TalentTable, ...]  # the loadout as the engine decoded it
    gear: tuple[SimcGearItem, ...]
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
        # Relative paths and cwd=tmp: the binary may be a container wrapper that mounts the cwd.
        with tempfile.TemporaryDirectory(prefix="reckoner-simc-") as tmp:
            Path(tmp, "profile.simc").write_text(profile_text)
            cmd = [
                self.binary,
                "profile.simc",
                f"iterations={self.iterations}",
                "json2=report.json",
                "html=report.html",  # the only report that carries the decoded talents
            ]
            try:
                proc = subprocess.run(
                    cmd, cwd=tmp, capture_output=True, text=True, timeout=settings.engine_timeout_s
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise EngineUnavailable(f"SimulationCraft did not run: {exc}") from exc
            out = Path(tmp, "report.json")
            if proc.returncode != 0 or not out.exists():
                tail = (proc.stderr or proc.stdout or "").strip()[-600:]
                raise SimcFailed(
                    f"SimulationCraft refused the profile (exit {proc.returncode}): {tail}"
                )
            raw = json.loads(out.read_text())
            report = Path(tmp, "report.html")
            tables = parse_talent_tables(report.read_text()) if report.exists() else ()
        return _parse(raw, self.iterations, tables)

    def talent_data(self, class_name: str) -> tuple[TalentNode, ...]:
        """Every talent node of a class, from ``spell_query`` — cached per binary and class."""
        if not self.available():
            raise EngineUnavailable(self.unavailable_reason())
        key = (self.binary or "", class_name.lower())
        if key not in _TALENT_DATA:
            cmd = [self.binary, f"spell_query=talent.class={class_name.lower()}"]
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=settings.engine_timeout_s
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise EngineUnavailable(f"SimulationCraft did not run: {exc}") from exc
            nodes = parse_spell_query(proc.stdout)
            if not nodes:
                raise SimcFailed(
                    f"SimulationCraft has no talent data for '{class_name}': "
                    + (proc.stderr or proc.stdout).strip()[-300:]
                )
            _TALENT_DATA[key] = nodes
        return _TALENT_DATA[key]


_TALENT_DATA: dict[tuple[str, str], tuple[TalentNode, ...]] = {}


def _num(d: dict, *path: str) -> float | None:
    cur: object = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return float(cur) if isinstance(cur, int | float) else None


def _parse(raw: dict, iterations: int, tables: tuple[TalentTable, ...] = ()) -> SimcResult:
    sim = raw.get("sim", raw)
    players = sim.get("players") or []
    p0 = players[0] if players else {}
    cd = p0.get("collected_data", {})
    gear = []
    for slot, g in (p0.get("gear") or {}).items():
        if not isinstance(g, dict):
            continue
        stats = {k: float(v) for k, v in g.items() if isinstance(v, int | float) and k != "ilevel"}
        ilevel = g.get("ilevel")
        gear.append(
            SimcGearItem(
                slot=slot,
                name=str(g["name"]).replace("_", " ").title() if g.get("name") else None,
                ilevel=int(ilevel) if isinstance(ilevel, int | float) else None,
                encoded=g.get("encoded_item"),
                stats=stats,
            )
        )
    dbc = p0.get("dbc") or {}
    live = dbc.get("Live") if isinstance(dbc, dict) else None
    options = sim.get("options") or {}
    return SimcResult(
        version=raw.get("version") or sim.get("version"),
        game_version=live.get("wow_version") if isinstance(live, dict) else None,
        iterations=int(_num(sim, "options", "iterations") or iterations),
        fight_style=options.get("fight_style") if isinstance(options, dict) else None,
        dps_mean=_num(cd, "dps", "mean"),
        dps_error=_num(cd, "dps", "mean_std_dev"),
        hps_mean=_num(cd, "hps", "mean"),
        dtps_mean=_num(cd, "dtps", "mean"),
        fight_length=_num(sim, "options", "max_time"),
        talents=p0.get("talents") if isinstance(p0.get("talents"), str) else None,
        talent_tables=tables,
        gear=tuple(gear),
        raw=raw,
    )
