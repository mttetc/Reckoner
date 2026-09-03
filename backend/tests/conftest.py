from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "pob"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture(scope="session")
def code_legacy() -> str:
    return _load("elementalist_bv_2019.txt")


@pytest.fixture(scope="session")
def code_scion() -> str:
    return _load("scion_import_lvl1_2019.txt")


@pytest.fixture(scope="session")
def code_modern() -> str:
    return _load("slayer_lightning_strike_3_27.txt")


@pytest.fixture(scope="session")
def code_void_sphere() -> str:
    return _load("void_sphere_pathfinder_3_29.txt")


@pytest.fixture(scope="session")
def code_minions() -> str:
    return _load("srs_guardian_3_23.txt")


@pytest.fixture(scope="session")
def code_no_total_dps() -> str:
    return _load("ballista_chieftain_3_29.txt")


@pytest.fixture(scope="session")
def all_codes() -> list[tuple[str, str]]:
    return [(p.name, p.read_text()) for p in sorted(FIXTURES.glob("*.txt"))]
