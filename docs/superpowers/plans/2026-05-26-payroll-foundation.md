# Payroll Foundation + Minimum Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the payroll business-logic layer to life as a minimum vertical slice: a deterministic engine that can compute a trivial salaried-monthly payslip (base salary minus employee-side TSU) end-to-end, with full audit trail and citations, driven by layered YAML rules.

**Architecture:** Hybrid — Python compensation primitives + YAML composition + layered rule resolver. This plan ships only two primitives (`BaseSalary`, `TSUContribution`) and stops short of `PayrollService.run_payroll` (deferred to Plan 3). The point is to land the framework correctly so subsequent plans add primitives and service methods without re-architecting.

**Tech Stack:** Python 3.12+, Pydantic v2, PyYAML, pytest + pytest-asyncio, hypothesis (used lightly here), `decimal.Decimal` for all money.

**Spec:** [`docs/superpowers/specs/2026-05-26-payroll-business-logic-design.md`](../specs/2026-05-26-payroll-business-logic-design.md)

---

## File Structure (Plan 1 only)

```
ERP_Agent/
├── pyproject.toml                                       [create]
├── .env.example                                         [create]
├── business_rules/
│   └── payroll/
│       ├── statutory_pt.yaml                            [create — minimal Plan 1 stub]
│       └── companies/
│           └── default_company.yaml                     [create — minimal]
├── logic/
│   └── payroll/
│       ├── __init__.py                                  [create]
│       ├── errors.py                                    [create]
│       ├── clock.py                                     [create]
│       ├── primitives/
│       │   ├── __init__.py                              [create]
│       │   ├── base.py                                  [create — Protocol, Registry, ExecutionContext, PrimitiveResult]
│       │   ├── rounding.py                              [create — RoundingPolicy]
│       │   ├── basesalary.py                            [create — BaseSalary]
│       │   └── tsu.py                                   [create — TSUContribution]
│       ├── public/
│       │   ├── __init__.py                              [create]
│       │   ├── service.py                               [create — minimal PayrollService]
│       │   └── schemas/
│       │       ├── __init__.py                          [create — re-exports]
│       │       ├── identity.py                          [create]
│       │       ├── period.py                            [create]
│       │       ├── output.py                            [create]
│       │       └── requests.py                          [create]
│       ├── rules/
│       │   ├── __init__.py                              [create]
│       │   ├── models.py                                [create — rule-doc Pydantic models]
│       │   ├── loader.py                                [create — RuleLoader with float rejection]
│       │   ├── resolver.py                              [create — layer merging]
│       │   └── plan.py                                  [create — CalculationPlan + builder]
│       └── engine/
│           ├── __init__.py                              [create]
│           ├── time_input.py                            [create — minimal normalisation]
│           ├── audit.py                                 [create — render entries]
│           └── executor.py                              [create — execute plan]
├── db/
│   └── repositories/
│       ├── __init__.py                                  [create]
│       ├── interfaces.py                                [create — Protocols]
│       └── memory.py                                    [create — in-memory fakes]
└── tests/
    └── payroll/
        ├── __init__.py                                  [create]
        ├── conftest.py                                  [create — shared fixtures]
        ├── test_errors.py                               [create]
        ├── test_clock.py                                [create]
        ├── domain/
        │   ├── __init__.py                              [create]
        │   ├── test_identity.py                         [create]
        │   ├── test_period.py                           [create]
        │   └── test_output.py                           [create]
        ├── primitives/
        │   ├── __init__.py                              [create]
        │   ├── test_rounding.py                         [create]
        │   ├── test_registry.py                         [create]
        │   ├── test_basesalary.py                       [create]
        │   └── test_tsu.py                              [create]
        ├── rules/
        │   ├── __init__.py                              [create]
        │   ├── test_loader.py                           [create]
        │   ├── test_resolver.py                         [create]
        │   └── test_plan.py                             [create]
        ├── engine/
        │   ├── __init__.py                              [create]
        │   ├── test_time_input.py                       [create]
        │   ├── test_audit.py                            [create]
        │   └── test_executor.py                         [create]
        ├── repositories/
        │   ├── __init__.py                              [create]
        │   └── test_memory.py                           [create]
        ├── service/
        │   ├── __init__.py                              [create]
        │   └── test_dry_run.py                          [create]
        └── golden/
            ├── __init__.py                              [create]
            ├── conftest.py                              [create]
            ├── test_golden.py                           [create]
            └── scenarios/
                └── salaried_simple/                     [create]
                    ├── statutory.yaml
                    ├── company.yaml
                    ├── inputs.json
                    └── expected_payslip.json
```

---

## Canonical Type Conventions (applied throughout this plan)

- All monetary fields are `decimal.Decimal`. Pydantic config uses `arbitrary_types_allowed=False` and `model_config = ConfigDict(strict=True)`.
- YAML loader rejects float literals; numeric values in YAML must be quoted strings.
- `RuleCitation` lives in `logic/payroll/public/schemas/output.py`. Errors carry citation as `dict | None`, not as `RuleCitation`, to avoid cycles.
- `Clock` Protocol is at `logic/payroll/clock.py` with `SystemClock` and `FixedClock` concrete implementations.
- Phase strings are lowercase snake_case: `input`, `gross`, `pre_tax_deduction`, `tax`, `post_tax`, `employer_contribution`.

---

## Tasks

### Task 1: Initialise pyproject.toml + dev venv

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "erp-agent"
version = "0.0.1"
description = "AI-native ERP — payroll module"
requires-python = ">=3.12"
dependencies = [
    "anthropic>=0.40.0",
    "pydantic>=2.9.0",
    "pyyaml>=6.0.2",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "hypothesis>=6.115.0",
    "httpx>=0.27.0",
]

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["logic*", "db*"]
exclude = ["tests*", "business_rules*", "docs*", "ui*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
pythonpath = ["."]
```

- [ ] **Step 2: Write .env.example**

```bash
ANTHROPIC_API_KEY=your-key-here
```

- [ ] **Step 3: Create venv and install (manual; engineer's responsibility)**

Run:
```
python3.12 -m venv .venv
.venv/Scripts/activate    # Windows
# or: source .venv/bin/activate
pip install -e .[dev]
```

Expected: install succeeds; `python -c "import pydantic, yaml, anthropic"` exits 0.

- [ ] **Step 4: Commit**

```
git add pyproject.toml .env.example
git commit -m "chore: pyproject.toml + .env.example for payroll module"
```

---

### Task 2: Scaffold package structure

**Files:**
- Create all `__init__.py` files listed in the File Structure section above.

- [ ] **Step 1: Create empty __init__.py files**

For each listed directory, create an empty `__init__.py`. The list is in the File Structure block. Use the project's existing shell or editor.

- [ ] **Step 2: Verify imports**

Run:
```
python -c "import logic.payroll; import logic.payroll.primitives; import logic.payroll.public; import logic.payroll.public.schemas; import logic.payroll.rules; import logic.payroll.engine; import db.repositories"
```

Expected: exits 0 with no output.

- [ ] **Step 3: Commit**

```
git add logic/ db/ tests/
git commit -m "chore: scaffold payroll package skeleton"
```

---

### Task 3: Typed exceptions

**Files:**
- Create: `logic/payroll/errors.py`
- Create: `tests/payroll/test_errors.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/payroll/test_errors.py
import pytest
from logic.payroll.errors import (
    PayrollError, RuleLoadError, RuleValidationError, MissingInput,
    RuleViolation, ImmutablePeriod, PeriodInProgress, EngineInvariantError,
)


def test_payroll_error_holds_code_and_messages():
    err = PayrollError(code="X1", msg_pt="erro", msg_en="error")
    assert err.code == "X1"
    assert err.msg_pt == "erro"
    assert err.msg_en == "error"
    assert err.citation is None
    assert str(err) == "error"


def test_payroll_error_optional_citation_is_a_dict():
    citation = {
        "document_path": "business_rules/payroll/statutory_pt.yaml",
        "layer": "statutory",
        "clause": "components.tsu_employee.rate",
    }
    err = PayrollError("X1", "erro", "error", citation=citation)
    assert err.citation == citation


@pytest.mark.parametrize(
    "cls",
    [RuleLoadError, RuleValidationError, MissingInput, RuleViolation,
     ImmutablePeriod, PeriodInProgress, EngineInvariantError],
)
def test_subclasses_inherit_payroll_error(cls):
    err = cls(code="X1", msg_pt="pt", msg_en="en")
    assert isinstance(err, PayrollError)
    assert err.code == "X1"


def test_can_be_raised_and_caught():
    with pytest.raises(RuleViolation) as exc_info:
        raise RuleViolation(code="LOCKED_FIELD", msg_pt="campo bloqueado", msg_en="locked field")
    assert exc_info.value.code == "LOCKED_FIELD"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```
pytest tests/payroll/test_errors.py -v
```

Expected: FAIL with `ImportError` / `ModuleNotFoundError` for `logic.payroll.errors`.

- [ ] **Step 3: Write minimal implementation**

```python
# logic/payroll/errors.py
from __future__ import annotations
from typing import Optional


class PayrollError(Exception):
    """Base class for all typed exceptions raised by the payroll module."""

    def __init__(
        self,
        code: str,
        msg_pt: str,
        msg_en: str,
        citation: Optional[dict] = None,
    ) -> None:
        self.code = code
        self.msg_pt = msg_pt
        self.msg_en = msg_en
        self.citation = citation
        super().__init__(msg_en)


class RuleLoadError(PayrollError):
    """Raised by RuleLoader when YAML is malformed or schema-invalid."""


class RuleValidationError(PayrollError):
    """Raised when cross-layer rules are inconsistent or a plan fails validation."""


class MissingInput(PayrollError):
    """Raised when an operation requires data that isn't available."""


class RuleViolation(PayrollError):
    """Raised when an operation is rejected by an active rule (e.g. locked field, overlapping absence)."""


class ImmutablePeriod(PayrollError):
    """Raised on any write attempt against a closed period."""


class PeriodInProgress(PayrollError):
    """Raised when a concurrent run_payroll attempt collides with an in-flight one."""


class EngineInvariantError(PayrollError):
    """Raised when an internal engine invariant is violated. This is a bug, not user error."""
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```
pytest tests/payroll/test_errors.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/errors.py tests/payroll/test_errors.py
git commit -m "feat: typed payroll exceptions with code/pt/en/citation"
```

---

### Task 4: Clock protocol

**Files:**
- Create: `logic/payroll/clock.py`
- Create: `tests/payroll/test_clock.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/payroll/test_clock.py
from datetime import datetime, timezone
from logic.payroll.clock import Clock, SystemClock, FixedClock


def test_system_clock_returns_utc_datetime():
    clock: Clock = SystemClock()
    now = clock.now()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None


def test_fixed_clock_returns_supplied_value():
    fixed = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)
    clock: Clock = FixedClock(fixed)
    assert clock.now() == fixed
    # Repeated calls return the same value
    assert clock.now() == fixed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/payroll/test_clock.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

```python
# logic/payroll/clock.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    def __init__(self, fixed_now: datetime) -> None:
        if fixed_now.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware datetime")
        self._now = fixed_now

    def now(self) -> datetime:
        return self._now
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/payroll/test_clock.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/clock.py tests/payroll/test_clock.py
git commit -m "feat: Clock protocol with SystemClock and FixedClock"
```

---

### Task 5: RoundingPolicy primitive utility

**Files:**
- Create: `logic/payroll/rounding.py`
- Create: `tests/payroll/test_rounding.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/payroll/test_rounding.py
from decimal import Decimal
import pytest
from pydantic import ValidationError
from logic.payroll.rounding import RoundingPolicy


def test_default_policy_is_round_half_up_two_places():
    p = RoundingPolicy()
    assert p.method == "ROUND_HALF_UP"
    assert p.decimal_places == 2
    assert p.apply(Decimal("1.235")) == Decimal("1.24")


def test_round_half_up_at_boundary():
    p = RoundingPolicy(method="ROUND_HALF_UP", decimal_places=2)
    assert p.apply(Decimal("0.125")) == Decimal("0.13")
    assert p.apply(Decimal("0.124")) == Decimal("0.12")


def test_round_half_even_at_boundary():
    p = RoundingPolicy(method="ROUND_HALF_EVEN", decimal_places=2)
    assert p.apply(Decimal("0.125")) == Decimal("0.12")
    assert p.apply(Decimal("0.135")) == Decimal("0.14")


def test_round_half_down_at_boundary():
    p = RoundingPolicy(method="ROUND_HALF_DOWN", decimal_places=2)
    assert p.apply(Decimal("0.125")) == Decimal("0.12")
    assert p.apply(Decimal("0.126")) == Decimal("0.13")


def test_zero_decimal_places():
    p = RoundingPolicy(method="ROUND_HALF_UP", decimal_places=0)
    assert p.apply(Decimal("1.5")) == Decimal("2")


def test_unknown_method_rejected():
    with pytest.raises(ValidationError):
        RoundingPolicy(method="ROUND_BANKERS")


def test_negative_decimal_places_rejected():
    with pytest.raises(ValidationError):
        RoundingPolicy(decimal_places=-1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/payroll/test_rounding.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

```python
# logic/payroll/rounding.py
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_DOWN, ROUND_HALF_EVEN
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


_METHOD_MAP = {
    "ROUND_HALF_UP": ROUND_HALF_UP,
    "ROUND_HALF_DOWN": ROUND_HALF_DOWN,
    "ROUND_HALF_EVEN": ROUND_HALF_EVEN,
}


class RoundingPolicy(BaseModel):
    model_config = ConfigDict(strict=True)

    method: Literal["ROUND_HALF_UP", "ROUND_HALF_DOWN", "ROUND_HALF_EVEN"] = "ROUND_HALF_UP"
    decimal_places: int = Field(ge=0, default=2)

    def apply(self, value: Decimal) -> Decimal:
        quantum = Decimal(1).scaleb(-self.decimal_places) if self.decimal_places > 0 else Decimal(1)
        return value.quantize(quantum, rounding=_METHOD_MAP[self.method])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/payroll/test_rounding.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/rounding.py tests/payroll/test_rounding.py
git commit -m "feat: RoundingPolicy with HALF_UP/DOWN/EVEN modes"
```

---

### Task 6: Output schemas (RuleCitation, AuditTrailEntry, PayslipLine, PayslipResult)

**Files:**
- Create: `logic/payroll/public/schemas/output.py`
- Create: `tests/payroll/domain/test_output.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/payroll/domain/test_output.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/payroll/domain/test_output.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

```python
# logic/payroll/public/schemas/output.py
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class RuleCitation(BaseModel):
    model_config = ConfigDict(strict=True)

    document_path: str
    layer: Literal["statutory", "cct", "company", "contract"]
    component_code: Optional[str] = None
    clause: str


class AuditTrailEntry(BaseModel):
    model_config = ConfigDict(strict=True)

    step_index: int = Field(ge=0)
    primitive: str
    inputs_snapshot: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    rule_citation: RuleCitation
    timestamp: datetime


class PayslipLine(BaseModel):
    model_config = ConfigDict(strict=True)

    component_code: str
    description: str
    amount: Decimal
    quantity: Optional[Decimal] = None
    rate: Optional[Decimal] = None
    tax_treatment: Literal["taxable", "exempt", "partially_exempt"]
    exempt_amount: Decimal = Decimal("0")
    source_audit_ref: int = Field(ge=0)


class PayslipResult(BaseModel):
    model_config = ConfigDict(strict=True)

    period_id: str
    employee_id: str
    gross_earnings: list[PayslipLine] = Field(default_factory=list)
    deductions: list[PayslipLine] = Field(default_factory=list)
    employer_contributions: list[PayslipLine] = Field(default_factory=list)
    net_pay: Decimal
    audit: list[AuditTrailEntry] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/payroll/domain/test_output.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/public/schemas/output.py tests/payroll/domain/test_output.py
git commit -m "feat: output domain models (RuleCitation, AuditTrailEntry, PayslipLine, PayslipResult)"
```

