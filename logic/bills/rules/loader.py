from __future__ import annotations
from pathlib import Path

import yaml

from logic.bills.rules.models import PurchaseInvoiceRule


class RuleLoader:
    """Loads the single purchase_invoice.yaml enterprise document."""

    def __init__(self, directory: Path | str) -> None:
        self._path = Path(directory) / "purchase_invoice.yaml"
        data = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        self._rule = PurchaseInvoiceRule.model_validate(data)

    def rule(self) -> PurchaseInvoiceRule:
        return self._rule
