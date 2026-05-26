from __future__ import annotations
from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    def __init__(self, fixed_now: datetime) -> None:
        if fixed_now.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware datetime")
        self._now = fixed_now

    def now(self) -> datetime:
        return self._now
