from decimal import Decimal
import pytest
from pydantic import ValidationError
from logic.payroll.rounding import RoundingPolicy


def test_default_policy_is_round_half_up_two_places():
    p = RoundingPolicy()
    assert p.method == "ROUND_HALF_UP"
    assert p.decimal_places == 2
    assert p.apply(Decimal("1.235")) == Decimal("1.24")


def test_round_half_up_at_boundary():
    p = RoundingPolicy(method="ROUND_HALF_UP", decimal_places=2)
    assert p.apply(Decimal("0.125")) == Decimal("0.13")
    assert p.apply(Decimal("0.124")) == Decimal("0.12")


def test_round_half_even_at_boundary():
    p = RoundingPolicy(method="ROUND_HALF_EVEN", decimal_places=2)
    assert p.apply(Decimal("0.125")) == Decimal("0.12")
    assert p.apply(Decimal("0.135")) == Decimal("0.14")


def test_round_half_down_at_boundary():
    p = RoundingPolicy(method="ROUND_HALF_DOWN", decimal_places=2)
    assert p.apply(Decimal("0.125")) == Decimal("0.12")
    assert p.apply(Decimal("0.126")) == Decimal("0.13")


def test_zero_decimal_places():
    p = RoundingPolicy(method="ROUND_HALF_UP", decimal_places=0)
    assert p.apply(Decimal("1.5")) == Decimal("2")


def test_unknown_method_rejected():
    with pytest.raises(ValidationError):
        RoundingPolicy(method="ROUND_BANKERS")


def test_negative_decimal_places_rejected():
    with pytest.raises(ValidationError):
        RoundingPolicy(decimal_places=-1)
