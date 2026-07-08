# logic/devcare/errors.py
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ValidationViolation:
    field: str
    message: str


@dataclass
class NormalizedChange:
    entity: str
    operation: str           # "create" | "update" | "delete"
    table: str
    primary_key: str
    columns: dict            # column -> value (writable fields only)
    target_pk: object | None # for update/delete


@dataclass
class ValidationResult:
    ok: bool
    change: NormalizedChange | None = None
    violations: list[ValidationViolation] = field(default_factory=list)
    rule_doc: str = ""
    rule_version: int = 0
