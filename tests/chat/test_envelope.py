from __future__ import annotations
import pytest
from pydantic import ValidationError

from logic.chat.envelope import (
    ChartBlock,
    Citation,
    ClaudeEnvelope,
    RawReportBlock,
    ReportBlock,
    TableBlock,
    TextBlock,
    ValueBlock,
)


def test_text_block_roundtrip():
    b = TextBlock(markdown="**hi**")
    assert b.model_dump() == {"kind": "text", "markdown": "**hi**"}


def test_value_block_optional_unit():
    b = ValueBlock(label="Revenue", value=123.45, unit="EUR")
    assert b.unit == "EUR"
    b2 = ValueBlock(label="Count", value=10)
    assert b2.unit is None


def test_table_block():
    b = TableBlock(columns=["a", "b"], rows=[[1, 2], [3, 4]])
    assert b.columns == ["a", "b"]
    assert b.rows == [[1, 2], [3, 4]]


def test_chart_block():
    b = ChartBlock(title="t", plotly={"data": [], "layout": {}})
    assert b.title == "t"


def test_raw_report_block_has_no_id_or_pdf_url():
    b = RawReportBlock(title="T", html="<p>x</p>")
    dumped = b.model_dump()
    assert "id" not in dumped
    assert "pdf_url" not in dumped


def test_report_block_requires_id_and_pdf_url():
    with pytest.raises(ValidationError):
        ReportBlock(title="T", html="<p>x</p>")  # missing id + pdf_url


def test_envelope_parses_mixed_blocks_from_json():
    payload = {
        "blocks": [
            {"kind": "text", "markdown": "hello"},
            {"kind": "value", "label": "n", "value": 1},
            {"kind": "table", "columns": ["x"], "rows": [[1]]},
            {"kind": "chart", "title": "t", "plotly": {"data": [], "layout": {}}},
            {"kind": "report", "title": "R", "html": "<p/>"},
        ],
        "citations": [{"summary": "top 10", "sql_log_id": "q_42"}],
    }
    env = ClaudeEnvelope.model_validate(payload)
    kinds = [b.kind for b in env.blocks]
    assert kinds == ["text", "value", "table", "chart", "report"]
    assert env.citations[0].sql_log_id == "q_42"


def test_envelope_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        ClaudeEnvelope.model_validate({"blocks": [{"kind": "video", "url": "x"}], "citations": []})


def test_envelope_rejects_extra_fields_on_block():
    with pytest.raises(ValidationError):
        ClaudeEnvelope.model_validate(
            {"blocks": [{"kind": "text", "markdown": "hi", "extra": 1}], "citations": []}
        )


def test_citation_optional_sql_log_id():
    c = Citation(summary="x")
    assert c.sql_log_id is None
