import json
import stat
from collections.abc import Callable
from pathlib import Path

import pytest
from factories import NOW, count, make_settings, mk
from harness import Harness
from provider_fakes import FakeCoach
from sqlalchemy import text

from nosolear.adapters.system_clock import SystemClock
from nosolear.cli import main
from nosolear.cli_client import ApiClient
from nosolear.domain.budget import Caps, Provider, Unit
from nosolear.domain.coach import CoachExplanation
from nosolear.domain.errors import CapExceeded
from nosolear.domain.observations import Outcome
from nosolear.domain.speech import RawResult
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY, Detector
from nosolear.persistence.db import create_engine_for
from nosolear.persistence.ledger import SqliteUsageLedger
from nosolear.persistence.models import format_utc
from nosolear.persistence.repositories import ObservationRepository, ProfileRepository
from nosolear.settings import Settings


def _api(h: Harness) -> ApiClient:
    # TestClient is an httpx client at runtime; the stub is typed narrower than it is.
    return ApiClient(h.client)  # pyright: ignore[reportArgumentType]


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


def test_doctor_probe_without_a_region_exits_1_and_reveals_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The keys are planted without a region, so every Azure call raises before anything is sent.
    # `_env_file=None` keeps the repo's .env out of the test.
    monkeypatch.setattr("nosolear.cli.Settings", make_settings)
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NOSOLEAR_AZURE_SPEECH_KEY", AZURE_KEY)
    monkeypatch.setenv("NOSOLEAR_ANTHROPIC_API_KEY", CLAUDE_KEY)
    assert main(["doctor", "--probe"]) == 1
    captured = capsys.readouterr()
    assert "NOSOLEAR_AZURE_SPEECH_REGION" in captured.out
    assert "failed" in captured.out
    for key in (AZURE_KEY, CLAUDE_KEY):
        assert key not in captured.out and key not in captured.err


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
    assert "no usage recorded yet" in out
    assert not data.exists()


def test_plan_prints_one_line_per_skill(
    make_harness: Callable[..., Harness], capsys: pytest.CaptureFixture[str]
) -> None:
    h = make_harness()

    assert main(["plan"], client=_api(h)) == 0

    lines = capsys.readouterr().out.splitlines()
    focus_lines = lines[:3]
    assert [line.split(":")[0] for line in focus_lines] == ["sounds", "on_the_spot", "articulate"]
    assert all("(" in line and "%" in line for line in focus_lines)
    assert any(line.startswith("probe: ") for line in lines)
    assert any(line.startswith("prompt: ") for line in lines)
    assert "  speak 60s" in lines


def test_plan_json_flag_prints_the_body(
    make_harness: Callable[..., Harness], capsys: pytest.CaptureFixture[str]
) -> None:
    h = make_harness()

    assert main(["plan", "--json"], client=_api(h)) == 0

    printed = json.loads(capsys.readouterr().out)
    assert printed == h.client.get("/api/plan/today").json()


def test_plan_is_idempotent_across_two_runs(
    make_harness: Callable[..., Harness], capsys: pytest.CaptureFixture[str]
) -> None:
    h = make_harness()
    api = _api(h)

    assert main(["plan", "--json"], client=api) == 0
    first = capsys.readouterr().out
    assert main(["plan", "--json"], client=api) == 0
    second = capsys.readouterr().out

    assert second == first
    assert count(h.engine, "daily_plans") == 1


def test_daily_start_prints_attempt_and_prompt(
    make_harness: Callable[..., Harness], capsys: pytest.CaptureFixture[str]
) -> None:
    h = make_harness()

    assert main(["daily", "start"], client=_api(h)) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("session ")
    assert lines[1].startswith("attempt ")
    assert lines[2].startswith("prompt: ")
    assert lines[2] != "prompt: none"


def test_daily_start_twice_prints_same_ids(
    make_harness: Callable[..., Harness], capsys: pytest.CaptureFixture[str]
) -> None:
    h = make_harness()
    api = _api(h)

    assert main(["daily", "start"], client=api) == 0
    first = capsys.readouterr().out
    assert main(["daily", "start"], client=api) == 0
    second = capsys.readouterr().out

    assert second == first


