import datetime

from logic.devcare.form_builder import build_form
from logic.devcare.rules.loader import RuleLoader


class FakeReader:
    def __init__(self, rows_by_table=None):
        self.rows_by_table = rows_by_table or {}

    def __call__(self, sql, params):
        for table, rows in self.rows_by_table.items():
            if table in sql:
                return rows
        return []


def _loader():
    return RuleLoader("business_rules/devcare")


def test_patient_create_form_input_types():
    loader = _loader()
    form = build_form(loader.get("patient"), loader, "create", FakeReader(), "DevCare.dbo.")
    assert form["entity"] == "patient" and form["operation"] == "create"
    by = {f["name"]: f for f in form["fields"]}
    assert by["name"]["input"] == "text" and by["name"]["required"] is True
    assert by["name"]["maxlength"] == 200
    assert by["birth_date"]["input"] == "date"
    assert by["gender"]["input"] == "select"
    assert [o["label"] for o in by["gender"]["options"]] == ["Male", "Female", "Unspecified"]
    assert all(f["value"] is None for f in form["fields"])  # blank on create


def test_doctor_form_specialty_reference_populated():
    loader = _loader()
    reader = FakeReader({"Especialidades": [
        {"value": 23, "label": "Cardiologia"}, {"value": 12, "label": "Neurologia"}]})
    form = build_form(loader.get("doctor"), loader, "create", reader, "DevCare.dbo.")
    spec = next(f for f in form["fields"] if f["name"] == "specialty")
    assert spec["input"] == "select"
    assert {"value": 23, "label": "Cardiologia"} in spec["options"]


def test_update_form_prefills_current_values():
    loader = _loader()

    class Reader:
        def __call__(self, sql, params):
            if "SELECT *" in sql:
                return [{"Nome": "Maria", "Sexo": 2,
                         "DataNasc": datetime.datetime(1990, 5, 14)}]
            return []

    form = build_form(loader.get("patient"), loader, "update", Reader(),
                      "DevCare.dbo.", target_pk=5)
    by = {f["name"]: f for f in form["fields"]}
    assert by["name"]["value"] == "Maria"
    assert by["gender"]["value"] == 2
    assert by["birth_date"]["value"] == "1990-05-14"  # datetime -> ISO date


def test_prefill_from_model_takes_precedence():
    loader = _loader()
    form = build_form(loader.get("patient"), loader, "create", FakeReader(),
                      "DevCare.dbo.", prefill={"name": "Joao", "gender": 1})
    by = {f["name"]: f for f in form["fields"]}
    assert by["name"]["value"] == "Joao"
    assert by["gender"]["value"] == 1
