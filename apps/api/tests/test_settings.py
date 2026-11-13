import logging
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from factories import make_settings
from pydantic import BaseModel, ValidationError, model_validator

from nosolear import settings as settings_module
from nosolear.settings import (
    CONTENT_DIR,
    LOOPBACK_NAMES,
    MIN_KEY_LENGTH,
    REPO_ROOT,
    TRANSCRIBERS,
    Settings,
    settings_error_summary,
)

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


def test_tilde_expands_to_the_home_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", "~/x")
    assert _settings().data_dir == tmp_path / "x"
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", "~")
    assert _settings().data_dir == tmp_path


def test_tilde_path_passed_directly_expands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("NOSOLEAR_DATA_DIR", raising=False)
    assert make_settings(data_dir=Path("~/x")).data_dir == tmp_path / "x"


def test_empty_value_in_env_file_counts_as_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("NOSOLEAR_DATA_DIR", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("NOSOLEAR_DATA_DIR=\n")
    assert Settings(_env_file=env_file).data_dir == DEFAULT  # pyright: ignore[reportCallIssue]


def _names(exc: ValidationError) -> str:
    return settings_error_summary(exc)


def test_plain_settings_never_sees_the_real_env_file() -> None:
    assert Settings.model_config.get("env_file") is None
    s = Settings()
    assert s.anthropic_api_key is None
    assert s.azure_speech_key is None
    assert s.azure_speech_region is None


def test_constants() -> None:
    assert sorted(LOOPBACK_NAMES) == ["127.0.0.1", "::1", "localhost"]
    assert TRANSCRIBERS == ("auto", "mlx_whisper", "faster_whisper", "azure_stt", "crisper_whisper")
    assert CONTENT_DIR == REPO_ROOT / "content"
    assert MIN_KEY_LENGTH == 16
    assert make_settings().packs_dir == CONTENT_DIR / "packs"


def test_defaults() -> None:
    s = make_settings()
    assert s.host == "127.0.0.1"
    assert s.port == 8000
    assert s.app_origins == ("http://localhost:5173", "http://127.0.0.1:5173")
    assert s.pack == "neutral"
    assert s.transcriber == "auto"
    assert (s.cap_azure_audio_hours, s.cap_azure_tts_chars, s.cap_claude_tokens) == (
        4.5,
        450000,
        100000,
    )
    assert s.coach_model == "claude-opus-5-5"
    assert s.job_workers == 1
    assert s.faster_whisper_model == "small.en"
    assert s.mlx_whisper_model == "whisper-large-v3-turbo"
    assert s.azure_locale == "en-US"
    assert s.tts_voice == "en-US-JennyNeural"
    assert s.azure_speech_key is None and s.anthropic_api_key is None
    assert s.azure_speech_region is None


@pytest.mark.parametrize("field", ["azure_speech_key", "anthropic_api_key"])
def test_short_key_rejected(field: str) -> None:
    short = "s" * 15
    with pytest.raises(ValidationError) as e:
        make_settings(**{field: short})
    summary = _names(e.value)
    assert f"NOSOLEAR_{field.upper()}" in summary
    assert "too short to be a real key" in summary
    assert short not in str(e.value) and short not in summary
    assert "15" not in summary
    ok = make_settings(**{field: "s" * 16})
    stored = getattr(ok, field)
    assert stored is not None and stored.get_secret_value() == "s" * 16


@pytest.mark.parametrize("workers", [0, -1])
def test_job_workers_must_be_positive(workers: int) -> None:
    with pytest.raises(ValidationError) as e:
        make_settings(job_workers=workers)
    assert "NOSOLEAR_JOB_WORKERS" in _names(e.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cap_azure_audio_hours", 0),
        ("cap_azure_audio_hours", -1.0),
        ("cap_azure_tts_chars", 0),
        ("cap_claude_tokens", -5),
        ("port", 0),
        ("port", 65536),
    ],
)
def test_numeric_bounds(field: str, value: float) -> None:
    with pytest.raises(ValidationError) as e:
        make_settings(**{field: value})
    assert f"NOSOLEAR_{field.upper()}" in _names(e.value)


@pytest.mark.parametrize("value", ["inf", "-inf", "nan"])
def test_float_caps_reject_inf_and_nan_via_kwarg(value: str) -> None:
    with pytest.raises(ValidationError) as e:
        make_settings(cap_azure_audio_hours=float(value))
    assert "NOSOLEAR_CAP_AZURE_AUDIO_HOURS" in _names(e.value)


