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


def test_write_session_rollback_on_exception(monkeypatch, tmp_path):
    db_url = f"sqlite:///{tmp_path / 'rb.db'}"
    monkeypatch.setenv("DEVCARE_WRITE_DATABASE_URL", db_url)
    devcare_connection._engine = None
    devcare_connection._SessionLocal = None

    from sqlalchemy import create_engine, text

    # Create the temp table before the test session so it exists in the DB file.
    setup_engine = create_engine(db_url)
    with setup_engine.connect() as conn:
        conn.execute(text("CREATE TABLE tmp_items (id INTEGER PRIMARY KEY)"))
        conn.commit()
    setup_engine.dispose()

    # Attempt an insert inside get_write_session, then raise to trigger rollback.
    with pytest.raises(ValueError, match="boom"):
        with devcare_connection.get_write_session() as s:
            s.execute(text("INSERT INTO tmp_items (id) VALUES (1)"))
            raise ValueError("boom")

    # Open a fresh connection and verify the row was NOT persisted.
    check_engine = create_engine(db_url)
    with check_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM tmp_items")).scalar()
    check_engine.dispose()
    assert count == 0
