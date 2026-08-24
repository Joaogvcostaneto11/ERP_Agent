from __future__ import annotations
import json
import re
from typing import Any

from pydantic import ValidationError

from logic.bills.rules.models import PurchaseInvoiceRule
from logic.bills.rules.proposal import (
    RuleChangeProposal, source_type, table_for, valid_sources,
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_SECTIONS = ("header", "lines")

_SYSTEM = (
    "You translate an administrator's description of a business rule into a "
    "structured change to a purchase-invoice write mapping. "
    "Return ONLY a JSON object with keys: rationale (string), base_version "
    "(integer), and changes (a list). Each change has: action (\"set\" or "
    "\"remove\"), section (one of {sections}), name (the logical field key), "
    "column (the database column), source (the extracted field), and required "
    "(boolean).\n\n"
    "The sections \"supplier_create\" and \"article_create\" are NOT available: "
    "the columns written when a new supplier or article record is created are "
    "not editable through this interface. Never propose a change to either "
    "section; if that is what was asked for, return an empty changes list and "
    "say so in rationale.\n\n"
    "You may ONLY use columns and sources from the lists below. If the request "
    "cannot be expressed with them, return an empty changes list and explain why "
    "in rationale. Never invent a column name.\n\n"
    "Each column is listed as Name[sql_type] and each source as name[python_type]. "
    "The types must be compatible or the change will be rejected. Text columns "
    "accept anything; a decimal source must NOT go to an integer column "
    "(bigint, int, smallint, tinyint), because the conversion silently discards "
    "the fractional part; a text source must go to a text column; a date source "
    "must go to a date or text column.\n\n"
    "Current mapping (version {version}):\n{mapping}\n\n"
    "Columns that exist, by table:\n{columns}\n\n"
    "Sources that exist:\n{sources}\n"
)


class RuleDraftError(RuntimeError):
    """Claude did not return a patch matching RuleChangeProposal. A RuntimeError
    so the route turns it into a 422 the admin can act on, not a bare 500."""


class RuleProposer:
    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    def _system(self, rule: PurchaseInvoiceRule, schema) -> str:
        columns = "\n".join(
            f"  {table_for(s, rule)}: "
            + ", ".join(sorted(f"{c.name}[{c.data_type}]"
                               for c in schema.columns(table_for(s, rule)).values()))
            for s in _SECTIONS
        )
        mapping = "\n".join(
            [f"  header.{k}: {v.column} <- {v.source}" for k, v in rule.header.fields.items()]
            + [f"  lines.{k}: {v.column} <- {v.source}" for k, v in rule.lines.fields.items()]
            + [f"  supplier_create (read-only): "
               f"{', '.join(rule.matching.supplier.create_columns)}",
               f"  article_create (read-only): "
               f"{', '.join(rule.matching.article.create_columns)}"]
        )
        return _SYSTEM.format(
            sections=", ".join(_SECTIONS), version=rule.version,
            mapping=mapping, columns=columns,
            sources=", ".join(
                f"{s}[{t.__name__}]" if (t := source_type(s)) else s
                for s in sorted(valid_sources())
            ),
        )

    def draft(self, prose: str, rule: PurchaseInvoiceRule,
              schema) -> RuleChangeProposal:
        resp = self._client.messages.create(
            model=self._model, max_tokens=2048, temperature=0,
            system=self._system(rule, schema),
            messages=[{"role": "user", "content": prose}],
        )
        text = "".join(getattr(c, "text", "") for c in resp.content
                       if getattr(c, "type", None) == "text")
        m = _JSON_RE.search(text)
        if not m:
            raise RuleDraftError(f"no JSON object in the reply: {text[:300]}")
        try:
            return RuleChangeProposal.model_validate(json.loads(m.group(0)))
        except (json.JSONDecodeError, ValidationError) as e:
            raise RuleDraftError(f"reply did not match the patch schema: {e}") from e
