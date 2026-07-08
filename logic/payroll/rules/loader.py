from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from pydantic import ValidationError
from logic.payroll.errors import RuleLoadError
from logic.payroll.rules.models import RuleDocument


class NoFloatYamlLoader(yaml.SafeLoader):
    """SafeLoader that refuses to coerce numeric scalars into Python floats.

    All numeric values in payroll YAML must be quoted strings (and parsed into
    `Decimal` later by Pydantic), to avoid the rounding errors inherent in float
    representation. Integer literals are still permitted (PyYAML parses them
    losslessly), but float literals (anything containing a decimal point or
    exponent) trigger a `RuleLoadError`.
    """


def _construct_float_rejecting(self: yaml.SafeLoader, node: yaml.ScalarNode) -> Any:
    raise yaml.constructor.ConstructorError(
        None, None,
        f"float literal {node.value!r} is not permitted in payroll YAML; quote the value to keep it as a string",
        node.start_mark,
    )


NoFloatYamlLoader.add_constructor(
    "tag:yaml.org,2002:float",
    _construct_float_rejecting,
)


class RuleLoader:
    def __init__(self) -> None:
        self._cache: dict[Path, RuleDocument] = {}

    def load_document(self, path: Path) -> RuleDocument:
        path = Path(path).resolve()
        if path in self._cache:
            return self._cache[path]
        if not path.exists():
            raise RuleLoadError(
                code="YAML_FILE_NOT_FOUND",
                msg_pt=f"ficheiro de regras nao encontrado: {path}",
                msg_en=f"rule file not found: {path}",
            )
        text = path.read_text(encoding="utf-8")
        try:
            raw = yaml.load(text, Loader=NoFloatYamlLoader)
        except yaml.constructor.ConstructorError as ex:
            if "float literal" in (ex.problem or ""):
                raise RuleLoadError(
                    code="YAML_FLOAT_LITERAL",
                    msg_pt=f"literal float nao permitido em {path}: {ex.problem}",
                    msg_en=f"float literal not permitted in {path}: {ex.problem}",
                ) from ex
            raise RuleLoadError(
                code="YAML_PARSE_ERROR",
                msg_pt=f"erro ao analisar YAML em {path}: {ex}",
                msg_en=f"YAML parse error in {path}: {ex}",
            ) from ex
        except yaml.YAMLError as ex:
            raise RuleLoadError(
                code="YAML_PARSE_ERROR",
                msg_pt=f"erro ao analisar YAML em {path}: {ex}",
                msg_en=f"YAML parse error in {path}: {ex}",
            ) from ex
        try:
            doc = RuleDocument.model_validate(raw)
        except ValidationError as ex:
            raise RuleLoadError(
                code="YAML_SCHEMA_INVALID",
                msg_pt=f"esquema invalido em {path}: {ex}",
                msg_en=f"invalid schema in {path}: {ex}",
            ) from ex
        self._cache[path] = doc
        return doc

    def reload(self) -> None:
        self._cache.clear()