---

### Task 7: Identity domain models — FiscalProfile, CCTReference, Company

**Files:**
- Create: `logic/payroll/public/schemas/identity.py`
- Create: `tests/payroll/domain/test_identity.py`

- [ ] **Step 1: Write failing tests for the first three identity models**

```python
# tests/payroll/domain/test_identity.py
from decimal import Decimal
import pytest
from pydantic import ValidationError
from logic.payroll.public.schemas.identity import (
    FiscalProfile, CCTReference, Company,
)
from logic.payroll.rounding import RoundingPolicy


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/payroll/domain/test_identity.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement the three models**

```python
# logic/payroll/public/schemas/identity.py
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from logic.payroll.rounding import RoundingPolicy


class FiscalProfile(BaseModel):
    model_config = ConfigDict(strict=True)

    irs_table_code: str
    dependents: int = Field(ge=0, default=0)
    has_disability: bool = False
    spouse_has_disability: bool = False
    residency_status: Literal["resident", "non_habitual_resident", "non_resident"] = "resident"
    voluntary_irs_rate: Optional[Decimal] = None


class CCTReference(BaseModel):
    model_config = ConfigDict(strict=True)

    cct_id: str
    cct_version: str
    role_category_code: str


class Company(BaseModel):
    model_config = ConfigDict(strict=True)

    company_id: str
    legal_name: str
    tax_id: str
    default_rounding_policy: RoundingPolicy
    default_subsidio_payment_mode: Literal["one_shot", "duodecimos"] = "duodecimos"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/payroll/domain/test_identity.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/public/schemas/identity.py tests/payroll/domain/test_identity.py
git commit -m "feat: identity models (FiscalProfile, CCTReference, Company)"
```

---

### Task 8: Identity domain models — Contract, Employee, CompensationPackage

**Files:**
- Modify: `logic/payroll/public/schemas/identity.py`
- Modify: `tests/payroll/domain/test_identity.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/payroll/domain/test_identity.py`:

```python
from datetime import date as _date
from logic.payroll.public.schemas.identity import (
    Contract, Employee, CompensationEntitlement, CompensationPackage,
)


def _valid_contract_kwargs(**overrides):
    base = dict(
        contract_id="c-1",
        employee_id="e-1",
        type="CT",
        start_date=_date(2025, 1, 1),
        end_date=None,
        role_category="developer",
        weekly_hours=Decimal("40"),
        fte_percent=Decimal("1.0"),
        base_monthly_salary=Decimal("1500"),
        cct_reference=None,
        company_id="acme",
        pay_frequency="monthly",
    )
    base.update(overrides)
    return base


def test_contract_valid():
    c = Contract(**_valid_contract_kwargs())
    assert c.type == "CT"
    assert c.pay_frequency == "monthly"


def test_contract_unknown_type_rejected():
    with pytest.raises(ValidationError):
        Contract(**_valid_contract_kwargs(type="freelancer"))


def test_contract_negative_salary_rejected():
    with pytest.raises(ValidationError):
        Contract(**_valid_contract_kwargs(base_monthly_salary=Decimal("-1")))


def test_contract_weekly_hours_must_be_positive():
    with pytest.raises(ValidationError):
        Contract(**_valid_contract_kwargs(weekly_hours=Decimal("0")))


def test_contract_fte_percent_in_range():
    Contract(**_valid_contract_kwargs(fte_percent=Decimal("0.5")))
    with pytest.raises(ValidationError):
        Contract(**_valid_contract_kwargs(fte_percent=Decimal("0")))
    with pytest.raises(ValidationError):
        Contract(**_valid_contract_kwargs(fte_percent=Decimal("1.5")))


def test_contract_end_before_start_rejected():
    with pytest.raises(ValidationError):
        Contract(**_valid_contract_kwargs(
            start_date=_date(2025, 6, 1),
            end_date=_date(2025, 5, 1),
        ))


def test_employee_basic():
    e = Employee(
        employee_id="e-1",
        full_name="Maria Santos",
        tax_id="123456789",
        social_security_id="11122233344",
        birth_date=_date(1990, 1, 1),
        hire_date=_date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="solteiro_sem_dependentes"),
    )
    assert e.status == "active"


def test_employee_status_enum():
    with pytest.raises(ValidationError):
        Employee(
            employee_id="e-1", full_name="x", tax_id="x", social_security_id="x",
            birth_date=_date(1990, 1, 1), hire_date=_date(2025, 1, 1),
            fiscal_profile=FiscalProfile(irs_table_code="x"),
            status="vacation",
        )


def test_compensation_package_default_empty():
    pkg = CompensationPackage(contract_id="c-1")
    assert pkg.entitlements == []


def test_compensation_entitlement_arbitrary_parameters():
    ent = CompensationEntitlement(component_code="meal_allowance", parameters={"daily_rate": "6.00"})
    assert ent.parameters["daily_rate"] == "6.00"
```

- [ ] **Step 2: Run tests to verify new ones fail**

Run: `pytest tests/payroll/domain/test_identity.py -v`
Expected: FAIL with ImportError for `Contract`, `Employee`, `CompensationEntitlement`, `CompensationPackage`.

- [ ] **Step 3: Extend identity.py**

Append to `logic/payroll/public/schemas/identity.py`:

```python
from datetime import date
from typing import Any
from pydantic import model_validator


class Contract(BaseModel):
    model_config = ConfigDict(strict=True)

    contract_id: str
    employee_id: str
    type: Literal["CT", "CTT", "CTI", "part_time", "internship"]
    start_date: date
    end_date: Optional[date] = None
    role_category: str
    weekly_hours: Decimal = Field(gt=Decimal("0"))
    fte_percent: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    base_monthly_salary: Decimal = Field(ge=Decimal("0"))
    cct_reference: Optional[CCTReference] = None
    company_id: str
    pay_frequency: Literal["monthly", "biweekly", "weekly"] = "monthly"

    @model_validator(mode="after")
    def _check_dates(self) -> "Contract":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        return self


class Employee(BaseModel):
    model_config = ConfigDict(strict=True)

    employee_id: str
    full_name: str
    tax_id: str
    social_security_id: str
    birth_date: date
    hire_date: date
    status: Literal["active", "suspended", "terminated"] = "active"
    fiscal_profile: FiscalProfile
    current_contract_id: Optional[str] = None
    bank_iban: Optional[str] = None


class CompensationEntitlement(BaseModel):
    model_config = ConfigDict(strict=True)

    component_code: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class CompensationPackage(BaseModel):
    model_config = ConfigDict(strict=True)

    contract_id: str
    entitlements: list[CompensationEntitlement] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/domain/test_identity.py -v`
Expected: 17 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/public/schemas/identity.py tests/payroll/domain/test_identity.py
git commit -m "feat: Contract, Employee, CompensationPackage domain models"
```

---

### Task 9: Period domain models — PayrollPeriod, AbsenceEntry, OvertimeBuckets, TimeInput

**Files:**
- Create: `logic/payroll/public/schemas/period.py`
- Create: `tests/payroll/domain/test_period.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/payroll/domain/test_period.py
from datetime import date
from decimal import Decimal
import pytest
from pydantic import ValidationError
from logic.payroll.public.schemas.period import (
    PayrollPeriod, AbsenceEntry, OvertimeBuckets, TimeInput,
)


def test_payroll_period_default_status_open():
    p = PayrollPeriod(
        period_id="2026-05",
        company_id="acme",
        pay_frequency="monthly",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    )
    assert p.status == "open"


def test_payroll_period_end_before_start_rejected():
    with pytest.raises(ValidationError):
        PayrollPeriod(
            period_id="x", company_id="acme", pay_frequency="monthly",
            start_date=date(2026, 5, 31), end_date=date(2026, 5, 1),
            pay_date=date(2026, 5, 31),
        )


def test_absence_entry_valid():
    a = AbsenceEntry(start_date=date(2026, 5, 10), end_date=date(2026, 5, 12), code="vacation")
    assert a.paid_percent is None


def test_absence_entry_end_before_start_rejected():
    with pytest.raises(ValidationError):
        AbsenceEntry(start_date=date(2026, 5, 12), end_date=date(2026, 5, 10), code="x")


def test_overtime_buckets_defaults_zero():
    b = OvertimeBuckets()
    assert b.first_hour == Decimal("0")
    assert b.weekend == Decimal("0")


def test_overtime_buckets_negative_rejected():
    with pytest.raises(ValidationError):
        OvertimeBuckets(first_hour=Decimal("-1"))


def test_time_input_defaults():
    t = TimeInput(period_id="2026-05", employee_id="e-1", normal_hours=Decimal("160"))
    assert t.overtime_buckets.first_hour == Decimal("0")
    assert t.absences == []
    assert t.meal_allowance_days == 0


def test_time_input_negative_normal_hours_rejected():
    with pytest.raises(ValidationError):
        TimeInput(period_id="p", employee_id="e", normal_hours=Decimal("-1"))


def test_time_input_negative_meal_days_rejected():
    with pytest.raises(ValidationError):
        TimeInput(period_id="p", employee_id="e", normal_hours=Decimal("0"), meal_allowance_days=-1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/payroll/domain/test_period.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

```python
# logic/payroll/public/schemas/period.py
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PayrollPeriod(BaseModel):
    model_config = ConfigDict(strict=True)

    period_id: str
    company_id: str
    pay_frequency: Literal["monthly", "biweekly", "weekly"]
    start_date: date
    end_date: date
    pay_date: date
    status: Literal["open", "calculated", "closed"] = "open"

    @model_validator(mode="after")
    def _check_dates(self) -> "PayrollPeriod":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        return self


class AbsenceEntry(BaseModel):
    model_config = ConfigDict(strict=True)

    start_date: date
    end_date: date
    code: str
    paid_percent: Optional[Decimal] = None

    @model_validator(mode="after")
    def _check_dates(self) -> "AbsenceEntry":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        return self


class OvertimeBuckets(BaseModel):
    model_config = ConfigDict(strict=True)

    first_hour: Decimal = Field(ge=Decimal("0"), default=Decimal("0"))
    additional_hours: Decimal = Field(ge=Decimal("0"), default=Decimal("0"))
    weekend: Decimal = Field(ge=Decimal("0"), default=Decimal("0"))
    holiday: Decimal = Field(ge=Decimal("0"), default=Decimal("0"))
    night: Decimal = Field(ge=Decimal("0"), default=Decimal("0"))


class TimeInput(BaseModel):
    model_config = ConfigDict(strict=True)

    period_id: str
    employee_id: str
    normal_hours: Decimal = Field(ge=Decimal("0"))
    overtime_buckets: OvertimeBuckets = Field(default_factory=OvertimeBuckets)
    absences: list[AbsenceEntry] = Field(default_factory=list)
    meal_allowance_days: int = Field(ge=0, default=0)
    notes: str = ""
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/domain/test_period.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/public/schemas/period.py tests/payroll/domain/test_period.py
git commit -m "feat: period domain models (PayrollPeriod, AbsenceEntry, OvertimeBuckets, TimeInput)"
```

---

### Task 10: Schemas package re-exports

**Files:**
- Modify: `logic/payroll/public/schemas/__init__.py`

- [ ] **Step 1: Write the re-exports**

```python
# logic/payroll/public/schemas/__init__.py
from logic.payroll.public.schemas.identity import (
    FiscalProfile, CCTReference, Company,
    Contract, Employee, CompensationEntitlement, CompensationPackage,
)
from logic.payroll.public.schemas.period import (
    PayrollPeriod, AbsenceEntry, OvertimeBuckets, TimeInput,
)
from logic.payroll.public.schemas.output import (
    RuleCitation, AuditTrailEntry, PayslipLine, PayslipResult,
)

__all__ = [
    "FiscalProfile", "CCTReference", "Company",
    "Contract", "Employee", "CompensationEntitlement", "CompensationPackage",
    "PayrollPeriod", "AbsenceEntry", "OvertimeBuckets", "TimeInput",
    "RuleCitation", "AuditTrailEntry", "PayslipLine", "PayslipResult",
]
```

- [ ] **Step 2: Verify import**

Run:
```
python -c "from logic.payroll.public.schemas import Employee, Contract, PayslipResult; print('OK')"
```

Expected: prints `OK`.

- [ ] **Step 3: Commit**

```
git add logic/payroll/public/schemas/__init__.py
git commit -m "feat: re-export all schemas from public.schemas package"
```

---

### Task 11: Primitive framework — PrimitiveResult and ExecutionContext

**Files:**
- Create: `logic/payroll/primitives/base.py`
- Create: `tests/payroll/primitives/test_registry.py` (for the next task; this task only adds the dataclasses and result model)

- [ ] **Step 1: Write the failing test file**

Create `tests/payroll/primitives/test_registry.py` with the following content. (Task 12 will append more tests; for now there are two.)

```python
# tests/payroll/primitives/test_registry.py
from datetime import date, datetime, timezone
from decimal import Decimal
import dataclasses
import pytest
from logic.payroll.primitives.base import (
    PrimitiveResult, ExecutionContext,
)
from logic.payroll.public.schemas import (
    Employee, Contract, FiscalProfile, Company, PayrollPeriod,
)
from logic.payroll.rounding import RoundingPolicy
from logic.payroll.clock import FixedClock


def _make_context() -> ExecutionContext:
    company = Company(
        company_id="acme", legal_name="Acme", tax_id="500000000",
        default_rounding_policy=RoundingPolicy(),
    )
    employee = Employee(
        employee_id="e-1", full_name="x", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="x"),
    )
    contract = Contract(
        contract_id="c-1", employee_id="e-1", type="CT",
        start_date=date(2025, 1, 1), role_category="dev",
        weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
        base_monthly_salary=Decimal("1500"), company_id="acme",
    )
    period = PayrollPeriod(
        period_id="2026-05", company_id="acme", pay_frequency="monthly",
        start_date=date(2026, 5, 1), end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    )
    return ExecutionContext(
        period=period, contract=contract, employee=employee, company=company,
        rounding_policy=RoundingPolicy(),
        clock=FixedClock(datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)),
    )


def test_primitive_result_minimal():
    r = PrimitiveResult(amount=Decimal("100"), tax_treatment="taxable")
    assert r.amount == Decimal("100")
    assert r.exempt_amount == Decimal("0")
    assert r.breakdown == []
    assert r.notes == ""


def test_execution_context_is_frozen():
    ctx = _make_context()
    assert dataclasses.is_dataclass(ctx)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.employee = None  # type: ignore
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/payroll/primitives/test_registry.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement PrimitiveResult and ExecutionContext**

```python
# logic/payroll/primitives/base.py
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field
from logic.payroll.public.schemas import (
    Employee, Contract, Company, PayrollPeriod, RuleCitation,
)
from logic.payroll.rounding import RoundingPolicy
from logic.payroll.clock import Clock


class PrimitiveResult(BaseModel):
    model_config = ConfigDict(strict=True)

    amount: Decimal
    quantity: Decimal | None = None
    rate: Decimal | None = None
    tax_treatment: Literal["taxable", "exempt", "partially_exempt"] = "taxable"
    exempt_amount: Decimal = Decimal("0")
    breakdown: list[dict[str, Any]] = Field(default_factory=list)
    notes: str = ""
    citations: list[RuleCitation] = Field(default_factory=list)


@dataclass(frozen=True)
class ExecutionContext:
    period: PayrollPeriod
    contract: Contract
    employee: Employee
    company: Company
    rounding_policy: RoundingPolicy
    clock: Clock
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/primitives/test_registry.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/primitives/base.py tests/payroll/primitives/test_registry.py
git commit -m "feat: PrimitiveResult model and ExecutionContext dataclass"
```

---

### Task 12: Primitive framework — Protocol, Registry, @register decorator

**Files:**
- Modify: `logic/payroll/primitives/base.py`
- Modify: `tests/payroll/primitives/test_registry.py`

- [ ] **Step 1: Append failing tests**

First, extend the imports at the top of `tests/payroll/primitives/test_registry.py` to add Protocol and Registry imports plus `BaseModel`:

