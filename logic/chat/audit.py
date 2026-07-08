from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


class AuditLog:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: dict[str, Any]) -> None:
        try:
            line = json.dumps(entry, separators=(",", ":"), default=str)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            _log.exception("audit log write failed")

    @staticmethod
    def now_iso() -> str:
        return (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
