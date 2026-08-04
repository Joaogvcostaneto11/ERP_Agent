from __future__ import annotations
import json
import re
from typing import Any

from logic.bills.models import Bill, PageText
from logic.bills.rules.models import PurchaseInvoiceRule

_SYSTEM = (
    "You extract structured data from a supplier invoice. You are given the raw "
    "OCR text of the invoice pages. Return ONLY a JSON object with these keys: "
    "supplier_name, supplier_tax_id, number, issue_date (YYYY-MM-DD), due_date "
    "(YYYY-MM-DD), currency, net_total, vat_total, gross_total, and lines (a list "
    "of objects with description, quantity, unit_price, vat_rate, total). Use null "
    "for anything not present. Amounts as decimal strings without currency symbols. "
    "vat_rate as a plain number without a percent sign (e.g. \"23\", not \"23%\"). "
    "Do not invent values."
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def field_hint(rule: PurchaseInvoiceRule) -> str:
    def _out_names(fields) -> str:
        names = [fr.source.split(".", 1)[1]
                 for fr in fields.values()
                 if not fr.source.endswith(".match")]
        return ", ".join(names)
    header = _out_names(rule.header.fields)
    lines = _out_names(rule.lines.fields)
    return f"Header fields: {header}. Line fields: {lines}."


def _extract_json(text: str) -> dict[str, Any]:
    m = _JSON_RE.search(text)
    if not m:
        raise ValueError("model returned no JSON object")
    return json.loads(m.group(0))


class BillParser:
    def __init__(self, anthropic_client: Any, model: str,
                 rule: PurchaseInvoiceRule) -> None:
        self._client = anthropic_client
        self._model = model
        self._rule = rule

    def parse(self, pages: list[PageText]) -> Bill:
        joined = "\n\n".join(f"--- page {p.page} ---\n{p.text}" for p in pages)
        user = f"{field_hint(self._rule)}\n\nOCR TEXT:\n{joined}"
        resp = self._client.messages.create(
            model=self._model, max_tokens=2048, temperature=0,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(getattr(c, "text", "") for c in resp.content
                       if getattr(c, "type", None) == "text")
        return Bill.model_validate(_extract_json(text))
