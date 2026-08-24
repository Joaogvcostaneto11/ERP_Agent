# Admin-Authored Write Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an admin describe in prose how bill data maps onto database columns, and turn that into a versioned, validated change to `business_rules/bills/purchase_invoice.yaml` — without prose or model output ever reaching SQL.

**Architecture:** Three stages. Claude *drafts* a structured patch (`RuleChangeProposal`); the patch is *validated* against live `INFORMATION_SCHEMA`, an identifier regex, the known extraction sources, and a protected-column list; only then is the merged `PurchaseInvoiceRule` *persisted* as a new version. The write executor keeps reading a plain validated rule object and is not modified.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, PyYAML, SQLAlchemy Core (`text()`), pytest, vanilla ES modules for the UI.

**Spec:** `docs/superpowers/specs/2026-08-24-bills-admin-write-mapping-design.md`

## Global Constraints

- **Model output never reaches SQL.** Claude produces a candidate patch only. Every column that survives to the YAML must have been resolved through `SchemaProbe.resolve()`.
- **Identifier regex is mandatory and independent:** `^[A-Za-z_][A-Za-z0-9_]*$`, applied even when the schema check passes. It is defence in depth, not a substitute.
- **Persisted column spelling comes from the schema**, never from the admin's or the model's casing.
- **Protected columns are never admin-targetable:** the header `primary_key`, every *value* in `header.audit_columns`, and every *key* in `header.draft_defaults`.
- **`write_executor.py` is not modified by this plan.** Its `_check_columns` whitelist behavior must keep passing its existing tests unchanged.
- **Operator path is untouched.** `/bills/upload`, `/bills/stage`, `/bills/commit` and their tests must not change.
- Admin gate env var: `BILLS_ADMIN_TOKEN`, header `X-Admin-Token`. Unset → 404 on every `/admin/rules*` route. Wrong → 403.
- Run tests with `python -m pytest`. The repo's `tests/conftest.py` already blanks gate secrets, so add `BILLS_ADMIN_TOKEN` there in Task 5.

---

### Task 1: Schema probe

**Files:**
- Create: `logic/bills/rules/schema_probe.py`
- Test: `tests/bills/test_schema_probe.py`

