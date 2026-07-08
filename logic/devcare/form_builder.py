"""Build a typed form descriptor for an entity create/update, used by the UI
to render real inputs (date pickers, dropdowns, number fields).

Identifiers in the queries come only from the registry (EntityRule), values
are bound params or registry-controlled ints — no user input is interpolated.
"""
from __future__ import annotations
from typing import Callable

from logic.devcare.rules.loader import RuleLoader
from logic.devcare.rules.models import EntityRule, FieldRule

Reader = Callable[[str, dict], list[dict]]
_OPTIONS_CAP = 1000


def _format_value(fr: FieldRule, raw):
    if raw is None or raw == "":
        return None
    if fr.type == "date":
        if hasattr(raw, "strftime"):
            return raw.strftime("%Y-%m-%d")
        return str(raw)[:10]
    return raw


def _reference_options(ref, loader: RuleLoader, reader: Reader, prefix: str) -> list[dict]:
    disp = ref.display_column or ref.column
    sql = f"SELECT {ref.column} AS value, {disp} AS label FROM {prefix}{ref.table}"
    # If the referenced table is itself a registered entity with a soft-delete
    # flag, only offer active rows.
    for name in loader.entities():
        r = loader.get(name)
        if r.table == ref.table and r.soft_delete is not None:
            sql += f" WHERE {r.soft_delete.column} = {r.soft_delete.active_value}"
            break
    sql += " ORDER BY label"
    out = []
    for row in reader(sql, {})[:_OPTIONS_CAP]:
        v = row.get("value")
        if v is None:
            continue
        label = row.get("label")
        out.append({"value": v, "label": str(label) if label not in (None, "") else str(v)})
    return out


def _input_spec(fname: str, fr: FieldRule, rule: EntityRule,
                loader: RuleLoader, reader: Reader, prefix: str) -> dict:
    spec: dict = {"name": fname, "label": fr.label or fname, "required": fr.required}
    ref = rule.references.get(fname)
    if ref is not None:
        spec["input"] = "select"
        spec["options"] = _reference_options(ref, loader, reader, prefix)
    elif fr.validation.options is not None:
        spec["input"] = "select"
        spec["options"] = [{"value": o.value, "label": o.label}
                           for o in fr.validation.options]
    elif fr.type == "date":
        spec["input"] = "date"
    elif fr.type in ("int", "float"):
        spec["input"] = "number"
        spec["step"] = 1 if fr.type == "int" else "any"
    else:
        spec["input"] = "text"
        if fr.validation.max_length is not None:
            spec["maxlength"] = fr.validation.max_length
    if fr.validation.regex is not None and spec["input"] == "text":
        spec["pattern"] = fr.validation.regex
    return spec


def build_form(rule: EntityRule, loader: RuleLoader, operation: str, reader: Reader,
               prefix: str, target_pk=None, prefill: dict | None = None) -> dict:
    prefill = prefill or {}
    current: dict = {}
    if operation == "update" and target_pk is not None:
        rows = reader(
            f"SELECT * FROM {prefix}{rule.table} WHERE {rule.primary_key} = :pk",
            {"pk": target_pk})
        if rows:
            current = rows[0]

    fields = []
    for fname, fr in rule.fields.items():
        spec = _input_spec(fname, fr, rule, loader, reader, prefix)
        if fname in prefill and prefill[fname] not in (None, ""):
            spec["value"] = prefill[fname]
        elif fr.column in current:
            spec["value"] = _format_value(fr, current[fr.column])
        else:
            spec["value"] = None
        fields.append(spec)

    return {
        "kind": "form",
        "entity": rule.entity,
        "operation": operation,
        "target_pk": target_pk,
        "title": f"{operation.capitalize()} {rule.entity}",
        "fields": fields,
    }
