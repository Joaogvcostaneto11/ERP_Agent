from decimal import Decimal
from logic.bills.models import Bill, BillLine, arithmetic_warnings


def _bill(**kw):
    base = dict(supplier_name="ACME", net_total=Decimal("100"),
                vat_total=Decimal("23"), gross_total=Decimal("123"),
                lines=[BillLine(description="X", quantity=Decimal("1"),
                                unit_price=Decimal("100"), vat_rate=Decimal("23"),
                                total=Decimal("100"))])
    base.update(kw)
    return Bill(**base)


def test_no_warning_when_totals_consistent():
    assert arithmetic_warnings(_bill()) == []


def test_warning_when_gross_mismatches_net_plus_vat():
    warnings = arithmetic_warnings(_bill(gross_total=Decimal("200")))
    assert any("gross" in w.lower() for w in warnings)


def test_warning_when_line_totals_do_not_sum_to_net():
    b = _bill(lines=[BillLine(description="X", total=Decimal("40"))])
    warnings = arithmetic_warnings(b)
    assert any("line" in w.lower() for w in warnings)


def test_missing_totals_produce_no_arithmetic_warning():
    b = _bill(net_total=None, vat_total=None, gross_total=None,
              lines=[BillLine(description="X")])
    assert arithmetic_warnings(b) == []


def test_vat_rate_strips_percent_sign():
    # The model routinely emits "23%" despite the prompt; keep the numeric value.
    assert BillLine(description="X", vat_rate="23%").vat_rate == Decimal("23")
    assert BillLine(description="X", vat_rate=" 23 % ").vat_rate == Decimal("23")
    assert BillLine(description="X", vat_rate=None).vat_rate is None
