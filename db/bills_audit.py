from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

TABLE = "ERPAgent_BillAudit"

# Module constants, never derived from the entry. An audit entry is
# caller-influenced, and nothing caller-influenced may reach an SQL identifier
# position — the same invariant write_executor._check_columns enforces for
# document and line columns.
_COLUMNS = ("Ts", "Operator", "ProposalId", "Status", "DocumentChave",
            "SupplierChave", "RuleDoc", "RuleVersion", "Payload")


def insert_audit(session, entry: dict[str, Any], *, table_prefix: str = "") -> None:
    """Insert one audit row on the session it is handed.

    Takes a session rather than opening one so the caller can put this inside
    the document's own transaction — the audit row and the document it records
    then commit or roll back together."""
    row = {
        "Ts": entry.get("ts"),
        "Operator": entry.get("operator"),
        "ProposalId": entry.get("proposal_id"),
        "Status": entry.get("status"),
        "DocumentChave": entry.get("document_chave"),
        "SupplierChave": entry.get("supplier_chave"),
        "RuleDoc": entry.get("rule_doc"),
        "RuleVersion": entry.get("rule_version"),
        "Payload": json.dumps(entry, separators=(",", ":"), default=str),
    }
    cols = ", ".join(_COLUMNS)
    binds = ", ".join(f":{c}" for c in _COLUMNS)
    session.execute(
        text(f"INSERT INTO {table_prefix}{TABLE} ({cols}) VALUES ({binds})"), row)
