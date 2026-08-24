from logic.bills.pending import PendingProposalStore


def test_put_get_pop_roundtrip():
    store = PendingProposalStore()
    store.put("p1", {"x": 1})
    assert store.get("p1") == {"x": 1}
    assert store.pop("p1") == {"x": 1}
    assert store.get("p1") is None


def test_pop_missing_returns_none():
    assert PendingProposalStore().pop("nope") is None
