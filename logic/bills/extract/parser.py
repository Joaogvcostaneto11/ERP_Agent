from __future__ import annotations
import json
import re
from typing import Any

from pydantic import ValidationError

from logic.bills.models import Bill, PageText
from logic.bills.rules.models import PurchaseInvoiceRule


class BillNotExtractable(RuntimeError):
    """The model read the page but could not produce a usable Bill — typically
    an illegible letterhead, where the prompt's null-over-guess instruction
    correctly returns null for a required field. A RuntimeError so app.py turns
    it into a 400 the operator can act on, not a bare 500."""

_SYSTEM_HEAD = "You extract structured data from a supplier invoice. "
_TEXT_SOURCE = "You are given the raw OCR text of the invoice pages. "
_IMAGE_SOURCE = "You are given a photograph or scan of the invoice. "
_SYSTEM_TAIL = (
    "Return ONLY a JSON object with these keys: "
    "supplier_name, supplier_tax_id, buyer_tax_id, number, issue_date (YYYY-MM-DD), due_date "
    "(YYYY-MM-DD), currency, net_total, vat_total, gross_total, and lines (a list "
    "of objects with description, quantity, unit_price, vat_rate, total). Use null "
    "for anything not present. Amounts as decimal strings without currency symbols. "
    "vat_rate as a plain number without a percent sign (e.g. \"23\", not \"23%\"). "
    "Do not invent values. If a digit or field is not clearly legible, return null "
    "for it rather than guessing a plausible value."
)

_TAX_ID_RULE = (
    " This invoice was issued BY a supplier TO a buyer, so two tax numbers usually appear "
    "on the page. supplier_tax_id must be the ISSUER's — the company whose logo and address "
    "head the document. buyer_tax_id is the recipient's. Decide which number belongs to "
    "which party by whose address block it sits in, not by its label alone: the same label "
    "(Contribuinte, NIF, NIPC) appears next to either party depending on the invoice. On "
    "Portuguese invoices the issuer's number is often printed only in the footer, beside "
    "NIPC, Contribuinte, IVA, or a commercial-registry line — look there before returning "
    "null. Never put the buyer's number in supplier_tax_id. If only one tax number is "
    "visible, decide which party it belongs to and leave the other null."
)


def _system(source: str) -> str:
    return _SYSTEM_HEAD + source + _SYSTEM_TAIL + _TAX_ID_RULE


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

    def _complete(self, content: Any, system: str) -> Bill:
        resp = self._client.messages.create(
            model=self._model, max_tokens=2048, temperature=0,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(getattr(c, "text", "") for c in resp.content
                       if getattr(c, "type", None) == "text")
        try:
            return Bill.model_validate(_extract_json(text))
        except ValidationError as e:
            fields = ", ".join(sorted({".".join(str(p) for p in err["loc"])
                                       for err in e.errors()}))
            raise BillNotExtractable(
                f"could not read these fields from the invoice: {fields} — "
                "retake the photo or enter them manually") from e

    def parse(self, pages: list[PageText]) -> Bill:
        joined = "\n\n".join(f"--- page {p.page} ---\n{p.text}" for p in pages)
        user = f"{field_hint(self._rule)}\n\nOCR TEXT:\n{joined}"
        return self._complete(user, _system(_TEXT_SOURCE))

    def parse_image(self, media_type: str, b64: str) -> Bill:
        content = [
            {"type": "image",
             "source": {"type": "base64", "media_type": media_type, "data": b64}},
            {"type": "text", "text": field_hint(self._rule)},
        ]
        return self._complete(content, _system(_IMAGE_SOURCE))
