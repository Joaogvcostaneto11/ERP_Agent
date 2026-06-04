# tests/devcare/test_connection.py
import os
import pytest
from db import devcare_connection


def test_missing_env_raises(monkeypatch):
    monkeypatch.delenv("DEVCARE_WRITE_DATABASE_URL", raising=False)
    devcare_connection._engine = None
    devcare_connection._SessionLocal = None
    with pytest.raises(RuntimeError, match="DEVCARE_WRITE_DATABASE_URL"):
        devcare_connection.get_write_session().__enter__()


def test_session_factory_uses_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("DEVCARE_WRITE_DATABASE_URL", f"sqlite:///{tmp_path/'w.db'}")
    devcare_connection._engine = None
    devcare_connection._SessionLocal = None
    from sqlalchemy import text
    with devcare_connection.get_write_session() as s:
        assert s.execute(text("SELECT 1")).scalar() == 1
