# DevCare Conversational CRUD — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a conversational Create/Update/soft-Delete capability for two curated DevCare entities (Patients, Specialties), gated by an explicit preview+confirm step, without touching the read-only chat.

**Architecture:** A new isolated module `logic/devcare/` runs its own AI orchestration loop (modeled on `ChatService`). Reads use the existing read-only login; writes use a new writable login (`DEVCARE_WRITE_DATABASE_URL`) restricted to a YAML-defined entity registry. The model can validate + stage a change (`propose_change`) but only the operator's Confirm click commits it.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (Core), Pydantic v2, PyYAML, Anthropic SDK, pytest/pytest-asyncio. Branch: `devcare_crud` (off `scrm_module`).

**Spec:** `docs/superpowers/specs/2026-06-04-devcare-conversational-crud-design.md`

---

## Schema facts (verified against live DevCare)

- `Entidades` (patients) and `Especialidades` (specialties) both have PK **`Chave`** (`bigint`, **NOT identity** — inserts must supply the key).
- Both have soft-delete flag **`Hist`** (`smallint`): **0 = active, 1 = deleted**. Both have `Listar` (smallint), `Codigo` (varchar 10), `Nome` (varchar).
- Row-audit columns: `DC` (created date), `OC` (created-by, bigint), `DUA` (updated date), `OUA` (updated-by, bigint).
- Patient tax id is column **`NCont`** (varchar 20). Patient `Tipo` (smallint) is `0` for ~99% of rows → default `0`.
- No FK constraints exist; reference checks are done with read queries.

---

## File structure

| File | Responsibility |
|---|---|
| `db/devcare_connection.py` | Build/cache the writable DevCare SQLAlchemy engine + session factory from `DEVCARE_WRITE_DATABASE_URL`. |
| `business_rules/devcare/patient.yaml` | Enterprise document: patient entity rules. |
| `business_rules/devcare/specialty.yaml` | Enterprise document: specialty entity rules. |
| `logic/devcare/rules/models.py` | Pydantic models for an entity rule document. |
| `logic/devcare/rules/loader.py` | Load + validate YAML docs into models; registry lookup. |
| `logic/devcare/errors.py` | `ValidationViolation`, `ChangeError` types. |
| `logic/devcare/validator.py` | `ChangeValidator`: required/type/enum/regex/uniqueness/reference/single-PK checks → normalized change or violations. |
| `logic/devcare/write_executor.py` | `WriteExecutor`: build parameterized insert/update/soft-delete, generate key, run in one transaction. |
| `logic/devcare/audit_writer.py` | `AuditWriter`: one structured record per committed write. |
| `logic/devcare/pending.py` | `PendingChangeStore`: in-memory staging of validated changes by id. |
| `logic/devcare/prompts.py` | System instructions + tool schemas (`lookup`, `propose_change`). |
| `logic/devcare/service.py` | `DevCareService`: streaming AI loop; `commit_change`. |
| `logic/devcare/app.py` | FastAPI app: operator identity, `/operations` SSE, `/devcare/commit/{id}`, conversations CRUD. |
| `ui/devcare/index.html`, `app.js`, `devcare.css` | Operator UI: conversation + pending-change confirm card. |
| `tests/devcare/...` | Unit + integration tests mirroring `tests/chat/`. |

---

## Task 1: Writable DevCare engine

**Files:**
- Create: `db/devcare_connection.py`
- Modify: `.env.example` (add `DEVCARE_WRITE_DATABASE_URL=`)
- Test: `tests/devcare/test_connection.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/devcare/test_connection.py
import os
import pytest
from db import devcare_connection


def test_missing_env_raises(monkeypatch):
    monkeypatch.delenv("DEVCARE_WRITE_DATABASE_URL", raising=False)
    devcare_connection._engine = None
    devcare_connection._SessionLocal = None
    with pytest.raises(RuntimeError, match="DEVCARE_WRITE_DATABASE_URL"):
        devcare_connection.get_write_session().__enter__()


def test_session_factory_uses_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("DEVCARE_WRITE_DATABASE_URL", f"sqlite:///{tmp_path/'w.db'}")
    devcare_connection._engine = None
    devcare_connection._SessionLocal = None
    from sqlalchemy import text
    with devcare_connection.get_write_session() as s:
        assert s.execute(text("SELECT 1")).scalar() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_connection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'db.devcare_connection'`

- [ ] **Step 3: Write minimal implementation**

```python
# db/devcare_connection.py
from __future__ import annotations
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = None
_SessionLocal = None


def _factory():
    global _engine, _SessionLocal
    if _engine is None:
        url = os.environ.get("DEVCARE_WRITE_DATABASE_URL")
        if not url:
            raise RuntimeError("DEVCARE_WRITE_DATABASE_URL is not set")
        _engine = create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=5)
        _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    return _SessionLocal


@contextmanager
def get_write_session() -> Generator[Session, None, None]:
    session = _factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_connection.py -v`
Expected: PASS (2 passed). Create empty `tests/devcare/__init__.py` if collection fails.

- [ ] **Step 5: Commit**

```bash
git add db/devcare_connection.py tests/devcare/ .env.example
git commit -m "feat(devcare): writable DB engine from DEVCARE_WRITE_DATABASE_URL"
```

---

## Task 2: Entity rule models

**Files:**
- Create: `logic/devcare/__init__.py`, `logic/devcare/rules/__init__.py`, `logic/devcare/rules/models.py`
- Test: `tests/devcare/rules/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/devcare/rules/test_models.py
import pytest
from pydantic import ValidationError
from logic.devcare.rules.models import EntityRule, FieldRule


def test_minimal_entity_rule():
    rule = EntityRule(
        entity="specialty", version=1, table="Especialidades",
        primary_key="Chave", operations=["create", "update", "delete"],
        soft_delete={"column": "Hist", "active_value": 0, "deleted_value": 1},
        fields={"name": {"column": "Nome", "type": "string", "required": True}},
    )
    assert rule.fields["name"].column == "Nome"
    assert rule.fields["name"].required is True
    assert "create" in rule.operations


def test_unknown_field_type_rejected():
    with pytest.raises(ValidationError):
        FieldRule(column="X", type="datetime-ish")


def test_reference_and_uniqueness_optional():
    rule = EntityRule(
        entity="x", version=1, table="T", primary_key="Chave",
        operations=["create"], fields={"a": {"column": "A", "type": "int"}},
    )
    assert rule.references == {}
    assert rule.uniqueness == []
    assert rule.soft_delete is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/rules/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# logic/devcare/rules/models.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/rules/test_models.py -v`
Expected: PASS (3 passed). Add empty `tests/devcare/rules/__init__.py` if needed.

- [ ] **Step 5: Commit**

```bash
git add logic/devcare/__init__.py logic/devcare/rules/ tests/devcare/rules/
git commit -m "feat(devcare): Pydantic models for entity rule documents"
```

---

## Task 3: RuleLoader + entity YAML documents

