from datetime import date
from decimal import Decimal

import pytest

from logic.bills.extract.at_qr import parse

SAGE = ("A:502667583*B:514380802*C:PT*D:FT*E:N*F:20260805*"
        "G:FCL FCL-P26/029346*H:J6FHJGSV-029346*I1:PT*I7:2058.72*I8:473.51*"
        "N:473.51*O:2532.23*Q:J6YV*R:213")


def test_parse_separates_issuer_from_buyer():
    # The whole point of the feature: A is the supplier, B is the buyer, and no
    # layout or label heuristic is involved.
    qr = parse(SAGE)
    assert qr.supplier_tax_id == "502667583"
    assert qr.buyer_tax_id == "514380802"


def test_parse_reads_header_fields():
    qr = parse(SAGE)
    assert qr.number == "FCL FCL-P26/029346"
    assert qr.issue_date == date(2026, 8, 5)
    assert qr.doc_type == "FT"
    assert qr.status == "N"


def test_parse_reads_totals():
    qr = parse(SAGE)
    assert qr.gross_total == Decimal("2532.23")
    assert qr.vat_total == Decimal("473.51")
    # net comes from the taxable bases, here the single normal-rate base I7
    assert qr.net_total == Decimal("2058.72")


def test_parse_sums_multiple_taxable_bases():
    payload = ("A:502667583*B:514380802*D:FT*E:N*F:20260805*G:FT 1/1*"
               "I3:100.00*I4:6.00*I7:200.00*I8:46.00*L:10.00*"
               "N:52.00*O:362.00")
    assert parse(payload).net_total == Decimal("310.00")  # 100 + 200 + 10


def test_parse_falls_back_to_gross_minus_vat_when_no_bases_present():
    payload = "A:502667583*D:FT*E:N*F:20260805*G:FT 1/1*N:23.00*O:123.00"
    assert parse(payload).net_total == Decimal("100.00")


def test_parse_ignores_unknown_fields():
    # The format permits fields we do not consume; they must not break decoding.
    payload = SAGE + "*Z9:something-new*ZZ:more"
    assert parse(payload).supplier_tax_id == "502667583"


@pytest.mark.parametrize("payload", [
    "",
    "just some text",
    "https://example.com/not-an-invoice",
    "A:502667583",          # has A but no O
    "O:123.00",             # has O but no A
])
def test_parse_rejects_non_at_payloads(payload):
    assert parse(payload) is None


def test_parse_survives_malformed_pairs():
    # A stray token with no colon must not raise.
    payload = "A:502667583*garbage*O:123.00*N:23.00*F:20260805"
    qr = parse(payload)
    assert qr is not None and qr.supplier_tax_id == "502667583"


def test_parse_returns_none_for_an_unparseable_date_but_keeps_the_rest():
    payload = "A:502667583*O:123.00*N:23.00*F:notadate*G:FT 1/1"
    qr = parse(payload)
    assert qr is not None
    assert qr.issue_date is None
    assert qr.number == "FT 1/1"
