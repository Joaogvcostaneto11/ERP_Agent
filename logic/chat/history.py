from __future__ import annotations
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from logic.chat.audit import AuditLog


TRANSCRIPT_CAP = 40


@dataclass(frozen=True)
class ConversationSummary:
    id: str
    title: str
    updated_at: str


@dataclass(frozen=True)
class Turn:
    user_message: str
    blocks: list[dict]
    citations: list[dict]
    ts: str


@dataclass(frozen=True)
class ConversationDetail:
    id: str
    title: str
    created_at: str
    updated_at: str
    turns: list[Turn]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation (
  id           TEXT PRIMARY KEY,
  session_id   TEXT NOT NULL,
  title        TEXT NOT NULL DEFAULT '',
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_conv_session ON conversation(session_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS turn (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id TEXT NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
  user_message    TEXT NOT NULL,
  blocks_json     TEXT NOT NULL,
  citations_json  TEXT NOT NULL,
  raw_transcript  TEXT NOT NULL,
  ts              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_turn_conv ON turn(conversation_id, id);

CREATE TABLE IF NOT EXISTS schema_version (
  version    INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);
"""


class HistoryStore:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def create_conversation(self, session_id: str) -> str:
        cid = "c_" + uuid.uuid4().hex[:12]
        now = AuditLog.now_iso()
        with self._write() as c:
            c.execute(
                "INSERT INTO conversation (id, session_id, title, created_at, updated_at) "
                "VALUES (?, ?, '', ?, ?)",
                (cid, session_id, now, now),
            )
        return cid

    def list_conversations(self, session_id: str, limit: int = 50) -> list[ConversationSummary]:
        rows = self._conn.execute(
            "SELECT id, title, updated_at FROM conversation "
            "WHERE session_id = ? ORDER BY updated_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [ConversationSummary(r["id"], r["title"], r["updated_at"]) for r in rows]

    def get_conversation(self, conversation_id: str, session_id: str) -> ConversationDetail | None:
        row = self._conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversation "
            "WHERE id = ? AND session_id = ?",
            (conversation_id, session_id),
        ).fetchone()
        if row is None:
            return None
        turn_rows = self._conn.execute(
            "SELECT user_message, blocks_json, citations_json, ts FROM turn "
            "WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,),
        ).fetchall()
        turns = [
            Turn(
                user_message=t["user_message"],
                blocks=json.loads(t["blocks_json"]),
                citations=json.loads(t["citations_json"]),
                ts=t["ts"],
            )
            for t in turn_rows
        ]
        return ConversationDetail(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            turns=turns,
        )

    def delete_conversation(self, conversation_id: str, session_id: str) -> bool:
        with self._write() as c:
            cur = c.execute(
                "DELETE FROM conversation WHERE id = ? AND session_id = ?",
                (conversation_id, session_id),
            )
            return cur.rowcount > 0

    def update_title(self, conversation_id: str, session_id: str, title: str) -> None:
        with self._write() as c:
            c.execute(
                "UPDATE conversation SET title = ? WHERE id = ? AND session_id = ?",
                (title[:200], conversation_id, session_id),
            )

    def append_turn(
        self,
        conversation_id: str,
        user_message: str,
        blocks: list[dict],
        citations: list[dict],
        raw_transcript: list[dict],
    ) -> None:
        capped = raw_transcript[-TRANSCRIPT_CAP:]
        now = AuditLog.now_iso()
        with self._write() as c:
            c.execute(
                "INSERT INTO turn (conversation_id, user_message, blocks_json, citations_json, raw_transcript, ts) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    conversation_id,
                    user_message,
                    json.dumps(blocks, default=str),
                    json.dumps(citations, default=str),
                    json.dumps(capped, default=str),
                    now,
                ),
            )
            c.execute("UPDATE conversation SET updated_at = ? WHERE id = ?", (now, conversation_id))

    def get_transcript(self, conversation_id: str, session_id: str) -> list[dict]:
        row = self._conn.execute(
            "SELECT t.raw_transcript FROM turn t "
            "JOIN conversation c ON c.id = t.conversation_id "
            "WHERE t.conversation_id = ? AND c.session_id = ? "
            "ORDER BY t.id DESC LIMIT 1",
            (conversation_id, session_id),
        ).fetchone()
        if row is None:
            return []
        return json.loads(row["raw_transcript"])

    def close(self) -> None:
        with self._lock:
            self._conn.close()
