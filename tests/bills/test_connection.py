import pytest
import db.bills_connection as bc


def test_missing_env_raises(monkeypatch):
    monkeypatch.delenv("BILLS_WRITE_DATABASE_URL", raising=False)
    bc._engine = None
    bc._SessionLocal = None
    with pytest.raises(RuntimeError, match="BILLS_WRITE_DATABASE_URL"):
        with bc.get_bills_write_session():
            pass
