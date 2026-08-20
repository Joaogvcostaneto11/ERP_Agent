from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from logic.bills.models import LinePlan, MatchResult, WritePlan
from logic.bills.rules.loader import RuleLoader
from logic.bills.write_executor import BillWriteExecutor

RULES_DIR = Path(__file__).resolve().parents[2] / "business_rules" / "bills"


@pytest.fixture
def session_factory(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path/'w.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE TiposDoc (Chave INTEGER, Codigo TEXT)"))
        c.execute(text("INSERT INTO TiposDoc (Chave, Codigo) VALUES (5, '31')"))
        c.execute(text("CREATE TABLE Entidades (Chave INTEGER, Nome TEXT, NCont TEXT, "
                       "Tipo INTEGER, Listar INTEGER, DC TEXT, OC INTEGER)"))
        c.execute(text("INSERT INTO Entidades (Chave, Nome) VALUES (7, 'Existing Supplier')"))
        c.execute(text("CREATE TABLE Artigos (Chave INTEGER, Nome TEXT, Codigo TEXT, "
                       "DC TEXT, OC INTEGER)"))
        c.execute(text("CREATE TABLE Doc001 (Chave INTEGER, TipoDoc INTEGER, Entidade INTEGER, "
                       "Data TEXT, Vencimento TEXT, VRef TEXT, Iliquido NUMERIC, IVA NUMERIC, "
                       "Total NUMERIC, Obs TEXT, Estado INTEGER, ATCUD TEXT, CodigoAT TEXT, "
                       "Certificacao TEXT, DC TEXT, OC INTEGER)"))
        c.execute(text("CREATE TABLE LinDoc001 (Chave INTEGER, Documento INTEGER, "
                       "ChaveProd INTEGER, Descricao TEXT, Quantidade NUMERIC, "
                       "Punit NUMERIC, Iva NUMERIC, Valor NUMERIC)"))
    Local = sessionmaker(bind=eng)

    @contextmanager
    def factory():
        s = Local()
        try:
            yield s; s.commit()
        except Exception:
            s.rollback(); raise
        finally:
            s.close()
    return factory, eng


def _rule():
    return RuleLoader(RULES_DIR).rule()


def _ex(factory):
    return BillWriteExecutor(factory, table_prefix="",
                             now=lambda: "2026-07-08T00:00:00Z", operator_key=0)


def _plan_matched_supplier():
    return WritePlan(
        proposal_id="p1",
        supplier=MatchResult(status="matched", chave=7),
        header={"Data": "2026-06-01", "VRef": "FT 2026/17",
                "Iliquido": "100", "IVA": "23", "Total": "123", "Obs": ""},
        lines=[LinePlan(article=MatchResult(status="matched", chave=42),
                        columns={"Descricao": "Widget", "Quantidade": "2",
                                 "Punit": "50", "Iva": "23", "Valor": "100"})],
        rule_doc="purchase_invoice", rule_version=1)


def test_commit_matched_supplier_and_article(session_factory):
    factory, eng = session_factory
    with eng.begin() as c:
        c.execute(text("INSERT INTO Artigos (Chave, Nome) VALUES (42, 'Widget')"))
    result = _ex(factory).execute(_plan_matched_supplier(), _rule(), operator="test", audit=NullAudit())
    with eng.begin() as c:
        doc = c.execute(text("SELECT * FROM Doc001")).fetchone()
        line = c.execute(text("SELECT * FROM LinDoc001")).fetchone()
    assert result["supplier_chave"] == 7 and result["created_supplier"] is False
    assert doc.Entidade == 7 and doc.TipoDoc == 5 and doc.Estado == 0
    assert doc.ATCUD == "" and doc.Total == 123
    assert line.Documento == result["document_chave"] and line.ChaveProd == 42


def test_commit_creates_new_supplier_and_article(session_factory):
    factory, eng = session_factory
    plan = WritePlan(
        proposal_id="p2",
        supplier=MatchResult(status="new", confirmed=True,
                             proposed_new={"Nome": "New Co", "NCont": "500999999"}),
        header={"Data": "2026-06-01", "VRef": "A1", "Iliquido": "10", "IVA": "2",
                "Total": "12", "Obs": ""},
        lines=[LinePlan(article=MatchResult(status="new", confirmed=True,
                                            proposed_new={"Nome": "New Item"}),
                        columns={"Descricao": "New Item", "Quantidade": "1",
                                 "Punit": "10", "Iva": "23", "Valor": "10"})],
        rule_doc="purchase_invoice", rule_version=1)
    result = _ex(factory).execute(plan, _rule(), operator="test", audit=NullAudit())
    with eng.begin() as c:
        sup = c.execute(text("SELECT Chave, Nome, NCont, Tipo FROM Entidades WHERE Nome='New Co'")).fetchone()
        art = c.execute(text("SELECT Chave, Nome FROM Artigos WHERE Nome='New Item'")).fetchone()
        doc = c.execute(text("SELECT Entidade FROM Doc001")).fetchone()
    assert result["created_supplier"] is True and sup is not None
    assert doc.Entidade == sup.Chave
    assert art.Chave in result["created_articles"]


def test_unconfirmed_new_supplier_is_rejected_and_nothing_written(session_factory):
    factory, eng = session_factory
    plan = _plan_matched_supplier()
    plan.supplier = MatchResult(status="new", confirmed=False,
                                proposed_new={"Nome": "X"})
    with pytest.raises(ValueError, match="not resolvable"):
        _ex(factory).execute(plan, _rule(), operator="test", audit=NullAudit())
    with eng.begin() as c:
        assert c.execute(text("SELECT COUNT(*) FROM Doc001")).scalar() == 0


def test_unknown_header_column_is_rejected_and_nothing_written(session_factory):
    factory, eng = session_factory
    plan = _plan_matched_supplier()
    plan.header["Bogus"] = "x"
    with pytest.raises(ValueError, match="Bogus"):
        _ex(factory).execute(plan, _rule(), operator="test", audit=NullAudit())
    with eng.begin() as c:
        assert c.execute(text("SELECT COUNT(*) FROM Doc001")).scalar() == 0


def test_two_new_articles_get_distinct_keys(session_factory):
    factory, eng = session_factory
    plan = WritePlan(
        proposal_id="p3",
        supplier=MatchResult(status="matched", chave=7),
        header={"Data": "2026-06-01", "VRef": "A2", "Iliquido": "20", "IVA": "4",
                "Total": "24", "Obs": ""},
        lines=[
            LinePlan(article=MatchResult(status="new", confirmed=True,
                                         proposed_new={"Nome": "Item A"}),
                     columns={"Descricao": "Item A", "Quantidade": "1",
                              "Punit": "10", "Iva": "23", "Valor": "10"}),
            LinePlan(article=MatchResult(status="new", confirmed=True,
                                         proposed_new={"Nome": "Item B"}),
                     columns={"Descricao": "Item B", "Quantidade": "1",
                              "Punit": "10", "Iva": "23", "Valor": "10"}),
        ],
        rule_doc="purchase_invoice", rule_version=1)
    result = _ex(factory).execute(plan, _rule(), operator="test", audit=NullAudit())
    assert len(set(result["created_articles"])) == 2
    with eng.begin() as c:
        chaves = [r[0] for r in c.execute(text("SELECT Chave FROM Artigos")).fetchall()]
    assert len(set(chaves)) == len(chaves) == 2


def test_unconfirmed_new_article_rolls_back_header(session_factory):
    factory, eng = session_factory
    plan = _plan_matched_supplier()
    plan.lines[0].article = MatchResult(status="new", confirmed=False,
                                        proposed_new={"Nome": "X"})
    with pytest.raises(ValueError, match="not resolvable"):
        _ex(factory).execute(plan, _rule(), operator="test", audit=NullAudit())
    with eng.begin() as c:
        assert c.execute(text("SELECT COUNT(*) FROM Doc001")).scalar() == 0
        assert c.execute(text("SELECT COUNT(*) FROM LinDoc001")).scalar() == 0


def test_rogue_proposed_new_key_is_rejected_and_nothing_written(session_factory):
    factory, eng = session_factory
    with eng.begin() as c:
        c.execute(text("INSERT INTO Artigos (Chave, Nome) VALUES (42, 'W')"))
    plan = WritePlan(
        proposal_id="pRogue",
        supplier=MatchResult(status="new", confirmed=True,
                             proposed_new={"Nome": "Evil", "Hist": 1}),  # Hist not in create_columns
        header={"Data": "2026-06-01", "VRef": "A", "Iliquido": "1", "IVA": "0",
                "Total": "1", "Obs": ""},
        lines=[LinePlan(article=MatchResult(status="matched", chave=42),
                        columns={"Descricao": "x", "Quantidade": "1", "Punit": "1",
                                 "Iva": "23", "Valor": "1"})],
        rule_doc="purchase_invoice", rule_version=1)
    with pytest.raises(ValueError, match="Hist"):
        _ex(factory).execute(plan, _rule(), operator="test", audit=NullAudit())
    with eng.begin() as c:
        assert c.execute(text("SELECT COUNT(*) FROM Doc001")).scalar() == 0
        assert c.execute(text("SELECT COUNT(*) FROM Entidades WHERE Nome='Evil'")).scalar() == 0


class RecordingAudit:
    """Captures whether the session was inside a transaction at call time."""
    def __init__(self):
        self.calls = []

    def insert(self, session, *, operator, plan, result, status):
        self.calls.append({"in_transaction": session.in_transaction(),
                           "operator": operator, "result": result, "status": status})


class ExplodingAudit:
    def insert(self, session, **kw):
        raise RuntimeError("audit unavailable")


class NullAudit:
    def insert(self, session, **kw):
        pass


def test_audit_is_written_inside_the_document_transaction(session_factory):
    factory, eng = session_factory
    with eng.begin() as c:
        c.execute(text("INSERT INTO Artigos (Chave, Nome) VALUES (42, 'Widget')"))
    audit = RecordingAudit()
    result = _ex(factory).execute(_plan_matched_supplier(), _rule(),
                                  operator="alice", audit=audit)
    assert len(audit.calls) == 1
    call = audit.calls[0]
    assert call["in_transaction"] is True
    assert call["operator"] == "alice"
    assert call["status"] == "ok"
    assert call["result"]["document_chave"] == result["document_chave"]


def test_a_failed_audit_rolls_the_document_back(session_factory):
    """The atomic guarantee stated as a test: if the audit row cannot be
    written, no document may survive. This is the whole point of putting the
    insert inside the transaction rather than after it."""
    factory, eng = session_factory
    with eng.begin() as c:
        c.execute(text("INSERT INTO Artigos (Chave, Nome) VALUES (42, 'Widget')"))
    with pytest.raises(RuntimeError):
        _ex(factory).execute(_plan_matched_supplier(), _rule(),
                             operator="alice", audit=ExplodingAudit())
    with eng.begin() as c:
        assert c.execute(text("SELECT COUNT(*) FROM Doc001")).scalar() == 0
        assert c.execute(text("SELECT COUNT(*) FROM LinDoc001")).scalar() == 0
