# tests/devcare/test_service.py
import json
from types import SimpleNamespace

import pytest

from logic.chat.audit import AuditLog
from logic.chat.history import HistoryStore
from logic.devcare.audit_writer import AuditWriter
from logic.devcare.pending import PendingChangeStore
from logic.devcare.rules.loader import RuleLoader
from logic.devcare.service import DevCareService, MAX_TOOL_ROUNDS
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


def _sqlite_setup(tmp_path):
    """Return (engine, sessionmaker factory, WriteExecutor) backed by SQLite with one pre-inserted row."""
    from contextlib import contextmanager
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    eng = create_engine(f"sqlite:///{tmp_path / 'wx2.db'}")
    with eng.begin() as c:
        c.execute(text(
            "CREATE TABLE Especialidades (Chave INTEGER, Codigo TEXT, "
            "Nome TEXT, Obs TEXT, Hist INTEGER, Listar INTEGER, DC TEXT, "
            "OC INTEGER, DUA TEXT, OUA INTEGER)"
        ))
        c.execute(text(
            "INSERT INTO Especialidades (Chave, Codigo, Nome, Hist) VALUES (1, 'A', 'Old', 0)"
        ))

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

    executor = WriteExecutor(factory, table_prefix="", now=lambda: "T", operator_key=0)
    return eng, executor


def _fake_reader_with_snapshot(snapshot: dict):
    """Reader that satisfies the validator's COUNT(*) check and returns snapshot for _fetch_before."""
    def reader(sql, params):
        if "COUNT(*)" in sql:
            return [{"cnt": 1}]
        return [snapshot]
    return reader


def _service_for_modify(client, deps, executor, snapshot):
    """Build a DevCareService with table_prefix="" and a fake reader that returns the snapshot."""
    reader = _fake_reader_with_snapshot(snapshot)
    validator = ChangeValidator(deps.loader, reader)
    return DevCareService(
        anthropic_client=client, validator=validator, loader=deps.loader,
        reader=reader, pending=deps.pending, executor=executor,
        audit=deps.audit, history=deps.history, model="claude-sonnet-4-6",
        table_prefix="",
    )


@pytest.mark.asyncio
async def test_commit_update_via_service(deps, tmp_path):
    from sqlalchemy import text as sqla_text

    snapshot = {"Chave": 1, "Codigo": "A", "Nome": "Old"}
    eng, executor = _sqlite_setup(tmp_path)

    final = _Resp([_ToolUse("t1", "propose_change",
                  {"entity": "specialty", "operation": "update",
                   "fields": {"name": "New"}, "target_pk": 1})], "tool_use")
    after_resp = _Resp([_Text("Updated.")], "end_turn")
    svc = _service_for_modify(FakeAnthropic([final, after_resp]), deps, executor, snapshot)
    cid = deps.history.create_conversation(SESSION)
    events = [e async for e in svc.stream_turn(cid, SESSION, OP, "rename specialty 1 to New")]
    change_id = next(e["payload"]["change_id"] for e in events
                     if e["type"] == "block" and e["payload"].get("kind") == "pending_change")

    result = svc.commit_change(cid, SESSION, OP, change_id)
    assert result["status"] == "ok"

    with eng.begin() as c:
        nome = c.execute(sqla_text("SELECT Nome FROM Especialidades WHERE Chave = 1")).scalar()
    assert nome == "New"

    rec = json.loads((tmp_path / "w.jsonl").read_text(encoding="utf-8").strip())
    assert rec["operation"] == "update"
    assert rec["before"] == snapshot


