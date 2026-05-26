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
