from __future__ import annotations
import re
from datetime import date
from decimal import Decimal
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict

from logic.bills.models import Bill, BillLine
from logic.bills.rules.models import PurchaseInvoiceRule

# write_executor interpolates column names into its INSERT statement. This regex
# is checked independently of the schema lookup so that a subverted or malformed
# schema row still cannot produce an identifier that changes the statement.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

Section = Literal["header", "lines", "supplier_create", "article_create"]
_MAPPED = ("header", "lines")
_CREATE = ("supplier_create", "article_create")


class FieldChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["set", "remove"]
    section: Section
    name: str | None = None      # logical field key; header/lines only
    column: str | None = None
    source: str | None = None
    required: bool = False


class RuleChangeProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rationale: str
    base_version: int
    changes: list[FieldChange]


class Violation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    change_index: int
    reason: str


# Not mappable: `lines` and `confidence` are containers, and `buyer_tax_id` is
# documented in models.py as extraction-only — it exists to give the model
# somewhere to put the OTHER tax number so it stops mistaking it for the
# issuer's. Mapping it would undo a deliberate decision; widening this set is a
# one-line change if that decision is ever revisited.
_UNMAPPABLE_BILL_FIELDS = frozenset({"lines", "confidence", "buyer_tax_id"})

# SQL Server type families, as INFORMATION_SCHEMA.DATA_TYPE spells them.
_TEXT = frozenset({"varchar", "nvarchar", "char", "nchar", "text", "ntext"})
_INTEGER = frozenset({"bigint", "int", "smallint", "tinyint"})
_NUMERIC = frozenset({"decimal", "numeric", "money", "smallmoney", "float", "real"})
_TEMPORAL = frozenset({"date", "datetime", "datetime2", "smalldatetime",
                       "datetimeoffset"})

# Which column families each source type may be written to.
#
# Text is a permitted sink for every type: SQL Server converts cleanly and
# nothing is lost. What this table exists to stop is the LOSSY conversions,
# and one in particular — a Decimal into an integer column. SQL Server performs
# that implicitly and silently truncates, so mapping gross_total onto a bigint
# turns 1234.56 into 1234 and writes the document without an error. Wrong money,
# no warning. On Doc001/LinDoc001 79 of 164 columns are integer types, so this
# is not a hypothetical mismapping.
_COMPATIBLE: dict[type, frozenset[str]] = {
    str: _TEXT,
    Decimal: _NUMERIC | _TEXT,
    date: _TEMPORAL | _TEXT,
    int: _INTEGER,          # the .match sentinels resolve to an entity key
}


def source_type(source: str) -> type | None:
    """The Python type a source yields, or None if it cannot be determined.

    Derived from the extraction models' own annotations so the two cannot drift,
    the same way valid_sources() is.
    """
    if source in ("supplier.match", "line.match"):
        return int
    prefix, _, field = source.partition(".")
    model = {"bill": Bill, "line": BillLine}.get(prefix)
    if model is None or field not in model.model_fields:
        return None
    annotation = model.model_fields[field].annotation
    # Unwrap Optional[X] / X | None, which is how most extracted fields are typed.
    args = [a for a in get_args(annotation) if a is not type(None)]
    return args[0] if args else annotation


def valid_sources() -> set[str]:
    """Every `source` an admin may name, derived from the extraction models so
    the two cannot drift.

    NOTE: the shipped rule document maps `notes: {column: Obs, source:
    bill.notes}`, but Bill has no `notes` field — that mapping is already dead
    and this function correctly refuses to reissue it. See the implementer notes.
    """
    out = {"supplier.match", "line.match"}
    out |= {f"bill.{n}" for n in Bill.model_fields if n not in _UNMAPPABLE_BILL_FIELDS}
    out |= {f"line.{n}" for n in BillLine.model_fields}
    return out


def table_for(section: str, rule: PurchaseInvoiceRule) -> str:
    return {
        "header": rule.header.table,
        "lines": rule.lines.table,
        "supplier_create": rule.matching.supplier.table,
        "article_create": rule.matching.article.table,
    }[section]


# Logical field keys the executor computes for itself (write_executor.py sets
# the supplier FK and article FK last, after caller columns). Retargeting or
# removing these would let a proposal redirect or drop a structural join, so
# they are protected per-section like the column-level set below.
_PROTECTED_FIELD_KEYS = {"header": "supplier", "lines": "article"}


def _protected(rule: PurchaseInvoiceRule, section: str) -> set[str]:
    """Columns the executor computes for itself and applies last, so a caller
    cannot override them. This applies to every section, not just `header`:
    the same primary-key/audit/draft-default columns are also written by
    `_resolve_entity()` when creating a new supplier or article row. Create
    sections additionally protect their own `create_defaults` keys, which
    `_resolve_entity()` seeds before splicing in the caller's `proposed_new`."""
    out = {rule.header.primary_key.lower()}
    out |= {c.lower() for c in rule.header.audit_columns.values()}
    out |= {c.lower() for c in rule.header.draft_defaults}
    if section == "supplier_create":
        out |= {c.lower() for c in rule.matching.supplier.create_defaults}
    elif section == "article_create":
        out |= {c.lower() for c in rule.matching.article.create_defaults}
    return out


