from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings

REPO_ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    anthropic_api_key: Optional[str] = None
    model: str = "claude-sonnet-4-6"
    business_rules_dir: Path = REPO_ROOT / "business_rules"
    database_url: Optional[str] = None

    model_config = {"env_file": ".env"}


settings = Settings()