```python
# At the top of the file, replace the existing primitives.base import with:
from logic.payroll.primitives.base import (
    PrimitiveResult, ExecutionContext, Primitive, PrimitiveRegistry, register,
)
from pydantic import BaseModel
```

Then append at the bottom:

```python
class _DummyParams(BaseModel):
    pass


class _DummyInputs(BaseModel):
    pass


def test_registry_register_and_get():
    reg = PrimitiveRegistry()

    class FakePrim:
        name = "FakePrim"
        parameter_schema = _DummyParams
        input_schema = _DummyInputs
        output_schema = PrimitiveResult

        def execute(self, params, inputs, context):
            return PrimitiveResult(amount=Decimal("0"), tax_treatment="taxable")

    reg.register("FakePrim", FakePrim)
    assert reg.get("FakePrim") is FakePrim


def test_registry_duplicate_name_rejected():
    reg = PrimitiveRegistry()

    class A:
        name = "X"; parameter_schema = _DummyParams; input_schema = _DummyInputs
        output_schema = PrimitiveResult

        def execute(self, params, inputs, context): ...

    class B:
        name = "X"; parameter_schema = _DummyParams; input_schema = _DummyInputs
        output_schema = PrimitiveResult

        def execute(self, params, inputs, context): ...

    reg.register("X", A)
    with pytest.raises(ValueError, match="already registered"):
        reg.register("X", B)


def test_registry_get_unknown_raises():
    reg = PrimitiveRegistry()
    with pytest.raises(KeyError):
        reg.get("Nonexistent")


def test_register_decorator_attaches_to_supplied_registry():
    reg = PrimitiveRegistry()

    @register("Decorated", registry=reg)
    class Decorated:
        name = "Decorated"
        parameter_schema = _DummyParams
        input_schema = _DummyInputs
        output_schema = PrimitiveResult

        def execute(self, params, inputs, context):
            return PrimitiveResult(amount=Decimal("0"), tax_treatment="taxable")

    assert reg.get("Decorated") is Decorated
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `pytest tests/payroll/primitives/test_registry.py -v`
Expected: FAIL with `ImportError` for `Primitive`, `PrimitiveRegistry`, `register`.

- [ ] **Step 3: Extend base.py**

Append to `logic/payroll/primitives/base.py`:

```python
class Primitive(Protocol):
    name: str
    parameter_schema: type[BaseModel]
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]

    def execute(self, params: BaseModel, inputs: BaseModel, context: ExecutionContext) -> PrimitiveResult: ...


class PrimitiveRegistry:
    def __init__(self) -> None:
        self._by_name: dict[str, type[Primitive]] = {}

    def register(self, name: str, primitive_cls: type[Primitive]) -> None:
        if name in self._by_name:
            raise ValueError(f"Primitive {name!r} already registered")
        self._by_name[name] = primitive_cls

    def get(self, name: str) -> type[Primitive]:
        return self._by_name[name]


DEFAULT_REGISTRY = PrimitiveRegistry()


def register(name: str, registry: PrimitiveRegistry | None = None):
    target = registry if registry is not None else DEFAULT_REGISTRY

    def decorator(cls):
        target.register(name, cls)
        return cls

    return decorator
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/primitives/test_registry.py -v`
Expected: 6 passed (2 from Task 11 + 4 new).

- [ ] **Step 5: Commit**

```
git add logic/payroll/primitives/base.py tests/payroll/primitives/test_registry.py
git commit -m "feat: Primitive Protocol, PrimitiveRegistry, and @register decorator"
```

---

### Task 13: BaseSalary primitive

**Files:**
- Create: `logic/payroll/primitives/basesalary.py`
- Create: `tests/payroll/primitives/test_basesalary.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/payroll/primitives/test_basesalary.py
from datetime import date, datetime, timezone
from decimal import Decimal
from logic.payroll.primitives.basesalary import BaseSalary, BaseSalaryParams, BaseSalaryInputs
from logic.payroll.primitives.base import ExecutionContext
from logic.payroll.rounding import RoundingPolicy
from logic.payroll.clock import FixedClock
from logic.payroll.public.schemas import (
    Employee, Contract, FiscalProfile, Company, PayrollPeriod,
)


def _ctx(salary: Decimal = Decimal("1500")) -> ExecutionContext:
    company = Company(
        company_id="acme", legal_name="Acme", tax_id="500000000",
        default_rounding_policy=RoundingPolicy(),
    )
    employee = Employee(
        employee_id="e-1", full_name="Maria", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="x"),
    )
    contract = Contract(
        contract_id="c-1", employee_id="e-1", type="CT",
        start_date=date(2025, 1, 1), role_category="dev",
        weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
        base_monthly_salary=salary, company_id="acme",
    )
    period = PayrollPeriod(
        period_id="2026-05", company_id="acme", pay_frequency="monthly",
        start_date=date(2026, 5, 1), end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    )
    return ExecutionContext(
        period=period, contract=contract, employee=employee, company=company,
        rounding_policy=RoundingPolicy(),
        clock=FixedClock(datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)),
    )


def test_base_salary_returns_contract_amount():
    prim = BaseSalary()
    result = prim.execute(BaseSalaryParams(), BaseSalaryInputs(), _ctx(Decimal("1500")))
    assert result.amount == Decimal("1500.00")
    assert result.tax_treatment == "taxable"


def test_base_salary_is_rounded_to_two_places():
    prim = BaseSalary()
    result = prim.execute(BaseSalaryParams(), BaseSalaryInputs(), _ctx(Decimal("1500.005")))
    assert result.amount == Decimal("1500.01")


def test_base_salary_metadata_attributes():
    assert BaseSalary.name == "BaseSalary"
    assert BaseSalary.parameter_schema is BaseSalaryParams
    assert BaseSalary.input_schema is BaseSalaryInputs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/payroll/primitives/test_basesalary.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

```python
# logic/payroll/primitives/basesalary.py
from __future__ import annotations
from pydantic import BaseModel, ConfigDict
from logic.payroll.primitives.base import (
    PrimitiveResult, ExecutionContext, register,
)


class BaseSalaryParams(BaseModel):
    model_config = ConfigDict(strict=True)


class BaseSalaryInputs(BaseModel):
    model_config = ConfigDict(strict=True)


@register("BaseSalary")
class BaseSalary:
    name = "BaseSalary"
    parameter_schema = BaseSalaryParams
    input_schema = BaseSalaryInputs
    output_schema = PrimitiveResult

    def execute(
        self,
        params: BaseSalaryParams,
        inputs: BaseSalaryInputs,
        context: ExecutionContext,
    ) -> PrimitiveResult:
        amount = context.rounding_policy.apply(context.contract.base_monthly_salary)
        return PrimitiveResult(
            amount=amount,
            tax_treatment="taxable",
            notes=f"Base monthly salary per contract {context.contract.contract_id}",
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/primitives/test_basesalary.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/primitives/basesalary.py tests/payroll/primitives/test_basesalary.py
git commit -m "feat: BaseSalary primitive (no proration; full month only)"
```

---

### Task 14: TSUContribution primitive (employee side)

**Files:**
- Create: `logic/payroll/primitives/tsu.py`
- Create: `tests/payroll/primitives/test_tsu.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/payroll/primitives/test_tsu.py
from datetime import date, datetime, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError
from logic.payroll.primitives.tsu import TSUContribution, TSUContributionParams, TSUContributionInputs
from logic.payroll.primitives.base import ExecutionContext
from logic.payroll.rounding import RoundingPolicy
from logic.payroll.clock import FixedClock
from logic.payroll.public.schemas import (
    Employee, Contract, FiscalProfile, Company, PayrollPeriod,
)


def _ctx() -> ExecutionContext:
    company = Company(
        company_id="acme", legal_name="Acme", tax_id="500000000",
        default_rounding_policy=RoundingPolicy(),
    )
    employee = Employee(
        employee_id="e-1", full_name="x", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="x"),
    )
    contract = Contract(
        contract_id="c-1", employee_id="e-1", type="CT",
        start_date=date(2025, 1, 1), role_category="dev",
        weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
        base_monthly_salary=Decimal("1500"), company_id="acme",
    )
    period = PayrollPeriod(
        period_id="2026-05", company_id="acme", pay_frequency="monthly",
        start_date=date(2026, 5, 1), end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    )
    return ExecutionContext(
        period=period, contract=contract, employee=employee, company=company,
        rounding_policy=RoundingPolicy(),
        clock=FixedClock(datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)),
    )


def test_tsu_employee_rate_applied_to_single_base_component():
    prim = TSUContribution()
    params = TSUContributionParams(rate=Decimal("0.11"), base_components=["base_salary"])
    inputs = TSUContributionInputs(component_values={"base_salary": Decimal("1500")})
    result = prim.execute(params, inputs, _ctx())
    assert result.amount == Decimal("165.00")
    assert result.tax_treatment == "taxable"


def test_tsu_sums_multiple_base_components():
    prim = TSUContribution()
    params = TSUContributionParams(rate=Decimal("0.11"), base_components=["base_salary", "diuturnidades"])
    inputs = TSUContributionInputs(component_values={
        "base_salary": Decimal("1500"),
        "diuturnidades": Decimal("100"),
    })
    result = prim.execute(params, inputs, _ctx())
    assert result.amount == Decimal("176.00")


def test_tsu_missing_input_raises():
    from logic.payroll.errors import MissingInput
    prim = TSUContribution()
    params = TSUContributionParams(rate=Decimal("0.11"), base_components=["base_salary"])
    inputs = TSUContributionInputs(component_values={})
    with pytest.raises(MissingInput) as exc:
        prim.execute(params, inputs, _ctx())
    assert exc.value.code == "TSU_MISSING_BASE_COMPONENT"


def test_tsu_rate_negative_rejected_at_param_validation():
    with pytest.raises(ValidationError):
        TSUContributionParams(rate=Decimal("-0.01"), base_components=["base_salary"])


def test_tsu_rate_above_one_rejected():
    with pytest.raises(ValidationError):
        TSUContributionParams(rate=Decimal("1.01"), base_components=["base_salary"])


def test_tsu_metadata():
    assert TSUContribution.name == "TSUContribution"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/payroll/primitives/test_tsu.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

```python
# logic/payroll/primitives/tsu.py
from __future__ import annotations
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
from logic.payroll.primitives.base import (
    PrimitiveResult, ExecutionContext, register,
)
from logic.payroll.errors import MissingInput


class TSUContributionParams(BaseModel):
    model_config = ConfigDict(strict=True)

    rate: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    base_components: list[str] = Field(min_length=1)


class TSUContributionInputs(BaseModel):
    model_config = ConfigDict(strict=True)

    component_values: dict[str, Decimal] = Field(default_factory=dict)


