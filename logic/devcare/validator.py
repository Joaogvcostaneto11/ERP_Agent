# logic/devcare/validator.py
from __future__ import annotations
import re
from datetime import datetime
from typing import Callable

from logic.devcare.errors import NormalizedChange, ValidationResult, ValidationViolation
from logic.devcare.rules.loader import RuleLoader
from logic.devcare.rules.models import EntityRule

Reader = Callable[[str, dict], list[dict]]


def _coerce(field_type: str, value):
    if field_type == "int":
        return int(value)
    if field_type == "float":
        return float(value)
    if field_type == "date":
        # Validate an ISO date; keep it as a YYYY-MM-DD string for binding
        # (SQL Server converts it to the datetime column on insert).
        datetime.strptime(str(value), "%Y-%m-%d")
        return str(value)
    return str(value)


class ChangeValidator:
    def __init__(self, loader: RuleLoader, reader: Reader) -> None:
        self._loader = loader
        self._reader = reader

    def validate(self, entity: str, operation: str, fields: dict,
                 target_pk=None) -> ValidationResult:
        rule = self._loader.get(entity)
        viols: list[ValidationViolation] = []

        if operation not in rule.operations:
            viols.append(ValidationViolation("operation",
                f"operation {operation!r} not allowed for {entity}"))
            return ValidationResult(False, violations=viols,
                                    rule_doc=entity, rule_version=rule.version)

        if operation in ("update", "delete") and target_pk is None:
            viols.append(ValidationViolation("target",
                "update/delete requires a resolved primary key"))
            return ValidationResult(False, violations=viols,
                                    rule_doc=entity, rule_version=rule.version)

        columns: dict = {}
        if operation == "delete":
            # nothing to coerce; soft-delete handled by executor
            pass
        else:
            columns = self._coerce_fields(rule, operation, fields, viols)
            self._check_uniqueness(rule, entity, fields, columns, target_pk, viols)
            self._check_references(rule, fields, viols)

        if not viols and operation in ("update", "delete"):
            self._check_target_exists(rule, target_pk, viols)

        if viols:
            return ValidationResult(False, violations=viols,
                                    rule_doc=entity, rule_version=rule.version)

        change = NormalizedChange(
            entity=entity, operation=operation, table=rule.table,
            primary_key=rule.primary_key, columns=columns, target_pk=target_pk,
        )
        return ValidationResult(True, change=change, rule_doc=entity,
                                rule_version=rule.version)

    def _coerce_fields(self, rule: EntityRule, operation: str, fields: dict,
                       viols: list[ValidationViolation]) -> dict:
        columns: dict = {}
        unknown = set(fields) - set(rule.fields)
        for u in unknown:
            viols.append(ValidationViolation(u, f"unknown field {u!r}"))
        for name, fr in rule.fields.items():
            if name not in fields or fields[name] in (None, ""):
                if operation == "create" and fr.required:
                    viols.append(ValidationViolation(name,
                        f"{fr.label or name} is required"))
                continue
            raw = fields[name]
            try:
                value = _coerce(fr.type, raw)
            except (ValueError, TypeError):
                viols.append(ValidationViolation(name,
                    f"{fr.label or name} must be {fr.type}"))
                continue
            self._check_field_validation(name, fr, value, viols)
            columns[fr.column] = value
        return columns

    def _check_field_validation(self, name, fr, value, viols):
        val = fr.validation
        if val.max_length is not None and isinstance(value, str) and len(value) > val.max_length:
            viols.append(ValidationViolation(name,
                f"{fr.label or name} exceeds max length {val.max_length}"))
        if val.regex is not None and isinstance(value, str) and not re.match(val.regex, value):
            viols.append(ValidationViolation(name,
                f"{fr.label or name} has invalid format"))
        if val.min is not None and isinstance(value, (int, float)) and value < val.min:
            viols.append(ValidationViolation(name, f"{fr.label or name} below minimum"))
        if val.max is not None and isinstance(value, (int, float)) and value > val.max:
            viols.append(ValidationViolation(name, f"{fr.label or name} above maximum"))
        if val.enum is not None and value not in val.enum:
            viols.append(ValidationViolation(name, f"{fr.label or name} not an allowed value"))

    def _check_uniqueness(self, rule, entity, fields, columns, target_pk, viols):
        for fieldset in rule.uniqueness:
            cols = {}
            complete = True
            for fname in fieldset:
                fr = rule.fields[fname]
                if fr.column not in columns:
                    complete = False
                    break
                cols[fr.column] = columns[fr.column]
            if not complete:
                continue
            where = " AND ".join(f"{c} = :{c}" for c in cols)
            params = dict(cols)
            sql = f"SELECT TOP 1 1 AS n FROM DevCare.dbo.{rule.table} WHERE {where}"
            if rule.soft_delete is not None:
                sql += f" AND {rule.soft_delete.column} = {rule.soft_delete.active_value}"
            if target_pk is not None:
                sql += f" AND {rule.primary_key} <> :_pk"
                params["_pk"] = target_pk
            rows = self._reader(sql, params)
            if rows:
                viols.append(ValidationViolation(",".join(fieldset),
                    f"a {entity} with this {', '.join(fieldset)} already exists (must be unique)"))

    def _check_references(self, rule, fields, viols):
        for fname, ref in rule.references.items():
            if fname not in fields or fields[fname] in (None, ""):
                continue
            try:
                value = _coerce(rule.fields[fname].type, fields[fname])
            except (ValueError, TypeError):
                continue
            sql = (f"SELECT TOP 1 1 AS n FROM DevCare.dbo.{ref.table} "
                   f"WHERE {ref.column} = :v")
            rows = self._reader(sql, {"v": value})
            if not rows:
                viols.append(ValidationViolation(fname,
                    f"referenced {ref.table} {fields[fname]!r} does not exist"))

    def _check_target_exists(self, rule, target_pk, viols):
        sql = (f"SELECT COUNT(*) AS cnt FROM DevCare.dbo.{rule.table} "
               f"WHERE {rule.primary_key} = :pk")
        rows = self._reader(sql, {"pk": target_pk})
        cnt = rows[0].get("cnt") if rows else 0
        if cnt != 1:
            viols.append(ValidationViolation("target",
                f"target row (primary key {target_pk}) not found"))
