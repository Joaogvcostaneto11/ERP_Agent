from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

# Portaria 195/2020 field keys. Bases are the taxable amounts per rate; the
# mainland (I), Açores (J) and Madeira (K) blocks share the same layout.
_BASE_KEYS = tuple(f"{region}{n}" for region in "IJK" for n in (2, 3, 5, 7)) + ("L",)


class AtQr(BaseModel):
    supplier_tax_id: str | None = None
    buyer_tax_id: str | None = None
    doc_type: str | None = None
    status: str | None = None
    issue_date: date | None = None
    number: str | None = None
    net_total: Decimal | None = None
    vat_total: Decimal | None = None
    gross_total: Decimal | None = None


def _fields(payload: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in payload.split("*"):
        key, sep, value = token.partition(":")
        if sep:  # tokens without a colon are skipped, not an error
            out[key.strip()] = value.strip()
    return out


def _decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _net(fields: dict[str, str], vat: Decimal | None,
         gross: Decimal | None) -> Decimal | None:
    bases = [d for k in _BASE_KEYS if (d := _decimal(fields.get(k))) is not None]
    if bases:
        return sum(bases, Decimal("0"))
    if gross is not None and vat is not None:
        return gross - vat
    return None


def parse(payload: str) -> AtQr | None:
    """Read a Portuguese AT invoice QR payload.

    Returns None for anything that is not one. A and O together are what
    distinguish an AT invoice code from any other QR that might be on the page —
    a URL, a payment code, a logo watermark.

    Unlike the vision model, this cannot misread a digit: the payload is emitted
    by certified invoicing software, so where it and the model disagree, it wins.
    """
    if not payload:
        return None
    fields = _fields(payload)
    if "A" not in fields or "O" not in fields:
        return None

    vat = _decimal(fields.get("N"))
    gross = _decimal(fields.get("O"))
    try:
        issued = datetime.strptime(fields["F"], "%Y%m%d").date() if "F" in fields else None
    except ValueError:
        issued = None

    return AtQr(
        supplier_tax_id=fields.get("A") or None,
        buyer_tax_id=fields.get("B") or None,
        doc_type=fields.get("D") or None,
        status=fields.get("E") or None,
        issue_date=issued,
        number=fields.get("G") or None,
        net_total=_net(fields, vat, gross),
        vat_total=vat,
        gross_total=gross,
    )