@pytest.mark.asyncio
async def test_commit_delete_via_service(deps, tmp_path):
    from sqlalchemy import text as sqla_text

    snapshot = {"Chave": 1, "Codigo": "A", "Nome": "Old"}
    eng, executor = _sqlite_setup(tmp_path)

    final = _Resp([_ToolUse("t1", "propose_change",
                  {"entity": "specialty", "operation": "delete",
                   "fields": {}, "target_pk": 1})], "tool_use")
    after_resp = _Resp([_Text("Deleted.")], "end_turn")
    svc = _service_for_modify(FakeAnthropic([final, after_resp]), deps, executor, snapshot)
    cid = deps.history.create_conversation(SESSION)
    events = [e async for e in svc.stream_turn(cid, SESSION, OP, "delete specialty 1")]
    change_id = next(e["payload"]["change_id"] for e in events
                     if e["type"] == "block" and e["payload"].get("kind") == "pending_change")

    result = svc.commit_change(cid, SESSION, OP, change_id)
    assert result["status"] == "ok"

    with eng.begin() as c:
        hist = c.execute(sqla_text("SELECT Hist FROM Especialidades WHERE Chave = 1")).scalar()
    assert hist == 1  # soft-deleted

    rec = json.loads((tmp_path / "w.jsonl").read_text(encoding="utf-8").strip())
    assert rec["operation"] == "delete"
    assert rec["after"] is None
    assert rec["before"] == snapshot


@pytest.mark.asyncio
async def test_tool_loop_stops_after_max_rounds(deps):
    # Fake that always returns a lookup tool_use, never a final text turn
    call_count = 0

    class _InfiniteClient:
        def __init__(self):
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kw):
            nonlocal call_count
            call_count += 1
            return _Resp([_ToolUse(f"t{call_count}", "lookup",
                                   {"sql": "SELECT 1"})], "tool_use")

    svc = _service(_InfiniteClient(), deps, executor=None)
    cid = deps.history.create_conversation(SESSION)
    events = [e async for e in svc.stream_turn(cid, SESSION, OP, "loop forever")]
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) >= 1
    assert call_count <= MAX_TOOL_ROUNDS + 1


@pytest.mark.asyncio
async def test_present_form_emits_form_block(deps):
    final = _Resp([_ToolUse("t1", "present_form",
                  {"entity": "patient", "operation": "create"})], "tool_use")
    after = _Resp([_Text("Please fill in the form.")], "end_turn")
    svc = _service(FakeAnthropic([final, after]), deps, executor=None)
    cid = deps.history.create_conversation(SESSION)
    events = [e async for e in svc.stream_turn(cid, SESSION, OP, "register a new patient")]
    forms = [e["payload"] for e in events
             if e["type"] == "block" and e["payload"].get("kind") == "form"]
    assert len(forms) == 1
    assert forms[0]["entity"] == "patient" and forms[0]["operation"] == "create"
    by = {f["name"]: f for f in forms[0]["fields"]}
    assert by["birth_date"]["input"] == "date"
    assert by["gender"]["input"] == "select"
    # no pending_change is staged just by presenting a form
    assert not [e for e in events if e["type"] == "block"
                and e["payload"].get("kind") == "pending_change"]


def test_stage_change_valid_returns_pending(deps):
    svc = _service(FakeAnthropic([]), deps, executor=None)
    cid = deps.history.create_conversation(SESSION)
    res = svc.stage_change(cid, SESSION, OP, "specialty", "create",
                           {"code": "Z9", "name": "Test"})
    assert res["ok"] is True
    assert res["pending_change"]["entity"] == "specialty"
    assert res["pending_change"]["columns"]["Nome"] == "Test"
    assert res["pending_change"]["change_id"].startswith("chg_")


def test_stage_change_invalid_returns_violations(deps):
    svc = _service(FakeAnthropic([]), deps, executor=None)
    cid = deps.history.create_conversation(SESSION)
    res = svc.stage_change(cid, SESSION, OP, "specialty", "create", {"code": "Z9"})
    assert res["ok"] is False
    assert any(v["field"] == "name" for v in res["violations"])


def test_stage_change_unknown_conversation(deps):
    svc = _service(FakeAnthropic([]), deps, executor=None)
    res = svc.stage_change("nope", SESSION, OP, "specialty", "create",
                           {"code": "Z9", "name": "Test"})
    assert res["ok"] is False
