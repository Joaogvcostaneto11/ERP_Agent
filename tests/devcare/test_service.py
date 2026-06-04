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
