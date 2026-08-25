from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import yaml
from sqlalchemy import text

from logic.bills.rules.loader import RuleLoader
from logic.bills.rules.models import PurchaseInvoiceRule
from logic.chat.audit import AuditLog

TABLE = "ERPAgent_BillRules"

# Module constants, never derived from a caller. Nothing caller-influenced may
# reach an SQL identifier position — the same invariant db/bills_audit.py and
# write_executor._check_columns enforce.
_COLUMNS = ("Version", "Yaml", "Ts", "Action", "Operator", "Prose",
            "Rationale", "Changes", "RevertedTo")


class RuleVersionNotFound(LookupError):
    """No stored rule document carries the requested version."""


class RuleStoreUnavailable(Exception):
    """The rule table could not be read. Raised rather than falling back to the
    packaged YAML, which would let the service keep writing under a mapping the
    operator had already replaced — silently, and only until the next restart.

    Deliberately NOT a RuntimeError, unlike its sibling SchemaUnavailable: the
    ingestion routes build the service inside `except RuntimeError -> 400`, and
    get_service() reads the rule document. As a RuntimeError this would reach
    the operator as "your file is bad" during a database outage. Staying off
    that hierarchy lets it reach app.py's 503 handler instead."""


class RuleStore:
    """Versioned persistence for the purchase-invoice rule document.

    Each row is one version AND the record of who produced it. Keeping the
    provenance in the same INSERT as the content is what stops the two from
    ever disagreeing.

    History is append-only: reverting to v3 from v5 writes v6 carrying v3's
    content. Committed documents record the version that authorized them via
    WritePlan.rule_version, so rewinding would leave them citing a version
    whose meaning had silently changed.

    The document lives in the database rather than on disk because Render's
    filesystem is ephemeral — an in-place rewrite reverted on every deploy.
    ``seed_path`` supplies the FIRST version only, from the YAML packaged in
    the image, and is never written to.
    """

    def __init__(self, session_factory: Callable, *, seed_path: Path | str,
                 table_prefix: str = "") -> None:
        self._factory = session_factory
        self._seed = Path(seed_path)
        self._t = f"{table_prefix}{TABLE}"

    # -- reads ----------------------------------------------------------
    def current(self) -> PurchaseInvoiceRule:
        """The document in force, seeding the table from the packaged YAML the
        first time it is found empty."""
        # A MAX() subquery rather than TOP/LIMIT: SQL Server has no LIMIT and
        # SQLite has no TOP, and this form needs neither.
        rows = self._fetch_all(
            f"SELECT Yaml FROM {self._t} "
            f"WHERE Version = (SELECT MAX(Version) FROM {self._t})")
        if not rows:
            return self._seed_from_package()
        return self._parse(rows[0][0])

    def versions(self) -> list[int]:
        """Versions that can be reverted to — every stored version except the
        one in force. The admin UI offers this list as revert targets, and
        reverting to the document already in effect is not a thing to offer."""
        rows = self._fetch_all(f"SELECT Version FROM {self._t} ORDER BY Version")
        stored = [int(r[0]) for r in rows]
        return stored[:-1]

    def historical(self, version: int) -> PurchaseInvoiceRule:
        rows = self._fetch_all(
            f"SELECT Yaml FROM {self._t} WHERE Version = :v", {"v": version})
        if not rows:
            raise RuleVersionNotFound(f"no stored rule for version {version}")
        return self._parse(rows[0][0])

    # -- writes ---------------------------------------------------------
    def save(self, rule: PurchaseInvoiceRule, *, operator: str | None,
             action: str = "apply", prose: str | None = None,
             rationale: str | None = None,
             changes: list[dict] | None = None,
             reverted_to: int | None = None) -> None:
        """Append ``rule`` as its own version.

        The version comes from the document itself — apply() bumps it — so a
        second save at a version already stored violates the primary key and
        raises, rather than one admin silently overwriting another's change.
        """
        self._insert({
            "Version": rule.version,
            "Yaml": yaml.safe_dump(rule.model_dump(mode="json"),
                                   sort_keys=False, allow_unicode=True),
            "Ts": AuditLog.now_iso(),
            "Action": action,
            "Operator": operator,
            "Prose": prose,
            "Rationale": rationale,
            "Changes": json.dumps(changes, separators=(",", ":"), default=str)
                       if changes is not None else None,
            "RevertedTo": reverted_to,
        })

    def revert(self, version: int, *, operator: str | None) -> PurchaseInvoiceRule:
        old = self.historical(version)          # raises if it never existed
        forward = old.model_copy(update={"version": self.current().version + 1})
        self.save(forward, operator=operator, action="revert", reverted_to=version)
        return forward

    # -- internals ------------------------------------------------------
    def _seed_from_package(self) -> PurchaseInvoiceRule:
        rule = RuleLoader(self._seed).rule()
        # No operator: nobody made this change, it is what the image shipped.
        self.save(rule, operator=None, action="seed")
        return rule

    @staticmethod
    def _parse(document: str) -> PurchaseInvoiceRule:
        return PurchaseInvoiceRule.model_validate(yaml.safe_load(document))

    def _insert(self, row: dict[str, Any]) -> None:
        cols = ", ".join(_COLUMNS)
        binds = ", ".join(f":{c}" for c in _COLUMNS)
        with self._factory() as session:
            session.execute(text(f"INSERT INTO {self._t} ({cols}) VALUES ({binds})"), row)

    def _fetch_all(self, sql: str, params: dict | None = None) -> list:
        try:
            with self._factory() as session:
                return session.execute(text(sql), params or {}).fetchall()
        except Exception as e:  # noqa: BLE001 - any read failure is an outage
            raise RuleStoreUnavailable(f"cannot read {self._t}: {e}") from e
