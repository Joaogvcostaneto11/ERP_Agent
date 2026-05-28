from __future__ import annotations
from pathlib import Path

from logic.chat.prompts import BASE_INSTRUCTIONS


class SchemaContext:
    def __init__(self, schema_path: Path | str) -> None:
        p = Path(schema_path)
        if not p.exists():
            raise FileNotFoundError(f"schema file not found: {p}")
        self.schema_reference = p.read_text(encoding="utf-8")

    def system_blocks(self) -> list[dict]:
        return [
            {"type": "text", "text": BASE_INSTRUCTIONS},
            {
                "type": "text",
                "text": self.schema_reference,
                "cache_control": {"type": "ephemeral"},
            },
        ]
