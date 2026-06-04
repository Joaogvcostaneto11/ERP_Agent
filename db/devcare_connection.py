from __future__ import annotations
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = None
_SessionLocal = None


def _factory():
    global _engine, _SessionLocal
    if _engine is None:
        url = os.environ.get("DEVCARE_WRITE_DATABASE_URL")
        if not url:
            raise RuntimeError("DEVCARE_WRITE_DATABASE_URL is not set")
        _engine = create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=5)
        _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    return _SessionLocal


@contextmanager
def get_write_session() -> Generator[Session, None, None]:
    session = _factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
