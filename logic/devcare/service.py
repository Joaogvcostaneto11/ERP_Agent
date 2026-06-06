# logic/devcare/service.py
from __future__ import annotations
import asyncio
import json
import uuid
from typing import Any, AsyncIterator, Callable

from logic.chat.events import ErrorCode, EventType, Phase
from logic.chat.history import HistoryStore
from logic.devcare.audit_writer import AuditWriter
from logic.devcare.pending import PendingChangeStore
from logic.devcare.prompts import (LOOKUP_TOOL, PROPOSE_CHANGE_TOOL, build_system)
from logic.devcare.rules.loader import RuleLoader
from logic.devcare.validator import ChangeValidator


MAX_TOOL_ROUNDS = 10


def _event(t: EventType, payload: dict) -> dict:
    return {"type": t.value, "payload": payload}


def _field_desc(field_name: str, fr) -> str:
    label = fr.label or field_name
    return f"{field_name} ({label})" if fr.label else field_name


def _entities_doc(loader: RuleLoader) -> str:
    lines = []
    for name in loader.entities():
        rule = loader.get(name)
        required = [_field_desc(fn, fr) for fn, fr in rule.fields.items() if fr.required]
        optional = [_field_desc(fn, fr) for fn, fr in rule.fields.items() if not fr.required]
        lines.append(f"- {name} (table {rule.table}; operations: "
                     f"{', '.join(rule.operations)})")
        lines.append(f"    required: {', '.join(required) or '(none)'}")
        lines.append(f"    recommended (optional): {', '.join(optional) or '(none)'}")
    return "\n".join(lines)


class DevCareService:
    def __init__(self, *, anthropic_client: Any, validator: ChangeValidator,
                 loader: RuleLoader, reader: Callable, pending: PendingChangeStore,
                 executor, audit: AuditWriter, history: HistoryStore, model: str,
                 table_prefix: str = "DevCare.dbo.") -> None:
        self._anthropic = anthropic_client
        self._validator = validator
        self._loader = loader
        self._reader = reader
        self._pending = pending
        self._executor = executor
        self._audit = audit
        self._history = history
        self._model = model
        self._prefix = table_prefix

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
            tool_rounds = 0
            while True:
                if tool_rounds > MAX_TOOL_ROUNDS:
                    yield _event(EventType.ERROR, {"code": ErrorCode.INTERNAL.value,
                                                   "message": "too many tool rounds; stopping"})
                    return
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
                tool_rounds += 1
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
        before = None
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
                               primary_key=staged.change.target_pk, before=before,
                               status="error")
            return {"status": "error", "message": str(e)[:500]}

    def _fetch_before(self, staged) -> dict | None:
        if staged.change.operation == "create":
            return None
        ch = staged.change
        # ch.table and ch.primary_key are registry-controlled identifiers (not user input); pk value is bound
        rows = self._reader(
            f"SELECT * FROM {self._prefix}{ch.table} WHERE {ch.primary_key} = :pk",
            {"pk": ch.target_pk})
        return rows[0] if rows else None

    async def _call(self, system: str, transcript: list[dict]) -> Any:
        kwargs = dict(model=self._model, max_tokens=2048, system=system,
                      tools=[LOOKUP_TOOL, PROPOSE_CHANGE_TOOL], messages=transcript)
        result = self._anthropic.messages.create(**kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result
