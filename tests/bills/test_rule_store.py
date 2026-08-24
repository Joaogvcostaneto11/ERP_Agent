import shutil
from pathlib import Path

import pytest
import yaml

from logic.bills.rules.store import RuleStore

_SRC = Path(__file__).resolve().parents[2] / "business_rules" / "bills" / "purchase_invoice.yaml"


@pytest.fixture
def store(tmp_path):
    shutil.copy(_SRC, tmp_path / "purchase_invoice.yaml")
    return RuleStore(tmp_path)


def test_current_loads_the_document(store):
    assert store.current().document == "purchase_invoice"


def test_save_archives_the_previous_version_then_replaces(store, tmp_path):
    original = store.current()
    bumped = original.model_copy(update={"version": original.version + 1})
    store.save(bumped)

    assert store.current().version == original.version + 1
    assert store.versions() == [original.version]
    assert store.historical(original.version).version == original.version


def test_revert_produces_a_new_version_carrying_the_old_content(store):
    v1 = store.current()
    v2 = v1.model_copy(update={"version": 2})
    v2.header.fields.pop("notes")
    store.save(v2)

    reverted = store.revert(1)

    assert reverted.version == 3                     # forward, never rewound
    assert "notes" in reverted.header.fields         # v1's content is back
    assert store.versions() == [1, 2]                # history intact


def test_saved_yaml_reloads_through_the_same_store(store):
    original = store.current()
    store.save(original.model_copy(update={"version": 9}))
    assert store.current().version == 9


def test_a_failed_write_leaves_the_previous_document_intact(store, tmp_path, monkeypatch):
    original_text = (tmp_path / "purchase_invoice.yaml").read_text(encoding="utf-8")

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr("logic.bills.rules.store.os.replace", boom)
    with pytest.raises(OSError):
        store.save(store.current().model_copy(update={"version": 42}))

    assert (tmp_path / "purchase_invoice.yaml").read_text(encoding="utf-8") == original_text
    assert not list(tmp_path.glob("*.tmp"))


def test_historical_for_an_unknown_version_raises(store):
    with pytest.raises(FileNotFoundError):
        store.historical(99)
