from __future__ import annotations
from pathlib import Path

from logic.chat.schema_context import SchemaContext


def test_loads_schema_file(tmp_path: Path):
    p = tmp_path / "schema.md"
    p.write_text("# Schema\nTable foo.\n", encoding="utf-8")
    ctx = SchemaContext(schema_path=p)
    assert "Table foo" in ctx.schema_reference


def test_system_blocks_contain_schema_and_base_instructions(tmp_path: Path):
    p = tmp_path / "schema.md"
    p.write_text("SCHEMA_HERE", encoding="utf-8")
    ctx = SchemaContext(schema_path=p)
    blocks = ctx.system_blocks()
    assert isinstance(blocks, list) and len(blocks) == 2
    # base instructions block (no cache_control)
    assert blocks[0]["type"] == "text"
    assert "cache_control" not in blocks[0]
    assert "ERP" in blocks[0]["text"]
    # schema block (cached)
    assert blocks[1]["type"] == "text"
    assert blocks[1]["cache_control"] == {"type": "ephemeral"}
    assert "SCHEMA_HERE" in blocks[1]["text"]


def test_missing_schema_file_raises(tmp_path: Path):
    import pytest
    with pytest.raises(FileNotFoundError):
        SchemaContext(schema_path=tmp_path / "nope.md")