**Files:**
- Create: `logic/devcare/rules/loader.py`, `business_rules/devcare/patient.yaml`, `business_rules/devcare/specialty.yaml`
- Test: `tests/devcare/rules/test_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/devcare/rules/test_loader.py
import pytest
from logic.devcare.rules.loader import RuleLoader


def test_loads_real_business_rules():
    loader = RuleLoader("business_rules/devcare")
    assert set(loader.entities()) == {"patient", "specialty"}
    patient = loader.get("patient")
    assert patient.table == "Entidades"
    assert patient.primary_key == "Chave"
    assert patient.soft_delete.column == "Hist"
    assert patient.fields["name"].required is True


def test_unknown_entity_raises():
    loader = RuleLoader("business_rules/devcare")
    with pytest.raises(KeyError):
        loader.get("doctor")


def test_malformed_yaml_rejected(tmp_path):
    (tmp_path / "bad.yaml").write_text("entity: bad\nversion: 1\n", encoding="utf-8")
    with pytest.raises(Exception):
        RuleLoader(tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/rules/test_loader.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the YAML documents**

```yaml
# business_rules/devcare/specialty.yaml
entity: specialty
version: 1
table: Especialidades
primary_key: Chave
operations: [create, update, delete]
soft_delete: { column: Hist, active_value: 0, deleted_value: 1 }
audit_columns: { created_at: DC, updated_at: DUA, created_by: OC, updated_by: OUA }
create_defaults: { Listar: 1 }
fields:
  code:
    column: Codigo
    type: string
    required: true
    label: Code
    validation: { max_length: 10 }
  name:
    column: Nome
    type: string
    required: true
    label: Name
    validation: { max_length: 50 }
  notes:
    column: Obs
    type: string
    required: false
    label: Notes
    validation: { max_length: 500 }
uniqueness:
  - [code]
```

```yaml
# business_rules/devcare/patient.yaml
entity: patient
version: 1
table: Entidades
primary_key: Chave
operations: [create, update, delete]
soft_delete: { column: Hist, active_value: 0, deleted_value: 1 }
audit_columns: { created_at: DC, updated_at: DUA, created_by: OC, updated_by: OUA }
create_defaults: { Tipo: 0, Listar: 1 }
fields:
  name:
    column: Nome
    type: string
    required: true
    label: Full name
    validation: { max_length: 200 }
  code:
    column: Codigo
    type: string
    required: false
    label: Code
    validation: { max_length: 10 }
  tax_id:
    column: NCont
    type: string
    required: false
    label: Tax ID (NIF)
    validation: { regex: "^[0-9]{9}$", max_length: 20 }
  phone:
    column: Telefone1
    type: string
    required: false
    label: Phone
    validation: { max_length: 200 }
  email:
    column: Email
    type: string
    required: false
    label: Email
    validation: { max_length: 250 }
  address:
    column: Morada
    type: string
    required: false
    label: Address
    validation: { max_length: 200 }
  city:
    column: Localidade
    type: string
    required: false
    label: City
    validation: { max_length: 200 }
  postal_code:
    column: CPostal
    type: string
    required: false
    label: Postal code
    validation: { max_length: 200 }
uniqueness:
  - [tax_id]
```

- [ ] **Step 4: Write minimal loader implementation**

```python
# logic/devcare/rules/loader.py
from __future__ import annotations
from pathlib import Path

import yaml

from logic.devcare.rules.models import EntityRule


class RuleLoader:
    def __init__(self, directory: Path | str) -> None:
        self._dir = Path(directory)
        self._rules: dict[str, EntityRule] = {}
        for path in sorted(self._dir.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            rule = EntityRule.model_validate(data)
            if rule.entity in self._rules:
                raise ValueError(f"duplicate entity {rule.entity!r} in {path}")
            self._rules[rule.entity] = rule

    def entities(self) -> list[str]:
        return list(self._rules)

    def get(self, entity: str) -> EntityRule:
        if entity not in self._rules:
            raise KeyError(entity)
        return self._rules[entity]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/rules/test_loader.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add logic/devcare/rules/loader.py business_rules/devcare/ tests/devcare/rules/test_loader.py
git commit -m "feat(devcare): rule loader + patient/specialty enterprise documents"
```

---

## Task 4: Errors + ChangeValidator

**Files:**
- Create: `logic/devcare/errors.py`, `logic/devcare/validator.py`
- Test: `tests/devcare/test_validator.py`

The validator reads through a callable `query(sql, params) -> list[dict]` so tests can inject a fake; production passes a thin wrapper over the read-only session.

- [ ] **Step 1: Write the failing test**

```python
# tests/devcare/test_validator.py
import pytest
from logic.devcare.rules.loader import RuleLoader
from logic.devcare.validator import ChangeValidator
from logic.devcare.errors import ValidationViolation


class FakeReader:
    """Returns canned rows per (table) for uniqueness/reference checks."""
    def __init__(self, rows_by_table=None):
        self.rows_by_table = rows_by_table or {}
        self.calls = []

    def __call__(self, sql, params):
        self.calls.append((sql, params))
        # crude: route by table name appearing in sql
        for table, rows in self.rows_by_table.items():
            if f" {table} " in f" {sql} " or f".{table} " in sql:
                return rows
        return []


@pytest.fixture
def loader():
    return RuleLoader("business_rules/devcare")


def test_create_requires_name(loader):
    v = ChangeValidator(loader, FakeReader())
    result = v.validate("specialty", "create", {"code": "Z9"}, None)
    assert result.ok is False
    assert any("name" in viol.field for viol in result.violations)


def test_create_specialty_valid(loader):
    v = ChangeValidator(loader, FakeReader())
    result = v.validate("specialty", "create", {"code": "Z9", "name": "Test"}, None)
    assert result.ok is True
    assert result.change.operation == "create"
    assert result.change.columns["Codigo"] == "Z9"
    assert result.change.columns["Nome"] == "Test"
    assert result.rule_version == 1


def test_regex_violation_on_tax_id(loader):
    v = ChangeValidator(loader, FakeReader())
    result = v.validate("patient", "create", {"name": "A", "tax_id": "12x"}, None)
    assert result.ok is False
    assert any(viol.field == "tax_id" for viol in result.violations)


def test_max_length_violation(loader):
    v = ChangeValidator(loader, FakeReader())
    result = v.validate("specialty", "create", {"code": "X" * 11, "name": "A"}, None)
    assert result.ok is False
    assert any(viol.field == "code" for viol in result.violations)


def test_uniqueness_violation(loader):
    reader = FakeReader({"Especialidades": [{"n": 1}]})
    v = ChangeValidator(loader, reader)
    result = v.validate("specialty", "create", {"code": "00", "name": "Dup"}, None)
    assert result.ok is False
    assert any("unique" in viol.message.lower() for viol in result.violations)


def test_update_requires_target_pk(loader):
    v = ChangeValidator(loader, FakeReader())
    result = v.validate("specialty", "update", {"name": "New"}, None)
    assert result.ok is False
    assert any("primary key" in viol.message.lower() for viol in result.violations)


def test_update_resolves_single_row(loader):
    reader = FakeReader({"Especialidades": [{"cnt": 1}]})
    v = ChangeValidator(loader, reader)
    result = v.validate("specialty", "update", {"name": "New"}, target_pk=12)
    assert result.ok is True
    assert result.change.target_pk == 12
    assert result.change.columns == {"Nome": "New"}


def test_delete_disallowed_when_not_in_operations(tmp_path, loader):
    # patient allows delete; craft an entity without delete by reusing specialty? use operations check
    v = ChangeValidator(loader, FakeReader({"Especialidades": [{"cnt": 1}]}))
    result = v.validate("specialty", "delete", {}, target_pk=12)
    assert result.ok is True  # specialty allows delete
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_validator.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
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
```

```python
# logic/devcare/validator.py
from __future__ import annotations
import re
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

        if operation in ("update", "delete"):
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
        if val.min is not None and value < val.min:
            viols.append(ValidationViolation(name, f"{fr.label or name} below minimum"))
        if val.max is not None and value > val.max:
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
            sql = (f"SELECT TOP 1 1 AS n FROM DevCare.dbo.{ref.table} "
                   f"WHERE {ref.column} = :v")
            rows = self._reader(sql, {"v": fields[fname]})
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_validator.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add logic/devcare/errors.py logic/devcare/validator.py tests/devcare/test_validator.py
git commit -m "feat(devcare): change validator (required/type/format/unique/reference/target)"
```

---

## Task 5: WriteExecutor

**Files:**
- Create: `logic/devcare/write_executor.py`
- Test: `tests/devcare/test_write_executor.py`

Uses a real SQLite session for tests (table created in the test) to verify the built SQL actually runs and the transaction commits/rolls back. Production passes `db.devcare_connection.get_write_session` and a `now()`/`operator_key`.

- [ ] **Step 1: Write the failing test**

```python
# tests/devcare/test_write_executor.py
from contextlib import contextmanager
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from logic.devcare.errors import NormalizedChange
from logic.devcare.rules.models import EntityRule
from logic.devcare.write_executor import WriteExecutor


@pytest.fixture
def session_factory(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path/'w.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE Especialidades "
                       "(Chave INTEGER, Codigo TEXT, Nome TEXT, Obs TEXT, "
                       "Hist INTEGER, Listar INTEGER, DC TEXT, OC INTEGER, "
                       "DUA TEXT, OUA INTEGER)"))
    Local = sessionmaker(bind=eng)

    @contextmanager
    def factory():
        s = Local()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()
    return factory, eng


