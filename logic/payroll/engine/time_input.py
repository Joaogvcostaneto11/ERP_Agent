from __future__ import annotations
from logic.payroll.public.schemas import TimeInput


def normalize_time_input(raw: TimeInput) -> TimeInput:
    """Normalise raw TimeInput into payable form.

    Plan 1 is a no-op pass-through. Plan 2 expands this to compute payable
    overtime, intersect absences with the period, and derive hourly rates.
    """
    return raw
