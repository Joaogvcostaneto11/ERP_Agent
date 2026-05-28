from __future__ import annotations

from logic.chat.prompts import BASE_INSTRUCTIONS, RUN_QUERY_TOOL


def test_base_instructions_mention_envelope_and_readonly():
    assert "blocks" in BASE_INSTRUCTIONS
    assert "read-only" in BASE_INSTRUCTIONS.lower()
    assert "run_query" in BASE_INSTRUCTIONS


def test_run_query_tool_spec_shape():
    assert RUN_QUERY_TOOL["name"] == "run_query"
    assert "sql" in RUN_QUERY_TOOL["input_schema"]["properties"]
    assert RUN_QUERY_TOOL["input_schema"]["required"] == ["sql"]
