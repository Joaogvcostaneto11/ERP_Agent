from decimal import Decimal
import pytest
from pydantic import ValidationError
from logic.payroll.public.schemas.identity import (
    FiscalProfile, CCTReference, Company,
)
from logic.payroll.primitives.rounding import RoundingPolicy


def test_fiscal_profile_defaults():
    fp = FiscalProfile(irs_table_code="solteiro_sem_dependentes")
    assert fp.dependents == 0
    assert fp.has_disability is False
    assert fp.residency_status == "resident"


def test_fiscal_profile_negative_dependents_rejected():
    with pytest.raises(ValidationError):
        FiscalProfile(irs_table_code="solteiro_sem_dependentes", dependents=-1)


def test_fiscal_profile_residency_enum():
    fp = FiscalProfile(irs_table_code="x", residency_status="non_habitual_resident")
    assert fp.residency_status == "non_habitual_resident"
    with pytest.raises(ValidationError):
        FiscalProfile(irs_table_code="x", residency_status="weird")


def test_cct_reference_valid():
    c = CCTReference(cct_id="cct-metalurgia-2025", cct_version="2025.1", role_category_code="op3")
    assert c.cct_id == "cct-metalurgia-2025"


def test_cct_reference_missing_field_rejected():
    with pytest.raises(ValidationError):
        CCTReference(cct_id="x", cct_version="1")  # missing role_category_code


def test_company_with_rounding_policy():
    c = Company(
        company_id="acme",
        legal_name="Acme, Lda.",
        tax_id="500000000",
        default_rounding_policy=RoundingPolicy(),
    )
    assert c.default_subsidio_payment_mode == "duodecimos"


def test_company_subsidio_mode_enum():
    c = Company(
        company_id="acme", legal_name="Acme", tax_id="500000000",
        default_rounding_policy=RoundingPolicy(),
        default_subsidio_payment_mode="one_shot",
    )
    assert c.default_subsidio_payment_mode == "one_shot"
    with pytest.raises(ValidationError):
        Company(
            company_id="x", legal_name="x", tax_id="x",
            default_rounding_policy=RoundingPolicy(),
            default_subsidio_payment_mode="quincenal",
        )
