# tests/payroll/golden/conftest.py
from pathlib import Path
import pytest


SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def pytest_generate_tests(metafunc):
    if "scenario_dir" in metafunc.fixturenames:
        scenarios = sorted(p for p in SCENARIOS_DIR.iterdir() if p.is_dir())
        metafunc.parametrize("scenario_dir", scenarios, ids=lambda p: p.name)
