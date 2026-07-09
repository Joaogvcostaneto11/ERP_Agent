from decimal import Decimal
from pathlib import Path
from logic.bills.matching import Matcher
from logic.bills.models import Bill, BillLine
from logic.bills.rules.loader import RuleLoader

RULES_DIR = Path(__file__).resolve().parents[2] / "business_rules" / "bills"


class FakeReader:
    """Answers by inspecting bound params, not SQL text."""
    def __init__(self, entidades=None, artigos=None):
        self._ents = entidades or []
        self._arts = artigos or []

    def __call__(self, sql, params):
        p = params or {}
        if "Entidades" in sql:
            if "NCont" in sql and "tax_id" in p:
                return [r for r in self._ents if r["NCont"] == p["tax_id"]]
            if "name" in p:
                needle = p["name"].strip("%").lower()
                return [r for r in self._ents if needle in r["Nome"].lower()]
        if "Artigos" in sql:
            needle = (p.get("name") or "").strip("%").lower()
            return [r for r in self._arts if needle and needle in r["Nome"].lower()]
        return []


def _rule():
    return RuleLoader(RULES_DIR).rule()


def _bill(**kw):
    return Bill(supplier_name=kw.get("supplier_name", "ACME"),
               supplier_tax_id=kw.get("supplier_tax_id"))


def test_supplier_matched_by_tax_id():
    reader = FakeReader(entidades=[{"Chave": 7, "Nome": "ACME LDA", "NCont": "500100200"}])
    m = Matcher(reader, _rule())
    res = m.match_supplier(_bill(supplier_tax_id="500100200"))
    assert res.status == "matched" and res.chave == 7


def test_supplier_ambiguous_by_name():
    reader = FakeReader(entidades=[{"Chave": 1, "Nome": "ACME LDA", "NCont": "x"},
                                   {"Chave": 2, "Nome": "ACME PORTO", "NCont": "y"}])
    m = Matcher(reader, _rule())
    res = m.match_supplier(_bill(supplier_name="ACME"))
    assert res.status == "ambiguous" and len(res.candidates) == 2


def test_supplier_new_when_no_match():
    m = Matcher(FakeReader(), _rule())
    res = m.match_supplier(_bill(supplier_name="Nobody", supplier_tax_id="999888777"))
    assert res.status == "new"
    assert res.proposed_new["Nome"] == "Nobody"
    assert res.proposed_new["NCont"] == "999888777"


def test_line_new_when_no_article_match():
    m = Matcher(FakeReader(), _rule())
    res = m.match_line(BillLine(description="Mystery Widget"))
    assert res.status == "new" and res.proposed_new["Nome"] == "Mystery Widget"


def test_line_matched_by_name():
    reader = FakeReader(artigos=[{"Chave": 42, "Nome": "Widget", "Codigo": "W1"}])
    m = Matcher(reader, _rule())
    res = m.match_line(BillLine(description="Widget"))
    assert res.status == "matched" and res.chave == 42
