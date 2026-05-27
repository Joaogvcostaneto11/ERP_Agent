from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from logic.payroll.public.schemas import RuleCitation
from logic.payroll.rules.loader import RuleLoader
from logic.payroll.rules.models import RuleDocument, ComponentDecl
from logic.payroll.errors import RuleValidationError


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
                msg_pt=f"componente {code!r} esta bloqueado; camada {higher_layer!r} nao pode sobrepor",
                msg_en=f"component {code!r} is locked; layer {higher_layer!r} cannot override it",
            )
    base_params = dict(lower.parameters) if lower is not None else {}
    base_params.update(higher_decl.parameters)  # higher layer wins for scalar params
    return ResolvedComponent(
        component_code=code,
        type=higher_decl.type,
        phase=higher_decl.phase,
        primitive=higher_decl.primitive,
        parameters=base_params,
        inputs_required=higher_decl.inputs_required or (lower.inputs_required if lower else []),
        taxable=higher_decl.taxable,
        subject_to_tsu=higher_decl.subject_to_tsu,
        locked=True if (lower is not None and lower.locked) else higher_decl.locked,
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
