import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from logic.bills.rules.loader import RuleLoader
from logic.bills.rules.proposer import RuleDraftError, RuleProposer
from logic.bills.rules.schema_probe import SchemaProbe


@pytest.fixture
def rule():
    root = Path(__file__).resolve().parents[2]
    return RuleLoader(root / "business_rules" / "bills").rule()


def _schema():
    cols = {"LinDoc001": ["Descricao", "CodigoForn"], "Doc001": ["Obs"],
            "Entidades": ["Nome"], "Artigos": ["Nome"]}
    def read(sql, params):
        return [{"COLUMN_NAME": c, "DATA_TYPE": "varchar", "IS_NULLABLE": "YES"}
                for c in cols.get(params["table"], [])]
    return SchemaProbe(read)


class FakeClient:
    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self._reply)])


def _client(reply: str) -> FakeClient:
    return FakeClient(reply)


PATCH = json.dumps({
    "rationale": "supplier's own code belongs in CodigoForn",
    "base_version": 1,
    "changes": [{"action": "set", "section": "lines", "name": "supplier_code",
                 "column": "CodigoForn", "source": "line.description",
                 "required": False}],
})


def test_draft_parses_a_structured_patch(rule):
    proposer = RuleProposer(_client(PATCH), "claude-sonnet-4-6")
    p = proposer.draft("supplier code goes to CodigoForn", rule, _schema())
    assert p.base_version == 1
    assert p.changes[0].column == "CodigoForn"


def test_draft_tolerates_prose_around_the_json(rule):
    proposer = RuleProposer(_client("Sure!\n" + PATCH + "\nHope that helps."),
                            "claude-sonnet-4-6")
    assert proposer.draft("x", rule, _schema()).changes[0].name == "supplier_code"


def test_draft_raises_when_there_is_no_json(rule):
    proposer = RuleProposer(_client("I cannot help with that."), "claude-sonnet-4-6")
    with pytest.raises(RuleDraftError):
        proposer.draft("x", rule, _schema())


def test_draft_raises_when_the_json_does_not_match_the_model(rule):
    proposer = RuleProposer(_client('{"rationale": "r", "changes": "not a list"}'),
                            "claude-sonnet-4-6")
    with pytest.raises(RuleDraftError):
        proposer.draft("x", rule, _schema())


def test_prompt_carries_the_real_columns_and_sources(rule):
    client = _client(PATCH)
    RuleProposer(client, "claude-sonnet-4-6").draft("x", rule, _schema())
    system = client.calls[0]["system"]
    assert "CodigoForn" in system          # real schema columns offered
    assert "line.description" in system    # real sources offered
    assert "temperature" in client.calls[0] and client.calls[0]["temperature"] == 0
