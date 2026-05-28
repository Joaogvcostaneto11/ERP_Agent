from __future__ import annotations
from enum import Enum


class EventType(str, Enum):
    STATUS = "status"
    BLOCK = "block"
    CITATION = "citation"
    ERROR = "error"
    DONE = "done"


class Phase(str, Enum):
    THINKING = "thinking"
    QUERYING = "querying"


class ErrorCode(str, Enum):
    BUDGET_EXCEEDED = "budget_exceeded"
    ENVELOPE_PARSE = "envelope_parse"
    INTERNAL = "internal"
    CONFIG = "config"
