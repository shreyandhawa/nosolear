from pathlib import Path

import pytest

from nosolear.cli import main


def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(tmp_path))


def test_dev_seed_then_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(tmp_path, monkeypatch)
    assert main(["db", "upgrade"]) == 0
    assert main(["dev-seed", "--days", "14", "--seed", "7"]) == 0
    assert "Rebuilt profile: 6 keys as of " in capsys.readouterr().out


def test_dev_seed_refuses_existing_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(tmp_path, monkeypatch)
    main(["db", "upgrade"])
    main(["dev-seed"])
    capsys.readouterr()
    assert main(["dev-seed"]) == 2
    assert "observations already exist; use --force" in capsys.readouterr().err


def test_dev_seed_force_appends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(tmp_path, monkeypatch)
    main(["db", "upgrade"])
    main(["dev-seed"])
    assert main(["dev-seed", "--force"]) == 0
    assert "Rebuilt profile: 6 keys" in capsys.readouterr().out


def test_rebuild_profile_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(tmp_path, monkeypatch)
    main(["db", "upgrade"])
    capsys.readouterr()
    assert main(["rebuild-profile"]) == 0
    assert "Rebuilt profile: 0 keys as of " in capsys.readouterr().out


@pytest.mark.parametrize("value", ["", "data", "./data"])
def test_dev_seed_refuses_the_default_data_dir(
    value: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", value)

    def _no_engine(url: str) -> object:
        raise AssertionError(f"must refuse before touching the database: {url}")

    monkeypatch.setattr("nosolear.cli.create_engine_for", _no_engine)
    assert main(["dev-seed"]) == 2
    assert main(["dev-seed", "--force"]) == 2
    err = capsys.readouterr().err
    assert "NOSOLEAR_DATA_DIR" in err and "data/dev" in err
