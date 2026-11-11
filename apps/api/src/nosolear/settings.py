from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NOSOLEAR_",
        env_file=REPO_ROOT / ".env",
        extra="ignore",
        env_ignore_empty=True,
    )

    data_dir: Path = REPO_ROOT / "data"

    @field_validator("data_dir")
    @classmethod
    def _resolve_against_repo_root(cls, value: Path) -> Path:
        """A relative path means relative to the repo, so every process agrees on one database."""
        return value if value.is_absolute() else REPO_ROOT / value

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'nosolear.sqlite'}"
