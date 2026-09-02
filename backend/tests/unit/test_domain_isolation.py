"""SPEC § 8 / § 3.14: the common domain must contain no game-specific assumptions."""

import re
from pathlib import Path

DOMAIN = Path(__file__).resolve().parents[2] / "app" / "domain"
FORBIDDEN = re.compile(
    r"\b(pob|PathOfBuilding|Path of Building|ascendanc\w*|divine|maxroll|mobalytics|"
    r"leaderboard|greater rift|app\.games)\b",
    re.IGNORECASE,
)


def test_domain_has_no_game_specific_code():
    offenders = []
    for py in DOMAIN.glob("*.py"):
        for lineno, line in enumerate(py.read_text().splitlines(), 1):
            if FORBIDDEN.search(line):
                offenders.append(f"{py.name}:{lineno}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


def test_domain_never_imports_adapters():
    for py in DOMAIN.glob("*.py"):
        assert "from app.games" not in py.read_text(), py.name
        assert "import app.games" not in py.read_text(), py.name
