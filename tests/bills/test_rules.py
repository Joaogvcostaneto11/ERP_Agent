from pathlib import Path
from logic.bills.rules.loader import RuleLoader

RULES_DIR = Path(__file__).resolve().parents[2] / "business_rules" / "bills"


def test_loads_purchase_invoice_rule():
    rule = RuleLoader(RULES_DIR).rule()
    assert rule.document == "purchase_invoice"
    assert rule.header.table in ("Doc001", "FO")
    assert rule.header.tipo_doc.code
    assert rule.header.fields["total"].required is True
    assert rule.header.fields["total"].column == "Total"
    assert rule.lines.parent_fk == "Documento"
    assert rule.matching.supplier.create is True
    assert "tax_id" in rule.matching.supplier.match_on
