from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict

FieldType = Literal["string", "int", "float"]
Operation = Literal["create", "update", "delete"]


class FieldValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_length: int | None = None
    regex: str | None = None
    min: float | None = None
    max: float | None = None
    enum: list[str | int] | None = None


class FieldRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str
    type: FieldType
    required: bool = False
    label: str | None = None
    validation: FieldValidation = FieldValidation()


class SoftDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str
    active_value: int
    deleted_value: int


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    column: str


class AuditColumns(BaseModel):
    model_config = ConfigDict(extra="forbid")
    created_at: str | None = None
    updated_at: str | None = None
    created_by: str | None = None
    updated_by: str | None = None


class EntityRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity: str
    version: int
    table: str
    primary_key: str
    operations: list[Operation]
    fields: dict[str, FieldRule]
    soft_delete: SoftDelete | None = None
    references: dict[str, Reference] = {}
    uniqueness: list[list[str]] = []
    audit_columns: AuditColumns = AuditColumns()
    create_defaults: dict[str, int | str] = {}