@register("TSUContribution")
class TSUContribution:
    name = "TSUContribution"
    parameter_schema = TSUContributionParams
    input_schema = TSUContributionInputs
    output_schema = PrimitiveResult

    def execute(
        self,
        params: TSUContributionParams,
        inputs: TSUContributionInputs,
        context: ExecutionContext,
    ) -> PrimitiveResult:
        base = Decimal("0")
        for code in params.base_components:
            if code not in inputs.component_values:
                raise MissingInput(
                    code="TSU_MISSING_BASE_COMPONENT",
                    msg_pt=f"componente base {code!r} em falta para TSU",
                    msg_en=f"missing base component {code!r} for TSU contribution",
                )
            base += inputs.component_values[code]
        gross = base * params.rate
        amount = context.rounding_policy.apply(gross)
        return PrimitiveResult(
            amount=amount,
            rate=params.rate,
            tax_treatment="taxable",
            notes=f"TSU = {params.rate} * sum({', '.join(params.base_components)})",
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/primitives/test_tsu.py -v`
Expected: 6 passed.

- [ ] **Step 5: Populate primitives/__init__.py so registry is filled on package import**

Replace the contents of `logic/payroll/primitives/__init__.py` with:

```python
# Importing these submodules has the side-effect of firing their @register
# decorators, populating DEFAULT_REGISTRY whenever any code touches the
# `logic.payroll.primitives` package (which Python does eagerly the first time
# anything under it is imported — including `logic.payroll.primitives.base`).
from logic.payroll.primitives.base import (  # noqa: F401
    DEFAULT_REGISTRY, Primitive, PrimitiveRegistry, PrimitiveResult,
    ExecutionContext, register,
)
from logic.payroll.primitives import basesalary, tsu  # noqa: F401
```

- [ ] **Step 6: Smoke-test that DEFAULT_REGISTRY is populated on plain import**

Run:
```
python -c "from logic.payroll.primitives.base import DEFAULT_REGISTRY; print(sorted(DEFAULT_REGISTRY._by_name.keys()))"
```

Expected output: `['BaseSalary', 'TSUContribution']`.

- [ ] **Step 7: Re-run primitive tests to confirm nothing broke**

Run: `pytest tests/payroll/primitives/ -v`
Expected: all primitive tests still pass.

- [ ] **Step 8: Commit**

```
git add logic/payroll/primitives/tsu.py logic/payroll/primitives/__init__.py tests/payroll/primitives/test_tsu.py
git commit -m "feat: TSUContribution primitive + auto-register via primitives package"
```

---

### Task 15: Rule-document Pydantic models

**Files:**
- Create: `logic/payroll/rules/models.py`
- Create: `tests/payroll/rules/test_models.py`

The rule documents are layered YAML files that declare components, their primitive bindings, phase, parameters, dependencies, and taxability metadata. This task defines the Pydantic models that those YAMLs parse into.

- [ ] **Step 1: Write failing tests**

```python
# tests/payroll/rules/test_models.py
from decimal import Decimal
import pytest
from pydantic import ValidationError
from logic.payroll.rules.models import (
    ComponentDecl, RuleDocument, RuleDocumentMetadata,
)


def test_component_decl_minimal():
    c = ComponentDecl(
        type="earning",
        phase="gross",
        primitive="BaseSalary",
        parameters={},
        inputs_required=[],
        taxable=True,
    )
    assert c.disabled is False
    assert c.locked is False


def test_component_decl_unknown_phase_rejected():
    with pytest.raises(ValidationError):
        ComponentDecl(type="earning", phase="bogus", primitive="X", parameters={}, inputs_required=[])


def test_component_decl_unknown_type_rejected():
    with pytest.raises(ValidationError):
        ComponentDecl(type="freebie", phase="gross", primitive="X", parameters={}, inputs_required=[])


def test_rule_document_with_components():
    doc = RuleDocument(
        metadata=RuleDocumentMetadata(jurisdiction="PT", effective_from="2026-01-01", version="2026.1"),
        components={
            "base_salary": ComponentDecl(
                type="earning", phase="gross", primitive="BaseSalary",
                parameters={}, inputs_required=[], taxable=True,
            ),
            "tsu_employee": ComponentDecl(
                type="deduction", phase="tax", primitive="TSUContribution",
                parameters={"rate": "0.11", "base_components": ["base_salary"]},
                inputs_required=["base_salary"],
            ),
        },
    )
    assert "base_salary" in doc.components
    assert doc.components["tsu_employee"].primitive == "TSUContribution"


def test_disabled_component_via_explicit_flag():
    c = ComponentDecl(
        type="earning", phase="gross", primitive="X",
        parameters={}, inputs_required=[], disabled=True,
    )
    assert c.disabled is True
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `pytest tests/payroll/rules/test_models.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

```python
# logic/payroll/rules/models.py
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class RuleDocumentMetadata(BaseModel):
    model_config = ConfigDict(strict=True)

    jurisdiction: str
    effective_from: str
    version: str


class ComponentDecl(BaseModel):
    """Declaration of a payroll component within a rule document."""

    model_config = ConfigDict(strict=True)

    type: Literal["earning", "deduction", "employer_contribution"]
    phase: Literal["input", "gross", "pre_tax_deduction", "tax", "post_tax", "employer_contribution"]
    primitive: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    inputs_required: list[str] = Field(default_factory=list)
    taxable: bool = True
    subject_to_tsu: bool = True
    disabled: bool = False
    locked: bool = False  # higher layers cannot override `parameters` of a locked component
    clause: str | None = None  # canonical path inside the doc (e.g., "components.base_salary"); resolver fills in if absent


class RuleDocument(BaseModel):
    model_config = ConfigDict(strict=True)

    metadata: RuleDocumentMetadata
    components: dict[str, ComponentDecl] = Field(default_factory=dict)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/rules/test_models.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/rules/models.py tests/payroll/rules/test_models.py
git commit -m "feat: rule-document Pydantic models (RuleDocument, ComponentDecl)"
```

---

### Task 16: RuleLoader — YAML loading with float rejection

**Files:**
- Create: `logic/payroll/rules/loader.py`
- Create: `tests/payroll/rules/test_loader.py`
- Create: `business_rules/payroll/statutory_pt.yaml`
- Create: `business_rules/payroll/companies/default_company.yaml`

- [ ] **Step 1: Write failing tests**

```python
# tests/payroll/rules/test_loader.py
from pathlib import Path
import pytest
from logic.payroll.errors import RuleLoadError
from logic.payroll.rules.loader import RuleLoader, NoFloatYamlLoader


def test_loader_loads_minimal_statutory(tmp_path: Path):
    yaml_path = tmp_path / "statutory.yaml"
    yaml_path.write_text(
        """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
    taxable: true
""",
        encoding="utf-8",
    )
    loader = RuleLoader()
    doc = loader.load_document(yaml_path)
    assert doc.metadata.jurisdiction == "PT"
    assert "base_salary" in doc.components


def test_loader_rejects_float_literal(tmp_path: Path):
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text(
        """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: 0.11
      base_components: ["base_salary"]
    inputs_required: ["base_salary"]
""",
        encoding="utf-8",
    )
    loader = RuleLoader()
    with pytest.raises(RuleLoadError) as exc:
        loader.load_document(yaml_path)
    assert exc.value.code == "YAML_FLOAT_LITERAL"


def test_loader_accepts_quoted_decimal(tmp_path: Path):
    yaml_path = tmp_path / "ok.yaml"
    yaml_path.write_text(
        """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: "0.11"
      base_components: ["base_salary"]
    inputs_required: ["base_salary"]
""",
        encoding="utf-8",
    )
    loader = RuleLoader()
    doc = loader.load_document(yaml_path)
    assert doc.components["tsu_employee"].parameters["rate"] == "0.11"


def test_loader_missing_file_raises(tmp_path: Path):
    loader = RuleLoader()
    with pytest.raises(RuleLoadError) as exc:
        loader.load_document(tmp_path / "missing.yaml")
    assert exc.value.code == "YAML_FILE_NOT_FOUND"


def test_loader_invalid_schema_raises(tmp_path: Path):
    yaml_path = tmp_path / "bad_schema.yaml"
    yaml_path.write_text(
        """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: weird
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
""",
        encoding="utf-8",
    )
    loader = RuleLoader()
    with pytest.raises(RuleLoadError) as exc:
        loader.load_document(yaml_path)
    assert exc.value.code == "YAML_SCHEMA_INVALID"


def test_loader_caches_loaded_documents(tmp_path: Path):
    yaml_path = tmp_path / "statutory.yaml"
    yaml_path.write_text(
        """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components: {}
""",
        encoding="utf-8",
    )
    loader = RuleLoader()
    doc1 = loader.load_document(yaml_path)
    doc2 = loader.load_document(yaml_path)
    assert doc1 is doc2  # cached identity


def test_loader_reload_clears_cache(tmp_path: Path):
    yaml_path = tmp_path / "statutory.yaml"
    yaml_path.write_text(
        """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components: {}
""",
        encoding="utf-8",
    )
    loader = RuleLoader()
    doc1 = loader.load_document(yaml_path)
    loader.reload()
    doc2 = loader.load_document(yaml_path)
    assert doc1 is not doc2
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/payroll/rules/test_loader.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement loader**

```python
# logic/payroll/rules/loader.py
from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from pydantic import ValidationError
from logic.payroll.errors import RuleLoadError
from logic.payroll.rules.models import RuleDocument


class NoFloatYamlLoader(yaml.SafeLoader):
    """SafeLoader that refuses to coerce numeric scalars into Python floats.

    All numeric values in payroll YAML must be quoted strings (and parsed into
    `Decimal` later by Pydantic), to avoid the rounding errors inherent in float
    representation. Integer literals are still permitted (PyYAML parses them
    losslessly), but float literals (anything containing a decimal point or
    exponent) trigger a `RuleLoadError`.
    """


def _construct_float_rejecting(self: yaml.SafeLoader, node: yaml.ScalarNode) -> Any:
    raise yaml.constructor.ConstructorError(
        None, None,
        f"float literal {node.value!r} is not permitted in payroll YAML; quote the value to keep it as a string",
        node.start_mark,
    )


NoFloatYamlLoader.add_constructor(
    "tag:yaml.org,2002:float",
    _construct_float_rejecting,
)


class RuleLoader:
    def __init__(self) -> None:
        self._cache: dict[Path, RuleDocument] = {}

    def load_document(self, path: Path) -> RuleDocument:
        path = Path(path).resolve()
        if path in self._cache:
            return self._cache[path]
        if not path.exists():
            raise RuleLoadError(
                code="YAML_FILE_NOT_FOUND",
                msg_pt=f"ficheiro de regras não encontrado: {path}",
                msg_en=f"rule file not found: {path}",
            )
        text = path.read_text(encoding="utf-8")
        try:
            raw = yaml.load(text, Loader=NoFloatYamlLoader)
        except yaml.constructor.ConstructorError as ex:
            if "float literal" in (ex.problem or ""):
                raise RuleLoadError(
                    code="YAML_FLOAT_LITERAL",
                    msg_pt=f"literal float não permitido em {path}: {ex.problem}",
                    msg_en=f"float literal not permitted in {path}: {ex.problem}",
                ) from ex
            raise RuleLoadError(
                code="YAML_PARSE_ERROR",
                msg_pt=f"erro ao analisar YAML em {path}: {ex}",
                msg_en=f"YAML parse error in {path}: {ex}",
            ) from ex
        except yaml.YAMLError as ex:
            raise RuleLoadError(
                code="YAML_PARSE_ERROR",
                msg_pt=f"erro ao analisar YAML em {path}: {ex}",
                msg_en=f"YAML parse error in {path}: {ex}",
            ) from ex
        try:
            doc = RuleDocument.model_validate(raw)
        except ValidationError as ex:
            raise RuleLoadError(
                code="YAML_SCHEMA_INVALID",
                msg_pt=f"esquema inválido em {path}: {ex}",
                msg_en=f"invalid schema in {path}: {ex}",
            ) from ex
        self._cache[path] = doc
        return doc

    def reload(self) -> None:
        self._cache.clear()
```

- [ ] **Step 4: Write the minimal Plan 1 YAML files**

```yaml
# business_rules/payroll/statutory_pt.yaml
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
    taxable: true
    subject_to_tsu: true
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: "0.11"
      base_components: ["base_salary"]
    inputs_required: ["base_salary"]
    taxable: false
    subject_to_tsu: false
```

```yaml
# business_rules/payroll/companies/default_company.yaml
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components: {}
```

(The company layer is intentionally empty in Plan 1 — it exists so the resolver can layer it on top.)

- [ ] **Step 5: Run loader tests**

Run: `pytest tests/payroll/rules/test_loader.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```
git add logic/payroll/rules/loader.py tests/payroll/rules/test_loader.py business_rules/payroll/
git commit -m "feat: RuleLoader with float-literal rejection + minimal Plan 1 YAML"
```

---

### Task 17: Rule resolver — RuleStackSnapshot model

**Files:**
- Create: `logic/payroll/rules/resolver.py`
- Create: `tests/payroll/rules/test_resolver.py`

- [ ] **Step 1: Write failing test for the snapshot model**

```python
# tests/payroll/rules/test_resolver.py
from pathlib import Path
from logic.payroll.rules.resolver import RuleStackSnapshot, ResolvedComponent
from logic.payroll.public.schemas import RuleCitation


def test_rule_stack_snapshot_is_frozen():
    import dataclasses
    snap = RuleStackSnapshot(
        statutory_path=Path("/x/statutory.yaml"),
        cct_path=None,
        company_path=Path("/x/company.yaml"),
        resolved_components={},
    )
    assert dataclasses.is_dataclass(snap)
    import pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.cct_path = Path("/y/cct.yaml")  # type: ignore


def test_resolved_component_holds_citations():
    c = RuleCitation(document_path="x", layer="statutory", clause="components.base_salary")
    rc = ResolvedComponent(
        component_code="base_salary",
        type="earning",
        phase="gross",
        primitive="BaseSalary",
        parameters={},
        inputs_required=[],
        taxable=True,
        subject_to_tsu=True,
        locked=False,
        citations=[c],
    )
    assert rc.citations[0].layer == "statutory"
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `pytest tests/payroll/rules/test_resolver.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement the snapshot model**

```python
# logic/payroll/rules/resolver.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from logic.payroll.public.schemas import RuleCitation


class ResolvedComponent(BaseModel):
    model_config = ConfigDict(strict=True)

    component_code: str
    type: Literal["earning", "deduction", "employer_contribution"]
    phase: Literal["input", "gross", "pre_tax_deduction", "tax", "post_tax", "employer_contribution"]
    primitive: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    inputs_required: list[str] = Field(default_factory=list)
    taxable: bool = True
    subject_to_tsu: bool = True
    locked: bool = False
    citations: list[RuleCitation] = Field(default_factory=list)


@dataclass(frozen=True)
class RuleStackSnapshot:
    statutory_path: Path
    cct_path: Optional[Path]
    company_path: Optional[Path]
    resolved_components: dict[str, ResolvedComponent] = field(default_factory=dict)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/rules/test_resolver.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/rules/resolver.py tests/payroll/rules/test_resolver.py
git commit -m "feat: RuleStackSnapshot and ResolvedComponent models"
```

---

### Task 18: Rule resolver — layer merging logic

**Files:**
- Modify: `logic/payroll/rules/resolver.py`
- Modify: `tests/payroll/rules/test_resolver.py`

- [ ] **Step 1: Append failing tests**

```python
# Append to tests/payroll/rules/test_resolver.py
from logic.payroll.rules.resolver import RuleResolver
from logic.payroll.rules.loader import RuleLoader


def _write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_resolver_picks_up_statutory_only(tmp_path):
    statutory = _write(tmp_path, "statutory.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
""")
    company = _write(tmp_path, "company.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components: {}
""")
    loader = RuleLoader()
    resolver = RuleResolver(loader)
    snapshot = resolver.resolve(statutory_path=statutory, company_path=company)
    assert "base_salary" in snapshot.resolved_components
    cits = snapshot.resolved_components["base_salary"].citations
    assert len(cits) == 1
    assert cits[0].layer == "statutory"


def test_resolver_company_layer_overrides_statutory_scalar(tmp_path):
    statutory = _write(tmp_path, "statutory.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: "0.11"
      base_components: ["base_salary"]
    inputs_required: ["base_salary"]
""")
    company = _write(tmp_path, "company.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: "0.105"
    inputs_required: ["base_salary"]
""")
    loader = RuleLoader()
    resolver = RuleResolver(loader)
    snapshot = resolver.resolve(statutory_path=statutory, company_path=company)
    tsu = snapshot.resolved_components["tsu_employee"]
    assert tsu.parameters["rate"] == "0.105"
    layers = [c.layer for c in tsu.citations]
    assert "statutory" in layers and "company" in layers


def test_resolver_company_adds_new_component(tmp_path):
    statutory = _write(tmp_path, "statutory.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
""")
    company = _write(tmp_path, "company.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  meal_allowance:
    type: earning
    phase: gross
    primitive: MealAllowance
    parameters:
      daily_rate: "6.00"
    inputs_required: []
""")
    loader = RuleLoader()
    resolver = RuleResolver(loader)
    snapshot = resolver.resolve(statutory_path=statutory, company_path=company)
    assert "meal_allowance" in snapshot.resolved_components
    assert snapshot.resolved_components["meal_allowance"].citations[0].layer == "company"


def test_resolver_disabled_drops_component(tmp_path):
    statutory = _write(tmp_path, "statutory.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
""")
    company = _write(tmp_path, "company.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
    disabled: true
""")
    loader = RuleLoader()
    resolver = RuleResolver(loader)
    snapshot = resolver.resolve(statutory_path=statutory, company_path=company)
    assert "base_salary" not in snapshot.resolved_components


def test_resolver_locked_field_blocks_higher_override(tmp_path):
    from logic.payroll.errors import RuleValidationError
    import pytest
    statutory = _write(tmp_path, "statutory.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: "0.11"
    inputs_required: ["base_salary"]
    locked: true
""")
    company = _write(tmp_path, "company.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: "0.105"
    inputs_required: ["base_salary"]
""")
    loader = RuleLoader()
    resolver = RuleResolver(loader)
    with pytest.raises(RuleValidationError) as exc:
        resolver.resolve(statutory_path=statutory, company_path=company)
    assert exc.value.code == "LOCKED_COMPONENT_OVERRIDE"
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/payroll/rules/test_resolver.py -v`
Expected: 5 new tests FAIL.

- [ ] **Step 3: Implement the resolver**

Add the following imports to the top of `logic/payroll/rules/resolver.py` (merging with the existing import block from Task 17 — do NOT duplicate the existing imports):

```python
from logic.payroll.rules.loader import RuleLoader
from logic.payroll.rules.models import RuleDocument, ComponentDecl
from logic.payroll.errors import RuleValidationError
```

Then append the following definitions at the bottom of the file (after the existing `RuleStackSnapshot` dataclass):

```python


_LAYER_ORDER = ["statutory", "cct", "company"]


def _component_citation(layer: str, path: Path, code: str) -> RuleCitation:
    return RuleCitation(
        document_path=str(path),
        layer=layer,
        component_code=code,
        clause=f"components.{code}",
    )


def _merge_component(
    lower: ResolvedComponent | None,
    higher_decl: ComponentDecl,
    higher_layer: str,
    higher_path: Path,
    code: str,
) -> ResolvedComponent:
    if lower is not None and lower.locked:
        # Only allow merges that change `disabled`; reject parameter/structural overrides.
        if higher_decl.parameters or _structural_differs(lower, higher_decl):
            raise RuleValidationError(
                code="LOCKED_COMPONENT_OVERRIDE",
                msg_pt=f"componente {code!r} está bloqueado; camada {higher_layer!r} não pode sobrepor",
                msg_en=f"component {code!r} is locked; layer {higher_layer!r} cannot override it",
            )
    base_params = dict(lower.parameters) if lower is not None else {}
    base_params.update(higher_decl.parameters)  # higher layer wins for scalar params
    return ResolvedComponent(
        component_code=code,
        type=higher_decl.type if lower is None else lower.type,
        phase=higher_decl.phase if lower is None else lower.phase,
        primitive=higher_decl.primitive if lower is None else lower.primitive,
        parameters=base_params,
        inputs_required=higher_decl.inputs_required or (lower.inputs_required if lower else []),
        taxable=higher_decl.taxable if lower is None else lower.taxable,
        subject_to_tsu=higher_decl.subject_to_tsu if lower is None else lower.subject_to_tsu,
        locked=lower.locked if lower is not None else higher_decl.locked,
        citations=(lower.citations if lower else []) + [_component_citation(higher_layer, higher_path, code)],
    )


def _structural_differs(lower: ResolvedComponent, higher: ComponentDecl) -> bool:
    return (
        higher.type != lower.type
        or higher.phase != lower.phase
        or higher.primitive != lower.primitive
    )


class RuleResolver:
    def __init__(self, loader: RuleLoader) -> None:
        self._loader = loader

    def resolve(
        self,
        statutory_path: Path,
        cct_path: Optional[Path] = None,
        company_path: Optional[Path] = None,
    ) -> RuleStackSnapshot:
        layers: list[tuple[str, Path, RuleDocument]] = []
        layers.append(("statutory", statutory_path, self._loader.load_document(statutory_path)))
        if cct_path is not None:
            layers.append(("cct", cct_path, self._loader.load_document(cct_path)))
        if company_path is not None:
            layers.append(("company", company_path, self._loader.load_document(company_path)))

        resolved: dict[str, ResolvedComponent] = {}
        for layer_name, path, doc in layers:
            for code, decl in doc.components.items():
                if decl.disabled:
                    resolved.pop(code, None)
                    continue
                resolved[code] = _merge_component(
                    lower=resolved.get(code),
                    higher_decl=decl,
                    higher_layer=layer_name,
                    higher_path=path,
                    code=code,
                )

        return RuleStackSnapshot(
            statutory_path=statutory_path,
            cct_path=cct_path,
            company_path=company_path,
            resolved_components=resolved,
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/rules/test_resolver.py -v`
Expected: 7 passed (2 from Task 17 + 5 new).

- [ ] **Step 5: Commit**

```
git add logic/payroll/rules/resolver.py tests/payroll/rules/test_resolver.py
git commit -m "feat: RuleResolver layered merge with citations, disabled, locked"
```

---

### Task 19: CalculationPlan models + plan builder

**Files:**
- Create: `logic/payroll/rules/plan.py`
- Create: `tests/payroll/rules/test_plan.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/payroll/rules/test_plan.py
from pathlib import Path
from decimal import Decimal
import pytest
from logic.payroll.errors import RuleValidationError
from logic.payroll.rules.plan import (
    PlanStep, CalculationPlan, CalculationPlanBuilder, PHASE_ORDER,
)
from logic.payroll.rules.resolver import RuleResolver, RuleStackSnapshot, ResolvedComponent
from logic.payroll.rules.loader import RuleLoader
from logic.payroll.primitives.base import DEFAULT_REGISTRY
from logic.payroll.rounding import RoundingPolicy
from logic.payroll.public.schemas import RuleCitation


def _make_snapshot_with(components: dict[str, ResolvedComponent]) -> RuleStackSnapshot:
    return RuleStackSnapshot(
        statutory_path=Path("/x/statutory.yaml"),
        cct_path=None,
        company_path=Path("/x/company.yaml"),
        resolved_components=components,
    )


def _comp(code: str, phase: str, primitive: str, params=None, inputs_required=None, type_="earning") -> ResolvedComponent:
    return ResolvedComponent(
        component_code=code, type=type_, phase=phase, primitive=primitive,
        parameters=params or {}, inputs_required=inputs_required or [],
        citations=[RuleCitation(document_path="x", layer="statutory", clause=f"components.{code}")],
    )


def test_phase_order_constant():
    assert PHASE_ORDER == ["input", "gross", "pre_tax_deduction", "tax", "post_tax", "employer_contribution"]


def test_plan_builder_emits_steps_in_phase_order():
    snap = _make_snapshot_with({
        "tsu_employee": _comp("tsu_employee", "tax", "TSUContribution",
                              params={"rate": "0.11", "base_components": ["base_salary"]},
                              inputs_required=["base_salary"], type_="deduction"),
        "base_salary": _comp("base_salary", "gross", "BaseSalary"),
    })
    builder = CalculationPlanBuilder(registry=DEFAULT_REGISTRY)
    plan = builder.build(
        snapshot=snap,
        employee_id="e-1", contract_id="c-1", period_id="2026-05",
        company_id="acme", rounding_policy=RoundingPolicy(),
    )
    phases_emitted = [step.phase for step in plan.steps]
    assert phases_emitted == ["gross", "tax"]
    codes = [s.component_code for s in plan.steps]
    assert codes == ["base_salary", "tsu_employee"]


def test_plan_builder_topological_sort_within_phase():
    snap = _make_snapshot_with({
        "b": _comp("b", "gross", "BaseSalary", inputs_required=["a"]),
        "a": _comp("a", "gross", "BaseSalary"),
    })
    builder = CalculationPlanBuilder(registry=DEFAULT_REGISTRY)
    plan = builder.build(
        snapshot=snap, employee_id="e", contract_id="c",
        period_id="p", company_id="x", rounding_policy=RoundingPolicy(),
    )
    codes = [s.component_code for s in plan.steps]
    assert codes == ["a", "b"]


def test_plan_builder_unknown_primitive_raises():
    snap = _make_snapshot_with({
        "x": _comp("x", "gross", "NonexistentPrimitive"),
    })
    builder = CalculationPlanBuilder(registry=DEFAULT_REGISTRY)
    with pytest.raises(RuleValidationError) as exc:
        builder.build(
            snapshot=snap, employee_id="e", contract_id="c",
            period_id="p", company_id="x", rounding_policy=RoundingPolicy(),
        )
    assert exc.value.code == "UNKNOWN_PRIMITIVE"


def test_plan_builder_missing_dependency_raises():
    snap = _make_snapshot_with({
        "tsu_employee": _comp("tsu_employee", "tax", "TSUContribution",
                              params={"rate": "0.11", "base_components": ["base_salary"]},
                              inputs_required=["base_salary"], type_="deduction"),
    })
    builder = CalculationPlanBuilder(registry=DEFAULT_REGISTRY)
    with pytest.raises(RuleValidationError) as exc:
        builder.build(
            snapshot=snap, employee_id="e", contract_id="c",
            period_id="p", company_id="x", rounding_policy=RoundingPolicy(),
        )
    assert exc.value.code == "UNRESOLVED_DEPENDENCY"


def test_plan_builder_param_schema_validation():
    snap = _make_snapshot_with({
        "tsu_employee": _comp("tsu_employee", "tax", "TSUContribution",
                              params={"rate": "not-a-number"}, type_="deduction"),
    })
    builder = CalculationPlanBuilder(registry=DEFAULT_REGISTRY)
    with pytest.raises(RuleValidationError) as exc:
        builder.build(
            snapshot=snap, employee_id="e", contract_id="c",
            period_id="p", company_id="x", rounding_policy=RoundingPolicy(),
        )
    assert exc.value.code == "PARAMETER_SCHEMA_INVALID"
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/payroll/rules/test_plan.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

```python
# logic/payroll/rules/plan.py
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from logic.payroll.errors import RuleValidationError
from logic.payroll.primitives.base import PrimitiveRegistry
from logic.payroll.rounding import RoundingPolicy
from logic.payroll.public.schemas import RuleCitation
from logic.payroll.rules.resolver import RuleStackSnapshot, ResolvedComponent


PHASE_ORDER = [
    "input",
    "gross",
    "pre_tax_deduction",
    "tax",
    "post_tax",
    "employer_contribution",
]


class PlanStep(BaseModel):
    model_config = ConfigDict(strict=True)

    index: int = Field(ge=0)
    phase: str
    component_code: str
    primitive_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    inputs_required: list[str] = Field(default_factory=list)
    citations: list[RuleCitation] = Field(default_factory=list)


class CalculationPlan(BaseModel):
    model_config = ConfigDict(strict=True)

    employee_id: str
    contract_id: str
    period_id: str
    company_id: str
    rounding_policy: RoundingPolicy
    steps: list[PlanStep] = Field(default_factory=list)


def _topological_sort(components: list[ResolvedComponent]) -> list[ResolvedComponent]:
    by_code = {c.component_code: c for c in components}
    visited: set[str] = set()
    ordered: list[ResolvedComponent] = []

    def visit(c: ResolvedComponent, stack: tuple[str, ...] = ()) -> None:
        if c.component_code in visited:
            return
        if c.component_code in stack:
            raise RuleValidationError(
                code="CYCLIC_DEPENDENCY",
                msg_pt=f"ciclo de dependências detectado: {stack + (c.component_code,)}",
                msg_en=f"cyclic dependency detected: {stack + (c.component_code,)}",
            )
        for dep in c.inputs_required:
            if dep in by_code:
                visit(by_code[dep], stack + (c.component_code,))
        visited.add(c.component_code)
        ordered.append(c)

    for c in components:
        visit(c)
    return ordered


class CalculationPlanBuilder:
    def __init__(self, registry: PrimitiveRegistry) -> None:
        self._registry = registry

    def build(
        self,
        snapshot: RuleStackSnapshot,
        employee_id: str,
        contract_id: str,
        period_id: str,
        company_id: str,
        rounding_policy: RoundingPolicy,
    ) -> CalculationPlan:
        all_codes = set(snapshot.resolved_components.keys())
        for comp in snapshot.resolved_components.values():
            for dep in comp.inputs_required:
                if dep not in all_codes:
                    raise RuleValidationError(
                        code="UNRESOLVED_DEPENDENCY",
                        msg_pt=f"componente {comp.component_code!r} depende de {dep!r}, que não existe",
                        msg_en=f"component {comp.component_code!r} depends on {dep!r}, which does not exist in the resolved stack",
                    )
            try:
                self._registry.get(comp.primitive)
            except KeyError as ex:
                raise RuleValidationError(
                    code="UNKNOWN_PRIMITIVE",
                    msg_pt=f"primitiva {comp.primitive!r} não registada",
                    msg_en=f"primitive {comp.primitive!r} is not registered",
                ) from ex
            prim_cls = self._registry.get(comp.primitive)
            try:
                prim_cls.parameter_schema.model_validate(comp.parameters)
            except ValidationError as ex:
                raise RuleValidationError(
                    code="PARAMETER_SCHEMA_INVALID",
                    msg_pt=f"parâmetros inválidos para {comp.component_code!r}: {ex}",
                    msg_en=f"invalid parameters for {comp.component_code!r}: {ex}",
                ) from ex

        steps: list[PlanStep] = []
        for phase in PHASE_ORDER:
            in_phase = [c for c in snapshot.resolved_components.values() if c.phase == phase]
            if not in_phase:
                continue
            for comp in _topological_sort(in_phase):
                steps.append(PlanStep(
                    index=len(steps),
                    phase=phase,
                    component_code=comp.component_code,
                    primitive_name=comp.primitive,
                    parameters=comp.parameters,
                    inputs_required=comp.inputs_required,
                    citations=comp.citations,
                ))

        return CalculationPlan(
            employee_id=employee_id,
            contract_id=contract_id,
            period_id=period_id,
            company_id=company_id,
            rounding_policy=rounding_policy,
            steps=steps,
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/rules/test_plan.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/rules/plan.py tests/payroll/rules/test_plan.py
git commit -m "feat: CalculationPlanBuilder with phase ordering, topo sort, schema validation"
```

---

### Task 20: TimeInput normaliser

**Files:**
- Create: `logic/payroll/engine/time_input.py`
- Create: `tests/payroll/engine/test_time_input.py`

For Plan 1, the normaliser is a stub: it passes through the raw `TimeInput`. The interface exists so Plan 2's full implementation (overtime computation, absence intersection) can slot in.

- [ ] **Step 1: Write failing tests**

```python
# tests/payroll/engine/test_time_input.py
from decimal import Decimal
from logic.payroll.engine.time_input import normalize_time_input
from logic.payroll.public.schemas import TimeInput


def test_normalize_passes_through_in_plan_1():
    ti = TimeInput(period_id="2026-05", employee_id="e-1", normal_hours=Decimal("160"))
    out = normalize_time_input(ti)
    assert out is ti  # Plan 1 is a no-op


def test_normalize_empty_meal_days_default():
    ti = TimeInput(period_id="p", employee_id="e", normal_hours=Decimal("0"))
    out = normalize_time_input(ti)
    assert out.meal_allowance_days == 0
```

- [ ] **Step 2: Run test**

Run: `pytest tests/payroll/engine/test_time_input.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

```python
# logic/payroll/engine/time_input.py
from __future__ import annotations
from logic.payroll.public.schemas import TimeInput


def normalize_time_input(raw: TimeInput) -> TimeInput:
    """Normalise raw TimeInput into payable form.

    Plan 1 is a no-op pass-through. Plan 2 expands this to compute payable
    overtime, intersect absences with the period, and derive hourly rates.
    """
    return raw
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/engine/test_time_input.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/engine/time_input.py tests/payroll/engine/test_time_input.py
git commit -m "feat: TimeInput normaliser (Plan 1 stub)"
```

---

### Task 21: Audit-trail rendering helper

**Files:**
- Create: `logic/payroll/engine/audit.py`
- Create: `tests/payroll/engine/test_audit.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/payroll/engine/test_audit.py
from datetime import datetime, timezone
from logic.payroll.engine.audit import select_primary_citation, render_citation_text
from logic.payroll.public.schemas import RuleCitation


def test_select_primary_citation_picks_highest_priority():
    cits = [
        RuleCitation(document_path="x", layer="statutory", clause="c"),
        RuleCitation(document_path="y", layer="company", clause="c"),
    ]
    primary = select_primary_citation(cits)
    assert primary.layer == "company"


def test_select_primary_citation_returns_only_when_single():
    cits = [RuleCitation(document_path="x", layer="statutory", clause="c")]
    primary = select_primary_citation(cits)
    assert primary.layer == "statutory"


def test_render_citation_text_basic():
    cit = RuleCitation(document_path="business_rules/payroll/statutory_pt.yaml",
                       layer="statutory", component_code="base_salary",
                       clause="components.base_salary")
    text = render_citation_text(cit)
    assert "statutory_pt.yaml" in text
    assert "components.base_salary" in text
```

- [ ] **Step 2: Run test**

Run: `pytest tests/payroll/engine/test_audit.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

```python
# logic/payroll/engine/audit.py
from __future__ import annotations
from logic.payroll.public.schemas import RuleCitation


_LAYER_PRIORITY = {"statutory": 0, "cct": 1, "company": 2, "contract": 3}


def select_primary_citation(citations: list[RuleCitation]) -> RuleCitation:
    """Pick the highest-priority citation from a merge chain.

    The highest-priority layer is the one whose values actually appear in the
    resolved component — i.e., the layer that "won" the merge. If multiple
    citations share the highest priority, the last one in the list wins.
    """
    if not citations:
        raise ValueError("select_primary_citation requires at least one citation")
    return max(citations, key=lambda c: _LAYER_PRIORITY[c.layer])


def render_citation_text(cit: RuleCitation) -> str:
    """Render a citation as a one-line human-readable string for AI consumption."""
    parts = [f"[{cit.layer}] {cit.document_path}::{cit.clause}"]
    if cit.component_code:
        parts.append(f"(component: {cit.component_code})")
    return " ".join(parts)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/engine/test_audit.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/engine/audit.py tests/payroll/engine/test_audit.py
git commit -m "feat: citation selection and rendering helpers"
```

---

### Task 22: Executor — execute CalculationPlan → PayslipResult

**Files:**
- Create: `logic/payroll/engine/executor.py`
- Create: `tests/payroll/engine/test_executor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/payroll/engine/test_executor.py
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytest
from logic.payroll.engine.executor import Executor
from logic.payroll.rules.plan import CalculationPlan, PlanStep
from logic.payroll.primitives.base import ExecutionContext, DEFAULT_REGISTRY
from logic.payroll.rounding import RoundingPolicy
from logic.payroll.clock import FixedClock
from logic.payroll.public.schemas import (
    Employee, Contract, FiscalProfile, Company, PayrollPeriod,
    RuleCitation, TimeInput,
)


def _ctx(salary: Decimal = Decimal("1500")) -> ExecutionContext:
    company = Company(
        company_id="acme", legal_name="Acme", tax_id="500000000",
        default_rounding_policy=RoundingPolicy(),
    )
    employee = Employee(
        employee_id="e-1", full_name="Maria", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="solteiro_sem_dependentes"),
    )
    contract = Contract(
        contract_id="c-1", employee_id="e-1", type="CT",
        start_date=date(2025, 1, 1), role_category="dev",
        weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
        base_monthly_salary=salary, company_id="acme",
    )
    period = PayrollPeriod(
        period_id="2026-05", company_id="acme", pay_frequency="monthly",
        start_date=date(2026, 5, 1), end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    )
    return ExecutionContext(
        period=period, contract=contract, employee=employee, company=company,
        rounding_policy=RoundingPolicy(),
        clock=FixedClock(datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)),
    )


def _plan_base_plus_tsu() -> CalculationPlan:
    cit_base = RuleCitation(document_path="statutory.yaml", layer="statutory", clause="components.base_salary")
    cit_tsu = RuleCitation(document_path="statutory.yaml", layer="statutory", clause="components.tsu_employee")
    return CalculationPlan(
        employee_id="e-1", contract_id="c-1", period_id="2026-05", company_id="acme",
        rounding_policy=RoundingPolicy(),
        steps=[
            PlanStep(
                index=0, phase="gross", component_code="base_salary",
                primitive_name="BaseSalary", parameters={}, inputs_required=[],
                citations=[cit_base],
            ),
            PlanStep(
                index=1, phase="tax", component_code="tsu_employee",
                primitive_name="TSUContribution",
                parameters={"rate": "0.11", "base_components": ["base_salary"]},
                inputs_required=["base_salary"],
                citations=[cit_tsu],
            ),
        ],
    )


def test_executor_simple_base_plus_tsu():
    plan = _plan_base_plus_tsu()
    ctx = _ctx(Decimal("1500"))
    ti = TimeInput(period_id="2026-05", employee_id="e-1", normal_hours=Decimal("160"))
    executor = Executor(registry=DEFAULT_REGISTRY)
    result = executor.execute(plan=plan, context=ctx, time_input=ti)

    assert len(result.gross_earnings) == 1
    assert result.gross_earnings[0].amount == Decimal("1500.00")
    assert result.gross_earnings[0].tax_treatment == "taxable"

    assert len(result.deductions) == 1
    assert result.deductions[0].amount == Decimal("165.00")

    assert result.net_pay == Decimal("1335.00")
    assert len(result.audit) == 2
    assert result.audit[0].primitive == "BaseSalary"
    assert result.audit[1].primitive == "TSUContribution"


def test_executor_audit_entries_have_timestamps_and_citations():
    plan = _plan_base_plus_tsu()
    ctx = _ctx()
    ti = TimeInput(period_id="2026-05", employee_id="e-1", normal_hours=Decimal("160"))
    executor = Executor(registry=DEFAULT_REGISTRY)
    result = executor.execute(plan=plan, context=ctx, time_input=ti)

    for entry in result.audit:
        assert entry.timestamp == datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
        assert entry.rule_citation.layer == "statutory"


def test_executor_payslip_line_audit_refs_resolve():
    plan = _plan_base_plus_tsu()
    ctx = _ctx()
    ti = TimeInput(period_id="2026-05", employee_id="e-1", normal_hours=Decimal("160"))
    executor = Executor(registry=DEFAULT_REGISTRY)
    result = executor.execute(plan=plan, context=ctx, time_input=ti)
    for line in result.gross_earnings + result.deductions:
        assert 0 <= line.source_audit_ref < len(result.audit)
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/payroll/engine/test_executor.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

```python
# logic/payroll/engine/executor.py
from __future__ import annotations
from decimal import Decimal
from logic.payroll.primitives.base import ExecutionContext, PrimitiveRegistry, PrimitiveResult
from logic.payroll.rules.plan import CalculationPlan, PlanStep
from logic.payroll.public.schemas import (
    AuditTrailEntry, PayslipLine, PayslipResult, TimeInput,
)
from logic.payroll.engine.audit import select_primary_citation


class Executor:
    def __init__(self, registry: PrimitiveRegistry) -> None:
        self._registry = registry

    def execute(
        self,
        plan: CalculationPlan,
        context: ExecutionContext,
        time_input: TimeInput,
    ) -> PayslipResult:
        gross_earnings: list[PayslipLine] = []
        deductions: list[PayslipLine] = []
        employer_contributions: list[PayslipLine] = []
        audit: list[AuditTrailEntry] = []
        produced: dict[str, Decimal] = {}

        for step in plan.steps:
            prim_cls = self._registry.get(step.primitive_name)
            params = prim_cls.parameter_schema.model_validate(step.parameters)
            inputs_payload = self._build_inputs(step, prim_cls, produced)
            inputs = prim_cls.input_schema.model_validate(inputs_payload)
            primitive = prim_cls()
            result: PrimitiveResult = primitive.execute(params, inputs, context)

            audit_entry = AuditTrailEntry(
                step_index=step.index,
                primitive=step.primitive_name,
                inputs_snapshot=inputs.model_dump(mode="json"),
                output=result.model_dump(mode="json"),
                rule_citation=select_primary_citation(step.citations),
                timestamp=context.clock.now(),
            )
            audit.append(audit_entry)

            line = PayslipLine(
                component_code=step.component_code,
                description=result.notes or step.component_code,
                amount=result.amount,
                quantity=result.quantity,
                rate=result.rate,
                tax_treatment=result.tax_treatment,
                exempt_amount=result.exempt_amount,
                source_audit_ref=step.index,
            )
            self._route_line(step, line, gross_earnings, deductions, employer_contributions)
            produced[step.component_code] = result.amount

        gross_total = sum((l.amount for l in gross_earnings), start=Decimal("0"))
        deduction_total = sum((l.amount for l in deductions), start=Decimal("0"))
        net = context.rounding_policy.apply(gross_total - deduction_total)

        return PayslipResult(
            period_id=plan.period_id,
            employee_id=plan.employee_id,
            gross_earnings=gross_earnings,
            deductions=deductions,
            employer_contributions=employer_contributions,
            net_pay=net,
            audit=audit,
        )

    @staticmethod
    def _build_inputs(step: PlanStep, prim_cls, produced: dict[str, Decimal]) -> dict:
        """Construct the inputs payload for a primitive based on its declared input schema."""
        # Convention: if a primitive's input_schema has a `component_values: dict[str, Decimal]` field,
        # we populate it with the upstream component amounts named in `step.inputs_required`.
        field_names = set(prim_cls.input_schema.model_fields.keys())
        payload: dict = {}
        if "component_values" in field_names:
            payload["component_values"] = {
                code: produced[code] for code in step.inputs_required if code in produced
            }
        return payload

    @staticmethod
    def _route_line(step: PlanStep, line: PayslipLine,
                    gross: list[PayslipLine], dedu: list[PayslipLine], emp: list[PayslipLine]) -> None:
        if step.phase in ("gross",):
            gross.append(line)
        elif step.phase in ("pre_tax_deduction", "tax", "post_tax"):
            dedu.append(line)
        elif step.phase == "employer_contribution":
            emp.append(line)
        # phase "input" produces no payslip line
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/engine/test_executor.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/engine/executor.py tests/payroll/engine/test_executor.py
git commit -m "feat: Executor produces PayslipResult with audit and line routing"
```

---

### Task 23: Repository interfaces (Protocols)

**Files:**
- Create: `db/repositories/interfaces.py`
- Create: `tests/payroll/repositories/test_memory.py` (test file lives here even though the protocols don't have behaviour yet — we test the in-memory implementation in the next task and the protocols by inference)

- [ ] **Step 1: Write protocol definitions**

```python
# db/repositories/interfaces.py
from __future__ import annotations
from typing import Protocol, Optional
from logic.payroll.public.schemas import (
    Employee, Contract, PayrollPeriod, TimeInput, PayslipResult,
)


class EmployeeRepository(Protocol):
    def upsert(self, employee: Employee) -> Employee: ...
    def get(self, employee_id: str) -> Optional[Employee]: ...


class ContractRepository(Protocol):
    def upsert(self, contract: Contract) -> Contract: ...
    def get(self, contract_id: str) -> Optional[Contract]: ...
    def get_for_employee(self, employee_id: str) -> Optional[Contract]: ...


class PeriodRepository(Protocol):
    def upsert(self, period: PayrollPeriod) -> PayrollPeriod: ...
    def get(self, period_id: str) -> Optional[PayrollPeriod]: ...


class TimeInputRepository(Protocol):
    def upsert(self, time_input: TimeInput) -> TimeInput: ...
    def get(self, period_id: str, employee_id: str) -> Optional[TimeInput]: ...


class PayslipRepository(Protocol):
    def upsert(self, payslip: PayslipResult) -> PayslipResult: ...
    def get(self, period_id: str, employee_id: str) -> Optional[PayslipResult]: ...
```

- [ ] **Step 2: Verify import**

Run:
```
python -c "from db.repositories.interfaces import EmployeeRepository, ContractRepository, PeriodRepository, TimeInputRepository, PayslipRepository; print('OK')"
```

Expected: prints `OK`.

- [ ] **Step 3: Commit**

```
git add db/repositories/interfaces.py
git commit -m "feat: repository protocols for payroll persistence boundary"
```

---

### Task 24: In-memory repository fakes

**Files:**
- Create: `db/repositories/memory.py`
- Modify: `tests/payroll/repositories/test_memory.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/payroll/repositories/test_memory.py
from datetime import date
from decimal import Decimal
from db.repositories.memory import (
    InMemoryEmployeeRepository, InMemoryContractRepository,
    InMemoryPeriodRepository, InMemoryTimeInputRepository,
    InMemoryPayslipRepository,
)
from logic.payroll.public.schemas import (
    Employee, Contract, FiscalProfile, PayrollPeriod, TimeInput,
    PayslipResult,
)


def _employee():
    return Employee(
        employee_id="e-1", full_name="Maria", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="x"),
    )


def _contract():
    return Contract(
        contract_id="c-1", employee_id="e-1", type="CT",
        start_date=date(2025, 1, 1), role_category="dev",
        weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
        base_monthly_salary=Decimal("1500"), company_id="acme",
    )


def _period():
    return PayrollPeriod(
        period_id="2026-05", company_id="acme", pay_frequency="monthly",
        start_date=date(2026, 5, 1), end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    )


def test_employee_repo_upsert_then_get():
    repo = InMemoryEmployeeRepository()
    repo.upsert(_employee())
    e = repo.get("e-1")
    assert e is not None and e.employee_id == "e-1"


def test_employee_repo_missing_returns_none():
    repo = InMemoryEmployeeRepository()
    assert repo.get("nope") is None


def test_contract_repo_get_for_employee():
    repo = InMemoryContractRepository()
    repo.upsert(_contract())
    c = repo.get_for_employee("e-1")
    assert c is not None and c.contract_id == "c-1"


def test_period_repo_upsert_then_get():
    repo = InMemoryPeriodRepository()
    repo.upsert(_period())
    p = repo.get("2026-05")
    assert p is not None


def test_time_input_repo_keyed_by_period_and_employee():
    repo = InMemoryTimeInputRepository()
    ti = TimeInput(period_id="2026-05", employee_id="e-1", normal_hours=Decimal("160"))
    repo.upsert(ti)
    assert repo.get("2026-05", "e-1") is not None
    assert repo.get("2026-05", "other") is None


def test_payslip_repo_upsert_then_get():
    repo = InMemoryPayslipRepository()
    payslip = PayslipResult(period_id="2026-05", employee_id="e-1", net_pay=Decimal("1335"))
    repo.upsert(payslip)
    out = repo.get("2026-05", "e-1")
    assert out is not None and out.net_pay == Decimal("1335")
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/payroll/repositories/test_memory.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

```python
# db/repositories/memory.py
from __future__ import annotations
from typing import Optional
from logic.payroll.public.schemas import (
    Employee, Contract, PayrollPeriod, TimeInput, PayslipResult,
)


class InMemoryEmployeeRepository:
    def __init__(self) -> None:
        self._store: dict[str, Employee] = {}

    def upsert(self, employee: Employee) -> Employee:
        self._store[employee.employee_id] = employee
        return employee

    def get(self, employee_id: str) -> Optional[Employee]:
        return self._store.get(employee_id)


class InMemoryContractRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, Contract] = {}
        self._by_employee: dict[str, Contract] = {}

    def upsert(self, contract: Contract) -> Contract:
        self._by_id[contract.contract_id] = contract
        self._by_employee[contract.employee_id] = contract
        return contract

    def get(self, contract_id: str) -> Optional[Contract]:
        return self._by_id.get(contract_id)

    def get_for_employee(self, employee_id: str) -> Optional[Contract]:
        return self._by_employee.get(employee_id)


class InMemoryPeriodRepository:
    def __init__(self) -> None:
        self._store: dict[str, PayrollPeriod] = {}

    def upsert(self, period: PayrollPeriod) -> PayrollPeriod:
        self._store[period.period_id] = period
        return period

    def get(self, period_id: str) -> Optional[PayrollPeriod]:
        return self._store.get(period_id)


class InMemoryTimeInputRepository:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], TimeInput] = {}

    def upsert(self, time_input: TimeInput) -> TimeInput:
        self._store[(time_input.period_id, time_input.employee_id)] = time_input
        return time_input

    def get(self, period_id: str, employee_id: str) -> Optional[TimeInput]:
        return self._store.get((period_id, employee_id))


class InMemoryPayslipRepository:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], PayslipResult] = {}

    def upsert(self, payslip: PayslipResult) -> PayslipResult:
        self._store[(payslip.period_id, payslip.employee_id)] = payslip
        return payslip

    def get(self, period_id: str, employee_id: str) -> Optional[PayslipResult]:
        return self._store.get((period_id, employee_id))
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/repositories/test_memory.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```
git add db/repositories/memory.py tests/payroll/repositories/test_memory.py
git commit -m "feat: in-memory repository fakes for payroll testing"
```

---

### Task 25: Service request DTOs

**Files:**
- Create: `logic/payroll/public/schemas/requests.py`
- Modify: `logic/payroll/public/schemas/__init__.py`

- [ ] **Step 1: Write the DTOs**

```python
# logic/payroll/public/schemas/requests.py
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from logic.payroll.public.schemas.identity import FiscalProfile, CCTReference


class CreateEmployeeInput(BaseModel):
    model_config = ConfigDict(strict=True)

    employee_id: str
    full_name: str
    tax_id: str
    social_security_id: str
    birth_date: date
    hire_date: date
    fiscal_profile: FiscalProfile
    bank_iban: Optional[str] = None


class CreateContractInput(BaseModel):
    model_config = ConfigDict(strict=True)

    contract_id: str
    employee_id: str
    type: Literal["CT", "CTT", "CTI", "part_time", "internship"]
    start_date: date
    end_date: Optional[date] = None
    role_category: str
    weekly_hours: Decimal = Field(gt=Decimal("0"))
    fte_percent: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    base_monthly_salary: Decimal = Field(ge=Decimal("0"))
    cct_reference: Optional[CCTReference] = None
    company_id: str
    pay_frequency: Literal["monthly", "biweekly", "weekly"] = "monthly"


class PeriodDefinition(BaseModel):
    model_config = ConfigDict(strict=True)

    period_id: str
    pay_frequency: Literal["monthly", "biweekly", "weekly"] = "monthly"
    start_date: date
    end_date: date
    pay_date: date


class TimeInputDraft(BaseModel):
    model_config = ConfigDict(strict=True)

    normal_hours: Decimal = Field(ge=Decimal("0"))
    meal_allowance_days: int = Field(ge=0, default=0)
    notes: str = ""
```

- [ ] **Step 2: Extend __init__.py re-exports**

Append to `logic/payroll/public/schemas/__init__.py`:

```python
from logic.payroll.public.schemas.requests import (
    CreateEmployeeInput, CreateContractInput, PeriodDefinition, TimeInputDraft,
)

__all__ = __all__ + [
    "CreateEmployeeInput", "CreateContractInput", "PeriodDefinition", "TimeInputDraft",
]
```

- [ ] **Step 3: Verify**

Run:
```
python -c "from logic.payroll.public.schemas import CreateEmployeeInput, PeriodDefinition; print('OK')"
```

Expected: prints `OK`.

- [ ] **Step 4: Commit**

```
git add logic/payroll/public/schemas/requests.py logic/payroll/public/schemas/__init__.py
git commit -m "feat: request DTOs for PayrollService inputs"
```

---

### Task 26: PayrollService — construction + registry methods

**Files:**
- Create: `logic/payroll/public/service.py`
- Create: `tests/payroll/service/test_dry_run.py`

This task creates the service shell with employee/contract registration and getters.

- [ ] **Step 1: Write failing tests**

```python
# tests/payroll/service/test_dry_run.py
from datetime import date
from decimal import Decimal
from pathlib import Path
import pytest
from logic.payroll.errors import MissingInput
from logic.payroll.public.service import PayrollService
from logic.payroll.public.schemas import (
    CreateEmployeeInput, CreateContractInput, FiscalProfile, PeriodDefinition,
    TimeInputDraft,
)
from logic.payroll.primitives.base import DEFAULT_REGISTRY
from logic.payroll.rounding import RoundingPolicy
from logic.payroll.rules.loader import RuleLoader
from logic.payroll.clock import FixedClock
from db.repositories.memory import (
    InMemoryEmployeeRepository, InMemoryContractRepository,
    InMemoryPeriodRepository, InMemoryTimeInputRepository,
    InMemoryPayslipRepository,
)
from datetime import datetime, timezone


@pytest.fixture
def service(tmp_path: Path):
    statutory = tmp_path / "statutory.yaml"
    statutory.write_text("""
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: "0.11"
      base_components: ["base_salary"]
    inputs_required: ["base_salary"]
""", encoding="utf-8")
    company = tmp_path / "company.yaml"
    company.write_text("""
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components: {}
""", encoding="utf-8")
    return PayrollService(
        employee_repo=InMemoryEmployeeRepository(),
        contract_repo=InMemoryContractRepository(),
        period_repo=InMemoryPeriodRepository(),
        time_input_repo=InMemoryTimeInputRepository(),
        payslip_repo=InMemoryPayslipRepository(),
        rule_loader=RuleLoader(),
        primitive_registry=DEFAULT_REGISTRY,
        clock=FixedClock(datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)),
        statutory_path=statutory,
        company_path=company,
    )


