import pytest

from logic.bills.rules.loader import RuleLoader
from logic.bills.rules.proposal import (
    FieldChange, RuleChangeProposal, apply, valid_sources, validate,
)
from logic.bills.rules.schema_probe import SchemaProbe

REAL_COLUMNS = {
    "Doc001": ["Chave", "Entidade", "Data", "Iliquido", "Total", "Obs", "DC", "OC", "Estado"],
    "LinDoc001": ["Documento", "ChaveProd", "Descricao", "Quantidade", "Punit", "CodigoForn"],
    "Entidades": ["Chave", "Nome", "NCont", "Tipo", "Listar"],
    "Artigos": ["Chave", "Nome", "Codigo"],
}


def _schema():
    def read(sql, params):
        return [{"COLUMN_NAME": c, "DATA_TYPE": "varchar", "IS_NULLABLE": "YES"}
                for c in REAL_COLUMNS.get(params["table"], [])]
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


@pytest.mark.parametrize("column", ["Chave", "DC", "OC", "Estado"])
def test_protected_columns_are_rejected(rule, column):
    # Chave = primary_key, DC/OC = audit_columns values, Estado = draft_defaults key
    p = _proposal(FieldChange(action="set", section="header", name="x",
                              column=column, source="bill.number"))
    v = validate(p, rule, _schema())
    assert len(v) == 1 and "protected" in v[0].reason


def test_create_column_change_is_validated_against_the_entity_table(rule):
    ok = _proposal(FieldChange(action="set", section="supplier_create", column="Nome"))
    assert validate(ok, rule, _schema()) == []
    bad = _proposal(FieldChange(action="set", section="supplier_create", column="Descricao"))
    assert len(validate(bad, rule, _schema())) == 1


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
