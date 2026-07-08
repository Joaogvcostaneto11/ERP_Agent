from __future__ import annotations
from logic.payroll.public.schemas import RuleCitation


_LAYER_PRIORITY = {"statutory": 0, "cct": 1, "company": 2, "contract": 3}


def select_primary_citation(citations: list[RuleCitation]) -> RuleCitation:
    """Pick the highest-priority citation from a merge chain.

    The highest-priority layer is the one whose values actually appear in the
    resolved component — i.e., the layer that "won" the merge. If multiple
    citations share the highest priority, the last one in the list wins.
    """
    if not citations:
        raise ValueError("select_primary_citation requires at least one citation")
    return max(citations, key=lambda c: _LAYER_PRIORITY[c.layer])


def render_citation_text(cit: RuleCitation) -> str:
    """Render a citation as a one-line human-readable string for AI consumption."""
    parts = [f"[{cit.layer}] {cit.document_path}::{cit.clause}"]
    if cit.component_code:
        parts.append(f"(component: {cit.component_code})")
    return " ".join(parts)
