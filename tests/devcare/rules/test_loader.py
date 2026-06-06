import pytest
from logic.devcare.rules.loader import RuleLoader


def test_loads_real_business_rules():
    loader = RuleLoader("business_rules/devcare")
    assert set(loader.entities()) == {"patient", "specialty", "doctor"}
    patient = loader.get("patient")
    assert patient.table == "Entidades"
    assert patient.primary_key == "Chave"
    assert patient.soft_delete.column == "Hist"
    assert patient.fields["name"].required is True
    doctor = loader.get("doctor")
    assert doctor.table == "Prescritores"
    assert doctor.references["specialty"].table == "Especialidades"


def test_unknown_entity_raises():
    loader = RuleLoader("business_rules/devcare")
    with pytest.raises(KeyError):
        loader.get("nurse")


def test_malformed_yaml_rejected(tmp_path):
    (tmp_path / "bad.yaml").write_text("entity: bad\nversion: 1\n", encoding="utf-8")
    with pytest.raises(Exception):
        RuleLoader(tmp_path)
