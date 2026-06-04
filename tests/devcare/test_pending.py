# tests/devcare/test_pending.py
import pytest
from logic.devcare.errors import NormalizedChange
from logic.devcare.pending import PendingChangeStore


def _change():
    return NormalizedChange("specialty", "create", "Especialidades", "Chave",
                            {"Nome": "X"}, None)


def test_stage_and_pop():
    store = PendingChangeStore()
    cid = store.stage("conv1", _change(), rule_doc="specialty", rule_version=1)
    assert cid.startswith("chg_")
    staged = store.pop("conv1", cid)
    assert staged.change.columns == {"Nome": "X"}
    assert staged.rule_version == 1


def test_pop_wrong_conversation_returns_none():
    store = PendingChangeStore()
    cid = store.stage("conv1", _change(), rule_doc="specialty", rule_version=1)
    assert store.pop("conv2", cid) is None


def test_pop_is_one_shot():
    store = PendingChangeStore()
    cid = store.stage("conv1", _change(), rule_doc="specialty", rule_version=1)
    assert store.pop("conv1", cid) is not None
    assert store.pop("conv1", cid) is None