@pytest.mark.parametrize("value", ["inf", "nan", "Infinity"])
def test_float_caps_reject_inf_and_nan_via_env(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOSOLEAR_CAP_AZURE_AUDIO_HOURS", value)
    with pytest.raises(ValidationError) as e:
        make_settings()
    assert "NOSOLEAR_CAP_AZURE_AUDIO_HOURS" in _names(e.value)


@pytest.mark.parametrize("field", ["azure_speech_key", "anthropic_api_key"])
@pytest.mark.parametrize(
    "key", [" " + "k" * 20, "k" * 20 + " ", "k" * 20 + "\n", "k" * 10 + " " + "k" * 10, " " * 16]
)
def test_key_with_whitespace_rejected(field: str, key: str) -> None:
    with pytest.raises(ValidationError) as e:
        make_settings(**{field: key})
    summary = _names(e.value)
    assert f"NOSOLEAR_{field.upper()}" in summary
    assert "whitespace" in summary
    assert "k" * 10 not in summary and "k" * 10 not in str(e.value)
    assert "20" not in summary and "21" not in summary


@pytest.mark.parametrize("transcriber", TRANSCRIBERS)
def test_every_transcriber_accepted(transcriber: str) -> None:
    assert make_settings(transcriber=transcriber).transcriber == transcriber


def test_port_accepts_range_ends() -> None:
    assert make_settings(port=1).port == 1
    assert make_settings(port=65535).port == 65535


@pytest.mark.parametrize("tz", ["Asia/Kathmandu", "UTC", "America/New_York"])
def test_timezone_accepts_iana_names(tz: str) -> None:
    assert make_settings(timezone=tz).tzinfo == ZoneInfo(tz)


@pytest.mark.parametrize("tz", ["Mars/Base", "../etc/passwd", "", "+05:45"])
def test_timezone_rejects_unknown_names(tz: str) -> None:
    with pytest.raises(ValidationError) as e:
        make_settings(timezone=tz)
    assert "NOSOLEAR_TIMEZONE" in _names(e.value)
    if tz:
        assert tz not in _names(e.value)


def test_timezone_default_is_the_machine_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_module, "_local_zone_name", lambda: "Asia/Kathmandu")
    assert make_settings().timezone == "Asia/Kathmandu"


def test_machine_zone_lookup_from_tz_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "Europe/Paris")
    assert settings_module._local_zone_name() == "Europe/Paris"


def test_machine_zone_lookup_failure_falls_back_to_utc(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(settings_module, "_LOCALTIME", tmp_path / "missing")
    assert settings_module._local_zone_name() == "UTC"
    link = tmp_path / "localtime"
    link.symlink_to(tmp_path)  # a target with no zoneinfo/ component
    monkeypatch.setattr(settings_module, "_LOCALTIME", link)
    assert settings_module._local_zone_name() == "UTC"


def test_invalid_tz_variable_falls_through_to_localtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    target = tmp_path / "zoneinfo" / "Asia" / "Kathmandu"
    target.parent.mkdir(parents=True)
    target.write_text("")
    link = tmp_path / "localtime"
    link.symlink_to(target)
    monkeypatch.setattr(settings_module, "_LOCALTIME", link)
    monkeypatch.setenv("TZ", "Not/AZone")
    with caplog.at_level(logging.WARNING):
        assert settings_module._local_zone_name() == "Asia/Kathmandu"
    assert not caplog.records


def test_tz_variable_with_leading_colon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", ":Europe/Paris")
    assert settings_module._local_zone_name() == "Europe/Paris"


@pytest.mark.parametrize("tz", [None, "Secret/Bad_Zone_42"])
def test_utc_fallback_logs_one_warning_without_the_tz_value(
    tz: str | None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    if tz is None:
        monkeypatch.delenv("TZ", raising=False)
    else:
        monkeypatch.setenv("TZ", tz)
    monkeypatch.setattr(settings_module, "_LOCALTIME", tmp_path / "missing")
    with caplog.at_level(logging.WARNING, logger="nosolear.settings"):
        assert settings_module._local_zone_name() == "UTC"
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.WARNING
    assert "NOSOLEAR_TIMEZONE" in record.getMessage()
    assert "Secret" not in record.getMessage()


def test_missing_zone_database_says_install_tzdata(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_db(name: str) -> ZoneInfo:
        raise settings_module.ZoneInfoNotFoundError(name)

    monkeypatch.setattr(settings_module, "ZoneInfo", _no_db)
    with pytest.raises(ValidationError) as e:
        make_settings(timezone="UTC")
    summary = _names(e.value)
    assert "tzdata" in summary and "no timezone database" in summary


def test_machine_zone_lookup_from_localtime_symlink(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TZ", raising=False)
    target = tmp_path / "var" / "zoneinfo" / "Asia" / "Kathmandu"
    target.parent.mkdir(parents=True)
    target.write_text("")
    link = tmp_path / "localtime"
    link.symlink_to(target)
    monkeypatch.setattr(settings_module, "_LOCALTIME", link)
    assert settings_module._local_zone_name() == "Asia/Kathmandu"


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "example.com", "::", ""])
def test_non_loopback_host_rejected(host: str) -> None:
    with pytest.raises(ValidationError) as e:
        make_settings(host=host)
    assert "NOSOLEAR_HOST" in _names(e.value)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "127.0.0.2"])
