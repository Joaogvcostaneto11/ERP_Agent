from __future__ import annotations
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

_engine = None
_SessionLocal = None


def _get_session_factory():
    global _engine, _SessionLocal
    if _engine is None:
        url = os.environ["DATABASE_URL"]
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
        )
        _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    return _SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = _get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
