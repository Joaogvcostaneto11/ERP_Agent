from __future__ import annotations
from enum import Enum


class EventType(str, Enum):
    STATUS = "status"
    BLOCK = "block"
    CITATION = "citation"
    STEP = "step"
    ERROR = "error"
    DONE = "done"


class Phase(str, Enum):
    THINKING = "thinking"
    QUERYING = "querying"


class ErrorCode(str, Enum):
    ENVELOPE_PARSE = "envelope_parse"
    ANSWER_TRUNCATED = "answer_truncated"
    INTERNAL = "internal"
    CONFIG = "config"
    UNAUTHORIZED = "unauthorized"