def test_create_employee_and_get(service):
    service.create_employee(CreateEmployeeInput(
        employee_id="e-1", full_name="Maria", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="solteiro_sem_dependentes"),
    ))
    e = service.get_employee("e-1")
    assert e.employee_id == "e-1"


def test_get_employee_missing_raises(service):
    with pytest.raises(MissingInput) as exc:
        service.get_employee("nope")
    assert exc.value.code == "EMPLOYEE_NOT_FOUND"


def test_create_contract_and_link(service):
    service.create_employee(CreateEmployeeInput(
        employee_id="e-1", full_name="x", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="x"),
    ))
    service.create_contract(CreateContractInput(
        contract_id="c-1", employee_id="e-1", type="CT",
        start_date=date(2025, 1, 1), role_category="dev",
        weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
        base_monthly_salary=Decimal("1500"), company_id="acme",
    ))
    c = service.get_contract_for_employee("e-1")
    assert c.contract_id == "c-1"


def test_create_contract_without_employee_raises(service):
    with pytest.raises(MissingInput) as exc:
        service.create_contract(CreateContractInput(
            contract_id="c-1", employee_id="nope", type="CT",
            start_date=date(2025, 1, 1), role_category="dev",
            weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
            base_monthly_salary=Decimal("1500"), company_id="acme",
        ))
    assert exc.value.code == "EMPLOYEE_NOT_FOUND"
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/payroll/service/test_dry_run.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement service shell + registry methods**

