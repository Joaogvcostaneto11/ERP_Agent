from __future__ import annotations
import os
import tempfile
from pathlib import Path

import yaml

from logic.bills.rules.models import PurchaseInvoiceRule

_NAME = "purchase_invoice.yaml"


class RuleStore:
    """Versioned persistence for the purchase-invoice rule document.

    History is append-only: reverting to v3 from v5 writes v6 carrying v3's
    content. Committed documents record the version that authorized them via
    WritePlan.rule_version, so rewinding would leave them citing a version whose
    meaning had silently changed.
    """

    def __init__(self, directory: Path | str) -> None:
        self._dir = Path(directory)
        self._path = self._dir / _NAME
        self._history = self._dir / "history"

    def current(self) -> PurchaseInvoiceRule:
        return PurchaseInvoiceRule.model_validate(
            yaml.safe_load(self._path.read_text(encoding="utf-8")))

    def versions(self) -> list[int]:
        if not self._history.exists():
            return []
        return sorted(int(p.stem.split(".v")[1])
                      for p in self._history.glob("purchase_invoice.v*.yaml"))

    def historical(self, version: int) -> PurchaseInvoiceRule:
        p = self._history / f"purchase_invoice.v{version}.yaml"
        if not p.exists():
            raise FileNotFoundError(f"no archived rule for version {version}")
        return PurchaseInvoiceRule.model_validate(
            yaml.safe_load(p.read_text(encoding="utf-8")))

    def save(self, rule: PurchaseInvoiceRule) -> None:
        previous = self.current()
        self._history.mkdir(parents=True, exist_ok=True)
        archive = self._history / f"purchase_invoice.v{previous.version}.yaml"
        archive.write_text(self._path.read_text(encoding="utf-8"), encoding="utf-8")
        self._atomic_write(yaml.safe_dump(rule.model_dump(mode="json"),
                                          sort_keys=False, allow_unicode=True))

    def revert(self, version: int) -> PurchaseInvoiceRule:
        old = self.historical(version)
        forward = old.model_copy(update={"version": self.current().version + 1})
        self.save(forward)
        return forward

    def _atomic_write(self, text: str) -> None:
        """Write via a temp file in the same directory, then os.replace, so an
        interrupted save cannot leave a half-written document that fails to load
        at next boot."""
        fd, tmp = tempfile.mkstemp(dir=str(self._dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, self._path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
