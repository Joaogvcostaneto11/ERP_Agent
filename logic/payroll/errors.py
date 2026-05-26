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