def test_loopback_host_accepted(host: str) -> None:
    assert make_settings(host=host).host == host


@pytest.mark.parametrize(
    "origin",
    [
        "https://example.com",
        "http://192.168.1.5:5173",
        "http://100.64.0.1:5173",
        "http://localhost:5173/path",
        "ftp://localhost",
        "http://user@localhost",
        "null",
        "*",
    ],
)
def test_non_loopback_or_malformed_origin_rejected(origin: str) -> None:
    with pytest.raises(ValidationError) as e:
        make_settings(app_origins=(origin,))
    summary = _names(e.value)
    assert "NOSOLEAR_APP_ORIGINS" in summary
    assert "token mode is not available until Phase 6" in summary
    assert origin not in summary and origin not in str(e.value)


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost.evil.com",
        "http://127.0.0.1.evil.com",
        "http://localhost@evil.com",
        "http://0.0.0.0:5173",
        "http://[::ffff:127.0.0.1]",
        "http://localhost:abc",
        "http://localhost:99999",
        "http://localhost:0",
        "http://[::1",
    ],
)
def test_host_confusion_and_unparseable_origins_rejected(origin: str) -> None:
    with pytest.raises(ValidationError) as e:
        make_settings(app_origins=(origin,))
    assert "NOSOLEAR_APP_ORIGINS" in _names(e.value)
    assert origin not in _names(e.value) and origin not in str(e.value)


def test_mixed_origin_list_rejected_via_kwarg() -> None:
    with pytest.raises(ValidationError) as e:
        make_settings(app_origins=("http://localhost:3000", "https://example.com"))
    assert "NOSOLEAR_APP_ORIGINS" in _names(e.value)
    assert "example.com" not in _names(e.value)


def test_mixed_origin_list_rejected_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOSOLEAR_APP_ORIGINS", "http://localhost:3000, https://example.com")
    with pytest.raises(ValidationError) as e:
        make_settings()
    assert "NOSOLEAR_APP_ORIGINS" in _names(e.value)
    assert "example.com" not in _names(e.value)


@pytest.mark.parametrize("raw", [",", " , ,", "  "])
def test_empty_origin_list_rejected(raw: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOSOLEAR_APP_ORIGINS", raw)
    with pytest.raises(ValidationError) as e:
        make_settings()
    assert "at least one origin is required" in _names(e.value)
    with pytest.raises(ValidationError):
        make_settings(app_origins=())


def test_default_ports_are_dropped_and_others_kept() -> None:
    s = make_settings(
        app_origins=(
            "http://localhost:80",
            "https://localhost:443",
            "https://localhost:80",
            "http://127.0.0.1:443",
        )
    )
    assert s.app_origins == (
        "http://localhost",
        "https://localhost",
        "https://localhost:80",
        "http://127.0.0.1:443",
    )


def test_error_summary_survives_an_empty_loc() -> None:
    class M(BaseModel):
        @model_validator(mode="after")
        def _boom(self):
            raise ValueError("whole-model failure")

    with pytest.raises(ValidationError) as e:
        M()
    assert "whole-model failure" in settings_error_summary(e.value)


def test_origins_parse_comma_list_and_normalise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "NOSOLEAR_APP_ORIGINS", "http://localhost:3000/, http://[::1]:3000,http://localhost:3000"
    )
    assert make_settings().app_origins == ("http://localhost:3000", "http://[::1]:3000")


