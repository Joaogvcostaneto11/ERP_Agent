import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from logic.bills.rules.store import RuleStore, RuleVersionNotFound

_SEED_DIR = Path(__file__).resolve().parents[2] / "business_rules" / "bills"


@pytest.fixture
def factory(tmp_path):
    """SQLite stand-in for the ERPAgent_BillRules table, same approach as
    tests/bills/test_write_executor.py — the store issues plain SQL, so the
    engine only has to agree about columns."""
    eng = create_engine(f"sqlite:///{tmp_path/'rules.db'}")
    with eng.begin() as c:
        c.execute(text(
            "CREATE TABLE ERPAgent_BillRules ("
            " Version INTEGER NOT NULL PRIMARY KEY, Yaml TEXT NOT NULL,"
            " Ts TEXT NOT NULL, Action TEXT NOT NULL, Operator TEXT,"
            " Prose TEXT, Rationale TEXT, Changes TEXT, RevertedTo INTEGER)"))
    Local = sessionmaker(bind=eng)

    @contextmanager
    def _factory():
        s = Local()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    return _factory


@pytest.fixture
def store(factory):
    return RuleStore(factory, seed_path=_SEED_DIR)


def _rows(factory):
    with factory() as s:
        return s.execute(text(
            "SELECT Version, Action, Operator, Prose, Rationale, Changes, RevertedTo "
            "FROM ERPAgent_BillRules ORDER BY Version")).fetchall()


# --- seeding ------------------------------------------------------------

def test_an_empty_table_is_seeded_from_the_packaged_document(store):
    assert store.current().document == "purchase_invoice"


def test_the_seed_is_recorded_as_a_version_with_no_operator(store, factory):
    store.current()
    rows = _rows(factory)
    assert len(rows) == 1
    assert rows[0].Action == "seed"
    assert rows[0].Operator is None, "nobody made that change; the image shipped it"


def test_seeding_happens_once_not_on_every_read(store, factory):
    store.current()
    store.current()
    assert len(_rows(factory)) == 1


# --- saving -------------------------------------------------------------

def test_save_appends_a_version_and_becomes_current(store):
    original = store.current()
    store.save(original.model_copy(update={"version": original.version + 1}),
               operator="alice", action="apply")
    assert store.current().version == original.version + 1


def test_save_records_who_changed_it_and_why(store, factory):
    original = store.current()
    store.save(original.model_copy(update={"version": original.version + 1}),
               operator="alice", action="apply", prose="map the due date",
               rationale="Vencimento holds it",
               changes=[{"action": "set", "section": "header"}])
    row = _rows(factory)[-1]
    assert row.Operator == "alice"
    assert row.Prose == "map the due date"
    assert row.Rationale == "Vencimento holds it"
    assert json.loads(row.Changes) == [{"action": "set", "section": "header"}]


def test_a_second_save_at_the_same_version_is_rejected(store):
    """Version is the primary key, so two admins applying against the same base
    collide here instead of one silently overwriting the other."""
    original = store.current()
    bumped = original.model_copy(update={"version": original.version + 1})
    store.save(bumped, operator="alice", action="apply")
    with pytest.raises(Exception):
        store.save(bumped, operator="bob", action="apply")


# --- history ------------------------------------------------------------

def test_versions_lists_what_can_be_reverted_to_excluding_current(store):
    original = store.current()
    store.save(original.model_copy(update={"version": original.version + 1}),
               operator="alice", action="apply")
    # The admin UI offers this list as revert targets; reverting to the version
    # already in force is not a thing to offer.
    assert store.versions() == [original.version]


def test_historical_returns_the_document_as_it_was(store):
    v1 = store.current()
    v2 = v1.model_copy(update={"version": v1.version + 1})
    v2.header.fields.pop("notes")
    store.save(v2, operator="alice", action="apply")
    assert "notes" in store.historical(v1.version).header.fields


def test_historical_for_an_unknown_version_raises(store):
    store.current()
    with pytest.raises(RuleVersionNotFound):
        store.historical(99)


# --- revert -------------------------------------------------------------

def test_revert_moves_forward_carrying_the_old_content(store):
    v1 = store.current()
    v2 = v1.model_copy(update={"version": v1.version + 1})
    v2.header.fields.pop("notes")
    store.save(v2, operator="alice", action="apply")

    reverted = store.revert(v1.version, operator="bob")

    assert reverted.version == v2.version + 1        # forward, never rewound
    assert "notes" in reverted.header.fields         # v1's content is back
    assert store.versions() == [v1.version, v2.version]


def test_revert_records_what_it_reverted_to(store, factory):
    v1 = store.current()
    store.save(v1.model_copy(update={"version": v1.version + 1}),
               operator="alice", action="apply")
    store.revert(v1.version, operator="bob")
    row = _rows(factory)[-1]
    assert row.Action == "revert"
    assert row.Operator == "bob"
    assert row.RevertedTo == v1.version


def test_revert_to_an_unknown_version_raises(store):
    store.current()
    with pytest.raises(RuleVersionNotFound):
        store.revert(99, operator="bob")