def _expl(message: str) -> CoachExplanation:
    raw = RawResult(
        provider="anthropic",
        provider_version="oracle",
        adapter="claude_coach",
        adapter_version=1,
        payload={},
    )
    return CoachExplanation(message=message, model_text="rewrite", tokens_used=1, raw=raw)


class _CappedCoach(FakeCoach):
    def explain(self, *, error_key: str, quote: str, context: str) -> CoachExplanation:
        raise CapExceeded()


def _daily_with_misses(h: Harness, capsys: pytest.CaptureFixture[str]) -> str:
    """Starts today's daily session through the CLI, stores one miss per skill for its attempt,
    and returns the session id the CLI printed."""
    assert main(["daily", "start"], client=_api(h)) == 0
    lines = capsys.readouterr().out.splitlines()
    session_id = lines[0].removeprefix("session ")
    attempt_id = lines[1].removeprefix("attempt ")
    ObservationRepository(h.engine).add_many(
        [
            mk(
                "sound.sub.v.w",
                Outcome.MISS,
                NOW,
                detector=Detector.AZURE_PA,
                attempt_id=attempt_id,
                evidence={"word": "very", "start_ms": 100, "end_ms": 300},
            ),
            mk(
                "fluency.filler",
                Outcome.MISS,
                NOW,
                detector=Detector.ASR_METRICS,
                attempt_id=attempt_id,
                evidence={"text": "um I think"},
            ),
            mk(
                "clarity.vague",
                Outcome.MISS,
                NOW,
                detector=Detector.COACH,
                attempt_id=attempt_id,
                evidence={"quote": "a lot of things"},
            ),
        ]
    )
    # The recording was uploaded and analysed: feedback and completion need a finished job.
    with h.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO jobs (id, kind, attempt_id, status, progress, steps_json, tries, "
                "created_at, updated_at) VALUES ('job-cli', 'analyze', :attempt, 'done', 1.0, "
                "'[]', 1, :stamp, :stamp)"
            ),
            {"attempt": attempt_id, "stamp": format_utc(NOW)},
        )
    return session_id


def test_daily_feedback_prints_card_per_skill(
    make_harness: Callable[..., Harness], capsys: pytest.CaptureFixture[str]
) -> None:
    coach = FakeCoach(
        explain_results=[_expl("Put your teeth on your lip."), _expl("Pause."), _expl("Shorter.")]
    )
    h = make_harness(coach=coach)
    session_id = _daily_with_misses(h, capsys)

    assert main(["daily", "feedback", session_id, "--generate"], client=_api(h)) == 0

    lines = capsys.readouterr().out.splitlines()
    cards = [line for line in lines if not line.startswith("  ")]
    assert [line.split(":")[0] for line in cards] == ["sounds", "on_the_spot", "articulate"]
    assert cards[0] == "sounds: sound.sub.v.w"
    assert "  Put your teeth on your lip." in lines
    assert "  say: rewrite" in lines


def test_daily_feedback_shows_degraded_reason(
    make_harness: Callable[..., Harness], capsys: pytest.CaptureFixture[str]
) -> None:
    h = make_harness(coach=_CappedCoach())
    session_id = _daily_with_misses(h, capsys)

    assert main(["daily", "feedback", session_id, "--generate"], client=_api(h)) == 0

    out = capsys.readouterr().out
    assert "[template: cap_exceeded]" in out


def test_daily_feedback_without_generate_reports_not_generated(
    make_harness: Callable[..., Harness], capsys: pytest.CaptureFixture[str]
) -> None:
    h = make_harness(coach=FakeCoach(explain_results=[_expl("unused")]))
    session_id = _daily_with_misses(h, capsys)

    assert main(["daily", "feedback", session_id], client=_api(h)) == 2

    captured = capsys.readouterr()
    assert "No feedback has been generated" in captured.err
    assert captured.out == ""


def test_daily_complete_prints_confirmation(
    make_harness: Callable[..., Harness], capsys: pytest.CaptureFixture[str]
) -> None:
    h = make_harness(coach=FakeCoach(explain_results=[_expl("unused")]))
    session_id = _daily_with_misses(h, capsys)

    assert main(["daily", "complete", session_id], client=_api(h)) == 0

    out = capsys.readouterr().out
    assert out.startswith(f"session {session_id} completed at ")
    assert main(["daily", "complete", session_id], client=_api(h)) == 0
    assert "was already completed" in capsys.readouterr().out
