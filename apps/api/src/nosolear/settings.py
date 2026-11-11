from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NOSOLEAR_",
        env_file=REPO_ROOT / ".env",
        extra="ignore",
    )

    data_dir: Path = REPO_ROOT / "data"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'nosolear.sqlite'}"
