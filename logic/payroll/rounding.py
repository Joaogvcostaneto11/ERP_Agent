from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_DOWN, ROUND_HALF_EVEN
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


_METHOD_MAP = {
    "ROUND_HALF_UP": ROUND_HALF_UP,
    "ROUND_HALF_DOWN": ROUND_HALF_DOWN,
    "ROUND_HALF_EVEN": ROUND_HALF_EVEN,
}


class RoundingPolicy(BaseModel):
    model_config = ConfigDict(strict=True)

    method: Literal["ROUND_HALF_UP", "ROUND_HALF_DOWN", "ROUND_HALF_EVEN"] = "ROUND_HALF_UP"
    decimal_places: int = Field(ge=0, default=2)

    def apply(self, value: Decimal) -> Decimal:
        quantum = Decimal(1).scaleb(-self.decimal_places) if self.decimal_places > 0 else Decimal(1)
        return value.quantize(quantum, rounding=_METHOD_MAP[self.method])
