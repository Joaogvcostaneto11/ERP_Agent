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
