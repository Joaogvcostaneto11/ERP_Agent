import json
from pathlib import Path
from logic.bills.extract.parser import BillParser, field_hint
from logic.bills.models import PageText
from logic.bills.rules.loader import RuleLoader

RULES_DIR = Path(__file__).resolve().parents[2] / "business_rules" / "bills"


class _FakeContent:
    def __init__(self, text): self.type = "text"; self.text = text


class _FakeResponse:
    def __init__(self, text): self.content = [_FakeContent(text)]


class _FakeAnthropic:
    def __init__(self, payload): self._payload = payload; self.messages = self
    def create(self, **kw):
        self.last_kwargs = kw
        return _FakeResponse(json.dumps(self._payload))


def _rule():
    return RuleLoader(RULES_DIR).rule()


def test_field_hint_lists_expected_fields():
    hint = field_hint(_rule())
    assert "issue_date" in hint and "gross_total" in hint and "description" in hint


def test_parse_returns_bill_from_model_json():
    payload = {"supplier_name": "ACME LDA", "supplier_tax_id": "500100200",
               "number": "FT 2026/17", "issue_date": "2026-06-01",
               "net_total": "100.00", "vat_total": "23.00", "gross_total": "123.00",
               "lines": [{"description": "Widget", "quantity": "2",
                          "unit_price": "50.00", "vat_rate": "23", "total": "100.00"}]}
    client = _FakeAnthropic(payload)
    parser = BillParser(client, "claude-sonnet-4-6", _rule())
    bill = parser.parse([PageText(page=1, text="raw ocr text")])
    assert bill.supplier_name == "ACME LDA"
    assert str(bill.gross_total) == "123.00"
    assert len(bill.lines) == 1 and bill.lines[0].description == "Widget"
    # OCR text is passed to the model
    assert "raw ocr text" in json.dumps(client.last_kwargs["messages"], default=str)


def test_parse_tolerates_json_wrapped_in_prose():
    payload = {"supplier_name": "X", "lines": []}
    text = "Here is the data:\n```json\n" + json.dumps(payload) + "\n```"

    class Wrapped(_FakeAnthropic):
        def create(self, **kw):
            return _FakeResponse(text)

    parser = BillParser(Wrapped({}), "claude-sonnet-4-6", _rule())
    bill = parser.parse([PageText(page=1, text="t")])
    assert bill.supplier_name == "X"
