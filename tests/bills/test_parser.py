import json
from pathlib import Path

import pytest

from logic.bills.extract.parser import BillNotExtractable, BillParser, field_hint
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


def test_parse_image_sends_one_image_block():
    payload = {"supplier_name": "SAGE PORTUGAL", "lines": []}
    client = _FakeAnthropic(payload)
    parser = BillParser(client, "claude-sonnet-4-6", _rule())
    bill = parser.parse_image("image/png", "QUJD")

    assert bill.supplier_name == "SAGE PORTUGAL"
    content = client.last_kwargs["messages"][0]["content"]
    images = [b for b in content if b["type"] == "image"]
    assert len(images) == 1
    assert images[0]["source"] == {"type": "base64", "media_type": "image/png",
                                   "data": "QUJD"}


def test_parse_image_includes_field_hint_text():
    client = _FakeAnthropic({"supplier_name": "X", "lines": []})
    parser = BillParser(client, "claude-sonnet-4-6", _rule())
    parser.parse_image("image/jpeg", "QUJD")
    texts = [b["text"] for b in client.last_kwargs["messages"][0]["content"]
             if b["type"] == "text"]
    assert any("issue_date" in t for t in texts)


def test_system_prompt_forbids_guessing_illegible_values():
    client = _FakeAnthropic({"supplier_name": "X", "lines": []})
    parser = BillParser(client, "claude-sonnet-4-6", _rule())
    parser.parse_image("image/jpeg", "QUJD")
    system = client.last_kwargs["system"].lower()
    assert "null" in system and "guess" in system


def test_both_paths_describe_their_own_source():
    client = _FakeAnthropic({"supplier_name": "X", "lines": []})
    parser = BillParser(client, "claude-sonnet-4-6", _rule())
    parser.parse([PageText(page=1, text="t")])
    text_system = client.last_kwargs["system"]
    parser.parse_image("image/jpeg", "QUJD")
    image_system = client.last_kwargs["system"]
    assert "OCR text" in text_system
    assert "photograph" in image_system


def test_parse_image_extracts_buyer_tax_id_separately():
    payload = {"supplier_name": "VODAFONE PORTUGAL", "supplier_tax_id": "502544180",
               "buyer_tax_id": "514380802", "lines": []}
    parser = BillParser(_FakeAnthropic(payload), "claude-sonnet-4-6", _rule())
    bill = parser.parse_image("image/jpeg", "QUJD")
    assert bill.supplier_tax_id == "502544180"
    assert bill.buyer_tax_id == "514380802"


def test_buyer_tax_id_defaults_to_none_when_absent():
    parser = BillParser(_FakeAnthropic({"supplier_name": "X", "lines": []}),
                        "claude-sonnet-4-6", _rule())
    assert parser.parse_image("image/jpeg", "QUJD").buyer_tax_id is None


def test_system_prompt_disambiguates_the_two_tax_ids():
    client = _FakeAnthropic({"supplier_name": "X", "lines": []})
    parser = BillParser(client, "claude-sonnet-4-6", _rule())
    parser.parse_image("image/jpeg", "QUJD")
    system = client.last_kwargs["system"]
    assert "buyer_tax_id" in system
    # The issuer's number is often footer-only on Portuguese invoices.
    assert "footer" in system.lower()
    # The label alone is not decisive — both parties can carry "Contribuinte".
    assert "label" in system.lower()


@pytest.mark.parametrize("name", [None, "", "   "])
def test_illegible_supplier_name_raises_a_runtime_error_not_validation_error(name):
    # The prompt tells the model to return null rather than guess, and an
    # illegible letterhead on a desk photo is exactly that case. pydantic's
    # ValidationError is not a RuntimeError, so app.py would miss it and the
    # operator would get a bare 500 instead of a readable 400.
    parser = BillParser(_FakeAnthropic({"supplier_name": name, "lines": []}),
                        "claude-sonnet-4-6", _rule())
    with pytest.raises(BillNotExtractable) as exc:
        parser.parse_image("image/jpeg", "QUJD")
    assert isinstance(exc.value, RuntimeError)
    assert "supplier_name" in str(exc.value)


def test_illegible_supplier_name_fails_the_text_path_the_same_way():
    parser = BillParser(_FakeAnthropic({"supplier_name": None, "lines": []}),
                        "claude-sonnet-4-6", _rule())
    with pytest.raises(BillNotExtractable):
        parser.parse([PageText(page=1, text="t")])


def test_supplier_name_is_stripped():
    parser = BillParser(_FakeAnthropic({"supplier_name": "  ACME LDA \n", "lines": []}),
                        "claude-sonnet-4-6", _rule())
    assert parser.parse_image("image/jpeg", "QUJD").supplier_name == "ACME LDA"


def test_tax_id_rule_reaches_the_text_path_too():
    client = _FakeAnthropic({"supplier_name": "X", "lines": []})
    parser = BillParser(client, "claude-sonnet-4-6", _rule())
    parser.parse([PageText(page=1, text="t")])
    assert "buyer_tax_id" in client.last_kwargs["system"]
