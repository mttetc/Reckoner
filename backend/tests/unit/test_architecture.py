"""Dependency rules (hexagonal): domain ← services/agent ← adapters; frameworks stay outside."""

import re
from pathlib import Path

APP = Path(__file__).parents[2] / "app"
IMPORT = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.M)


def _imports(folder: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for f in (APP / folder).rglob("*.py"):
        out[str(f.relative_to(APP))] = set(IMPORT.findall(f.read_text()))
    return out


def _forbid(folder: str, prefixes: tuple[str, ...]) -> None:
    for file, mods in _imports(folder).items():
        bad = sorted(m for m in mods if m.startswith(prefixes))
        assert not bad, f"{file} must not import {bad}"


def test_domain_depends_on_nothing_of_ours_but_itself():
    _forbid(
        "domain",
        (
            "app.api",
            "app.db",
            "app.games",
            "app.services",
            "app.agent",
            "app.knowledge",
            "app.corpus",
            "sqlalchemy",
            "fastapi",
            "httpx",
        ),
    )


def test_services_and_agent_speak_to_ports_only():
    _forbid("services", ("app.api", "app.db", "app.knowledge.repository", "sqlalchemy", "fastapi"))
    _forbid("agent", ("app.api", "app.db", "app.knowledge.repository", "sqlalchemy", "fastapi"))


def test_only_the_composition_root_wires_implementations():
    files = _imports("api")
    for file, mods in files.items():
        if file.endswith("deps.py"):
            continue
        assert not any(
            m.startswith(("app.db.repository", "app.knowledge.repository")) for m in mods
        ), f"{file} must get stores from app.api.deps, not build them"
