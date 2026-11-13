import stat
from pathlib import Path

import pytest
from factories import make_settings

from nosolear.adapters.system_clock import SystemClock
from nosolear.cli import main
from nosolear.domain.budget import Caps, Provider, Unit
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.persistence.db import create_engine_for
from nosolear.persistence.ledger import SqliteUsageLedger
from nosolear.persistence.repositories import ProfileRepository
from nosolear.settings import Settings


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


_LABELS = [
    "Azure Speech",
    "Azure capabilities",
    "Anthropic",
    "Transcriber",
    "Phone probe",
    "Language pack",
    "Data dir",
    "Usage",
]
AZURE_KEY = "AzurePlantedKey-0123456789abcdef"
CLAUDE_KEY = "AnthropicPlantedKey-0123456789abcdef"


def test_doctor_reports_missing_keys_and_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(data))
    assert main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "Azure Speech" in out and "NOSOLEAR_AZURE_SPEECH_KEY" in out
    assert not data.exists()


def test_doctor_exits_0_when_configured_and_never_prints_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NOSOLEAR_AZURE_SPEECH_KEY", AZURE_KEY)
    monkeypatch.setenv("NOSOLEAR_AZURE_SPEECH_REGION", "westus2")
    monkeypatch.setenv("NOSOLEAR_ANTHROPIC_API_KEY", CLAUDE_KEY)
    assert main(["doctor"]) == 0
    captured = capsys.readouterr()
    assert all(label in captured.out for label in _LABELS)
    assert not (tmp_path / "data").exists()
    for key in (AZURE_KEY, CLAUDE_KEY):
        assert key not in captured.out and key not in captured.err


def test_doctor_probe_is_not_available_yet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(tmp_path / "data"))
    assert main(["doctor", "--probe"]) == 2
    captured = capsys.readouterr()
    assert "probes arrive in Phase 0d" in captured.err and captured.out == ""


def test_doctor_with_an_unknown_pack_still_prints_every_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NOSOLEAR_PACK", "nosuchpack")
    assert main(["doctor"]) == 1
    out = capsys.readouterr().out
    labels = [
        "Azure Speech",
        "Azure capabilities",
        "Anthropic",
        "Transcriber",
        "Phone probe",
        "Language pack",
        "Data dir",
        "Usage",
    ]
    assert all(label in out for label in labels)
    assert "nosuchpack" in out
    assert not (tmp_path / "data").exists()


def test_doctor_keeps_the_invalid_settings_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NOSOLEAR_HOST", "0.0.0.0")
    assert main(["doctor"]) == 2
    assert "NOSOLEAR_HOST" in capsys.readouterr().err


def test_doctor_reports_a_loose_existing_data_dir_without_touching_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    data.chmod(0o755)
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(data))
    before = sorted(p.name for p in tmp_path.rglob("*"))
    main(["doctor"])
    out = capsys.readouterr().out
    line = next(line for line in out.splitlines() if line.startswith("Data dir"))
    assert "degraded" in line and "chmod 700" in out
    assert data.stat().st_mode & 0o777 == 0o755
    assert sorted(p.name for p in tmp_path.rglob("*")) == before


def _env_file(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setitem(Settings.model_config, "env_file", path)


def test_doctor_unreadable_env_file_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env = tmp_path / ".env"
    env.write_text("NOSOLEAR_PORT=9000\n")
    env.chmod(0o000)
    _env_file(monkeypatch, env)
    try:
        assert main(["doctor"]) == 2
    finally:
        env.chmod(0o600)
    err = capsys.readouterr().err
    assert err.startswith("cannot read settings:") and "NOSOLEAR_PORT" not in err


def test_doctor_non_utf8_env_file_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env = tmp_path / ".env"
    env.write_bytes(b"NOSOLEAR_PORT=\xff\xfe\n")
    _env_file(monkeypatch, env)
    assert main(["doctor"]) == 2
    assert "cannot read settings: .env is not valid UTF-8" in capsys.readouterr().err


def _spy_uvicorn(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake_run(app: str, **kwargs: object) -> None:
        calls.append({"app": app, **kwargs})

    monkeypatch.setattr("uvicorn.run", fake_run)
    return calls


def test_serve_runs_uvicorn_on_loopback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(data))
    calls = _spy_uvicorn(monkeypatch)
    assert main(["serve"]) == 0
    assert calls == [
        {
            "app": "nosolear.api.app:create_app",
            "factory": True,
            "host": "127.0.0.1",
            "port": 8000,
            "reload": False,
            "proxy_headers": False,
        }
    ]
    # the data dir pre-flight runs, but serve does no database work itself
    assert stat.S_IMODE(data.stat().st_mode) == 0o700
    assert list(data.iterdir()) == []


def test_serve_reload_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(tmp_path, monkeypatch)
    calls = _spy_uvicorn(monkeypatch)
    assert main(["serve", "--reload"]) == 0
    assert calls[0]["reload"] is True


def test_serve_refuses_a_non_loopback_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("NOSOLEAR_HOST", "0.0.0.0")

    def fail(*a: object, **k: object) -> None:
        raise AssertionError("uvicorn.run must not be called")

    monkeypatch.setattr("uvicorn.run", fail)
    assert main(["serve"]) == 2
    assert "NOSOLEAR_HOST" in capsys.readouterr().err


@pytest.mark.parametrize(
    "env,expected",
    [({"NOSOLEAR_PORT": "9001"}, {"port": 9001}), ({"NOSOLEAR_HOST": "::1"}, {"host": "::1"})],
)
def test_serve_passes_configured_host_and_port(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, str],
    expected: dict[str, object],
) -> None:
    _env(tmp_path, monkeypatch)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    calls = _spy_uvicorn(monkeypatch)
    assert main(["serve"]) == 0
    assert {k: calls[0][k] for k in expected} == expected


def test_serve_reports_a_bad_data_dir_and_does_not_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    blocker = tmp_path / "data"
    blocker.write_text("a file where the directory should be")
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(blocker))

    def fail(*a: object, **k: object) -> None:
        raise AssertionError("uvicorn.run must not be called")

    monkeypatch.setattr("uvicorn.run", fail)
    assert main(["serve"]) == 2
    assert "data directory problem:" in capsys.readouterr().err


def test_doctor_shows_the_recorded_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(tmp_path))
    assert main(["db", "upgrade"]) == 0
    settings = make_settings(data_dir=tmp_path)
    engine = create_engine_for(settings.database_url)
    try:
        caps = Caps.from_hours_chars_tokens(
            azure_audio_hours=settings.cap_azure_audio_hours,
            azure_tts_chars=settings.cap_azure_tts_chars,
            claude_tokens=settings.cap_claude_tokens,
        )
        ledger = SqliteUsageLedger(engine, caps=caps, clock=SystemClock())
        ledger.record(ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 3000), 2000)
        ledger.reserve(Provider.AZURE, Unit.AUDIO_SECONDS, 1800)  # still open
    finally:
        engine.dispose()
    capsys.readouterr()
    main(["doctor"])
    out = capsys.readouterr().out
    assert "Azure 0.5 of 4.5 h" in out
    assert "Claude 2k of 100k tokens today" in out


def test_doctor_without_a_database_keeps_the_caps_only_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(data))
    main(["doctor"])
    out = capsys.readouterr().out
    assert "usage tracking arrives with the ledger" in out
    assert not data.exists()
