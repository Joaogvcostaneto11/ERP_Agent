from datetime import datetime, timezone
from logic.payroll.engine.audit import select_primary_citation, render_citation_text
from logic.payroll.public.schemas import RuleCitation


def test_select_primary_citation_picks_highest_priority():
    cits = [
        RuleCitation(document_path="x", layer="statutory", clause="c"),
        RuleCitation(document_path="y", layer="company", clause="c"),
    ]
    primary = select_primary_citation(cits)
    assert primary.layer == "company"


def test_select_primary_citation_returns_only_when_single():
    cits = [RuleCitation(document_path="x", layer="statutory", clause="c")]
    primary = select_primary_citation(cits)
    assert primary.layer == "statutory"


def test_render_citation_text_basic():
    cit = RuleCitation(document_path="business_rules/payroll/statutory_pt.yaml",
                       layer="statutory", component_code="base_salary",
                       clause="components.base_salary")
    text = render_citation_text(cit)
    assert "statutory_pt.yaml" in text
    assert "components.base_salary" in text
