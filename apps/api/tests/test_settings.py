from pathlib import Path

import pytest

from nosolear.settings import REPO_ROOT, Settings

DEFAULT = REPO_ROOT / "data"


def _settings() -> Settings:
    return Settings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_default_is_repo_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOSOLEAR_DATA_DIR", raising=False)
    assert _settings().data_dir == DEFAULT


def test_empty_env_value_counts_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", "")
    assert _settings().data_dir == DEFAULT


def test_relative_value_resolves_against_repo_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", "data/dev")
    assert _settings().data_dir == REPO_ROOT / "data" / "dev"
    assert _settings().database_url == f"sqlite:///{REPO_ROOT / 'data' / 'dev' / 'nosolear.sqlite'}"


def test_absolute_value_is_kept(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(tmp_path))
    assert _settings().data_dir == tmp_path


def test_empty_value_in_env_file_counts_as_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("NOSOLEAR_DATA_DIR", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("NOSOLEAR_DATA_DIR=\n")
    assert Settings(_env_file=env_file).data_dir == DEFAULT  # pyright: ignore[reportCallIssue]