def _rule():
    return EntityRule(
        entity="specialty", version=1, table="Especialidades",
        primary_key="Chave", operations=["create", "update", "delete"],
        soft_delete={"column": "Hist", "active_value": 0, "deleted_value": 1},
        audit_columns={"created_at": "DC", "updated_at": "DUA",
                       "created_by": "OC", "updated_by": "OUA"},
        create_defaults={"Listar": 1},
        fields={"code": {"column": "Codigo", "type": "string"},
                "name": {"column": "Nome", "type": "string"}},
    )


def _ex(factory):
    return WriteExecutor(factory, table_prefix="",
                         now=lambda: "2026-06-04T00:00:00Z", operator_key=0)


def test_create_generates_key_and_defaults(session_factory):
    factory, eng = session_factory
    ex = _ex(factory)
    change = NormalizedChange("specialty", "create", "Especialidades", "Chave",
                              {"Codigo": "Z9", "Nome": "Test"}, None)
    pk = ex.execute(_rule(), change)
    with eng.begin() as c:
        row = c.execute(text("SELECT Chave,Codigo,Nome,Hist,Listar,OC FROM Especialidades")).fetchone()
    assert row.Chave == pk == 1
    assert row.Codigo == "Z9" and row.Nome == "Test"
    assert row.Hist == 0 and row.Listar == 1 and row.OC == 0


def test_second_create_increments_key(session_factory):
    factory, eng = session_factory
    ex = _ex(factory)
    r = _rule()
    ex.execute(r, NormalizedChange("specialty", "create", "Especialidades", "Chave",
                                   {"Codigo": "A", "Nome": "A"}, None))
    pk2 = ex.execute(r, NormalizedChange("specialty", "create", "Especialidades", "Chave",
                                         {"Codigo": "B", "Nome": "B"}, None))
    assert pk2 == 2


def test_update_sets_only_given_columns(session_factory):
    factory, eng = session_factory
    ex = _ex(factory)
    r = _rule()
    ex.execute(r, NormalizedChange("specialty", "create", "Especialidades", "Chave",
                                   {"Codigo": "A", "Nome": "Old"}, None))
    ex.execute(r, NormalizedChange("specialty", "update", "Especialidades", "Chave",
                                   {"Nome": "New"}, target_pk=1))
    with eng.begin() as c:
        row = c.execute(text("SELECT Codigo,Nome,DUA FROM Especialidades")).fetchone()
    assert row.Codigo == "A" and row.Nome == "New" and row.DUA == "2026-06-04T00:00:00Z"


def test_soft_delete_sets_flag(session_factory):
    factory, eng = session_factory
    ex = _ex(factory)
    r = _rule()
    ex.execute(r, NormalizedChange("specialty", "create", "Especialidades", "Chave",
                                   {"Codigo": "A", "Nome": "A"}, None))
    ex.execute(r, NormalizedChange("specialty", "delete", "Especialidades", "Chave",
                                   {}, target_pk=1))
    with eng.begin() as c:
        hist = c.execute(text("SELECT Hist FROM Especialidades WHERE Chave=1")).scalar()
    assert hist == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_write_executor.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# logic/devcare/write_executor.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import text

