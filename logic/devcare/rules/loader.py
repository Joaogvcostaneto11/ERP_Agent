from __future__ import annotations
from pathlib import Path

import yaml

from logic.devcare.rules.models import EntityRule


class RuleLoader:
    def __init__(self, directory: Path | str) -> None:
        self._dir = Path(directory)
        self._rules: dict[str, EntityRule] = {}
        for path in sorted(self._dir.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            rule = EntityRule.model_validate(data)
            if rule.entity in self._rules:
                raise ValueError(f"duplicate entity {rule.entity!r} in {path}")
            self._rules[rule.entity] = rule

    def entities(self) -> list[str]:
        return list(self._rules)

    def get(self, entity: str) -> EntityRule:
        if entity not in self._rules:
            raise KeyError(entity)
        return self._rules[entity]
