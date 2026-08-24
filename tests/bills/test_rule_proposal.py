import re

import pytest

from logic.bills.rules.loader import RuleLoader
from logic.bills.rules.proposal import (
    FieldChange, RuleChangeProposal, _protected, apply, valid_sources, validate,
)
from logic.bills.rules.schema_probe import SchemaProbe

REAL_COLUMNS = {
    # Chave and TipoDoc included because write_executor.py writes both
    # (write_executor.py:93-94, :114) — a fake schema missing them would let a
    # protected-column test pass vacuously via "does not exist" instead of
    # actually exercising the protected-column check.
    "Doc001": ["Chave", "Entidade", "Data", "Iliquido", "Total", "Obs", "DC", "OC", "Estado", "TipoDoc"],
    "LinDoc001": ["Chave", "Documento", "ChaveProd", "Descricao", "Quantidade", "Punit", "CodigoForn"],
    "Entidades": ["Chave", "Nome", "NCont", "Tipo", "Listar"],
    "Artigos": ["Chave", "Nome", "Codigo"],
}


def _schema():
    def read(sql, params):
        return [{"COLUMN_NAME": c, "DATA_TYPE": "varchar", "IS_NULLABLE": "YES"}
                for c in REAL_COLUMNS.get(params["table"], [])]
    return SchemaProbe(read)


# Mirrors the real Doc001/LinDoc001 shape, where 79 of 164 columns are integer
# types — the family a Decimal source must never reach.
TYPED_COLUMNS = {
    "Doc001": {"Obs": "varchar", "Data": "smalldatetime", "Iliquido": "decimal",
               "Total": "decimal", "Volumes": "bigint", "Entidade": "bigint",
               "Chave": "bigint", "DC": "smalldatetime", "OC": "bigint",
               "Estado": "tinyint", "TipoDoc": "bigint"},
    "LinDoc001": {"Descricao": "varchar", "Quantidade": "decimal",
                  "Punit": "decimal", "Armazem": "bigint", "ChaveProd": "bigint",
                  "Chave": "bigint", "Documento": "bigint"},
    "Entidades": {"Chave": "bigint", "Nome": "varchar", "NCont": "varchar"},
    "Artigos": {"Chave": "bigint", "Nome": "varchar", "Codigo": "varchar"},
}


def _typed_schema():
    def read(sql, params):
        return [{"COLUMN_NAME": c, "DATA_TYPE": t, "IS_NULLABLE": "NO",
                 "CHARACTER_MAXIMUM_LENGTH": 50 if t == "varchar" else None}
                for c, t in TYPED_COLUMNS.get(params["table"], {}).items()]
    return SchemaProbe(read)


@pytest.fixture
def rule():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    return RuleLoader(root / "business_rules" / "bills").rule()


def _proposal(*changes, base=1):
    return RuleChangeProposal(rationale="r", base_version=base, changes=list(changes))


def test_valid_sources_cover_bill_and_line_fields():
    s = valid_sources()
    assert "bill.net_total" in s and "line.description" in s
    assert "supplier.match" in s and "line.match" in s
    # containers, and the deliberately extraction-only buyer_tax_id
    assert "bill.lines" not in s and "bill.confidence" not in s
    assert "bill.buyer_tax_id" not in s