def validate(proposal: RuleChangeProposal, rule: PurchaseInvoiceRule,
             schema) -> list[Violation]:
    """Every reason `proposal` cannot be applied. Empty list means applicable."""
    out: list[Violation] = []
    sources = valid_sources()

    for i, ch in enumerate(proposal.changes):
        def bad(reason: str) -> None:
            out.append(Violation(change_index=i, reason=reason))

        if ch.section in _CREATE:
            # create_columns is only a whitelist the executor checks the payload
            # against (write_executor._check_columns); the payload itself is
            # hardcoded in matching.supplier_proposal/line_proposal. So adding a
            # column here does nothing, and removing one makes _check_columns
            # raise on every bill with an unmatched supplier or article. Until
            # the payload is derived from the whitelist, refuse the whole
            # section rather than ship an inert-or-breaking control. The
            # protected-column checks below stay in place as defence in depth.
            bad(f"editing {ch.section} is not supported yet: the new-entity "
                "payload is hardcoded in matching.py rather than derived from "
                "create_columns, so adding a column has no effect and removing "
                "one breaks every bill that needs a new record")
            continue

        protected_key = _PROTECTED_FIELD_KEYS.get(ch.section)

        if ch.section in _MAPPED and ch.action == "remove":
            if not ch.name:
                bad("name is required to remove a mapped field")
            elif ch.name == protected_key:
                bad(f"{ch.name!r} is a protected field and cannot be removed")
            continue
        if ch.section in _CREATE and ch.action == "remove":
            if not ch.column:
                bad("column is required to remove a create column")
            elif not _IDENT_RE.fullmatch(ch.column):
                bad(f"{ch.column!r} is not a valid identifier")
            continue

        if ch.section in _MAPPED and not ch.name:
            bad("name is required for a mapped field")
            continue
        if ch.section in _MAPPED and ch.name == protected_key:
            bad(f"{ch.name!r} is a protected field and cannot be retargeted")
            continue
        if not ch.column:
            bad("column is required")
            continue
        if ch.section in _MAPPED and not ch.source:
            bad("source is required for a mapped field")
            continue

        if not _IDENT_RE.fullmatch(ch.column):
            bad(f"{ch.column!r} is not a valid identifier")
            continue
        if ch.column.lower() in _protected(rule, ch.section):
            bad(f"{ch.column!r} is protected and cannot be mapped")
            continue

        table = table_for(ch.section, rule)
        if schema.resolve(table, ch.column) is None:
            bad(f"column {ch.column!r} does not exist on {table}")
            continue
        if ch.source is not None and ch.source not in sources:
            bad(f"{ch.source!r} is not a known source")
            continue

        # Type compatibility. Skipped when the probe cannot describe the column
        # (a stub in tests) or the source type is unknown — the checks above
        # already established the column exists and the source is real.
        if ch.source is not None:
            info = schema.columns(table).get(ch.column.lower())
            st = source_type(ch.source)
            allowed = _COMPATIBLE.get(st) if st is not None else None
            if info is not None and allowed is not None \
                    and info.data_type.lower() not in allowed:
                # Plain ASCII: a violation reason can reach a Windows console,
                # where cp1252 cannot encode an em dash.
                bad(f"{ch.source} yields {st.__name__}, which cannot be written "
                    f"to {table}.{info.name} of type {info.data_type}: "
                    "the conversion would lose data")
                continue

    return out


def apply(proposal: RuleChangeProposal, rule: PurchaseInvoiceRule,
          schema) -> PurchaseInvoiceRule:
    """Merge `proposal` into `rule`, bumping the version.

    Callers must run validate() first: this asserts rather than re-checks, so an
    unvalidated proposal fails loudly instead of writing an unverified column.
    """
    data = rule.model_dump()

    for ch in proposal.changes:
        table = table_for(ch.section, rule)
        column = None
        # Only a `set` needs the schema's spelling. A `remove` on a mapped
        # section is keyed by `name` and validate() never inspects its `column`,
        # so resolving it here would assert on an unchecked value; a create
        # remove matches case-insensitively against the existing list.
        if ch.column is not None and ch.action != "remove":
            column = schema.resolve(table, ch.column)
            assert column is not None, f"unvalidated column {ch.column!r} on {table}"

        if ch.section in _MAPPED:
            fields = data["header" if ch.section == "header" else "lines"]["fields"]
            if ch.action == "remove":
                fields.pop(ch.name, None)
            else:
                fields[ch.name] = {"column": column, "source": ch.source,
                                   "required": ch.required}
        else:
            key = "supplier" if ch.section == "supplier_create" else "article"
            cols = data["matching"][key]["create_columns"]
            if ch.action == "remove":
                data["matching"][key]["create_columns"] = [
                    c for c in cols if c.lower() != ch.column.lower()]
            elif column not in cols:
                cols.append(column)

    data["version"] = rule.version + 1
    return PurchaseInvoiceRule.model_validate(data)
