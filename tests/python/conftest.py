import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

SCHEMAS = ROOT / "schemas"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def fixtures() -> Path:
    return FIXTURES


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def quadratic_problem() -> dict:
    return load_fixture("problem_quadratic.json")


@pytest.fixture(scope="session")
def quadratic_answer() -> dict:
    return load_fixture("answer_quadratic.json")


@pytest.fixture(scope="session")
def geometry_problem() -> dict:
    return load_fixture("problem_geometry.json")


@pytest.fixture(scope="session")
def geometry_diagram() -> dict:
    return load_fixture("diagram_geometry.json")
