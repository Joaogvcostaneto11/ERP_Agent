# logic/devcare/pending.py
from __future__ import annotations
import uuid
from dataclasses import dataclass

from logic.devcare.errors import NormalizedChange


@dataclass
class StagedChange:
    conversation_id: str
    change: NormalizedChange
    rule_doc: str
    rule_version: int


class PendingChangeStore:
    """In-memory staging of validated changes awaiting operator confirmation."""

    def __init__(self) -> None:
        self._items: dict[str, StagedChange] = {}

    def stage(self, conversation_id: str, change: NormalizedChange, *,
              rule_doc: str, rule_version: int) -> str:
        cid = "chg_" + uuid.uuid4().hex[:12]
        self._items[cid] = StagedChange(conversation_id, change, rule_doc, rule_version)
        return cid

    def pop(self, conversation_id: str, change_id: str) -> StagedChange | None:
        staged = self._items.get(change_id)
        if staged is None or staged.conversation_id != conversation_id:
            return None
        del self._items[change_id]
        return staged