```python
# logic/payroll/public/service.py
from __future__ import annotations
from pathlib import Path
from typing import Optional
from logic.payroll.errors import MissingInput
from logic.payroll.public.schemas import (
    Employee, Contract, FiscalProfile, PayrollPeriod, TimeInput,
    CreateEmployeeInput, CreateContractInput, PeriodDefinition,
    TimeInputDraft, PayslipResult,
)
from logic.payroll.primitives.base import PrimitiveRegistry
from logic.payroll.rules.loader import RuleLoader
from logic.payroll.clock import Clock
from db.repositories.interfaces import (
    EmployeeRepository, ContractRepository, PeriodRepository,
    TimeInputRepository, PayslipRepository,
)


class PayrollService:
    def __init__(
        self,
        employee_repo: EmployeeRepository,
        contract_repo: ContractRepository,
        period_repo: PeriodRepository,
        time_input_repo: TimeInputRepository,
        payslip_repo: PayslipRepository,
        rule_loader: RuleLoader,
        primitive_registry: PrimitiveRegistry,
        clock: Clock,
        statutory_path: Path,
        company_path: Optional[Path] = None,
        cct_path: Optional[Path] = None,
    ) -> None:
        self._employees = employee_repo
        self._contracts = contract_repo
        self._periods = period_repo
        self._time_inputs = time_input_repo
        self._payslips = payslip_repo
        self._rule_loader = rule_loader
        self._registry = primitive_registry
        self._clock = clock
        self._statutory_path = statutory_path
        self._company_path = company_path
        self._cct_path = cct_path

    # --- Registry ---

    def create_employee(self, input: CreateEmployeeInput) -> Employee:
        employee = Employee(
            employee_id=input.employee_id,
            full_name=input.full_name,
            tax_id=input.tax_id,
            social_security_id=input.social_security_id,
            birth_date=input.birth_date,
            hire_date=input.hire_date,
            status="active",
            fiscal_profile=input.fiscal_profile,
            bank_iban=input.bank_iban,
        )
        return self._employees.upsert(employee)

    def get_employee(self, employee_id: str) -> Employee:
        e = self._employees.get(employee_id)
        if e is None:
            raise MissingInput(
                code="EMPLOYEE_NOT_FOUND",
                msg_pt=f"colaborador {employee_id!r} não encontrado",
                msg_en=f"employee {employee_id!r} not found",
            )
        return e

    def create_contract(self, input: CreateContractInput) -> Contract:
        # Ensure employee exists
        self.get_employee(input.employee_id)
        contract = Contract(
            contract_id=input.contract_id,
            employee_id=input.employee_id,
            type=input.type,
            start_date=input.start_date,
            end_date=input.end_date,
            role_category=input.role_category,
            weekly_hours=input.weekly_hours,
            fte_percent=input.fte_percent,
            base_monthly_salary=input.base_monthly_salary,
            cct_reference=input.cct_reference,
            company_id=input.company_id,
            pay_frequency=input.pay_frequency,
        )
        saved = self._contracts.upsert(contract)
        # Update employee current_contract_id
        employee = self.get_employee(input.employee_id)
        updated = employee.model_copy(update={"current_contract_id": saved.contract_id})
        self._employees.upsert(updated)
        return saved

    def get_contract_for_employee(self, employee_id: str) -> Contract:
        c = self._contracts.get_for_employee(employee_id)
        if c is None:
            raise MissingInput(
                code="CONTRACT_NOT_FOUND",
                msg_pt=f"contrato para colaborador {employee_id!r} não encontrado",
                msg_en=f"no contract for employee {employee_id!r}",
            )
        return c
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/service/test_dry_run.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/public/service.py tests/payroll/service/test_dry_run.py
git commit -m "feat: PayrollService shell + employee/contract registry methods"
```