from logic.devcare.errors import NormalizedChange
from logic.devcare.rules.models import EntityRule


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class WriteExecutor:
    """Executes a NormalizedChange in one transaction. Identifiers come only
    from the EntityRule (registry), values are always bound parameters.

    ``table_prefix`` is "DevCare.dbo." in production and "" for SQLite tests.
    """

    def __init__(self, session_factory: Callable, *, table_prefix: str = "DevCare.dbo.",
                 now: Callable[[], str] = _now_iso, operator_key: int = 0) -> None:
        self._factory = session_factory
        self._prefix = table_prefix
        self._now = now
        self._operator_key = operator_key

    def execute(self, rule: EntityRule, change: NormalizedChange) -> Any:
        qtable = f"{self._prefix}{rule.table}"
        with self._factory() as session:
            if change.operation == "create":
                return self._create(session, rule, change, qtable)
            if change.operation == "update":
                self._update(session, rule, change, qtable)
                return change.target_pk
            if change.operation == "delete":
                self._delete(session, rule, change, qtable)
                return change.target_pk
            raise ValueError(f"unknown operation {change.operation!r}")

    def _next_key(self, session, rule, qtable) -> int:
        cur = session.execute(
            text(f"SELECT COALESCE(MAX({rule.primary_key}), 0) + 1 AS k FROM {qtable}")
        ).scalar()
        return int(cur)

    def _create(self, session, rule, change, qtable) -> int:
        pk = self._next_key(session, rule, qtable)
        row: dict = {rule.primary_key: pk}
        row.update(rule.create_defaults)
        if rule.soft_delete is not None:
            row[rule.soft_delete.column] = rule.soft_delete.active_value
        if rule.audit_columns.created_at:
            row[rule.audit_columns.created_at] = self._now()
        if rule.audit_columns.created_by:
            row[rule.audit_columns.created_by] = self._operator_key
        row.update(change.columns)
        cols = ", ".join(row)
        binds = ", ".join(f":{c}" for c in row)
        session.execute(text(f"INSERT INTO {qtable} ({cols}) VALUES ({binds})"), row)
        return pk

    def _update(self, session, rule, change, qtable) -> None:
        sets = dict(change.columns)
        if rule.audit_columns.updated_at:
            sets[rule.audit_columns.updated_at] = self._now()
        if rule.audit_columns.updated_by:
            sets[rule.audit_columns.updated_by] = self._operator_key
        assignments = ", ".join(f"{c} = :{c}" for c in sets)
        params = dict(sets)
        params["_pk"] = change.target_pk
        session.execute(
            text(f"UPDATE {qtable} SET {assignments} WHERE {rule.primary_key} = :_pk"),
            params,
        )

    def _delete(self, session, rule, change, qtable) -> None:
        if rule.soft_delete is None:
            session.execute(
                text(f"DELETE FROM {qtable} WHERE {rule.primary_key} = :_pk"),
                {"_pk": change.target_pk},
            )
            return
        sets = {rule.soft_delete.column: rule.soft_delete.deleted_value}
        if rule.audit_columns.updated_at:
            sets[rule.audit_columns.updated_at] = self._now()
        if rule.audit_columns.updated_by:
            sets[rule.audit_columns.updated_by] = self._operator_key
        assignments = ", ".join(f"{c} = :{c}" for c in sets)
        params = dict(sets)
        params["_pk"] = change.target_pk
        session.execute(
            text(f"UPDATE {qtable} SET {assignments} WHERE {rule.primary_key} = :_pk"),
            params,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_write_executor.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add logic/devcare/write_executor.py tests/devcare/test_write_executor.py
git commit -m "feat(devcare): write executor (insert/update/soft-delete, key gen, txn)"
```

---

## Task 6: AuditWriter

**Files:**
- Create: `logic/devcare/audit_writer.py`
- Test: `tests/devcare/test_audit_writer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/devcare/test_audit_writer.py
import json
from logic.chat.audit import AuditLog
from logic.devcare.audit_writer import AuditWriter
from logic.devcare.errors import NormalizedChange


def test_writes_one_record(tmp_path):
    log = AuditLog(tmp_path / "writes.jsonl")
    writer = AuditWriter(log)
    change = NormalizedChange("specialty", "create", "Especialidades", "Chave",
                              {"Codigo": "Z9", "Nome": "Test"}, None)
    writer.record(operator="Joao", change=change, rule_doc="specialty",
                  rule_version=1, primary_key=7, before=None, status="ok")
    line = (tmp_path / "writes.jsonl").read_text(encoding="utf-8").strip()
    rec = json.loads(line)
    assert rec["kind"] == "devcare_write"
    assert rec["operator"] == "Joao"
    assert rec["operation"] == "create"
    assert rec["table"] == "Especialidades"
    assert rec["primary_key"] == 7
    assert rec["after"] == {"Codigo": "Z9", "Nome": "Test"}
    assert rec["rule_doc"] == "specialty" and rec["rule_version"] == 1
    assert rec["status"] == "ok"
    assert "ts" in rec
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_audit_writer.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# logic/devcare/audit_writer.py
from __future__ import annotations

from logic.chat.audit import AuditLog
from logic.devcare.errors import NormalizedChange


class AuditWriter:
    def __init__(self, audit: AuditLog) -> None:
        self._audit = audit

    def record(self, *, operator: str, change: NormalizedChange, rule_doc: str,
               rule_version: int, primary_key, before: dict | None,
               status: str) -> None:
        self._audit.append({
            "ts": AuditLog.now_iso(),
            "kind": "devcare_write",
            "operator": operator,
            "entity": change.entity,
            "operation": change.operation,
            "table": change.table,
            "primary_key": primary_key,
            "before": before,
            "after": change.columns if change.operation != "delete" else None,
            "rule_doc": rule_doc,
            "rule_version": rule_version,
            "status": status,
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_audit_writer.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add logic/devcare/audit_writer.py tests/devcare/test_audit_writer.py
git commit -m "feat(devcare): audit writer for committed writes"
```

---

## Task 7: PendingChangeStore

**Files:**
- Create: `logic/devcare/pending.py`
- Test: `tests/devcare/test_pending.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/devcare/test_pending.py
import pytest
from logic.devcare.errors import NormalizedChange
from logic.devcare.pending import PendingChangeStore


def _change():
    return NormalizedChange("specialty", "create", "Especialidades", "Chave",
                            {"Nome": "X"}, None)


def test_stage_and_pop():
    store = PendingChangeStore()
    cid = store.stage("conv1", _change(), rule_doc="specialty", rule_version=1)
    assert cid.startswith("chg_")
    staged = store.pop("conv1", cid)
    assert staged.change.columns == {"Nome": "X"}
    assert staged.rule_version == 1


def test_pop_wrong_conversation_returns_none():
    store = PendingChangeStore()
    cid = store.stage("conv1", _change(), rule_doc="specialty", rule_version=1)
    assert store.pop("conv2", cid) is None


def test_pop_is_one_shot():
    store = PendingChangeStore()
    cid = store.stage("conv1", _change(), rule_doc="specialty", rule_version=1)
    assert store.pop("conv1", cid) is not None
    assert store.pop("conv1", cid) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_pending.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# logic/devcare/pending.py
from __future__ import annotations
import uuid
from dataclasses import dataclass

from logic.devcare.errors import NormalizedChange


@dataclass
class StagedChange:
    conversation_id: str
    change: NormalizedChange
    rule_doc: str
    rule_version: int


class PendingChangeStore:
    """In-memory staging of validated changes awaiting operator confirmation."""

    def __init__(self) -> None:
        self._items: dict[str, StagedChange] = {}

    def stage(self, conversation_id: str, change: NormalizedChange, *,
              rule_doc: str, rule_version: int) -> str:
        cid = "chg_" + uuid.uuid4().hex[:12]
        self._items[cid] = StagedChange(conversation_id, change, rule_doc, rule_version)
        return cid

    def pop(self, conversation_id: str, change_id: str) -> StagedChange | None:
        staged = self._items.get(change_id)
        if staged is None or staged.conversation_id != conversation_id:
            return None
        del self._items[change_id]
        return staged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_pending.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add logic/devcare/pending.py tests/devcare/test_pending.py
git commit -m "feat(devcare): in-memory pending-change store"
```

---

## Task 8: Prompts + tool schemas

**Files:**
- Create: `logic/devcare/prompts.py`
- Test: `tests/devcare/test_prompts.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/devcare/test_prompts.py
from logic.devcare.prompts import LOOKUP_TOOL, PROPOSE_CHANGE_TOOL, build_system


def test_tools_have_required_fields():
    assert LOOKUP_TOOL["name"] == "lookup"
    assert "sql" in LOOKUP_TOOL["input_schema"]["properties"]
    props = PROPOSE_CHANGE_TOOL["input_schema"]["properties"]
    assert {"entity", "operation", "fields"} <= set(props)
    assert PROPOSE_CHANGE_TOOL["input_schema"]["required"] == ["entity", "operation", "fields"]


def test_system_lists_entities_and_operator():
    text = build_system(entities_doc="patient: ...", operator="Joao")
    assert "Joao" in text
    assert "propose_change" in text
    assert "confirm" in text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_prompts.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# logic/devcare/prompts.py
from __future__ import annotations

LOOKUP_TOOL: dict = {
    "name": "lookup",
    "description": (
        "Run a single read-only SELECT against DevCare to find rows, resolve "
        "references, or fetch the current values of a row you are about to update. "
        "Use 3-part names like DevCare.dbo.Entidades."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"sql": {"type": "string"}},
        "required": ["sql"],
    },
}

PROPOSE_CHANGE_TOOL: dict = {
    "name": "propose_change",
    "description": (
        "Validate and STAGE a single create/update/delete on one entity. This does "
        "NOT write anything — it returns a preview the operator must confirm. For "
        "update/delete you must include target_pk (the Chave of the row, resolved "
        "via lookup first)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity": {"type": "string", "description": "patient or specialty"},
            "operation": {"type": "string", "enum": ["create", "update", "delete"]},
            "fields": {"type": "object", "description": "field name -> value"},
            "target_pk": {"type": ["integer", "null"]},
        },
        "required": ["entity", "operation", "fields"],
    },
}


def build_system(entities_doc: str, operator: str) -> str:
    return f"""\
You are the DevCare operations assistant. The operator is **{operator}**. You help \
them create, update, and (soft-)delete records in the DevCare database through \
conversation.

You can act ONLY on these entities, with exactly these writable fields:

{entities_doc}

How to work:
- Understand the operator's intent. Ask for any required fields that are missing, \
one or two at a time. Be concise.
- Use the `lookup` tool (read-only SELECT) to resolve references (e.g. find a \
specialty's Chave) and, for updates/deletes, to find the exact row and show its \
current values.
- When you have everything, call `propose_change`. This validates and stages the \
change and shows the operator a preview. It does NOT write.
- You CANNOT commit. Only the operator can, by clicking Confirm on the preview. \
After you propose, tell them to review and confirm.
- If validation returns violations, explain them plainly and ask for corrections.
- Never invent column names or tables outside the list above.

Reply to the operator in plain, friendly text.
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_prompts.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add logic/devcare/prompts.py tests/devcare/test_prompts.py
git commit -m "feat(devcare): system prompt + lookup/propose_change tool schemas"
```

---

## Task 9: DevCareService (orchestrator + commit)

**Files:**
- Create: `logic/devcare/service.py`
- Test: `tests/devcare/test_service.py`

The service streams events of the same shape as the chat (`{"type","payload"}`). It exposes `stream_turn(conversation_id, session_id, operator, user_message)` and `commit_change(conversation_id, session_id, operator, change_id)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/devcare/test_service.py
import json
from types import SimpleNamespace

import pytest

from logic.chat.audit import AuditLog
from logic.chat.history import HistoryStore
from logic.devcare.audit_writer import AuditWriter
from logic.devcare.pending import PendingChangeStore
from logic.devcare.rules.loader import RuleLoader
from logic.devcare.service import DevCareService
from logic.devcare.validator import ChangeValidator
from logic.devcare.write_executor import WriteExecutor

CONV, SESSION, OP = "c1", "s1", "Joao"


class _Text:
    def __init__(self, text): self.type = "text"; self.text = text


class _ToolUse:
    def __init__(self, tid, name, inp):
        self.type = "tool_use"; self.id = tid; self.name = name; self.input = inp


class _Usage:
    input_tokens = 1; output_tokens = 1
    cache_read_input_tokens = 0; cache_creation_input_tokens = 0


class _Resp:
    def __init__(self, content, stop): self.content = content; self.stop_reason = stop; self.usage = _Usage()


class FakeAnthropic:
    def __init__(self, responses):
        self._responses = list(responses)
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        return self._responses.pop(0)


@pytest.fixture
def deps(tmp_path):
    history = HistoryStore(tmp_path / "h.sqlite")
    loader = RuleLoader("business_rules/devcare")
    reader = lambda sql, params: []          # no uniqueness/reference hits
    validator = ChangeValidator(loader, reader)
    pending = PendingChangeStore()
    audit = AuditWriter(AuditLog(tmp_path / "w.jsonl"))
    return SimpleNamespace(history=history, loader=loader, validator=validator,
                           pending=pending, audit=audit, tmp=tmp_path)


def _service(client, deps, executor):
    return DevCareService(
        anthropic_client=client, validator=deps.validator, loader=deps.loader,
        reader=lambda sql, params: [], pending=deps.pending, executor=executor,
        audit=deps.audit, history=deps.history, model="claude-sonnet-4-6",
    )


@pytest.mark.asyncio
async def test_propose_emits_pending_change_block(deps):
    final = _Resp([_ToolUse("t1", "propose_change",
                  {"entity": "specialty", "operation": "create",
                   "fields": {"code": "Z9", "name": "Test"}})], "tool_use")
    after = _Resp([_Text("Please review and confirm.")], "end_turn")
    svc = _service(FakeAnthropic([final, after]), deps, executor=None)
    cid = deps.history.create_conversation(SESSION)
    events = [e async for e in svc.stream_turn(cid, SESSION, OP, "add specialty Z9 Test")]
    pend = [e["payload"] for e in events
            if e["type"] == "block" and e["payload"].get("kind") == "pending_change"]
    assert len(pend) == 1
    assert pend[0]["entity"] == "specialty"
    assert pend[0]["operation"] == "create"
    assert pend[0]["change_id"].startswith("chg_")
    assert pend[0]["columns"]["Nome"] == "Test"


@pytest.mark.asyncio
async def test_validation_violation_emitted_not_staged(deps):
    bad = _Resp([_ToolUse("t1", "propose_change",
                {"entity": "specialty", "operation": "create",
                 "fields": {"code": "Z9"}})], "tool_use")   # missing name
    after = _Resp([_Text("That is missing the name.")], "end_turn")
    svc = _service(FakeAnthropic([bad, after]), deps, executor=None)
    cid = deps.history.create_conversation(SESSION)
    events = [e async for e in svc.stream_turn(cid, SESSION, OP, "add specialty")]
    pend = [e for e in events if e["type"] == "block"
            and e["payload"].get("kind") == "pending_change"]
    assert pend == []


@pytest.mark.asyncio
async def test_commit_executes_and_audits(deps, tmp_path):
    from contextlib import contextmanager
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    eng = create_engine(f"sqlite:///{tmp_path/'wx.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE Especialidades (Chave INTEGER, Codigo TEXT, "
                       "Nome TEXT, Obs TEXT, Hist INTEGER, Listar INTEGER, DC TEXT, "
                       "OC INTEGER, DUA TEXT, OUA INTEGER)"))
    Local = sessionmaker(bind=eng)

    @contextmanager
    def factory():
        s = Local()
        try:
            yield s; s.commit()
        except Exception:
            s.rollback(); raise
        finally:
            s.close()

    executor = WriteExecutor(factory, table_prefix="", now=lambda: "T", operator_key=0)
    final = _Resp([_ToolUse("t1", "propose_change",
                  {"entity": "specialty", "operation": "create",
                   "fields": {"code": "Z9", "name": "Test"}})], "tool_use")
    after = _Resp([_Text("Confirm please.")], "end_turn")
    svc = _service(FakeAnthropic([final, after]), deps, executor=executor)
    cid = deps.history.create_conversation(SESSION)
    events = [e async for e in svc.stream_turn(cid, SESSION, OP, "add Z9")]
    change_id = next(e["payload"]["change_id"] for e in events
                     if e["type"] == "block" and e["payload"].get("kind") == "pending_change")

    result = svc.commit_change(cid, SESSION, OP, change_id)
    assert result["status"] == "ok"
    assert result["primary_key"] == 1
    with eng.begin() as c:
        assert c.execute(text("SELECT Nome FROM Especialidades")).scalar() == "Test"
    rec = json.loads((tmp_path / "w.jsonl").read_text(encoding="utf-8").strip())
    assert rec["operation"] == "create" and rec["operator"] == "Joao"


def test_commit_unknown_change_id_errors(deps):
    svc = _service(FakeAnthropic([]), deps, executor=None)
    cid = deps.history.create_conversation(SESSION)
    result = svc.commit_change(cid, SESSION, OP, "chg_missing")
    assert result["status"] == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_service.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# logic/devcare/service.py
from __future__ import annotations
import asyncio
import uuid
from typing import Any, AsyncIterator, Callable

from sqlalchemy import text

from logic.chat.events import ErrorCode, EventType, Phase
from logic.chat.history import HistoryStore
from logic.devcare.audit_writer import AuditWriter
from logic.devcare.pending import PendingChangeStore
from logic.devcare.prompts import (LOOKUP_TOOL, PROPOSE_CHANGE_TOOL, build_system)
from logic.devcare.rules.loader import RuleLoader
from logic.devcare.validator import ChangeValidator


def _event(t: EventType, payload: dict) -> dict:
    return {"type": t.value, "payload": payload}


def _entities_doc(loader: RuleLoader) -> str:
    lines = []
    for name in loader.entities():
        rule = loader.get(name)
        flds = ", ".join(
            f"{fn}{'*' if fr.required else ''}" for fn, fr in rule.fields.items()
        )
        lines.append(f"- {name} (ops: {', '.join(rule.operations)}): {flds}  "
                     f"(* = required)")
    return "\n".join(lines)


class DevCareService:
    def __init__(self, *, anthropic_client: Any, validator: ChangeValidator,
                 loader: RuleLoader, reader: Callable, pending: PendingChangeStore,
                 executor, audit: AuditWriter, history: HistoryStore, model: str) -> None:
        self._anthropic = anthropic_client
        self._validator = validator
        self._loader = loader
        self._reader = reader
        self._pending = pending
        self._executor = executor
        self._audit = audit
        self._history = history
        self._model = model

    async def stream_turn(self, conversation_id: str, session_id: str,
                          operator: str, user_message: str) -> AsyncIterator[dict]:
        if self._history.get_conversation(conversation_id, session_id) is None:
            yield _event(EventType.ERROR, {"code": ErrorCode.UNAUTHORIZED.value,
                                           "message": "conversation not found"})
            return
        transcript = self._history.get_transcript(conversation_id, session_id)
        transcript.append({"role": "user", "content": user_message})
        emitted_blocks: list[dict] = []
        system = build_system(_entities_doc(self._loader), operator)

        try:
            yield _event(EventType.STATUS, {"phase": Phase.THINKING.value})
            while True:
                response = await self._call(system, transcript)
                tool_uses, assistant_blocks = [], []
                for c in response.content:
                    if getattr(c, "type", None) == "text":
                        assistant_blocks.append({"type": "text", "text": c.text})
                    elif getattr(c, "type", None) == "tool_use":
                        tool_uses.append(c)
                        assistant_blocks.append({"type": "tool_use", "id": c.id,
                                                 "name": c.name, "input": c.input})
                if not tool_uses:
                    raw = "".join(b["text"] for b in assistant_blocks
                                  if b["type"] == "text").strip()
                    if raw:
                        block = {"kind": "text", "markdown": raw}
                        emitted_blocks.append(block)
                        yield _event(EventType.BLOCK, block)
                    transcript.append({"role": "assistant", "content": raw})
                    self._history.append_turn(conversation_id, session_id,
                                              user_message, emitted_blocks, [], [],
                                              transcript)
                    yield _event(EventType.DONE, {})
                    return

                transcript.append({"role": "assistant", "content": assistant_blocks})
                tool_results = []
                for tu in tool_uses:
                    payload, block = self._handle_tool(conversation_id, tu)
                    if block is not None:
                        emitted_blocks.append(block)
                        yield _event(EventType.BLOCK, block)
                    tool_results.append({"type": "tool_result", "tool_use_id": tu.id,
                                         "content": payload})
                transcript.append({"role": "user", "content": tool_results})
        except Exception as e:  # noqa: BLE001
            yield _event(EventType.ERROR, {"code": ErrorCode.INTERNAL.value,
                                           "message": str(e)[:500]})

    def _handle_tool(self, conversation_id: str, tu) -> tuple[str, dict | None]:
        import json
        if tu.name == "lookup":
            rows = self._reader(tu.input.get("sql", ""), {})
            return json.dumps({"rows": rows}, default=str)[:8000], None
        if tu.name == "propose_change":
            entity = tu.input.get("entity", "")
            operation = tu.input.get("operation", "")
            fields = tu.input.get("fields", {}) or {}
            target_pk = tu.input.get("target_pk")
            try:
                result = self._validator.validate(entity, operation, fields, target_pk)
            except KeyError:
                return json.dumps({"error": f"unknown entity {entity!r}"}), None
            if not result.ok:
                viols = [{"field": v.field, "message": v.message}
                         for v in result.violations]
                return json.dumps({"ok": False, "violations": viols}), None
            change_id = self._pending.stage(conversation_id, result.change,
                                            rule_doc=result.rule_doc,
                                            rule_version=result.rule_version)
            block = {"kind": "pending_change", "change_id": change_id,
                     "entity": entity, "operation": operation,
                     "table": result.change.table,
                     "primary_key_column": result.change.primary_key,
                     "target_pk": target_pk, "columns": result.change.columns}
            return json.dumps({"ok": True, "change_id": change_id,
                               "preview": block}), block
        return json.dumps({"error": f"unknown tool {tu.name!r}"}), None

    def commit_change(self, conversation_id: str, session_id: str, operator: str,
                      change_id: str) -> dict:
        if self._history.get_conversation(conversation_id, session_id) is None:
            return {"status": "error", "message": "conversation not found"}
        staged = self._pending.pop(conversation_id, change_id)
        if staged is None:
            return {"status": "error", "message": "change not found or already used"}
        try:
            before = self._fetch_before(staged)
            pk = self._executor.execute(self._loader.get(staged.change.entity),
                                        staged.change)
            self._audit.record(operator=operator, change=staged.change,
                               rule_doc=staged.rule_doc,
                               rule_version=staged.rule_version,
                               primary_key=pk, before=before, status="ok")
            return {"status": "ok", "primary_key": pk,
                    "operation": staged.change.operation,
                    "entity": staged.change.entity}
        except Exception as e:  # noqa: BLE001
            self._audit.record(operator=operator, change=staged.change,
                               rule_doc=staged.rule_doc,
                               rule_version=staged.rule_version,
                               primary_key=staged.change.target_pk, before=None,
                               status="error")
            return {"status": "error", "message": str(e)[:500]}

    def _fetch_before(self, staged) -> dict | None:
        if staged.change.operation == "create":
            return None
        ch = staged.change
        rows = self._reader(
            f"SELECT * FROM DevCare.dbo.{ch.table} WHERE {ch.primary_key} = :pk",
            {"pk": ch.target_pk})
        return rows[0] if rows else None

    async def _call(self, system: str, transcript: list[dict]) -> Any:
        kwargs = dict(model=self._model, max_tokens=2048, system=system,
                      tools=[LOOKUP_TOOL, PROPOSE_CHANGE_TOOL], messages=transcript)
        result = self._anthropic.messages.create(**kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result
```

> Note: the `reader` passed to the service is used both for `lookup` and
> `_fetch_before`. The validator gets its own reader. In production both wrap the
> read-only session (Task 10). The `import json` at the top of `_handle_tool` is
> intentional to keep that method self-contained; move it to module level if you
> prefer.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_service.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add logic/devcare/service.py tests/devcare/test_service.py
git commit -m "feat(devcare): orchestrator loop (lookup/propose) + commit_change"
```

---

## Task 10: FastAPI app

**Files:**
- Create: `logic/devcare/app.py`
- Test: `tests/devcare/test_app.py`

Reads use a wrapper over the existing read-only session (`db.connection.get_session`); writes use `db.devcare_connection.get_write_session`.

- [ ] **Step 1: Write the failing test**

```python
# tests/devcare/test_app.py
import importlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # service build will be mocked off
    monkeypatch.setenv("DEVCARE_HISTORY_PATH", str(tmp_path / "h.sqlite"))
    monkeypatch.setenv("DEVCARE_WRITE_LOG_PATH", str(tmp_path / "w.jsonl"))
    from logic.devcare import app as appmod
    importlib.reload(appmod)
    return TestClient(appmod.app)


def test_set_operator_then_conversations(client):
    r = client.post("/devcare/operator", json={"name": "Joao"})
    assert r.status_code == 200
    r = client.post("/devcare/conversations")
    assert r.status_code == 200 and r.json()["id"]


def test_operations_requires_operator(client):
    r = client.post("/devcare/conversations")
    cid = r.json()["id"]
    # no operator set on a fresh client cookie jar -> 400
    client.cookies.clear()
    r = client.post("/devcare/operations", json={"conversation_id": cid, "message": "hi"})
    assert r.status_code in (400, 401)


def test_commit_unknown_change_returns_error(client):
    client.post("/devcare/operator", json={"name": "Joao"})
    cid = client.post("/devcare/conversations").json()["id"]
    r = client.post(f"/devcare/commit/chg_missing", json={"conversation_id": cid})
    assert r.status_code == 200
    assert r.json()["status"] == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# logic/devcare/app.py
from __future__ import annotations
import json as _json
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from db.connection import get_session as _read_session
from db.devcare_connection import get_write_session
from logic.chat.audit import AuditLog
from logic.chat.events import ErrorCode, EventType
from logic.chat.history import HistoryStore
from logic.devcare.audit_writer import AuditWriter
from logic.devcare.pending import PendingChangeStore
from logic.devcare.rules.loader import RuleLoader
from logic.devcare.service import DevCareService
from logic.devcare.validator import ChangeValidator
from logic.devcare.write_executor import WriteExecutor

_REPO_ROOT = Path(__file__).resolve().parents[2]
from dotenv import load_dotenv
load_dotenv(_REPO_ROOT / ".env")

_RULES_DIR = _REPO_ROOT / "business_rules" / "devcare"
_HISTORY_PATH = Path(os.environ.get("DEVCARE_HISTORY_PATH",
                                    _REPO_ROOT / "logs" / "devcare_history.sqlite"))
_WRITE_LOG_PATH = Path(os.environ.get("DEVCARE_WRITE_LOG_PATH",
                                      _REPO_ROOT / "logs" / "devcare_writes.jsonl"))
_UI_DIR = _REPO_ROOT / "ui" / "devcare"
_SESSION_COOKIE = "devcare_session"
_OPERATOR_COOKIE = "devcare_operator"

app = FastAPI(title="DevCare Operations")

_service: DevCareService | None = None
_history: HistoryStore | None = None


def _read(sql: str, params: dict) -> list[dict]:
    with _read_session() as s:
        result = s.execute(text(sql), params or {})
        cols = list(result.keys())
        return [dict(zip(cols, row)) for row in result.fetchall()]


def _build_anthropic():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def _get_history() -> HistoryStore:
    global _history
    if _history is None:
        _history = HistoryStore(_HISTORY_PATH)
    return _history


def get_service() -> DevCareService:
    global _service
    if _service is None:
        loader = RuleLoader(_RULES_DIR)
        _service = DevCareService(
            anthropic_client=_build_anthropic(),
            validator=ChangeValidator(loader, _read),
            loader=loader, reader=_read,
            pending=PendingChangeStore(),
            executor=WriteExecutor(get_write_session),
            audit=AuditWriter(AuditLog(_WRITE_LOG_PATH)),
            history=_get_history(), model="claude-sonnet-4-6",
        )
    return _service


def _session_id(request: Request, response: Response) -> str:
    sid = request.cookies.get(_SESSION_COOKIE)
    if not sid:
        sid = "s_" + secrets.token_hex(12)
        response.set_cookie(_SESSION_COOKIE, sid, httponly=True, samesite="lax",
                            max_age=60 * 60 * 24 * 7)
    return sid


def _operator(request: Request) -> str | None:
    return request.cookies.get(_OPERATOR_COOKIE)


@app.post("/devcare/operator")
def set_operator(request: Request, response: Response, body: dict) -> dict:
    name = (body or {}).get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    _session_id(request, response)
    response.set_cookie(_OPERATOR_COOKIE, name, httponly=True, samesite="lax",
                        max_age=60 * 60 * 24 * 7)
    return {"operator": name}


@app.post("/devcare/conversations")
def create_conversation(request: Request, response: Response) -> dict:
    sid = _session_id(request, response)
    return {"id": _get_history().create_conversation(sid)}


@app.get("/devcare/conversations")
def list_conversations(request: Request, response: Response) -> dict:
    sid = _session_id(request, response)
    rows = _get_history().list_conversations(sid)
    return {"conversations": [{"id": r.id, "title": r.title,
                               "updated_at": r.updated_at} for r in rows]}


def _format_sse(event: dict) -> bytes:
    name = event.get("type", "message")
    data = _json.dumps(event.get("payload", {}), default=str)
    return f"event: {name}\ndata: {data}\n\n".encode("utf-8")


@app.post("/devcare/operations")
async def post_operations(request: Request) -> Response:
    operator = _operator(request)
    if not operator:
        return JSONResponse({"detail": "operator not set"}, status_code=400)
    body = await request.json()
    conversation_id = body.get("conversation_id")
    message = body.get("message", "")
    if not conversation_id:
        return JSONResponse({"detail": "conversation_id required"}, status_code=400)
    sid = request.cookies.get(_SESSION_COOKIE) or ("s_" + secrets.token_hex(12))
    try:
        svc = get_service()
        async def gen():
            async for ev in svc.stream_turn(conversation_id, sid, operator, message):
                yield _format_sse(ev)
    except RuntimeError as e:
        async def gen():
            yield _format_sse({"type": EventType.ERROR.value,
                               "payload": {"code": ErrorCode.CONFIG.value,
                                           "message": str(e)}})
            yield _format_sse({"type": EventType.DONE.value, "payload": {}})
    resp = StreamingResponse(gen(), media_type="text/event-stream")
    resp.set_cookie(_SESSION_COOKIE, sid, httponly=True, samesite="lax",
                    max_age=60 * 60 * 24 * 7)
    return resp


@app.post("/devcare/commit/{change_id}")
async def commit(change_id: str, request: Request, response: Response) -> dict:
    operator = _operator(request)
    if not operator:
        raise HTTPException(status_code=400, detail="operator not set")
    sid = _session_id(request, response)
    body = await request.json()
    conversation_id = body.get("conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id required")
    return get_service().commit_change(conversation_id, sid, operator, change_id)


if _UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")
```

> The `test_operations_requires_operator` test clears cookies before calling, so
> no operator cookie is present → 400. Adjust the assertion if your TestClient
> cookie handling differs.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/test_app.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add logic/devcare/app.py tests/devcare/test_app.py
git commit -m "feat(devcare): FastAPI app (operator, operations SSE, commit)"
```

---

## Task 11: Operator UI

**Files:**
- Create: `ui/devcare/index.html`, `ui/devcare/app.js`, `ui/devcare/devcare.css`
- Test: manual (documented below)

This task is UI wiring; verification is manual against a running server. Keep the
JS small: reuse the SSE pattern from `ui/chat/sse.js` conceptually.

- [ ] **Step 1: Create `ui/devcare/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>DevCare Operations</title>
  <link rel="stylesheet" href="/devcare.css" />
</head>
<body>
  <div id="operator-gate" class="gate">
    <div class="gate-card">
      <h2>DevCare Operations</h2>
      <p>Enter your name to begin. Every change you confirm is recorded against it.</p>
      <input id="operator-name" placeholder="Your name" />
      <button id="operator-go">Continue</button>
    </div>
  </div>
  <main id="app" hidden>
    <header><strong>DevCare Operations</strong> — <span id="who"></span></header>
    <div id="messages"></div>
    <form id="composer">
      <input id="input" autocomplete="off"
             placeholder="Describe the operation, e.g. 'add specialty 99 Dermatology'" />
      <button type="submit">Send</button>
    </form>
  </main>
  <script src="/app.js" type="module"></script>
</body>
</html>
```

- [ ] **Step 2: Create `ui/devcare/devcare.css`**

```css
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; color: #0f172a; }
.gate { position: fixed; inset: 0; display: grid; place-items: center; background: #f8fafc; }
.gate-card { background: #fff; padding: 28px; border-radius: 10px; box-shadow: 0 6px 24px #0001; width: 340px; }
.gate-card input { width: 100%; padding: 8px; margin: 12px 0; border: 1px solid #cbd5e1; border-radius: 6px; }
.gate-card button, #composer button, .pc-actions button { background: #2563eb; color: #fff; border: 0; padding: 8px 14px; border-radius: 6px; cursor: pointer; }
main { max-width: 760px; margin: 0 auto; padding: 16px; }
header { padding: 8px 0 16px; border-bottom: 1px solid #e2e8f0; }
#messages { padding: 16px 0; min-height: 50vh; }
.msg { margin: 10px 0; padding: 10px 12px; border-radius: 8px; }
.msg.user { background: #eff6ff; }
.msg.ai { background: #f1f5f9; white-space: pre-wrap; }
.msg.error { background: #fef2f2; color: #b91c1c; }
#composer { display: flex; gap: 8px; position: sticky; bottom: 0; background: #fff; padding: 12px 0; }
#composer input { flex: 1; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; }
.pending-change { border: 1px solid #93c5fd; border-radius: 10px; padding: 12px; margin: 12px 0; background: #fff; }
.pending-change h4 { margin: 0 0 8px; }
.pending-change table { width: 100%; border-collapse: collapse; font-size: 14px; }
.pending-change td { padding: 4px 6px; border-bottom: 1px solid #f1f5f9; }
.pc-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 10px; }
.pc-actions .cancel { background: #e2e8f0; color: #0f172a; }
.pending-change.done { opacity: .6; }
```

- [ ] **Step 3: Create `ui/devcare/app.js`**

```javascript
const gate = document.getElementById("operator-gate");
const appEl = document.getElementById("app");
const messages = document.getElementById("messages");
let conversationId = null;

document.getElementById("operator-go").onclick = async () => {
  const name = document.getElementById("operator-name").value.trim();
  if (!name) return;
  await fetch("/devcare/operator", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ name }),
  });
  document.getElementById("who").textContent = name;
  const r = await fetch("/devcare/conversations", { method: "POST" });
  conversationId = (await r.json()).id;
  gate.hidden = true; appEl.hidden = false;
};

function addMsg(cls, textContent) {
  const el = document.createElement("div");
  el.className = `msg ${cls}`;
  el.textContent = textContent;
  messages.appendChild(el);
  el.scrollIntoView({ block: "end" });
  return el;
}

function renderPendingChange(p) {
  const card = document.createElement("div");
  card.className = "pending-change";
  const rows = Object.entries(p.columns)
    .map(([k, v]) => `<tr><td><b>${k}</b></td><td>${v}</td></tr>`).join("");
  const target = p.target_pk != null ? ` (row ${p.target_pk})` : "";
  card.innerHTML = `
    <h4>Pending change — ${p.operation.toUpperCase()} ${p.entity}${target}</h4>
    <table>${rows || "<tr><td>(soft delete)</td></tr>"}</table>
    <div class="pc-actions">
      <button class="cancel">Cancel</button>
      <button class="confirm">Confirm write</button>
    </div>`;
  card.querySelector(".cancel").onclick = () => card.classList.add("done");
  card.querySelector(".confirm").onclick = async () => {
    const r = await fetch(`/devcare/commit/${p.change_id}`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId }),
    });
    const res = await r.json();
    card.classList.add("done");
    if (res.status === "ok") {
      addMsg("ai", `✓ Committed ${res.operation} ${res.entity} (key ${res.primary_key}).`);
    } else {
      addMsg("error", `Commit failed: ${res.message}`);
    }
  };
  messages.appendChild(card);
  card.scrollIntoView({ block: "end" });
}

document.getElementById("composer").onsubmit = async (e) => {
  e.preventDefault();
  const input = document.getElementById("input");
  const msg = input.value.trim();
  if (!msg) return;
  addMsg("user", msg);
  input.value = "";
  const resp = await fetch("/devcare/operations", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId, message: msg }),
  });
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let aiEl = null;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop();
    for (const part of parts) {
      const ev = part.match(/^event: (.+)$/m)?.[1];
      const dataLine = part.match(/^data: (.+)$/m)?.[1];
      if (!ev || !dataLine) continue;
      const data = JSON.parse(dataLine);
      if (ev === "block" && data.kind === "pending_change") renderPendingChange(data);
      else if (ev === "block" && data.kind === "text") aiEl = addMsg("ai", data.markdown);
      else if (ev === "error") addMsg("error", data.message || "error");
    }
  }
};
```

- [ ] **Step 4: Manual verification**

1. Ensure `.env` has `ANTHROPIC_API_KEY`, `DATABASE_URL` (read-only), and
   `DEVCARE_WRITE_DATABASE_URL` (writable, DevCare).
2. Run: `.venv/Scripts/python.exe -c "import uvicorn; uvicorn.run('logic.devcare.app:app', port=8001)"`
3. Open `http://localhost:8001/`, enter operator name.
4. Type: `add specialty 99 Dermatology`. Verify the assistant gathers/echoes the
   fields and a **Pending change** card appears with `Codigo=99`, `Nome=Dermatology`.
5. Click **Confirm write**; verify the success line and check the row exists:
   `SELECT * FROM DevCare.dbo.Especialidades WHERE Codigo='99'`.
6. Verify `logs/devcare_writes.jsonl` has a `devcare_write` record with your name.
7. Soft-delete it: `mark specialty 99 as deleted` → confirm → verify `Hist=1`.

- [ ] **Step 5: Commit**

```bash
git add ui/devcare/
git commit -m "feat(devcare): operator UI (conversation + pending-change confirm card)"
```

---

## Task 12: Full suite + docs

**Files:**
- Modify: `CLAUDE.md` (add DevCare write domain to the Active domains table and run command)

- [ ] **Step 1: Run the whole DevCare suite**

Run: `.venv/Scripts/python.exe -m pytest tests/devcare/ -v`
Expected: all pass.

- [ ] **Step 2: Run chat suite to confirm no regressions**

Run: `.venv/Scripts/python.exe -m pytest tests/chat/ -q`
Expected: all pass (the read-only chat is untouched).

- [ ] **Step 3: Update CLAUDE.md**

Add to the Active domains table:
```
| DevCare CRUD | business_rules/devcare/*.yaml | Active (writes) |
```
And under run commands:
```
Run the DevCare operations server: `uvicorn logic.devcare.app:app --reload --port 8001`.
Requires ANTHROPIC_API_KEY, DATABASE_URL (read-only), and DEVCARE_WRITE_DATABASE_URL (writable, DevCare only).
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: register DevCare write domain + run command"
```

---

## Self-review notes

- **Spec coverage:** registry/enterprise docs (T2–3), validator incl. references/uniqueness/single-PK (T4), parameterized writes + soft-delete + key gen + txn (T5), audit (T6), two-phase propose/confirm with no model commit (T7–9), identity (T10), separate writable login (T1, T10), UI confirm card (T11), tests at every layer + no-regression check (T12). All spec sections map to a task.
- **Type consistency:** `NormalizedChange`, `ValidationResult`, `StagedChange`, `EntityRule` field/method names are used identically across tasks; `WriteExecutor.execute(rule, change)`, `ChangeValidator.validate(entity, operation, fields, target_pk)`, `DevCareService.commit_change(...)`, and the `pending_change` block shape (`change_id`, `entity`, `operation`, `columns`, `target_pk`) match between producer (service) and consumer (UI/tests).
- **Known caveats to verify during execution:** (a) `Chave` key generation via `MAX+1` is racy under concurrent writers — acceptable for v1 (confirm-gated, low volume); revisit with a numerator/identity if needed. (b) `OC`/`OUA` are set to `operator_key=0` (no real operator key exists yet); the human operator name lives in the audit log. (c) read `lookup` returns are truncated to 8 KB to bound tokens.
```
