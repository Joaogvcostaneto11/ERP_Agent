from functools import lru_cache
from pathlib import Path

import yaml

from logic.config import settings


@lru_cache(maxsize=None)
def load_rule(domain: str) -> dict:
    path = settings.business_rules_dir / f"{domain}.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=None)
def rule_as_text(domain: str) -> str:
    path = settings.business_rules_dir / f"{domain}.yaml"
    return path.read_text(encoding="utf-8")
