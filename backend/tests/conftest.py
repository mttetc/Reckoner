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