def test_bill_notes_is_not_a_valid_source(rule):
    # The shipped YAML maps source: bill.notes, but Bill has no `notes` field.
    # That mapping is already dead; validation must not let it be reissued.
    assert "bill.notes" not in valid_sources()
    p = _proposal(FieldChange(action="set", section="header", name="notes",
                              column="Obs", source="bill.notes"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "not a known source" in v[0].reason


def test_valid_change_passes_and_merges_with_schema_spelling(rule):
    p = _proposal(FieldChange(action="set", section="lines", name="supplier_code",
                              column="codigoforn", source="line.description"))
    assert validate(p, rule, _schema()) == []
    merged = apply(p, rule, _schema())
    # persisted using the schema's exact spelling, not the admin's casing
    assert merged.lines.fields["supplier_code"].column == "CodigoForn"
    assert merged.version == rule.version + 1


def test_column_absent_from_the_target_table_is_rejected(rule):
    p = _proposal(FieldChange(action="set", section="lines", name="x",
                              column="NoSuchColumn", source="line.description"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "does not exist" in v[0].reason


def test_column_that_exists_but_on_another_table_is_rejected(rule):
    # Iliquido is a real column — on Doc001, not on LinDoc001
    p = _proposal(FieldChange(action="set", section="lines", name="x",
                              column="Iliquido", source="line.total"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "does not exist" in v[0].reason


def test_injection_shaped_identifier_is_rejected_even_if_schema_says_yes(rule):
    evil = "Descricao); DROP TABLE LinDoc001; --"

    class YesProbe:
        def resolve(self, table, column):
            return column          # schema check subverted
        def columns(self, table):
            return {}

    p = _proposal(FieldChange(action="set", section="lines", name="x",
                              column=evil, source="line.description"))
    v = validate(p, rule, YesProbe())
    assert len(v) == 1 and "not a valid identifier" in v[0].reason


def test_unknown_source_is_rejected(rule):
    p = _proposal(FieldChange(action="set", section="header", name="x",
                              column="Obs", source="bill.not_a_field"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "not a known source" in v[0].reason


PROTECTED_COLUMNS = ["Chave", "DC", "OC", "Estado", "ATCUD", "CodigoAT", "Certificacao"]


def _protected_change(section, column):
    # header/lines are mapped sections and need name+source; the two *_create
    # sections take a bare column.
    if section == "header":
        return FieldChange(action="set", section=section, name="x",
                           column=column, source="bill.number")
    if section == "lines":
        return FieldChange(action="set", section=section, name="x",
                           column=column, source="line.description")
    return FieldChange(action="set", section=section, column=column)


@pytest.mark.parametrize("section", ["header", "lines"])
@pytest.mark.parametrize("column", PROTECTED_COLUMNS)
def test_protected_columns_are_rejected_in_every_mapped_section(rule, column, section):
    # Chave = primary_key, DC/OC = audit_columns values, Estado/ATCUD/CodigoAT/
    # Certificacao = draft_defaults keys.
    # Regression for C1: the protected-column check must not be gated to the
    # header section. The two *_create sections used to be covered here too;
    # they are now refused wholesale before this check runs (see
    # test_create_section_* below), so their share of C1 is asserted through
    # _protected() directly instead.
    p = _proposal(_protected_change(section, column))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "protected" in v[0].reason


@pytest.mark.parametrize("section", ["supplier_create", "article_create"])
@pytest.mark.parametrize("column", PROTECTED_COLUMNS)
def test_create_sections_still_compute_their_protected_columns(rule, column, section):
    # Defence in depth for C1 behind I1's blanket refusal: if create-section
    # editing is ever wired up, _protected() must still cover the columns
    # _resolve_entity() computes for itself (write_executor.py:53-56).
    assert column.lower() in _protected(rule, section)


def test_supplier_create_defaults_are_protected(rule):
    # Regression for C1's second half: create_defaults keys (Tipo, Listar for
    # supplier_create) must also be protected. _resolve_entity() seeds
    # create_defaults into the new row before splicing in proposed_new
    # (write_executor.py:54); a mappable Tipo would let a proposal override it.
    assert {"tipo", "listar"} <= _protected(rule, "supplier_create")


def test_create_section_add_is_rejected(rule):
    # Regression for I1: create_columns is only the whitelist write_executor
    # checks the hardcoded matching.py payload against, so adding a column here
    # is inert. Refuse it rather than let an admin believe it took effect.
    p = _proposal(FieldChange(action="set", section="supplier_create", column="Nome"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "not supported yet" in v[0].reason


def test_create_section_remove_is_rejected(rule):
    # The dangerous half of I1: dropping Nome from the whitelist makes
    # _check_columns raise ValueError on every bill with an unmatched supplier,
    # and /bills/commit only catches RuntimeError — HTTP 500 until reverted.
    p = _proposal(FieldChange(action="remove", section="supplier_create", column="Nome"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "not supported yet" in v[0].reason


@pytest.mark.parametrize("section,column", [
    ("supplier_create", "Chave"),
    ("article_create", "Chave"),
])
def test_c1_net_protected_column_is_rejected_in_create_sections(rule, section, column):
    # C1 regression net. validate() must reject a protected column (the
    # primary key, here) smuggled into a create section's payload, no matter
    # which gate does the rejecting: today it's the I1 blanket refusal of
    # supplier_create/article_create ("not supported yet"); if that gate is
    # ever lifted for create-section editing, the protected-column check
    # itself must still catch it ("protected"). This is the test that must
    # go red if someone re-gates the protected check to `ch.section in
    # _MAPPED` while also lifting the I1 gate — the same C1 bug, respelled.
    p = _proposal(_protected_change(section, column))
    v = validate(p, rule, _schema())
    assert len(v) == 1
    assert re.search(r"protected|not supported", v[0].reason)


def test_c1_net_create_defaults_key_is_rejected_in_supplier_create(rule):
    # Second half of C1: create_defaults keys (Tipo, seeded by
    # _resolve_entity() before splicing in proposed_new) must also be
    # unreachable through a create-section proposal.
    p = _proposal(_protected_change("supplier_create", "Tipo"))
    v = validate(p, rule, _schema())
    assert len(v) == 1
    assert re.search(r"protected|not supported", v[0].reason)


def test_apply_adds_and_removes_create_columns(rule):
    p = _proposal(FieldChange(action="set", section="article_create", column="Codigo"))
    merged = apply(p, rule, _schema())
    assert "Codigo" in merged.matching.article.create_columns

    p2 = RuleChangeProposal(rationale="r", base_version=merged.version, changes=[
        FieldChange(action="remove", section="article_create", column="Codigo")])
    back = apply(p2, merged, _schema())
    assert "Codigo" not in back.matching.article.create_columns


def test_remove_of_a_header_field_drops_the_mapping(rule):
    p = _proposal(FieldChange(action="remove", section="header", name="notes"))
    merged = apply(p, rule, _schema())
    assert "notes" not in merged.header.fields


def test_set_without_a_source_is_rejected_for_mapped_sections(rule):
    p = _proposal(FieldChange(action="set", section="header", name="x", column="Obs"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "source is required" in v[0].reason


def test_violations_report_every_bad_change_not_just_the_first(rule):
    p = _proposal(
        FieldChange(action="set", section="header", name="a", column="Nope", source="bill.number"),
        FieldChange(action="set", section="header", name="b", column="Obs", source="bill.nope"),
    )
    v = validate(p, rule, _schema())
    assert [x.change_index for x in v] == [0, 1]


def test_remove_with_an_injection_shaped_column_is_rejected(rule):
    # Originally a regression for the create-section remove branch, which used
    # to `continue` after a presence check only and let an injection-shaped
    # column through validate(). I1's blanket refusal of create sections now
    # catches it first; what matters is that it is still rejected.
    evil = "Codigo); DROP TABLE Artigos; --"
    p = _proposal(FieldChange(action="remove", section="article_create", column=evil))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "not supported yet" in v[0].reason


def test_mapped_remove_with_a_stray_column_does_not_crash_apply(rule):
    # Regression for I2: validate() `continue`s on a mapped remove without
    # inspecting ch.column, but apply() used to resolve ch.column whenever it
    # was set — so a remove carrying a column for another table validated
    # clean and then blew up with AssertionError (HTTP 500) inside apply().
    p = _proposal(FieldChange(action="remove", section="lines", name="vat_rate",
                              column="Obs"))
    assert validate(p, rule, _schema()) == []
    merged = apply(p, rule, _schema())
    assert "vat_rate" not in merged.lines.fields


def test_structural_header_field_cannot_be_removed(rule):
    # Regression for I1 (second half): removing header.supplier would drop the
    # mapping write_executor.py:94 depends on (`rule.header.fields["supplier"]`),
    # raising KeyError on every subsequent write.
    p = _proposal(FieldChange(action="remove", section="header", name="supplier"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "protected" in v[0].reason


def test_structural_lines_field_cannot_be_removed(rule):
    # Same as above for write_executor.py:116 (`rule.lines.fields["article"]`).
    p = _proposal(FieldChange(action="remove", section="lines", name="article"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "protected" in v[0].reason


def test_structural_field_cannot_be_retargeted(rule):
    # Regression for I1 (second half): retargeting header.supplier to Obs would
    # reroute the supplier FK into the notes column instead of just dropping it.
    p = _proposal(FieldChange(action="set", section="header", name="supplier",
                              column="Obs", source="bill.number"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "protected" in v[0].reason


def test_trailing_newline_identifier_is_rejected(rule):
    # Regression for I2: `_IDENT_RE.match()` let "Descricao\n" through because
    # `$` matches just before a trailing newline. Use a schema double that
    # would approve any column, so only the regex determines the outcome —
    # this is the case the regex exists for: the schema lookup cannot be
    # trusted to catch what the regex misses.
    class YesProbe:
        def resolve(self, table, column):
            return column
        def columns(self, table):
            return {}

    p = _proposal(FieldChange(action="set", section="lines", name="x",
                              column="Descricao\n", source="line.description"))
    v = validate(p, rule, YesProbe())
    assert len(v) == 1 and "not a valid identifier" in v[0].reason


# --- column type compatibility -------------------------------------------

def test_source_type_is_derived_from_the_extraction_models():
    from datetime import date
    from decimal import Decimal

    from logic.bills.rules.proposal import source_type

    assert source_type("bill.gross_total") is Decimal   # unwraps Decimal | None
    assert source_type("bill.issue_date") is date
    assert source_type("bill.supplier_name") is str     # bare str, not Optional
    assert source_type("line.quantity") is Decimal
    assert source_type("supplier.match") is int         # entity key sentinel
    assert source_type("line.match") is int
    assert source_type("bill.not_a_field") is None


def test_a_decimal_source_cannot_be_written_to_an_integer_column(rule):
    """The silent one. SQL Server converts decimal->bigint implicitly and drops
    the fractional part, so 1234.56 is written as 1234 with no error."""
    p = _proposal(FieldChange(action="set", section="header", name="x",
                              column="Volumes", source="bill.gross_total"))
    v = validate(p, rule, _typed_schema())
    assert len(v) == 1
    assert "cannot be written" in v[0].reason and "bigint" in v[0].reason


def test_a_text_source_cannot_be_written_to_a_numeric_or_date_column(rule):
    numeric = _proposal(FieldChange(action="set", section="header", name="x",
                                    column="Iliquido", source="bill.supplier_name"))
    assert len(validate(numeric, rule, _typed_schema())) == 1
    temporal = _proposal(FieldChange(action="set", section="header", name="x",
                                     column="Data", source="bill.supplier_name"))
    assert len(validate(temporal, rule, _typed_schema())) == 1


def test_a_date_source_cannot_be_written_to_a_numeric_column(rule):
    p = _proposal(FieldChange(action="set", section="header", name="x",
                              column="Iliquido", source="bill.issue_date"))
    assert len(validate(p, rule, _typed_schema())) == 1


def test_compatible_mappings_are_accepted(rule):
    ok = [
        ("header", "Iliquido", "bill.net_total"),      # Decimal -> decimal
        ("header", "Data", "bill.issue_date"),         # date    -> smalldatetime
        ("header", "Obs", "bill.number"),              # str     -> varchar
        ("lines", "Descricao", "line.description"),    # str     -> varchar
        ("lines", "Quantidade", "line.quantity"),      # Decimal -> decimal
    ]
    for section, column, source in ok:
        p = _proposal(FieldChange(action="set", section=section, name="x",
                                  column=column, source=source))
        assert validate(p, rule, _typed_schema()) == [], f"{source} -> {column}"


def test_text_columns_accept_any_source_because_the_conversion_is_lossless(rule):
    for source in ("bill.gross_total", "bill.issue_date", "bill.supplier_name"):
        p = _proposal(FieldChange(action="set", section="header", name="x",
                                  column="Obs", source=source))
        assert validate(p, rule, _typed_schema()) == [], source


def test_an_entity_key_source_must_go_to_an_integer_column(rule):
    ok = _proposal(FieldChange(action="set", section="header", name="x",
                               column="Entidade", source="supplier.match"))
    assert validate(ok, rule, _typed_schema()) == []
    bad = _proposal(FieldChange(action="set", section="header", name="x",
                                column="Obs", source="supplier.match"))
    assert len(validate(bad, rule, _typed_schema())) == 1


def test_type_checking_is_skipped_when_the_probe_cannot_describe_the_column(rule):
    """A stub probe that resolves names but exposes no column metadata must not
    make every mapping fail — existence and identifier checks still apply."""
    class NameOnlyProbe:
        def resolve(self, table, column): return column
        def columns(self, table): return {}

    p = _proposal(FieldChange(action="set", section="header", name="x",
                              column="Obs", source="bill.gross_total"))
    assert validate(p, rule, NameOnlyProbe()) == []