---

### Task 27: PayrollService — period + time input methods

**Files:**
- Modify: `logic/payroll/public/service.py`
- Modify: `tests/payroll/service/test_dry_run.py`

- [ ] **Step 1: Append failing tests**

```python
def test_open_period_and_get(service):
    p = service.open_period("acme", PeriodDefinition(
        period_id="2026-05", pay_frequency="monthly",
        start_date=date(2026, 5, 1), end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    ))
    assert p.status == "open"
    got = service.get_period("2026-05")
    assert got.period_id == "2026-05"


def test_get_period_missing_raises(service):
    with pytest.raises(MissingInput) as exc:
        service.get_period("nope")
    assert exc.value.code == "PERIOD_NOT_FOUND"


def test_set_time_input_idempotent(service):
    service.create_employee(CreateEmployeeInput(
        employee_id="e-1", full_name="x", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="x"),
    ))
    service.open_period("acme", PeriodDefinition(
        period_id="2026-05", pay_frequency="monthly",
        start_date=date(2026, 5, 1), end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    ))
    service.set_time_input("2026-05", "e-1", TimeInputDraft(normal_hours=Decimal("160")))
    service.set_time_input("2026-05", "e-1", TimeInputDraft(normal_hours=Decimal("170")))
    ti = service.get_time_input("2026-05", "e-1")
    assert ti.normal_hours == Decimal("170")
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/payroll/service/test_dry_run.py -v`
Expected: 3 new tests FAIL with AttributeError or similar.

- [ ] **Step 3: Implement period and time-input methods**

Append to `PayrollService` class in `logic/payroll/public/service.py`:

```python
    # --- Period management ---

    def open_period(self, company_id: str, definition: PeriodDefinition) -> PayrollPeriod:
        period = PayrollPeriod(
            period_id=definition.period_id,
            company_id=company_id,
            pay_frequency=definition.pay_frequency,
            start_date=definition.start_date,
            end_date=definition.end_date,
            pay_date=definition.pay_date,
            status="open",
        )
        return self._periods.upsert(period)

    def get_period(self, period_id: str) -> PayrollPeriod:
        p = self._periods.get(period_id)
        if p is None:
            raise MissingInput(
                code="PERIOD_NOT_FOUND",
                msg_pt=f"período {period_id!r} não encontrado",
                msg_en=f"period {period_id!r} not found",
            )
        return p

    # --- Time / attendance ---

    def set_time_input(self, period_id: str, employee_id: str, draft: TimeInputDraft) -> TimeInput:
        self.get_period(period_id)
        self.get_employee(employee_id)
        ti = TimeInput(
            period_id=period_id,
            employee_id=employee_id,
            normal_hours=draft.normal_hours,
            meal_allowance_days=draft.meal_allowance_days,
            notes=draft.notes,
        )
        return self._time_inputs.upsert(ti)

    def get_time_input(self, period_id: str, employee_id: str) -> TimeInput:
        ti = self._time_inputs.get(period_id, employee_id)
        if ti is None:
            raise MissingInput(
                code="TIME_INPUT_NOT_FOUND",
                msg_pt=f"sem dados de tempo para colaborador {employee_id!r} no período {period_id!r}",
                msg_en=f"no time input for employee {employee_id!r} in period {period_id!r}",
            )
        return ti
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/service/test_dry_run.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/public/service.py tests/payroll/service/test_dry_run.py
git commit -m "feat: PayrollService period and time-input methods"
```

---

### Task 28: PayrollService — build_calculation_plan + dry_run_payslip

**Files:**
- Modify: `logic/payroll/public/service.py`
- Modify: `tests/payroll/service/test_dry_run.py`

- [ ] **Step 1: Append failing tests**

```python
def test_build_calculation_plan_minimum(service):
    service.create_employee(CreateEmployeeInput(
        employee_id="e-1", full_name="x", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="x"),
    ))
    service.create_contract(CreateContractInput(
        contract_id="c-1", employee_id="e-1", type="CT",
        start_date=date(2025, 1, 1), role_category="dev",
        weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
        base_monthly_salary=Decimal("1500"), company_id="acme",
    ))
    service.open_period("acme", PeriodDefinition(
        period_id="2026-05", pay_frequency="monthly",
        start_date=date(2026, 5, 1), end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    ))
    plan = service.build_calculation_plan("2026-05", "e-1")
    codes = [s.component_code for s in plan.steps]
    assert codes == ["base_salary", "tsu_employee"]


def test_dry_run_payslip_end_to_end(service):
    service.create_employee(CreateEmployeeInput(
        employee_id="e-1", full_name="x", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="solteiro_sem_dependentes"),
    ))
    service.create_contract(CreateContractInput(
        contract_id="c-1", employee_id="e-1", type="CT",
        start_date=date(2025, 1, 1), role_category="dev",
        weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
        base_monthly_salary=Decimal("1500"), company_id="acme",
    ))
    service.open_period("acme", PeriodDefinition(
        period_id="2026-05", pay_frequency="monthly",
        start_date=date(2026, 5, 1), end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    ))
    service.set_time_input("2026-05", "e-1", TimeInputDraft(normal_hours=Decimal("160")))
    result = service.dry_run_payslip("2026-05", "e-1")
    assert result.net_pay == Decimal("1335.00")
    assert len(result.audit) == 2
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/payroll/service/test_dry_run.py -v`
Expected: 2 new tests FAIL.

- [ ] **Step 3: Implement**

Add these imports to the top of `logic/payroll/public/service.py` (merging with the existing import block from Task 26 — do NOT duplicate):

```python
from logic.payroll.engine.executor import Executor
from logic.payroll.engine.time_input import normalize_time_input
from logic.payroll.primitives.base import ExecutionContext
from logic.payroll.rules.plan import CalculationPlan, CalculationPlanBuilder
from logic.payroll.rules.resolver import RuleResolver
```

Append the following methods to the `PayrollService` class body (inside the class, after the existing `get_time_input` method from Task 27):

```python
    # --- Plan & calculation (Plan 1 surface) ---

    def build_calculation_plan(self, period_id: str, employee_id: str) -> CalculationPlan:
        period = self.get_period(period_id)
        employee = self.get_employee(employee_id)
        contract = self.get_contract_for_employee(employee_id)
        resolver = RuleResolver(self._rule_loader)
        snapshot = resolver.resolve(
            statutory_path=self._statutory_path,
            cct_path=self._cct_path,
            company_path=self._company_path,
        )
        company = self._resolve_company(period.company_id)
        builder = CalculationPlanBuilder(self._registry)
        return builder.build(
            snapshot=snapshot,
            employee_id=employee.employee_id,
            contract_id=contract.contract_id,
            period_id=period.period_id,
            company_id=period.company_id,
            rounding_policy=company.default_rounding_policy,
        )

    def dry_run_payslip(self, period_id: str, employee_id: str) -> PayslipResult:
        period = self.get_period(period_id)
        employee = self.get_employee(employee_id)
        contract = self.get_contract_for_employee(employee_id)
        time_input = self.get_time_input(period_id, employee_id)
        company = self._resolve_company(period.company_id)
        plan = self.build_calculation_plan(period_id, employee_id)
        context = ExecutionContext(
            period=period,
            contract=contract,
            employee=employee,
            company=company,
            rounding_policy=company.default_rounding_policy,
            clock=self._clock,
        )
        executor = Executor(self._registry)
        return executor.execute(
            plan=plan,
            context=context,
            time_input=normalize_time_input(time_input),
        )

    def _resolve_company(self, company_id: str):
        from logic.payroll.public.schemas import Company
        from logic.payroll.rounding import RoundingPolicy
        # Plan 1 has no Company repository yet; return a hard-coded default.
        # Plan 3 wires this through a CompanyRepository.
        return Company(
            company_id=company_id,
            legal_name=f"{company_id.title()} Default",
            tax_id="000000000",
            default_rounding_policy=RoundingPolicy(),
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/payroll/service/test_dry_run.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```
git add logic/payroll/public/service.py tests/payroll/service/test_dry_run.py
git commit -m "feat: build_calculation_plan and dry_run_payslip end-to-end"
```

---

### Task 29: Shared test fixtures (conftest)

**Files:**
- Create: `tests/payroll/conftest.py`

This task consolidates the repetitive fixtures used in earlier task tests into shared ones so later plans don't duplicate setup. It does not change behaviour.

- [ ] **Step 1: Write conftest**

```python
# tests/payroll/conftest.py
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytest
from logic.payroll.public.schemas import (
    Employee, Contract, FiscalProfile, Company, PayrollPeriod,
)
from logic.payroll.primitives.base import ExecutionContext
from logic.payroll.rounding import RoundingPolicy
from logic.payroll.clock import FixedClock


@pytest.fixture
def fixed_clock():
    return FixedClock(datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc))


@pytest.fixture
def default_company():
    return Company(
        company_id="acme",
        legal_name="Acme, Lda.",
        tax_id="500000000",
        default_rounding_policy=RoundingPolicy(),
    )


@pytest.fixture
def default_period():
    return PayrollPeriod(
        period_id="2026-05",
        company_id="acme",
        pay_frequency="monthly",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    )


