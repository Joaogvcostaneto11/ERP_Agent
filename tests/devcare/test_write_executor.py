# tests/devcare/test_write_executor.py
from contextlib import contextmanager
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from logic.devcare.errors import NormalizedChange
from logic.devcare.rules.models import EntityRule
from logic.devcare.write_executor import WriteExecutor


@pytest.fixture
def session_factory(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path/'w.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE Especialidades "
                       "(Chave INTEGER, Codigo TEXT, Nome TEXT, Obs TEXT, "
                       "Hist INTEGER, Listar INTEGER, DC TEXT, OC INTEGER, "
                       "DUA TEXT, OUA INTEGER)"))
    Local = sessionmaker(bind=eng)

    @contextmanager
    def factory():
        s = Local()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()
    return factory, eng


def _rule():
    return EntityRule(
        entity="specialty", version=1, table="Especialidades",
        primary_key="Chave", operations=["create", "update", "delete"],
        soft_delete={"column": "Hist", "active_value": 0, "deleted_value": 1},
        audit_columns={"created_at": "DC", "updated_at": "DUA",
                       "created_by": "OC", "updated_by": "OUA"},
        create_defaults={"Listar": 1},
        fields={"code": {"column": "Codigo", "type": "string"},
                "name": {"column": "Nome", "type": "string"}},
    )


def _ex(factory):
    return WriteExecutor(factory, table_prefix="",
                         now=lambda: "2026-06-04T00:00:00Z", operator_key=0)


def test_create_generates_key_and_defaults(session_factory):
    factory, eng = session_factory
    ex = _ex(factory)
    change = NormalizedChange("specialty", "create", "Especialidades", "Chave",
                              {"Codigo": "Z9", "Nome": "Test"}, None)
    pk = ex.execute(_rule(), change)
    with eng.begin() as c:
        row = c.execute(text("SELECT Chave,Codigo,Nome,Hist,Listar,OC FROM Especialidades")).fetchone()
    assert row.Chave == pk == 1
    assert row.Codigo == "Z9" and row.Nome == "Test"
    assert row.Hist == 0 and row.Listar == 1 and row.OC == 0


def test_second_create_increments_key(session_factory):
    factory, eng = session_factory
    ex = _ex(factory)
    r = _rule()
    ex.execute(r, NormalizedChange("specialty", "create", "Especialidades", "Chave",
                                   {"Codigo": "A", "Nome": "A"}, None))
    pk2 = ex.execute(r, NormalizedChange("specialty", "create", "Especialidades", "Chave",
                                         {"Codigo": "B", "Nome": "B"}, None))
    assert pk2 == 2


def test_update_sets_only_given_columns(session_factory):
    factory, eng = session_factory
    ex = _ex(factory)
    r = _rule()
    ex.execute(r, NormalizedChange("specialty", "create", "Especialidades", "Chave",
                                   {"Codigo": "A", "Nome": "Old"}, None))
    ex.execute(r, NormalizedChange("specialty", "update", "Especialidades", "Chave",
                                   {"Nome": "New"}, target_pk=1))
    with eng.begin() as c:
        row = c.execute(text("SELECT Codigo,Nome,DUA FROM Especialidades")).fetchone()
    assert row.Codigo == "A" and row.Nome == "New" and row.DUA == "2026-06-04T00:00:00Z"


def test_soft_delete_sets_flag(session_factory):
    factory, eng = session_factory
    ex = _ex(factory)
    r = _rule()
    ex.execute(r, NormalizedChange("specialty", "create", "Especialidades", "Chave",
                                   {"Codigo": "A", "Nome": "A"}, None))
    ex.execute(r, NormalizedChange("specialty", "delete", "Especialidades", "Chave",
                                   {}, target_pk=1))
    with eng.begin() as c:
        hist = c.execute(text("SELECT Hist FROM Especialidades WHERE Chave=1")).scalar()
    assert hist == 1
