from datetime import datetime, timezone
from logic.payroll.clock import Clock, SystemClock, FixedClock


def test_system_clock_returns_utc_datetime():
    clock: Clock = SystemClock()
    now = clock.now()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None


def test_fixed_clock_returns_supplied_value():
    fixed = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)
    clock: Clock = FixedClock(fixed)
    assert clock.now() == fixed
    # Repeated calls return the same value
    assert clock.now() == fixed
