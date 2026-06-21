from __future__ import annotations
import asyncio
from pathlib import Path
from types import SimpleNamespace

from logic.chat.knowledge_store import KnowledgeStore
from logic.chat.schema_context import SchemaContext
from logic.chat.service import ChatService


def _service(tmp_path: Path, draft_text: str):
    schema = tmp_path / "schema.md"
    schema.write_text("SCHEMA_HERE", encoding="utf-8")
    captured: dict = {}

    def _create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=draft_text)], usage=None)

    client = SimpleNamespace(messages=SimpleNamespace(create=_create))
    svc = ChatService(
        anthropic_client=client,
        sql_executor=SimpleNamespace(),
        audit=SimpleNamespace(),
        schema_context=SchemaContext(schema),
        report_store=SimpleNamespace(),
        history=SimpleNamespace(),
        knowledge_store=KnowledgeStore(tmp_path / "k.md"),
        model="claude-sonnet-4-6",
    )
    return svc, captured


def test_draft_entry_returns_model_text(tmp_path: Path):
    draft = "### Net sales definition\n- **Business rule:** subtract credit notes"
    svc, captured = _service(tmp_path, draft)
    out = asyncio.run(svc.draft_entry("what were net sales?", "SELECT SUM(Total) ...", "must subtract credit notes"))
    assert out.strip() == draft
    # the developer's explanation is passed to the model
    user_msg = captured["messages"][0]["content"]
    assert "subtract credit notes" in user_msg
    # schema is available so the model can map to columns
    assert any("SCHEMA_HERE" in b["text"] for b in captured["system"])
