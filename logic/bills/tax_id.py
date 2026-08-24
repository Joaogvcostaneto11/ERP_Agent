from __future__ import annotations

_WEIGHTS = (9, 8, 7, 6, 5, 4, 3, 2)


def pt_nif_is_valid(value: str | None) -> bool | None:
    """Validate a Portuguese NIF's check digit.

    Returns True/False for a PT-shaped value (optional leading "PT",
    9 digits once whitespace is stripped). Returns None for anything not
    PT-shaped — empty, None, wrong length, non-digit content — since a
    foreign tax ID is not ours to judge.
    """
    if not value:
        return None
    v = value.strip()
    if v[:2].upper() == "PT":
        v = v[2:]
    if len(v) != 9 or not v.isdigit():
        return None
    digits = [int(c) for c in v]
    total = sum(d * w for d, w in zip(digits[:8], _WEIGHTS))
    remainder = total % 11
    expected = 0 if remainder in (0, 1) else 11 - remainder
    return expected == digits[8]
