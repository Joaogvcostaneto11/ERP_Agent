from datetime import datetime, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError
from logic.payroll.public.schemas.output import (
    RuleCitation, AuditTrailEntry, PayslipLine, PayslipResult,
)


def test_rule_citation_valid():
    c = RuleCitation(
        document_path="business_rules/payroll/statutory_pt.yaml",
        layer="statutory",
        component_code="base_salary",
        clause="components.base_salary",
    )
    assert c.layer == "statutory"
    assert c.component_code == "base_salary"


def test_rule_citation_unknown_layer_rejected():
    with pytest.raises(ValidationError):
        RuleCitation(document_path="x", layer="federal", clause="y")


def test_audit_entry_basic():
    cit = RuleCitation(document_path="x", layer="statutory", clause="c")
    e = AuditTrailEntry(
        step_index=0,
        primitive="BaseSalary",
        inputs_snapshot={"base_monthly_salary": "1500.00"},
        output={"amount": "1500.00"},
        rule_citation=cit,
        timestamp=datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc),
    )
    assert e.primitive == "BaseSalary"


def test_payslip_line_requires_tax_treatment():
    with pytest.raises(ValidationError):
        PayslipLine(component_code="x", description="d", amount=Decimal("0"), source_audit_ref=0)


def test_payslip_line_tax_treatment_enum():
    line = PayslipLine(
        component_code="base_salary",
        description="Base",
        amount=Decimal("1500"),
        tax_treatment="taxable",
        source_audit_ref=0,
    )
    assert line.tax_treatment == "taxable"
    with pytest.raises(ValidationError):
        PayslipLine(
            component_code="x", description="d", amount=Decimal("0"),
            tax_treatment="bogus", source_audit_ref=0,
        )


def test_payslip_result_net_pay_required():
    with pytest.raises(ValidationError):
        PayslipResult(period_id="p", employee_id="e")


def test_payslip_result_with_lines_and_audit():
    cit = RuleCitation(document_path="x", layer="statutory", clause="c")
    audit = AuditTrailEntry(
        step_index=0, primitive="BaseSalary",
        inputs_snapshot={}, output={"amount": "1500.00"},
        rule_citation=cit, timestamp=datetime(2026, 5, 26, tzinfo=timezone.utc),
    )
    line = PayslipLine(
        component_code="base_salary", description="Base",
        amount=Decimal("1500"), tax_treatment="taxable", source_audit_ref=0,
    )
    res = PayslipResult(
        period_id="2026-05",
        employee_id="emp-1",
        gross_earnings=[line],
        net_pay=Decimal("1500"),
        audit=[audit],
    )
    assert res.net_pay == Decimal("1500")
    assert len(res.gross_earnings) == 1
