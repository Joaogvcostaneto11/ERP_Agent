from __future__ import annotations
import asyncio
from pathlib import Path
from types import SimpleNamespace

from logic.chat.knowledge_store import KnowledgeStore
from logic.chat.schema_context import SchemaContext
from logic.chat.service import ChatService


def _service(tmp_path: Path, knowledge_text: str | None):
    schema = tmp_path / "schema.md"
    schema.write_text("SCHEMA_HERE", encoding="utf-8")
    kpath = tmp_path / "query_knowledge.md"
    if knowledge_text is not None:
        kpath.write_text(knowledge_text, encoding="utf-8")
    captured: dict = {}

    def _create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="{}")], usage=None)

    client = SimpleNamespace(messages=SimpleNamespace(create=_create))
    svc = ChatService(
        anthropic_client=client,
        sql_executor=SimpleNamespace(),
        audit=SimpleNamespace(),
        schema_context=SchemaContext(schema),
        report_store=SimpleNamespace(),
        history=SimpleNamespace(),
        knowledge_store=KnowledgeStore(kpath),
        model="claude-sonnet-4-6",
    )
    return svc, captured


def test_knowledge_block_included_when_present(tmp_path: Path):
    svc, captured = _service(tmp_path, "# Query Knowledge\nKE-0001 rule about net sales")
    asyncio.run(svc._call_claude([{"role": "user", "content": "hi"}]))
    system_text = " ".join(b["text"] for b in captured["system"])
    assert "net sales" in system_text


def test_knowledge_block_omitted_when_absent(tmp_path: Path):
    svc, captured = _service(tmp_path, None)
    asyncio.run(svc._call_claude([{"role": "user", "content": "hi"}]))
    # only base-instructions + schema blocks
    assert len(captured["system"]) == 2
