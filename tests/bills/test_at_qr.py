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


@pytest.mark.parametrize("payload", [
    "A:502667583*D:FT*E:N*F:20260805*G:FT 1/1*N:23.00*O:nan",
    "A:502667583*D:FT*E:N*F:20260805*G:FT 1/1*N:23.00*O:Infinity",
    "A:502667583*D:FT*E:N*F:20260805*G:FT 1/1*N:inf*O:123.00",
])
def test_parse_does_not_raise_for_a_non_finite_amount(payload):
    # Decimal() happily accepts "nan"/"Infinity"/"inf", but pydantic's Decimal
    # field rejects non-finite values with a ValidationError — which is not a
    # RuntimeError and would otherwise escape app.py's guard as a 500. A QR
    # this malformed must degrade to "field absent", never break the upload.
    qr = parse(payload)
    assert qr is not None


def test_parse_treats_a_non_finite_taxable_base_as_absent_from_net():
    # I3 is a taxable-base field consumed via _net(), a different code path
    # from the top-level N/O fields above.
    payload = "A:502667583*D:FT*E:N*F:20260805*G:FT 1/1*I3:nan*N:23.00*O:123.00"
    qr = parse(payload)
    assert qr is not None
    # the nan base is dropped, so net falls back to gross - vat
    assert qr.net_total == Decimal("100.00")


from logic.bills.extract.at_qr import merge
from logic.bills.models import Bill, BillLine


def _vision_bill(**over) -> Bill:
    base = dict(supplier_name="SAGE PORTUGAL", supplier_tax_id="502267583",
                buyer_tax_id="514380802", number="FCL FCL-P26/029346",
                issue_date=date(2026, 8, 5), net_total=Decimal("2058.72"),
                vat_total=Decimal("473.51"), gross_total=Decimal("2532.23"),
                lines=[BillLine(description="SubA Accountants", total=Decimal("1998.62"))])
    base.update(over)
    return Bill(**base)


def test_merge_overwrites_the_misread_supplier_nif():
    # This is the real defect from the previous cycle: vision read 502267583
    # where the invoice says 502667583.
    merged, _ = merge(_vision_bill(), parse(SAGE))
    assert merged.supplier_tax_id == "502667583"


def test_merge_warns_when_the_qr_contradicts_the_model():
    _, warnings = merge(_vision_bill(), parse(SAGE))
    assert any("502267583" in w and "502667583" in w for w in warnings)


def test_merge_is_silent_when_the_model_already_agreed():
    _, warnings = merge(_vision_bill(supplier_tax_id="502667583"), parse(SAGE))
    assert warnings == []


def test_merge_keeps_line_items_untouched():
    # The QR carries no line detail, so vision's lines must survive.
    merged, _ = merge(_vision_bill(), parse(SAGE))
    assert len(merged.lines) == 1
    assert merged.lines[0].description == "SubA Accountants"


def test_merge_fills_a_field_the_model_left_null_without_warning():
    merged, warnings = merge(_vision_bill(supplier_tax_id=None), parse(SAGE))
    assert merged.supplier_tax_id == "502667583"
    assert warnings == []  # filling a gap is not a disagreement


def test_merge_leaves_a_field_alone_when_the_qr_lacks_it():
    qr = parse("A:502667583*O:2532.23*N:473.51")
    merged, _ = merge(_vision_bill(), qr)
    assert merged.number == "FCL FCL-P26/029346"


def test_merge_warns_loudly_about_a_cancelled_document():
    qr = parse(SAGE.replace("*E:N*", "*E:A*"))
    _, warnings = merge(_vision_bill(), qr)
    assert any("cancel" in w.lower() for w in warnings)


def test_merge_warns_about_a_non_invoice_document_type():
    qr = parse(SAGE.replace("*D:FT*", "*D:NC*"))
    _, warnings = merge(_vision_bill(), qr)
    assert any("NC" in w for w in warnings)


def test_merge_does_not_warn_for_ordinary_invoice_types():
    for doc_type in ("FT", "FS", "FR"):
        qr = parse(SAGE.replace("*D:FT*", f"*D:{doc_type}*"))
        _, warnings = merge(_vision_bill(supplier_tax_id="502667583"), qr)
        assert warnings == [], f"{doc_type} should not warn"


def test_merge_does_not_mutate_the_original_bill():
    original = _vision_bill()
    merge(original, parse(SAGE))
    assert original.supplier_tax_id == "502267583"