@pytest.fixture
def default_employee():
    return Employee(
        employee_id="e-1",
        full_name="Maria Santos",
        tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1),
        hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="solteiro_sem_dependentes"),
    )


@pytest.fixture
def default_contract():
    return Contract(
        contract_id="c-1",
        employee_id="e-1",
        type="CT",
        start_date=date(2025, 1, 1),
        role_category="developer",
        weekly_hours=Decimal("40"),
        fte_percent=Decimal("1"),
        base_monthly_salary=Decimal("1500"),
        company_id="acme",
    )


@pytest.fixture
def default_context(default_period, default_employee, default_contract, default_company, fixed_clock):
    return ExecutionContext(
        period=default_period,
        contract=default_contract,
        employee=default_employee,
        company=default_company,
        rounding_policy=RoundingPolicy(),
        clock=fixed_clock,
    )
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `pytest tests/payroll/ -v`
Expected: all previously-passing tests still pass; conftest does not break anything because earlier tests don't use these fixtures yet. Plan 2 tests will adopt them.

- [ ] **Step 3: Commit**

```
git add tests/payroll/conftest.py
git commit -m "test: shared payroll test fixtures (conftest)"
```

---

### Task 30: Golden-test harness

**Files:**
- Create: `tests/payroll/golden/conftest.py`
- Create: `tests/payroll/golden/test_golden.py`

The harness parametrizes over directories in `tests/payroll/golden/scenarios/`. Each scenario directory contains `statutory.yaml`, `company.yaml`, `inputs.json`, `expected_payslip.json`.

- [ ] **Step 1: Write the harness**

```python
# tests/payroll/golden/conftest.py
from pathlib import Path
import pytest


SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def pytest_generate_tests(metafunc):
    if "scenario_dir" in metafunc.fixturenames:
        scenarios = sorted(p for p in SCENARIOS_DIR.iterdir() if p.is_dir())
        metafunc.parametrize("scenario_dir", scenarios, ids=lambda p: p.name)
```

```python
# tests/payroll/golden/test_golden.py
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from logic.payroll.public.service import PayrollService
from logic.payroll.public.schemas import (
    CreateEmployeeInput, CreateContractInput, FiscalProfile, PeriodDefinition,
    TimeInputDraft,
)
from logic.payroll.primitives.base import DEFAULT_REGISTRY
from logic.payroll.rules.loader import RuleLoader
from logic.payroll.clock import FixedClock
from db.repositories.memory import (
    InMemoryEmployeeRepository, InMemoryContractRepository,
    InMemoryPeriodRepository, InMemoryTimeInputRepository,
    InMemoryPayslipRepository,
)


def _decimal_loads(text: str):
    return json.loads(text, parse_float=Decimal)


def test_golden_scenario(scenario_dir: Path):
    statutory = scenario_dir / "statutory.yaml"
    company = scenario_dir / "company.yaml"
    inputs = _decimal_loads((scenario_dir / "inputs.json").read_text(encoding="utf-8"))
    expected = _decimal_loads((scenario_dir / "expected_payslip.json").read_text(encoding="utf-8"))

    clock_iso = inputs["clock"]
    clock = FixedClock(datetime.fromisoformat(clock_iso))

    service = PayrollService(
        employee_repo=InMemoryEmployeeRepository(),
        contract_repo=InMemoryContractRepository(),
        period_repo=InMemoryPeriodRepository(),
        time_input_repo=InMemoryTimeInputRepository(),
        payslip_repo=InMemoryPayslipRepository(),
        rule_loader=RuleLoader(),
        primitive_registry=DEFAULT_REGISTRY,
        clock=clock,
        statutory_path=statutory,
        company_path=company,
    )

    emp = inputs["employee"]
    service.create_employee(CreateEmployeeInput(
        employee_id=emp["employee_id"], full_name=emp["full_name"],
        tax_id=emp["tax_id"], social_security_id=emp["social_security_id"],
        birth_date=date.fromisoformat(emp["birth_date"]),
        hire_date=date.fromisoformat(emp["hire_date"]),
        fiscal_profile=FiscalProfile(**emp["fiscal_profile"]),
    ))
    con = inputs["contract"]
    service.create_contract(CreateContractInput(
        contract_id=con["contract_id"], employee_id=con["employee_id"],
        type=con["type"], start_date=date.fromisoformat(con["start_date"]),
        role_category=con["role_category"],
        weekly_hours=Decimal(con["weekly_hours"]),
        fte_percent=Decimal(con["fte_percent"]),
        base_monthly_salary=Decimal(con["base_monthly_salary"]),
        company_id=con["company_id"],
    ))
    per = inputs["period"]
    service.open_period(per["company_id"], PeriodDefinition(
        period_id=per["period_id"], pay_frequency=per["pay_frequency"],
        start_date=date.fromisoformat(per["start_date"]),
        end_date=date.fromisoformat(per["end_date"]),
        pay_date=date.fromisoformat(per["pay_date"]),
    ))
    ti = inputs["time_input"]
    service.set_time_input(per["period_id"], emp["employee_id"], TimeInputDraft(
        normal_hours=Decimal(ti["normal_hours"]),
        meal_allowance_days=ti.get("meal_allowance_days", 0),
    ))

    result = service.dry_run_payslip(per["period_id"], emp["employee_id"])

    # Compare structured fields with the expected JSON
    assert result.net_pay == Decimal(expected["net_pay"])
    assert len(result.gross_earnings) == len(expected["gross_earnings"])
    for got, exp in zip(result.gross_earnings, expected["gross_earnings"]):
        assert got.component_code == exp["component_code"]
        assert got.amount == Decimal(exp["amount"])
        assert got.tax_treatment == exp["tax_treatment"]
    assert len(result.deductions) == len(expected["deductions"])
    for got, exp in zip(result.deductions, expected["deductions"]):
        assert got.component_code == exp["component_code"]
        assert got.amount == Decimal(exp["amount"])
```

- [ ] **Step 2: Commit harness (no scenarios yet — test will be skipped)**

Run: `pytest tests/payroll/golden/ -v`
Expected: 0 tests collected because `scenarios/` is empty.

Note: pytest's `pytest_generate_tests` will simply not parametrize when the directory is empty. This is intentional — Task 31 adds the first scenario.

```
git add tests/payroll/golden/conftest.py tests/payroll/golden/test_golden.py
git commit -m "test: golden-scenario harness for end-to-end payroll fixtures"
```

---

### Task 31: First golden scenario — salaried_simple

**Files:**
- Create: `tests/payroll/golden/scenarios/salaried_simple/statutory.yaml`
- Create: `tests/payroll/golden/scenarios/salaried_simple/company.yaml`
- Create: `tests/payroll/golden/scenarios/salaried_simple/inputs.json`
- Create: `tests/payroll/golden/scenarios/salaried_simple/expected_payslip.json`

- [ ] **Step 1: Write the YAML files**

```yaml
# tests/payroll/golden/scenarios/salaried_simple/statutory.yaml
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
    taxable: true
    subject_to_tsu: true
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: "0.11"
      base_components: ["base_salary"]
    inputs_required: ["base_salary"]
    taxable: false
    subject_to_tsu: false
```

```yaml
# tests/payroll/golden/scenarios/salaried_simple/company.yaml
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components: {}
```

- [ ] **Step 2: Write the inputs JSON**

```json
{
  "clock": "2026-05-26T12:00:00+00:00",
  "employee": {
    "employee_id": "e-1",
    "full_name": "Maria Santos",
    "tax_id": "123456789",
    "social_security_id": "11122233344",
    "birth_date": "1990-01-01",
    "hire_date": "2025-01-01",
    "fiscal_profile": {
      "irs_table_code": "solteiro_sem_dependentes"
    }
  },
  "contract": {
    "contract_id": "c-1",
    "employee_id": "e-1",
    "type": "CT",
    "start_date": "2025-01-01",
    "role_category": "developer",
    "weekly_hours": "40",
    "fte_percent": "1",
    "base_monthly_salary": "1500",
    "company_id": "acme"
  },
  "period": {
    "period_id": "2026-05",
    "company_id": "acme",
    "pay_frequency": "monthly",
    "start_date": "2026-05-01",
    "end_date": "2026-05-31",
    "pay_date": "2026-05-31"
  },
  "time_input": {
    "normal_hours": "160"
  }
}
```

- [ ] **Step 3: Write the expected payslip JSON**

```json
{
  "net_pay": "1335.00",
  "gross_earnings": [
    {
      "component_code": "base_salary",
      "amount": "1500.00",
      "tax_treatment": "taxable"
    }
  ],
  "deductions": [
    {
      "component_code": "tsu_employee",
      "amount": "165.00",
      "tax_treatment": "taxable"
    }
  ],
  "employer_contributions": []
}
```

- [ ] **Step 4: Run the golden harness**

Run: `pytest tests/payroll/golden/test_golden.py -v`
Expected: 1 passed — `test_golden_scenario[salaried_simple]`.

- [ ] **Step 5: Commit**

```
git add tests/payroll/golden/scenarios/
git commit -m "test: golden scenario 'salaried_simple' — base salary + TSU employee"
```

---

### Task 32: Determinism property invariant

**Files:**
- Create: `tests/payroll/test_determinism.py`

- [ ] **Step 1: Write the test**

```python
# tests/payroll/test_determinism.py
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import json
from logic.payroll.public.service import PayrollService
from logic.payroll.public.schemas import (
    CreateEmployeeInput, CreateContractInput, FiscalProfile, PeriodDefinition,
    TimeInputDraft,
)
from logic.payroll.primitives.base import DEFAULT_REGISTRY
from logic.payroll.rules.loader import RuleLoader
from logic.payroll.clock import FixedClock
from db.repositories.memory import (
    InMemoryEmployeeRepository, InMemoryContractRepository,
    InMemoryPeriodRepository, InMemoryTimeInputRepository,
    InMemoryPayslipRepository,
)


def _run_dry_run(statutory: Path, company: Path) -> dict:
    service = PayrollService(
        employee_repo=InMemoryEmployeeRepository(),
        contract_repo=InMemoryContractRepository(),
        period_repo=InMemoryPeriodRepository(),
        time_input_repo=InMemoryTimeInputRepository(),
        payslip_repo=InMemoryPayslipRepository(),
        rule_loader=RuleLoader(),
        primitive_registry=DEFAULT_REGISTRY,
        clock=FixedClock(datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)),
        statutory_path=statutory,
        company_path=company,
    )
    service.create_employee(CreateEmployeeInput(
        employee_id="e-1", full_name="x", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="x"),
    ))
    service.create_contract(CreateContractInput(
        contract_id="c-1", employee_id="e-1", type="CT",
        start_date=date(2025, 1, 1), role_category="dev",
        weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
        base_monthly_salary=Decimal("1500"), company_id="acme",
    ))
    service.open_period("acme", PeriodDefinition(
        period_id="2026-05", pay_frequency="monthly",
        start_date=date(2026, 5, 1), end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    ))
    service.set_time_input("2026-05", "e-1", TimeInputDraft(normal_hours=Decimal("160")))
    result = service.dry_run_payslip("2026-05", "e-1")
    return result.model_dump(mode="json")


def test_determinism_byte_identical_runs(tmp_path: Path):
    statutory = tmp_path / "statutory.yaml"
    statutory.write_text("""
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: "0.11"
      base_components: ["base_salary"]
    inputs_required: ["base_salary"]
""", encoding="utf-8")
    company = tmp_path / "company.yaml"
    company.write_text("""
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components: {}
""", encoding="utf-8")

    run1 = _run_dry_run(statutory, company)
    run2 = _run_dry_run(statutory, company)
    assert json.dumps(run1, sort_keys=True) == json.dumps(run2, sort_keys=True)
```

- [ ] **Step 2: Run test**

Run: `pytest tests/payroll/test_determinism.py -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```
git add tests/payroll/test_determinism.py
git commit -m "test: determinism invariant (same inputs + same rules => identical payslip)"
```

---

### Task 33: Final integration check — full suite green

- [ ] **Step 1: Run the entire test suite**

Run: `pytest tests/payroll/ -v`
Expected: all tests pass. Total count: ~75–80 tests across all files.

- [ ] **Step 2: If any test fails, fix it before proceeding.** Do not commit partial fixes; investigate root cause.

- [ ] **Step 3: Final commit (only if changes were needed)**

If you made changes to fix issues:
```
git commit -am "fix: address final integration issues for Plan 1"
```

If no changes: skip this step.

---

## End State after Plan 1

Working software:
- `PayrollService.dry_run_payslip(period_id, employee_id)` computes an end-to-end payslip for a Portuguese full-month salaried employee.
- Numbers are produced by deterministic primitives (`BaseSalary`, `TSUContribution`) with `Decimal` arithmetic.
- Every payslip line points to an `AuditTrailEntry` with a `RuleCitation` to the YAML clause that authorized it.
- Layered rule resolution works for statutory + company layers; the merge semantics (scalar override, disabled, locked) are tested.
- Determinism is property-tested: same inputs + same rules → byte-identical JSON.
- One golden scenario (`salaried_simple`) runs end-to-end against the harness; Plan 2 adds the remaining nine.

Not yet implemented (covered by Plans 2 and 3):
- All other primitives (overtime, subsídios, meal allowance, IRS withholding table, diuturnidades, fixed allowance, absence deduction, employer-side TSU).
- Proration for mid-period hire/termination.
- CCT layer in the resolver (the code path exists, but no CCT YAML is loaded yet).
- Full `run_payroll` two-phase semantics, atomicity, idempotency, immutability, concurrency.
- `recalculate_employee`, `close_period`, `explain_line`, `validate_rules`, `reload_rules`.
- AI orchestration, tools, narration validator.
- The remaining nine golden scenarios.
- Property-based invariants for audit completeness, citation completeness, layer precedence, sign discipline.

---

## Spec Coverage Map

| Spec section | Covered by tasks |
|---|---|
| §3 Architecture | T2 (module structure) |
| §4 Module structure | T2 |
| §5 Data model — RuleCitation, AuditTrailEntry, PayslipLine, PayslipResult | T6 |
| §5 Data model — identity (FiscalProfile, CCTReference, Company) | T7 |
| §5 Data model — identity (Contract, Employee, CompensationPackage) | T8 |
| §5 Data model — period (PayrollPeriod, AbsenceEntry, OvertimeBuckets, TimeInput) | T9 |
| §5 Decimal discipline | T5 (rounding) + Pydantic Decimal fields throughout |
| §6 Rule resolver — layer stack & merge | T17, T18 |
| §6 CalculationPlan, phase ordering, topo sort | T19 |
| §6 Up-front validation (primitives, params, deps) | T19 |
| §7 Primitive contract | T11, T12 |
| §7 BaseSalary primitive | T13 |
| §7 TSUContribution primitive (employee side) | T14 |
| §7 RoundingPolicy utility | T5 |
| §8 PayrollService construction | T26 |
| §8 Registry methods (subset) | T26 |
| §8 Period methods (open_period, get_period) | T27 |
| §8 Time-input methods | T27 |
| §8 build_calculation_plan | T28 |
| §8 dry_run_payslip | T28 |
| §9 Audit trail flow (PrimitiveResult → AuditTrailEntry → PayslipLine.source_audit_ref) | T22 |
| §10 Typed exceptions | T3 |
| §10 Float-literal rejection | T16 |
| §10 Unknown primitive / unresolved dependency | T19 |
| §10 LOCKED_COMPONENT_OVERRIDE | T18 |
| §11 Testing — primitives (BaseSalary, TSU, Rounding) | T5, T13, T14 |
| §11 Testing — resolver merge | T18 |
| §11 Testing — engine integration | T22 |
| §11 Testing — service | T26, T27, T28 |
| §11 Testing — golden harness | T30 |
| §11 Testing — first golden scenario | T31 |
| §11 Property invariant — determinism | T32 |

Deferred to Plans 2 and 3 (explicitly listed in "End State / Not yet implemented" above).
