from pathlib import Path
import pytest
from logic.payroll.errors import RuleLoadError
from logic.payroll.rules.loader import RuleLoader, NoFloatYamlLoader


def test_loader_loads_minimal_statutory(tmp_path: Path):
    yaml_path = tmp_path / "statutory.yaml"
    yaml_path.write_text(
        """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
    taxable: true
""",
        encoding="utf-8",
    )
    loader = RuleLoader()
    doc = loader.load_document(yaml_path)
    assert doc.metadata.jurisdiction == "PT"
    assert "base_salary" in doc.components


def test_loader_rejects_float_literal(tmp_path: Path):
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text(
        """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: 0.11
      base_components: ["base_salary"]
    inputs_required: ["base_salary"]
""",
        encoding="utf-8",
    )
    loader = RuleLoader()
    with pytest.raises(RuleLoadError) as exc:
        loader.load_document(yaml_path)
    assert exc.value.code == "YAML_FLOAT_LITERAL"


def test_loader_accepts_quoted_decimal(tmp_path: Path):
    yaml_path = tmp_path / "ok.yaml"
    yaml_path.write_text(
        """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: "0.11"
      base_components: ["base_salary"]
    inputs_required: ["base_salary"]
""",
        encoding="utf-8",
    )
    loader = RuleLoader()
    doc = loader.load_document(yaml_path)
    assert doc.components["tsu_employee"].parameters["rate"] == "0.11"


def test_loader_missing_file_raises(tmp_path: Path):
    loader = RuleLoader()
    with pytest.raises(RuleLoadError) as exc:
        loader.load_document(tmp_path / "missing.yaml")
    assert exc.value.code == "YAML_FILE_NOT_FOUND"


def test_loader_invalid_schema_raises(tmp_path: Path):
    yaml_path = tmp_path / "bad_schema.yaml"
    yaml_path.write_text(
        """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: weird
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
""",
        encoding="utf-8",
    )
    loader = RuleLoader()
    with pytest.raises(RuleLoadError) as exc:
        loader.load_document(yaml_path)
    assert exc.value.code == "YAML_SCHEMA_INVALID"


def test_loader_caches_loaded_documents(tmp_path: Path):
    yaml_path = tmp_path / "statutory.yaml"
    yaml_path.write_text(
        """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components: {}
""",
        encoding="utf-8",
    )
    loader = RuleLoader()
    doc1 = loader.load_document(yaml_path)
    doc2 = loader.load_document(yaml_path)
    assert doc1 is doc2  # cached identity


def test_loader_rejects_unknown_yaml_field(tmp_path: Path):
    yaml_path = tmp_path / "unknown_field.yaml"
    yaml_path.write_text(
        """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
    unknown_field: foo
""",
        encoding="utf-8",
    )
    loader = RuleLoader()
    with pytest.raises(RuleLoadError) as exc:
        loader.load_document(yaml_path)
    assert exc.value.code == "YAML_SCHEMA_INVALID"


def test_loader_reload_clears_cache(tmp_path: Path):
    yaml_path = tmp_path / "statutory.yaml"
    yaml_path.write_text(
        """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components: {}
""",
        encoding="utf-8",
    )
    loader = RuleLoader()
    doc1 = loader.load_document(yaml_path)
    loader.reload()
    doc2 = loader.load_document(yaml_path)
    assert doc1 is not doc2
