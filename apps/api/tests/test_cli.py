from pathlib import Path

import pytest

from nosolear.cli import main
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.persistence.db import create_engine_for
from nosolear.persistence.repositories import ProfileRepository


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


def test_cli_reports_bad_settings_without_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NOSOLEAR_HOST", "0.0.0.0")
    assert main(["rebuild-profile"]) == 2
    err = capsys.readouterr().err
    assert "NOSOLEAR_HOST" in err and "0.0.0.0" not in err


def test_cli_short_key_exits_2_without_leaking(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    key = "Sh0rtKeyValue15!"[:15]
    monkeypatch.setenv("NOSOLEAR_ANTHROPIC_API_KEY", key)
    assert main(["rebuild-profile"]) == 2
    captured = capsys.readouterr()
    assert "NOSOLEAR_ANTHROPIC_API_KEY" in captured.err
    assert key not in captured.err and key not in captured.out
    assert captured.out == ""


def test_db_upgrade_tightens_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "loose"
    data.mkdir()
    data.chmod(0o755)
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(data))
    assert main(["db", "upgrade"]) == 0
    assert data.stat().st_mode & 0o777 == 0o700


def test_db_upgrade_creates_owner_only_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "fresh"
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(data))
    assert main(["db", "upgrade"]) == 0
    assert (data / "nosolear.sqlite").stat().st_mode & 0o777 == 0o600


def test_data_dir_problem_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    file = tmp_path / "afile"
    file.write_text("x")
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(file))
    assert main(["db", "upgrade"]) == 2
    assert "data directory problem:" in capsys.readouterr().err


def _p_hats(tmp_path: Path) -> dict[str, float]:
    engine = create_engine_for(f"sqlite:///{tmp_path / 'nosolear.sqlite'}")
    try:
        profile = ProfileRepository(engine, DEFAULT_TAXONOMY).latest()
        assert profile is not None
        return {e.definition.key: e.estimate.p_hat for e in profile.entries}
    finally:
        engine.dispose()


def test_rebuild_profile_follows_the_pack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("NOSOLEAR_PACK", "nepali")
    assert main(["db", "upgrade"]) == 0
    assert main(["dev-seed"]) == 0
    nepali = _p_hats(tmp_path)
    monkeypatch.setenv("NOSOLEAR_PACK", "neutral")
    assert main(["rebuild-profile"]) == 0
    assert _p_hats(tmp_path) != nepali
    engine = create_engine_for(f"sqlite:///{tmp_path / 'nosolear.sqlite'}")
    try:
        assert ProfileRepository(engine, DEFAULT_TAXONOMY).latest_pack_id() == "neutral"
    finally:
        engine.dispose()


def test_unknown_pack_exits_2_with_a_clean_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("NOSOLEAR_PACK", "nosuchpack")
    assert main(["rebuild-profile"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("pack error:") and "nosuchpack" in err and "Traceback" not in err


def test_path_like_pack_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("NOSOLEAR_PACK", "../x")
    assert main(["rebuild-profile"]) == 2
    assert "Traceback" not in capsys.readouterr().err
