from __future__ import annotations
from pathlib import Path

from logic.chat.knowledge_store import KnowledgeStore


def test_system_block_none_when_absent(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "query_knowledge.md")
    assert store.system_block() is None


def test_system_block_none_when_blank(tmp_path: Path):
    p = tmp_path / "query_knowledge.md"
    p.write_text("   \n\n", encoding="utf-8")
    assert KnowledgeStore(p).system_block() is None


def test_system_block_cached_text_when_present(tmp_path: Path):
    p = tmp_path / "query_knowledge.md"
    p.write_text("# Query Knowledge\nKE-0001 net sales rule", encoding="utf-8")
    block = KnowledgeStore(p).system_block()
    assert block["type"] == "text"
    assert block["cache_control"] == {"type": "ephemeral"}
    assert "net sales rule" in block["text"]


def test_next_id_starts_at_one(tmp_path: Path):
    assert KnowledgeStore(tmp_path / "k.md").next_id() == "KE-0001"


def test_append_allocates_sequential_ids_and_heading(tmp_path: Path):
    p = tmp_path / "k.md"
    store = KnowledgeStore(p)
    id1 = store.append_entry("### Net sales definition\n- **Business rule:** subtract credit notes", "t_abc")
    id2 = store.append_entry("### Active patients\n- **Business rule:** Estado=1", "t_def")
    assert (id1, id2) == ("KE-0001", "KE-0002")
    text = p.read_text(encoding="utf-8")
    assert "### KE-0001 — Net sales definition" in text
    assert "### KE-0002 — Active patients" in text


def test_append_adds_provenance_and_rewrites_existing_id(tmp_path: Path):
    p = tmp_path / "k.md"
    store = KnowledgeStore(p)
    # heading already carries a (stale) id — it must be rewritten, not duplicated
    ke = store.append_entry("### KE-9999 — Net sales\n- **Business rule:** x", "t_xyz")
    text = p.read_text(encoding="utf-8")
    assert ke == "KE-0001"
    assert "### KE-0001 — Net sales" in text
    assert "KE-9999" not in text
    assert "**Provenance:**" in text
    assert "t_xyz" in text
