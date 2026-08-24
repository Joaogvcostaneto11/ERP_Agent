from __future__ import annotations
from typing import Any


class PendingProposalStore:
    """In-memory staging of proposals/write-plans awaiting confirmation.
    Keyed by proposal_id. Single-process, like DevCare's PendingChangeStore."""

    def __init__(self) -> None:
        self._items: dict[str, Any] = {}

    def put(self, key: str, value: Any) -> None:
        self._items[key] = value

    def get(self, key: str) -> Any:
        return self._items.get(key)

    def pop(self, key: str) -> Any:
        return self._items.pop(key, None)
