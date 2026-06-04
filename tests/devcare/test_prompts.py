from logic.devcare.prompts import LOOKUP_TOOL, PROPOSE_CHANGE_TOOL, build_system


def test_tools_have_required_fields():
    assert LOOKUP_TOOL["name"] == "lookup"
    assert "sql" in LOOKUP_TOOL["input_schema"]["properties"]
    props = PROPOSE_CHANGE_TOOL["input_schema"]["properties"]
    assert {"entity", "operation", "fields"} <= set(props)
    assert PROPOSE_CHANGE_TOOL["input_schema"]["required"] == ["entity", "operation", "fields"]


def test_system_lists_entities_and_operator():
    text = build_system(entities_doc="patient: ...", operator="Joao")
    assert "Joao" in text
    assert "propose_change" in text
    assert "confirm" in text.lower()