**Interfaces:**
- Consumes: the reader callable already used by `Matcher` — `Callable[[str, dict], list[dict]]`, as built at `logic/bills/app.py:58`.
- Produces: `ColumnInfo(name: str, data_type: str, nullable: bool)`; `SchemaUnavailable(RuntimeError)`; `SchemaProbe(reader)` with `.columns(table) -> dict[str, ColumnInfo]` (keyed by lowercased name), `.resolve(table, column) -> str | None` (schema's exact spelling), `.refresh() -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/bills/test_schema_probe.py
import pytest

from logic.bills.rules.schema_probe import SchemaProbe

ROWS = {
    "Doc001": [
        {"COLUMN_NAME": "Chave", "DATA_TYPE": "int", "IS_NULLABLE": "NO"},
        {"COLUMN_NAME": "Iliquido", "DATA_TYPE": "decimal", "IS_NULLABLE": "YES"},
    ],
    "LinDoc001": [
        {"COLUMN_NAME": "Descricao", "DATA_TYPE": "varchar", "IS_NULLABLE": "YES"},
    ],
}


def _reader(calls=None):
    def read(sql, params):
        if calls is not None:
            calls.append(params["table"])
        return ROWS.get(params["table"], [])
    return read


def test_columns_are_keyed_case_insensitively_but_keep_schema_spelling():
    probe = SchemaProbe(_reader())
    cols = probe.columns("Doc001")
    assert set(cols) == {"chave", "iliquido"}
    assert cols["iliquido"].name == "Iliquido"
    assert cols["iliquido"].nullable is True
    assert cols["chave"].nullable is False


def test_resolve_returns_schema_spelling_for_any_casing():
    probe = SchemaProbe(_reader())
    assert probe.resolve("Doc001", "ILIQUIDO") == "Iliquido"
    assert probe.resolve("Doc001", "iliquido") == "Iliquido"


def test_resolve_returns_none_for_unknown_column_and_unknown_table():
    probe = SchemaProbe(_reader())
    assert probe.resolve("Doc001", "NoSuchColumn") is None
    assert probe.resolve("NoSuchTable", "Chave") is None


def test_results_are_cached_per_table_and_refresh_clears_them():
    calls = []
    probe = SchemaProbe(_reader(calls))
    probe.columns("Doc001")
    probe.columns("Doc001")
    assert calls == ["Doc001"]
    probe.refresh()
    probe.columns("Doc001")
    assert calls == ["Doc001", "Doc001"]


def test_a_database_failure_raises_schema_unavailable_rather_than_an_empty_map():
    # An empty map would silently mean "no such column" and reject every valid
    # proposal. Validation must fail loudly instead of degrading.
    from logic.bills.rules.schema_probe import SchemaUnavailable

    def broken(sql, params):
        raise OSError("connection reset")

    with pytest.raises(SchemaUnavailable):
        SchemaProbe(broken).columns("Doc001")


def test_a_failed_probe_is_not_cached():
    state = {"fail": True}

    def flaky(sql, params):
        if state["fail"]:
            raise OSError("down")
        return ROWS["Doc001"]

    probe = SchemaProbe(flaky)
    with pytest.raises(Exception):
        probe.columns("Doc001")
    state["fail"] = False
    assert probe.resolve("Doc001", "Chave") == "Chave"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bills/test_schema_probe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'logic.bills.rules.schema_probe'`

- [ ] **Step 3: Write minimal implementation**

```python
# logic/bills/rules/schema_probe.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

_SQL = (
    "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE "
    "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = :table"
)


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool


class SchemaUnavailable(RuntimeError):
    """The schema could not be read. Raised rather than returning an empty map,
    which would look identical to "this table has no such column" and would
    reject every valid proposal instead of reporting the outage."""


class SchemaProbe:
    """The sole authority on which column identifiers exist.

    Nothing else may vouch for a column name: write_executor interpolates
    column names into its INSERT statement, so a name that reaches the rule
    document without passing through here is an injection vector.
    """

    def __init__(self, reader: Callable[[str, dict], list[dict]]) -> None:
        self._read = reader
        self._cache: dict[str, dict[str, ColumnInfo]] = {}

    def columns(self, table: str) -> dict[str, ColumnInfo]:
        """Columns of `table`, keyed by lowercased name. Unknown table -> {}."""
        key = table.lower()
        if key not in self._cache:
            try:
                rows = self._read(_SQL, {"table": table})
            except Exception as e:      # noqa: BLE001 - any read failure is an outage
                raise SchemaUnavailable(f"cannot read schema for {table}: {e}") from e
            # Assigned only on success, so a transient outage is not cached.
            self._cache[key] = {
                r["COLUMN_NAME"].lower(): ColumnInfo(
                    name=r["COLUMN_NAME"],
                    data_type=r["DATA_TYPE"],
                    nullable=r["IS_NULLABLE"] == "YES",
                )
                for r in rows
            }
        return self._cache[key]

    def resolve(self, table: str, column: str) -> str | None:
        """The schema's exact spelling of `column`, or None if it does not exist."""
        info = self.columns(table).get(column.lower())
        return info.name if info else None

    def refresh(self) -> None:
        self._cache.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/bills/test_schema_probe.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add logic/bills/rules/schema_probe.py tests/bills/test_schema_probe.py
git commit -m "feat(bills): schema probe as the sole authority on column identifiers"
```

---

### Task 2: Proposal model, validation, and merge

This is the security core. Test it adversarially.

**Files:**
- Create: `logic/bills/rules/proposal.py`
- Test: `tests/bills/test_rule_proposal.py`

**Interfaces:**
- Consumes: `SchemaProbe` from Task 1; `PurchaseInvoiceRule`, `HeaderFieldRule`, `LineFieldRule` from `logic/bills/rules/models.py`; `Bill`, `BillLine` from `logic/bills/models.py`.
- Produces:
  - `FieldChange` — `action: "set"|"remove"`, `section: "header"|"lines"|"supplier_create"|"article_create"`, `name: str | None`, `column: str | None`, `source: str | None`, `required: bool = False`
  - `RuleChangeProposal` — `rationale: str`, `base_version: int`, `changes: list[FieldChange]`
  - `Violation` — `change_index: int`, `reason: str`
  - `valid_sources() -> set[str]`
  - `table_for(section, rule) -> str`
  - `validate(proposal, rule, schema) -> list[Violation]`
  - `apply(proposal, rule, schema) -> PurchaseInvoiceRule`

- [ ] **Step 1: Write the failing test**

```python
# tests/bills/test_rule_proposal.py
import pytest

from logic.bills.rules.loader import RuleLoader
from logic.bills.rules.proposal import (
    FieldChange, RuleChangeProposal, apply, valid_sources, validate,
)
from logic.bills.rules.schema_probe import SchemaProbe

REAL_COLUMNS = {
    "Doc001": ["Chave", "Entidade", "Data", "Iliquido", "Total", "Obs", "DC", "OC", "Estado"],
    "LinDoc001": ["Documento", "ChaveProd", "Descricao", "Quantidade", "Punit", "CodigoForn"],
    "Entidades": ["Chave", "Nome", "NCont", "Tipo", "Listar"],
    "Artigos": ["Chave", "Nome", "Codigo"],
}


def _schema():
    def read(sql, params):
        return [{"COLUMN_NAME": c, "DATA_TYPE": "varchar", "IS_NULLABLE": "YES"}
                for c in REAL_COLUMNS.get(params["table"], [])]
    return SchemaProbe(read)


@pytest.fixture
def rule():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    return RuleLoader(root / "business_rules" / "bills").rule()


def _proposal(*changes, base=1):
    return RuleChangeProposal(rationale="r", base_version=base, changes=list(changes))


def test_valid_sources_cover_bill_and_line_fields():
    s = valid_sources()
    assert "bill.net_total" in s and "line.description" in s
    assert "supplier.match" in s and "line.match" in s
    # containers, and the deliberately extraction-only buyer_tax_id
    assert "bill.lines" not in s and "bill.confidence" not in s
    assert "bill.buyer_tax_id" not in s


def test_bill_notes_is_not_a_valid_source(rule):
    # The shipped YAML maps source: bill.notes, but Bill has no `notes` field.
    # That mapping is already dead; validation must not let it be reissued.
    assert "bill.notes" not in valid_sources()
    p = _proposal(FieldChange(action="set", section="header", name="notes",
                              column="Obs", source="bill.notes"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "not a known source" in v[0].reason


def test_valid_change_passes_and_merges_with_schema_spelling(rule):
    p = _proposal(FieldChange(action="set", section="lines", name="supplier_code",
                              column="codigoforn", source="line.description"))
    assert validate(p, rule, _schema()) == []
    merged = apply(p, rule, _schema())
    # persisted using the schema's exact spelling, not the admin's casing
    assert merged.lines.fields["supplier_code"].column == "CodigoForn"
    assert merged.version == rule.version + 1


def test_column_absent_from_the_target_table_is_rejected(rule):
    p = _proposal(FieldChange(action="set", section="lines", name="x",
                              column="NoSuchColumn", source="line.description"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "does not exist" in v[0].reason


def test_column_that_exists_but_on_another_table_is_rejected(rule):
    # Iliquido is a real column — on Doc001, not on LinDoc001
    p = _proposal(FieldChange(action="set", section="lines", name="x",
                              column="Iliquido", source="line.total"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "does not exist" in v[0].reason


def test_injection_shaped_identifier_is_rejected_even_if_schema_says_yes(rule):
    evil = "Descricao); DROP TABLE LinDoc001; --"

    class YesProbe:
        def resolve(self, table, column):
            return column          # schema check subverted
        def columns(self, table):
            return {}

    p = _proposal(FieldChange(action="set", section="lines", name="x",
                              column=evil, source="line.description"))
    v = validate(p, rule, YesProbe())
    assert len(v) == 1 and "not a valid identifier" in v[0].reason


def test_unknown_source_is_rejected(rule):
    p = _proposal(FieldChange(action="set", section="header", name="x",
                              column="Obs", source="bill.not_a_field"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "not a known source" in v[0].reason


@pytest.mark.parametrize("column", ["Chave", "DC", "OC", "Estado"])
def test_protected_columns_are_rejected(rule, column):
    # Chave = primary_key, DC/OC = audit_columns values, Estado = draft_defaults key
    p = _proposal(FieldChange(action="set", section="header", name="x",
                              column=column, source="bill.number"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "protected" in v[0].reason


def test_create_column_change_is_validated_against_the_entity_table(rule):
    ok = _proposal(FieldChange(action="set", section="supplier_create", column="Nome"))
    assert validate(ok, rule, _schema()) == []
    bad = _proposal(FieldChange(action="set", section="supplier_create", column="Descricao"))
    assert len(validate(bad, rule, _schema())) == 1


def test_apply_adds_and_removes_create_columns(rule):
    p = _proposal(FieldChange(action="set", section="article_create", column="Codigo"))
    merged = apply(p, rule, _schema())
    assert "Codigo" in merged.matching.article.create_columns

    p2 = RuleChangeProposal(rationale="r", base_version=merged.version, changes=[
        FieldChange(action="remove", section="article_create", column="Codigo")])
    back = apply(p2, merged, _schema())
    assert "Codigo" not in back.matching.article.create_columns


def test_remove_of_a_header_field_drops_the_mapping(rule):
    p = _proposal(FieldChange(action="remove", section="header", name="notes"))
    merged = apply(p, rule, _schema())
    assert "notes" not in merged.header.fields


def test_set_without_a_source_is_rejected_for_mapped_sections(rule):
    p = _proposal(FieldChange(action="set", section="header", name="x", column="Obs"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "source is required" in v[0].reason


def test_violations_report_every_bad_change_not_just_the_first(rule):
    p = _proposal(
        FieldChange(action="set", section="header", name="a", column="Nope", source="bill.number"),
        FieldChange(action="set", section="header", name="b", column="Obs", source="bill.nope"),
    )
    v = validate(p, rule, _schema())
    assert [x.change_index for x in v] == [0, 1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bills/test_rule_proposal.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'logic.bills.rules.proposal'`

- [ ] **Step 3: Write minimal implementation**

```python
# logic/bills/rules/proposal.py
from __future__ import annotations
import re
from typing import Literal

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


def _protected(rule: PurchaseInvoiceRule) -> set[str]:
    """Columns the executor computes for itself. It applies them last precisely
    so a caller cannot override them; admin remapping would undo that."""
    out = {rule.header.primary_key.lower()}
    out |= {c.lower() for c in rule.header.audit_columns.values()}
    out |= {c.lower() for c in rule.header.draft_defaults}
    return out


def validate(proposal: RuleChangeProposal, rule: PurchaseInvoiceRule,
             schema) -> list[Violation]:
    """Every reason `proposal` cannot be applied. Empty list means applicable."""
    out: list[Violation] = []
    sources = valid_sources()
    protected = _protected(rule)

    for i, ch in enumerate(proposal.changes):
        def bad(reason: str) -> None:
            out.append(Violation(change_index=i, reason=reason))

        if ch.section in _MAPPED and ch.action == "remove":
            if not ch.name:
                bad("name is required to remove a mapped field")
            continue
        if ch.section in _CREATE and ch.action == "remove":
            if not ch.column:
                bad("column is required to remove a create column")
            continue

        if ch.section in _MAPPED and not ch.name:
            bad("name is required for a mapped field")
            continue
        if not ch.column:
            bad("column is required")
            continue
        if ch.section in _MAPPED and not ch.source:
            bad("source is required for a mapped field")
            continue

        if not _IDENT_RE.match(ch.column):
            bad(f"{ch.column!r} is not a valid identifier")
            continue
        if ch.column.lower() in protected and ch.section == "header":
            bad(f"{ch.column!r} is protected and cannot be mapped")
            continue

        table = table_for(ch.section, rule)
        if schema.resolve(table, ch.column) is None:
            bad(f"column {ch.column!r} does not exist on {table}")
            continue
        if ch.source is not None and ch.source not in sources:
            bad(f"{ch.source!r} is not a known source")
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
        if ch.column is not None:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/bills/test_rule_proposal.py -v`
Expected: PASS — 16 passed (12 test functions; the protected-column case is parametrized four ways)

- [ ] **Step 5: Commit**

```bash
git add logic/bills/rules/proposal.py tests/bills/test_rule_proposal.py
git commit -m "feat(bills): validated rule-change proposals with an identifier whitelist"
```

---

### Task 3: Versioned rule store

**Files:**
- Create: `logic/bills/rules/store.py`
- Test: `tests/bills/test_rule_store.py`

**Interfaces:**
- Consumes: `PurchaseInvoiceRule` from `logic/bills/rules/models.py`.
- Produces: `RuleStore(directory)` with `.current() -> PurchaseInvoiceRule`, `.save(rule) -> None`, `.versions() -> list[int]`, `.historical(version) -> PurchaseInvoiceRule`, `.revert(version) -> PurchaseInvoiceRule`.

- [ ] **Step 1: Write the failing test**

```python
# tests/bills/test_rule_store.py
import shutil
from pathlib import Path

import pytest
import yaml

from logic.bills.rules.store import RuleStore

_SRC = Path(__file__).resolve().parents[2] / "business_rules" / "bills" / "purchase_invoice.yaml"


@pytest.fixture
def store(tmp_path):
    shutil.copy(_SRC, tmp_path / "purchase_invoice.yaml")
    return RuleStore(tmp_path)


def test_current_loads_the_document(store):
    assert store.current().document == "purchase_invoice"


def test_save_archives_the_previous_version_then_replaces(store, tmp_path):
    original = store.current()
    bumped = original.model_copy(update={"version": original.version + 1})
    store.save(bumped)

    assert store.current().version == original.version + 1
    assert store.versions() == [original.version]
    assert store.historical(original.version).version == original.version


def test_revert_produces_a_new_version_carrying_the_old_content(store):
    v1 = store.current()
    v2 = v1.model_copy(update={"version": 2})
    v2.header.fields.pop("notes")
    store.save(v2)

    reverted = store.revert(1)

    assert reverted.version == 3                     # forward, never rewound
    assert "notes" in reverted.header.fields         # v1's content is back
    assert store.versions() == [1, 2]                # history intact


def test_saved_yaml_reloads_through_the_same_store(store):
    original = store.current()
    store.save(original.model_copy(update={"version": 9}))
    assert store.current().version == 9


def test_a_failed_write_leaves_the_previous_document_intact(store, tmp_path, monkeypatch):
    original_text = (tmp_path / "purchase_invoice.yaml").read_text(encoding="utf-8")

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr("logic.bills.rules.store.os.replace", boom)
    with pytest.raises(OSError):
        store.save(store.current().model_copy(update={"version": 42}))

    assert (tmp_path / "purchase_invoice.yaml").read_text(encoding="utf-8") == original_text
    assert not list(tmp_path.glob("*.tmp"))


def test_historical_for_an_unknown_version_raises(store):
    with pytest.raises(FileNotFoundError):
        store.historical(99)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bills/test_rule_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'logic.bills.rules.store'`

- [ ] **Step 3: Write minimal implementation**

```python
# logic/bills/rules/store.py
from __future__ import annotations
import os
import tempfile
from pathlib import Path

import yaml

from logic.bills.rules.models import PurchaseInvoiceRule

_NAME = "purchase_invoice.yaml"


class RuleStore:
    """Versioned persistence for the purchase-invoice rule document.

    History is append-only: reverting to v3 from v5 writes v6 carrying v3's
    content. Committed documents record the version that authorized them via
    WritePlan.rule_version, so rewinding would leave them citing a version whose
    meaning had silently changed.
    """

    def __init__(self, directory: Path | str) -> None:
        self._dir = Path(directory)
        self._path = self._dir / _NAME
        self._history = self._dir / "history"

    def current(self) -> PurchaseInvoiceRule:
        return PurchaseInvoiceRule.model_validate(
            yaml.safe_load(self._path.read_text(encoding="utf-8")))

    def versions(self) -> list[int]:
        if not self._history.exists():
            return []
        return sorted(int(p.stem.split(".v")[1])
                      for p in self._history.glob("purchase_invoice.v*.yaml"))

    def historical(self, version: int) -> PurchaseInvoiceRule:
        p = self._history / f"purchase_invoice.v{version}.yaml"
        if not p.exists():
            raise FileNotFoundError(f"no archived rule for version {version}")
        return PurchaseInvoiceRule.model_validate(
            yaml.safe_load(p.read_text(encoding="utf-8")))

    def save(self, rule: PurchaseInvoiceRule) -> None:
        previous = self.current()
        self._history.mkdir(parents=True, exist_ok=True)
        archive = self._history / f"purchase_invoice.v{previous.version}.yaml"
        archive.write_text(self._path.read_text(encoding="utf-8"), encoding="utf-8")
        self._atomic_write(yaml.safe_dump(rule.model_dump(mode="json"),
                                          sort_keys=False, allow_unicode=True))

    def revert(self, version: int) -> PurchaseInvoiceRule:
        old = self.historical(version)
        forward = old.model_copy(update={"version": self.current().version + 1})
        self.save(forward)
        return forward

    def _atomic_write(self, text: str) -> None:
        """Write via a temp file in the same directory, then os.replace, so an
        interrupted save cannot leave a half-written document that fails to load
        at next boot."""
        fd, tmp = tempfile.mkstemp(dir=str(self._dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, self._path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/bills/test_rule_store.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add logic/bills/rules/store.py tests/bills/test_rule_store.py
git commit -m "feat(bills): versioned rule store with append-only history"
```

---

### Task 4: Claude drafts the structured patch

**Files:**
- Create: `logic/bills/rules/proposer.py`
- Test: `tests/bills/test_rule_proposer.py`

**Interfaces:**
- Consumes: `RuleChangeProposal` from Task 2; `SchemaProbe` from Task 1; the synchronous `anthropic.Anthropic` client shape already used by `BillParser` (`client.messages.create(...)` returning `.content` blocks with `.type`/`.text`).
- Produces: `RuleDraftError(RuntimeError)`; `RuleProposer(client, model)` with `.draft(prose, rule, schema) -> RuleChangeProposal`.

- [ ] **Step 1: Write the failing test**

```python
# tests/bills/test_rule_proposer.py
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from logic.bills.rules.loader import RuleLoader
from logic.bills.rules.proposer import RuleDraftError, RuleProposer
from logic.bills.rules.schema_probe import SchemaProbe


@pytest.fixture
def rule():
    root = Path(__file__).resolve().parents[2]
    return RuleLoader(root / "business_rules" / "bills").rule()


def _schema():
    cols = {"LinDoc001": ["Descricao", "CodigoForn"], "Doc001": ["Obs"],
            "Entidades": ["Nome"], "Artigos": ["Nome"]}
    def read(sql, params):
        return [{"COLUMN_NAME": c, "DATA_TYPE": "varchar", "IS_NULLABLE": "YES"}
                for c in cols.get(params["table"], [])]
    return SchemaProbe(read)


class FakeClient:
    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self._reply)])


def _client(reply: str) -> FakeClient:
    return FakeClient(reply)


PATCH = json.dumps({
    "rationale": "supplier's own code belongs in CodigoForn",
    "base_version": 1,
    "changes": [{"action": "set", "section": "lines", "name": "supplier_code",
                 "column": "CodigoForn", "source": "line.description",
                 "required": False}],
})


def test_draft_parses_a_structured_patch(rule):
    proposer = RuleProposer(_client(PATCH), "claude-sonnet-4-6")
    p = proposer.draft("supplier code goes to CodigoForn", rule, _schema())
    assert p.base_version == 1
    assert p.changes[0].column == "CodigoForn"


def test_draft_tolerates_prose_around_the_json(rule):
    proposer = RuleProposer(_client("Sure!\n" + PATCH + "\nHope that helps."),
                            "claude-sonnet-4-6")
    assert proposer.draft("x", rule, _schema()).changes[0].name == "supplier_code"


def test_draft_raises_when_there_is_no_json(rule):
    proposer = RuleProposer(_client("I cannot help with that."), "claude-sonnet-4-6")
    with pytest.raises(RuleDraftError):
        proposer.draft("x", rule, _schema())


def test_draft_raises_when_the_json_does_not_match_the_model(rule):
    proposer = RuleProposer(_client('{"rationale": "r", "changes": "not a list"}'),
                            "claude-sonnet-4-6")
    with pytest.raises(RuleDraftError):
        proposer.draft("x", rule, _schema())


def test_prompt_carries_the_real_columns_and_sources(rule):
    client = _client(PATCH)
    RuleProposer(client, "claude-sonnet-4-6").draft("x", rule, _schema())
    system = client.calls[0]["system"]
    assert "CodigoForn" in system          # real schema columns offered
    assert "line.description" in system    # real sources offered
    assert "temperature" in client.calls[0] and client.calls[0]["temperature"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bills/test_rule_proposer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'logic.bills.rules.proposer'`

- [ ] **Step 3: Write minimal implementation**

```python
# logic/bills/rules/proposer.py
from __future__ import annotations
import json
import re
from typing import Any

from pydantic import ValidationError

from logic.bills.rules.models import PurchaseInvoiceRule
from logic.bills.rules.proposal import (
    RuleChangeProposal, table_for, valid_sources,
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_SECTIONS = ("header", "lines", "supplier_create", "article_create")

_SYSTEM = (
    "You translate an administrator's description of a business rule into a "
    "structured change to a purchase-invoice write mapping. "
    "Return ONLY a JSON object with keys: rationale (string), base_version "
    "(integer), and changes (a list). Each change has: action (\"set\" or "
    "\"remove\"), section (one of {sections}), name (the logical field key, for "
    "header and lines only), column (the database column), source (the extracted "
    "field, for header and lines only), and required (boolean).\n\n"
    "You may ONLY use columns and sources from the lists below. If the request "
    "cannot be expressed with them, return an empty changes list and explain why "
    "in rationale. Never invent a column name.\n\n"
    "Current mapping (version {version}):\n{mapping}\n\n"
    "Columns that exist, by table:\n{columns}\n\n"
    "Sources that exist:\n{sources}\n"
)


class RuleDraftError(RuntimeError):
    """Claude did not return a patch matching RuleChangeProposal. A RuntimeError
    so the route turns it into a 422 the admin can act on, not a bare 500."""


class RuleProposer:
    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    def _system(self, rule: PurchaseInvoiceRule, schema) -> str:
        columns = "\n".join(
            f"  {table_for(s, rule)}: "
            + ", ".join(sorted(c.name for c in schema.columns(table_for(s, rule)).values()))
            for s in _SECTIONS
        )
        mapping = "\n".join(
            [f"  header.{k}: {v.column} <- {v.source}" for k, v in rule.header.fields.items()]
            + [f"  lines.{k}: {v.column} <- {v.source}" for k, v in rule.lines.fields.items()]
            + [f"  supplier_create: {', '.join(rule.matching.supplier.create_columns)}",
               f"  article_create: {', '.join(rule.matching.article.create_columns)}"]
        )
        return _SYSTEM.format(
            sections=", ".join(_SECTIONS), version=rule.version,
            mapping=mapping, columns=columns,
            sources=", ".join(sorted(valid_sources())),
        )

    def draft(self, prose: str, rule: PurchaseInvoiceRule,
              schema) -> RuleChangeProposal:
        resp = self._client.messages.create(
            model=self._model, max_tokens=2048, temperature=0,
            system=self._system(rule, schema),
            messages=[{"role": "user", "content": prose}],
        )
        text = "".join(getattr(c, "text", "") for c in resp.content
                       if getattr(c, "type", None) == "text")
        m = _JSON_RE.search(text)
        if not m:
            raise RuleDraftError(f"no JSON object in the reply: {text[:300]}")
        try:
            return RuleChangeProposal.model_validate(json.loads(m.group(0)))
        except (json.JSONDecodeError, ValidationError) as e:
            raise RuleDraftError(f"reply did not match the patch schema: {e}") from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/bills/test_rule_proposer.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add logic/bills/rules/proposer.py tests/bills/test_rule_proposer.py
git commit -m "feat(bills): Claude drafts rule changes as structured patches"
```

---

### Task 5: Admin gate, endpoints, and service reload

**Files:**
- Modify: `logic/bills/app.py` — add imports, `reset_service()`, admin helpers and five routes. Insert the routes after `commit` (currently `app.py:125-133`) and before `_favicon` (`app.py:136`), so they land above the `StaticFiles` mount at `app.py:141-142` which answers anything unrouted.
- Modify: `tests/conftest.py:16` — add `BILLS_ADMIN_TOKEN` to the blanked list.
- Test: `tests/bills/test_admin_rules.py`

**Interfaces:**
- Consumes: `SchemaProbe` (Task 1), `validate`/`apply`/`RuleChangeProposal` (Task 2), `RuleStore` (Task 3), `RuleProposer`/`RuleDraftError` (Task 4), the existing `AuditLog` (`logic/chat/audit.py`) and `_read` (`app.py:58`).
- Produces: routes `GET /admin/rules/enabled`, `GET /admin/rules/current`, `POST /admin/rules/draft`, `POST /admin/rules/apply`, `POST /admin/rules/revert/{version}`; module functions `reset_service()`, `get_rule_store()`, `get_schema_probe()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/bills/test_admin_rules.py
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import logic.bills.app as appmod

_SRC = Path(__file__).resolve().parents[2] / "business_rules" / "bills" / "purchase_invoice.yaml"

PATCH = {
    "rationale": "supplier's own code",
    "base_version": 1,
    "changes": [{"action": "set", "section": "lines", "name": "supplier_code",
                 "column": "CodigoForn", "source": "line.description",
                 "required": False}],
}

COLUMNS = {
    "Doc001": ["Chave", "Entidade", "Data", "Iliquido", "Total", "Obs", "DC", "OC", "Estado"],
    "LinDoc001": ["Documento", "ChaveProd", "Descricao", "Quantidade", "Punit", "CodigoForn"],
    "Entidades": ["Chave", "Nome", "NCont", "Tipo", "Listar"],
    "Artigos": ["Chave", "Nome", "Codigo"],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    shutil.copy(_SRC, tmp_path / "purchase_invoice.yaml")
    monkeypatch.setattr(appmod, "_RULES_DIR", tmp_path)
    monkeypatch.setattr(appmod, "_WRITE_LOG_PATH", tmp_path / "bills_writes.jsonl")
    monkeypatch.setenv("BILLS_ADMIN_TOKEN", "s3cret")

    def read(sql, params):
        return [{"COLUMN_NAME": c, "DATA_TYPE": "varchar", "IS_NULLABLE": "YES"}
                for c in COLUMNS.get(params["table"], [])]
    monkeypatch.setattr(appmod, "_read", read)

    class FakeProposer:
        def draft(self, prose, rule, schema):
            from logic.bills.rules.proposal import RuleChangeProposal
            return RuleChangeProposal.model_validate(PATCH)
    monkeypatch.setattr(appmod, "get_proposer", lambda: FakeProposer())

    appmod.reset_service()
    return TestClient(appmod.app)


def _h(token="s3cret"):
    return {"X-Admin-Token": token}


def test_routes_are_404_when_the_token_is_unset(client, monkeypatch):
    monkeypatch.delenv("BILLS_ADMIN_TOKEN", raising=False)
    assert client.get("/admin/rules/current", headers=_h()).status_code == 404
    assert client.get("/admin/rules/enabled").json() == {"enabled": False}


def test_wrong_token_is_403(client):
    assert client.get("/admin/rules/current", headers=_h("nope")).status_code == 403


def test_current_reports_version_schema_and_history(client):
    body = client.get("/admin/rules/current", headers=_h()).json()
    assert body["version"] == 1
    assert "CodigoForn" in body["schema"]["LinDoc001"]
    assert body["history"] == []


def test_draft_returns_a_validated_proposal_with_no_violations(client):
    r = client.post("/admin/rules/draft", headers=_h(),
                    json={"prose": "supplier code to CodigoForn"})
    assert r.status_code == 200
    assert r.json()["violations"] == []
    assert r.json()["proposal"]["changes"][0]["column"] == "CodigoForn"


def test_apply_bumps_the_version_and_audits(client, tmp_path):
    client.post("/admin/rules/apply", headers=_h(),
                json={"proposal": PATCH, "base_version": 1})
    assert client.get("/admin/rules/current", headers=_h()).json()["version"] == 2

    rows = [json.loads(l) for l in
            (tmp_path / "bills_writes.jsonl").read_text(encoding="utf-8").splitlines()]
    changes = [r for r in rows if r.get("kind") == "rule_change"]
    assert len(changes) == 1
    assert changes[0]["from_version"] == 1 and changes[0]["to_version"] == 2


def test_apply_with_a_stale_base_version_is_409_and_changes_nothing(client):
    client.post("/admin/rules/apply", headers=_h(),
                json={"proposal": PATCH, "base_version": 1})
    r = client.post("/admin/rules/apply", headers=_h(),
                    json={"proposal": PATCH, "base_version": 1})
    assert r.status_code == 409
    assert client.get("/admin/rules/current", headers=_h()).json()["version"] == 2


def test_apply_of_an_invalid_proposal_is_422_and_changes_nothing(client):
    bad = dict(PATCH, changes=[dict(PATCH["changes"][0], column="NoSuchColumn")])
    r = client.post("/admin/rules/apply", headers=_h(),
                    json={"proposal": bad, "base_version": 1})
    assert r.status_code == 422
    assert r.json()["violations"][0]["reason"]
    assert client.get("/admin/rules/current", headers=_h()).json()["version"] == 1


def test_apply_reloads_the_service_so_the_new_mapping_is_live(client):
    client.post("/admin/rules/apply", headers=_h(),
                json={"proposal": PATCH, "base_version": 1})
    from logic.bills.rules.store import RuleStore
    rule = RuleStore(appmod._RULES_DIR).current()
    assert rule.lines.fields["supplier_code"].column == "CodigoForn"
    assert appmod._service is None      # reset; rebuilt lazily on next request


def test_revert_walks_forward_to_a_new_version(client):
    client.post("/admin/rules/apply", headers=_h(),
                json={"proposal": PATCH, "base_version": 1})
    r = client.post("/admin/rules/revert/1", headers=_h())
    assert r.status_code == 200
    assert r.json()["version"] == 3


def test_revert_to_an_unknown_version_is_404(client):
    assert client.post("/admin/rules/revert/99", headers=_h()).status_code == 404


def test_a_schema_outage_is_503_not_a_silent_rejection(client, monkeypatch):
    def broken(sql, params):
        raise OSError("connection reset")
    monkeypatch.setattr(appmod, "_read", broken)
    appmod.reset_service()          # drop the cached probe
    r = client.get("/admin/rules/current", headers=_h())
    assert r.status_code == 503
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bills/test_admin_rules.py -v`
Expected: FAIL — `AttributeError: module 'logic.bills.app' has no attribute 'reset_service'`

- [ ] **Step 3: Add `BILLS_ADMIN_TOKEN` to the conftest blanklist**

Modify `tests/conftest.py:16` — the loop currently reads:

```python
for _var in ("APP_PASSWORD", "BILLS_APP_PASSWORD", "CHAT_FEEDBACK_TOKEN"):
```

Change it to:

```python
for _var in ("APP_PASSWORD", "BILLS_APP_PASSWORD", "BILLS_ADMIN_TOKEN",
             "CHAT_FEEDBACK_TOKEN"):
```

- [ ] **Step 4: Write the implementation**

Add to the imports at the top of `logic/bills/app.py`:

```python
import secrets

from logic.bills.rules.proposal import RuleChangeProposal, apply as apply_patch, validate
from logic.bills.rules.proposer import RuleDraftError, RuleProposer
from logic.bills.rules.schema_probe import SchemaProbe, SchemaUnavailable
from logic.bills.rules.store import RuleStore
```

Add `reset_service` and the admin plumbing immediately after `get_service` (after `app.py:85`):

```python
def reset_service() -> None:
    """Drop the memoised service so the next request rebuilds it from the rule
    document on disk. RuleLoader parses that document once in __init__, so an
    applied rule change is invisible until this runs."""
    global _service, _schema_probe
    _service = None
    _schema_probe = None


_schema_probe: SchemaProbe | None = None


def get_schema_probe() -> SchemaProbe:
    global _schema_probe
    if _schema_probe is None:
        _schema_probe = SchemaProbe(_read)
    return _schema_probe


def get_rule_store() -> RuleStore:
    return RuleStore(_RULES_DIR)


def get_proposer() -> RuleProposer:
    return RuleProposer(_build_anthropic(), "claude-sonnet-4-6")


def _admin_token() -> str | None:
    return os.environ.get("BILLS_ADMIN_TOKEN") or None


def _require_admin(request: Request) -> None:
    token = _admin_token()
    if not token:
        raise HTTPException(status_code=404, detail="admin rules disabled")
    if not secrets.compare_digest(request.headers.get("X-Admin-Token", ""), token):
        raise HTTPException(status_code=403, detail="invalid admin token")


def _rule_audit() -> AuditLog:
    return AuditLog(_WRITE_LOG_PATH)
```

Register a handler so a schema outage is a 503 rather than a bare 500. Validation must
never be skipped, so the admin routes refuse to operate rather than degrade. Add
immediately after the `install_password_gate` call (`app.py:43-44`):

```python
@app.exception_handler(SchemaUnavailable)
async def _schema_unavailable(_request: Request, exc: SchemaUnavailable) -> Response:
    return JSONResponse({"detail": str(exc)}, status_code=503)
```

and add `SchemaUnavailable` to the `schema_probe` import.

Add the routes after `commit` (after `app.py:133`) and before `_favicon`:

```python
@app.get("/admin/rules/enabled")
def admin_rules_enabled() -> dict:
    return {"enabled": _admin_token() is not None}


@app.get("/admin/rules/current")
def admin_rules_current(request: Request) -> dict:
    _require_admin(request)
    store = get_rule_store()
    rule = store.current()
    probe = get_schema_probe()
    tables = [rule.header.table, rule.lines.table,
              rule.matching.supplier.table, rule.matching.article.table]
    return {
        "version": rule.version,
        "rule": rule.model_dump(mode="json"),
        "schema": {t: sorted(c.name for c in probe.columns(t).values()) for t in tables},
        "history": store.versions(),
    }


@app.post("/admin/rules/draft")
async def admin_rules_draft(request: Request) -> Response:
    _require_admin(request)
    prose = (await request.json()).get("prose", "").strip()
    if not prose:
        return JSONResponse({"detail": "prose required"}, status_code=400)
    rule = get_rule_store().current()
    probe = get_schema_probe()
    try:
        proposal = get_proposer().draft(prose, rule, probe)
    except RuleDraftError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    return JSONResponse({
        "proposal": proposal.model_dump(mode="json"),
        "violations": [v.model_dump() for v in validate(proposal, rule, probe)],
    })


@app.post("/admin/rules/apply")
async def admin_rules_apply(request: Request) -> Response:
    _require_admin(request)
    body = await request.json()
    store = get_rule_store()
    rule = store.current()

    if body.get("base_version") != rule.version:
        return JSONResponse(
            {"detail": f"rule is at version {rule.version}; re-draft your change"},
            status_code=409)

    try:
        proposal = RuleChangeProposal.model_validate(body.get("proposal") or {})
    except ValidationError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)

    probe = get_schema_probe()
    violations = validate(proposal, rule, probe)
    if violations:
        return JSONResponse({"violations": [v.model_dump() for v in violations]},
                            status_code=422)

    try:
        merged = apply_patch(proposal, rule, probe)
    except ValidationError as e:
        # The merge produced a document PurchaseInvoiceRule rejects — extra="forbid"
        # catching something structural the per-change checks did not model.
        # The YAML on disk is untouched; save() has not been reached.
        return JSONResponse({"detail": f"merged rule is invalid: {e}"},
                            status_code=422)

    store.save(merged)
    _rule_audit().append({
        "ts": AuditLog.now_iso(), "kind": "rule_change", "action": "apply",
        "from_version": rule.version, "to_version": merged.version,
        "rationale": proposal.rationale,
        "changes": [c.model_dump() for c in proposal.changes],
        "operator": _operator(request),
    })
    reset_service()
    return JSONResponse({"version": merged.version})


@app.post("/admin/rules/revert/{version}")
def admin_rules_revert(version: int, request: Request) -> Response:
    _require_admin(request)
    store = get_rule_store()
    previous = store.current().version
    try:
        reverted = store.revert(version)
    except FileNotFoundError:
        return JSONResponse({"detail": f"no archived rule for version {version}"},
                            status_code=404)
    _rule_audit().append({
        "ts": AuditLog.now_iso(), "kind": "rule_change", "action": "revert",
        "from_version": previous, "to_version": reverted.version,
        "reverted_to": version, "operator": _operator(request),
    })
    reset_service()
    return JSONResponse({"version": reverted.version})
```

Add `ValidationError` to the imports:

```python
from pydantic import ValidationError
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/bills/test_admin_rules.py -v`
Expected: PASS — 11 passed

- [ ] **Step 6: Verify the operator path did not regress**

Run: `python -m pytest tests/bills -q`
Expected: PASS — no failures; `test_app.py` in particular unchanged

- [ ] **Step 7: Commit**

```bash
git add logic/bills/app.py tests/bills/test_admin_rules.py tests/conftest.py
git commit -m "feat(bills): admin endpoints for drafting and applying write-mapping changes"
```

---

### Task 6: Admin panel in the bills UI

**Files:**
- Create: `ui/bills/admin.js`
- Modify: `ui/bills/index.html` — add the panel markup and the module script tag
- Modify: `ui/bills/bills.css` — panel styles

**Interfaces:**
- Consumes: the five routes from Task 5.
- Produces: no exports consumed elsewhere; `admin.js` self-initialises on import.

- [ ] **Step 1: Write `ui/bills/admin.js`**

```javascript
// Admin panel: draft a mapping change in prose, review the diff, apply it.
// Hidden unless the server reports the feature on AND a token is stored —
// the same two-part gate ui/chat/app.js uses for Teach/Fix.
const TOKEN_KEY = "bills_admin_token";

const panel = document.getElementById("admin-panel");
const tokenInput = document.getElementById("admin-token");
const proseInput = document.getElementById("admin-prose");
const draftBtn = document.getElementById("admin-draft");
const applyBtn = document.getElementById("admin-apply");
const out = document.getElementById("admin-output");
const versionEl = document.getElementById("admin-version");
const historyEl = document.getElementById("admin-history");

let current = null;     // { version, rule, schema, history }
let proposal = null;

const token = () => localStorage.getItem(TOKEN_KEY) || "";
const headers = () => ({ "Content-Type": "application/json", "X-Admin-Token": token() });

async function init() {
  const r = await fetch("/admin/rules/enabled");
  if (!(await r.json()).enabled) return;
  panel.hidden = false;
  tokenInput.value = token();
  if (token()) await refresh();
}

tokenInput.addEventListener("change", async () => {
  const v = tokenInput.value.trim();
  if (v) localStorage.setItem(TOKEN_KEY, v);
  else localStorage.removeItem(TOKEN_KEY);
  await refresh();
});

async function refresh() {
  const r = await fetch("/admin/rules/current", { headers: headers() });
  if (!r.ok) { out.textContent = `Cannot load rules (${r.status})`; return; }
  current = await r.json();
  versionEl.textContent = `v${current.version}`;
  historyEl.replaceChildren(...current.history.map(v => {
    const b = document.createElement("button");
    b.textContent = `revert to v${v}`;
    b.addEventListener("click", () => revert(v));
    return b;
  }));
  renderMapping();
}

function renderMapping() {
  const rows = [];
  for (const [k, f] of Object.entries(current.rule.header.fields))
    rows.push(`header.${k}: ${f.column} <- ${f.source}`);
  for (const [k, f] of Object.entries(current.rule.lines.fields))
    rows.push(`lines.${k}: ${f.column} <- ${f.source}`);
  out.textContent = rows.join("\n");
  applyBtn.hidden = true;
}

draftBtn.addEventListener("click", async () => {
  const r = await fetch("/admin/rules/draft", {
    method: "POST", headers: headers(),
    body: JSON.stringify({ prose: proseInput.value }),
  });
  const body = await r.json();
  if (!r.ok) { out.textContent = body.detail || `Draft failed (${r.status})`; return; }
  proposal = body.proposal;
  const lines = body.proposal.changes.map(c => c.action === "remove"
    ? `- remove ${c.section}.${c.name ?? c.column}`
    : `+ ${c.section}.${c.name ?? c.column} -> ${c.column}` +
      (c.source ? ` <- ${c.source}` : ""));
  if (body.violations.length) {
    out.textContent = "Rejected:\n" +
      body.violations.map(v => `  change ${v.change_index}: ${v.reason}`).join("\n");
    applyBtn.hidden = true;
    return;
  }
  out.textContent = `${body.proposal.rationale}\n\n${lines.join("\n")}`;
  applyBtn.hidden = false;
});

applyBtn.addEventListener("click", async () => {
  const r = await fetch("/admin/rules/apply", {
    method: "POST", headers: headers(),
    body: JSON.stringify({ proposal, base_version: current.version }),
  });
  const body = await r.json();
  if (r.status === 409) { out.textContent = body.detail; await refresh(); return; }
  if (!r.ok) {
    out.textContent = body.violations
      ? body.violations.map(v => `change ${v.change_index}: ${v.reason}`).join("\n")
      : (body.detail || `Apply failed (${r.status})`);
    return;
  }
  proseInput.value = "";
  await refresh();
});

async function revert(v) {
  const r = await fetch(`/admin/rules/revert/${v}`, { method: "POST", headers: headers() });
  if (!r.ok) { out.textContent = `Revert failed (${r.status})`; return; }
  await refresh();
}

init();
```

- [ ] **Step 2: Add the panel to `ui/bills/index.html`**

Insert before the closing `</body>` tag, after the existing app script tag:

```html
<section id="admin-panel" hidden class="admin">
  <h2>Write mapping <span id="admin-version"></span></h2>
  <label>Admin token <input id="admin-token" type="password" autocomplete="off"></label>
  <textarea id="admin-prose" rows="3"
    placeholder="e.g. the supplier's own article code belongs in LinDoc001.CodigoForn"></textarea>
  <div class="admin-actions">
    <button id="admin-draft">Draft change</button>
    <button id="admin-apply" hidden>Apply</button>
  </div>
  <pre id="admin-output"></pre>
  <div id="admin-history" class="admin-history"></div>
</section>
<script type="module" src="./admin.js"></script>
```

- [ ] **Step 3: Add styles to `ui/bills/bills.css`**

Append:

```css
.admin { margin-top: 2rem; padding: 1rem; border: 1px solid #d0d0d0; border-radius: 6px; }
.admin h2 { margin: 0 0 .5rem; font-size: 1rem; }
.admin label { display: block; margin-bottom: .5rem; font-size: .85rem; }
.admin textarea { width: 100%; box-sizing: border-box; }
.admin-actions { margin: .5rem 0; display: flex; gap: .5rem; }
.admin pre { white-space: pre-wrap; background: #f6f6f6; padding: .75rem; border-radius: 4px; }
.admin-history { display: flex; gap: .5rem; flex-wrap: wrap; }
```

- [ ] **Step 4: Verify manually**

Run: `BILLS_ADMIN_TOKEN=dev uvicorn logic.bills.app:app --reload --port 8002`

Open http://localhost:8002/. Confirm: the panel is visible; entering the token loads the current mapping and version; a prose request produces a diff; Apply bumps the version; a revert button appears and works. Then restart without `BILLS_ADMIN_TOKEN` and confirm the panel stays hidden.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest tests -q`
Expected: PASS — no failures

- [ ] **Step 6: Commit**

```bash
git add ui/bills/admin.js ui/bills/index.html ui/bills/bills.css
git commit -m "feat(bills): admin panel for authoring write-mapping changes"
```

---

## Notes for the implementer

**Do not touch `logic/bills/write_executor.py`.** Its `_check_columns` whitelist is the last line of defence and its tests encode that. This plan makes the *rule document* editable; the executor keeps trusting a validated rule object exactly as before.

**The identifier regex is not redundant.** `test_injection_shaped_identifier_is_rejected_even_if_schema_says_yes` stubs the schema probe to approve everything. If you reorder validation so the regex runs after an early `continue`, that test fails — which is the point.

**`RuleLoader` parses once in `__init__`.** Every path that changes the document must call `reset_service()`, or the running service keeps the old mapping until the next deploy.

**Pre-existing bug found while writing this plan — do not fix it here.** The shipped
`business_rules/bills/purchase_invoice.yaml` contains:

```yaml
notes: { column: Obs, source: bill.notes }
```

`Bill` has no `notes` field (`logic/bills/models.py:30-45`), so this mapping is dead —
`Doc001.Obs` is wired to a source that never resolves and is presumably never populated.
Nothing in the current code errors on it; the mapping is simply skipped.

`valid_sources()` is derived from the model, so it correctly refuses `bill.notes`, and
`test_bill_notes_is_not_a_valid_source` pins that. The consequence to be aware of: once an
admin removes the `notes` mapping they cannot re-add it, because the source does not exist.

Fixing it properly means either adding a `notes` field to `Bill` and extracting it, or
deleting the dead mapping from the YAML. Both are out of scope for this plan and should be
raised separately — a change to `Bill` touches the extraction prompt, which this work is
explicitly not modifying.