@pytest.mark.parametrize("region", ["westus2", "eastus"])
def test_region_accepted(region: str) -> None:
    assert make_settings(azure_speech_region=region).azure_speech_region == region


@pytest.mark.parametrize("region", ["West US", "west-us", "a.b", "x/../y", "evil.com#", "WESTUS"])
def test_region_rejected(region: str) -> None:
    with pytest.raises(ValidationError) as e:
        make_settings(azure_speech_region=region)
    assert "NOSOLEAR_AZURE_SPEECH_REGION" in _names(e.value)
    assert region not in _names(e.value)


@pytest.mark.parametrize("pack", ["../x", "NEPALI", "a/b", "a b", "x.y"])
def test_pack_rejected(pack: str) -> None:
    with pytest.raises(ValidationError) as e:
        make_settings(pack=pack)
    assert "NOSOLEAR_PACK" in _names(e.value)


def test_pack_accepted() -> None:
    assert make_settings(pack="nepali_2").pack == "nepali_2"


@pytest.mark.parametrize(
    ("field", "good", "bad"),
    [
        ("azure_locale", ["en-US", "fil-PH"], ["en_US", "EN-us", "english", "en-US "]),
        (
            "tts_voice",
            ["en-US-JennyNeural", "en-GB-RyanNeural"],
            ["en-US-Jenny", "JennyNeural", "en-US-Jenny Neural", "en-US-Jenny/../Neural"],
        ),
        ("coach_model", ["claude-opus-5-5", "m.v_1"], ["a b", "a/b", "", "x;y"]),
        ("faster_whisper_model", ["small.en", "large-v3"], ["a b", "../x", "", "a/b"]),
        ("mlx_whisper_model", ["whisper-large-v3-turbo"], ["a b", "org/model", "", "x;y"]),
    ],
)
def test_voice_model_locale_patterns(field: str, good: list[str], bad: list[str]) -> None:
    for value in good:
        assert make_settings(**{field: value}).model_dump()[field] == value
    for value in bad:
        with pytest.raises(ValidationError) as e:
            make_settings(**{field: value})
        assert f"NOSOLEAR_{field.upper()}" in _names(e.value)


def test_transcriber_rejects_unknown() -> None:
    with pytest.raises(ValidationError) as e:
        make_settings(transcriber="whisperx")
    assert "NOSOLEAR_TRANSCRIBER" in _names(e.value)
    assert "whisperx" not in _names(e.value)


def test_secret_fields_mask_in_repr_and_dump() -> None:
    s = make_settings(azure_speech_key="k" * 32, anthropic_api_key="a" * 40)
    assert "k" * 32 not in repr(s) and "k" * 32 not in str(s.model_dump())
    assert "a" * 40 not in s.model_dump_json()
    assert "a" * 40 not in repr(s) and "k" * 32 not in str(s)
    assert "k" * 32 not in s.model_dump_json()


def test_secret_values_lists_only_configured_keys() -> None:
    assert make_settings().secret_values() == ()
    only = make_settings(anthropic_api_key="a" * 20)
    assert only.secret_values() == ("a" * 20,)
    both = make_settings(azure_speech_key="k" * 20, anthropic_api_key="a" * 20)
    assert both.secret_values() == ("k" * 20, "a" * 20)


def test_validation_error_hides_input() -> None:
    secret = "SECRET_pasted_into_the_wrong_field_123"
    with pytest.raises(ValidationError) as e:
        make_settings(azure_speech_region=secret)
    assert secret not in str(e.value) and secret not in settings_error_summary(e.value)
    assert "NOSOLEAR_AZURE_SPEECH_REGION" in settings_error_summary(e.value)


def test_error_summary_has_one_line_per_error() -> None:
    with pytest.raises(ValidationError) as e:
        make_settings(host="0.0.0.0", pack="../x")
    lines = settings_error_summary(e.value).splitlines()
    assert len(lines) == 2
    assert all(line.startswith("NOSOLEAR_") and ": " in line for line in lines)
