from __future__ import annotations
import re
from datetime import date
from pathlib import Path

_HEADING_RE = re.compile(r"^###\s+(?:KE-\d+\s+—\s+)?(.*\S)\s*$", re.MULTILINE)
_ID_RE = re.compile(r"^###\s+KE-(\d+)\b", re.MULTILINE)

_FILE_HEADER = (
    "# Query Knowledge — Business rules for interpreting questions\n\n"
    "Authoritative business rules for translating user questions into SQL. "
    "Prefer them over inference. Note the KE id you applied in your citation.\n"
)


class KnowledgeStore:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def _read(self) -> str:
        if not self._path.exists():
            return ""
        return self._path.read_text(encoding="utf-8")

    def system_block(self) -> dict | None:
        text = self._read()
        if not text.strip():
            return None
        return {
            "type": "text",
            "text": text,
            "cache_control": {"type": "ephemeral"},
        }

    def next_id(self) -> str:
        nums = [int(m) for m in _ID_RE.findall(self._read())]
        return f"KE-{(max(nums) + 1) if nums else 1:04d}"

    def append_entry(self, markdown: str, source_turn_id: str) -> str:
        ke_id = self.next_id()
        body = markdown.strip()
        m = _HEADING_RE.search(body)
        title = m.group(1) if m else "Untitled"
        if m:
            body = body[:m.start()] + f"### {ke_id} — {title}" + body[m.end():]
        else:
            body = f"### {ke_id} — {title}\n" + body
        provenance = f"- **Provenance:** added {date.today().isoformat()} · source turn {source_turn_id}"
        entry = body.rstrip() + "\n" + provenance + "\n"

        existing = self._read()
        if not existing.strip():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            out = _FILE_HEADER + "\n" + entry
        else:
            out = existing.rstrip() + "\n\n" + entry
        self._path.write_text(out, encoding="utf-8")
        return ke_id
