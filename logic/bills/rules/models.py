from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict


class TipoDocRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolve_by: Literal["code"]
    code: str


class HeaderFieldRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str
    source: str
    required: bool = False


class LineFieldRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str
    source: str
    required: bool = False


class HeaderRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    primary_key: str
    tipo_doc: TipoDocRef
    draft_defaults: dict[str, int | str] = {}
    audit_columns: dict[str, str] = {}
    fields: dict[str, HeaderFieldRule]


class LinesRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    parent_fk: str
    fields: dict[str, LineFieldRule]


class MatchTargetRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    tipo: str | None = None
    match_on: list[str]
    create: bool = False
    create_defaults: dict[str, int | str] = {}
    create_columns: list[str] = []


class MatchingRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier: MatchTargetRule
    article: MatchTargetRule


class PurchaseInvoiceRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document: str
    version: int
    header: HeaderRule
    lines: LinesRule
    matching: MatchingRule
