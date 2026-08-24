import pytest

from logic.bills.tax_id import pt_nif_is_valid


@pytest.mark.parametrize("value, expected", [
    ("502667583", True),      # Sage, correct
    ("502267583", False),     # what the model returned (misread digit)
    ("502544180", True),      # Vodafone
    ("513989536", True),      # Atlante
    ("503448672", True),      # Alves & Catalão
    ("PT505939347", True),    # Databox, PT-prefixed
    ("514380802", True),      # FORUMSI, the buyer
    ("514580802", False),     # the buyer transposition
    ("ESB65814709", None),    # Jotelulu, Spanish VAT: not PT-shaped
])
def test_brief_table(value, expected):
    assert pt_nif_is_valid(value) is expected


@pytest.mark.parametrize("value", ["", None, "12345", "50266758X"])
def test_non_pt_shaped_returns_none_not_false(value):
    assert pt_nif_is_valid(value) is None


def test_tolerates_surrounding_whitespace():
    assert pt_nif_is_valid("  502667583  ") is True


def test_tolerates_pt_prefix_and_whitespace_together():
    assert pt_nif_is_valid("  PT505939347  ") is True
