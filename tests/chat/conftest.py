from __future__ import annotations
from pathlib import Path
import pytest


@pytest.fixture
def tmp_log_path(tmp_path: Path) -> Path:
    return tmp_path / "queries.jsonl"
