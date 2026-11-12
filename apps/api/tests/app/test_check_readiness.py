from pathlib import Path

import pytest
from factories import FakeEnvironment, make_settings
from hypothesis import given
from hypothesis import strategies as st

from nosolear.app.check_readiness import check_readiness
from nosolear.domain.readiness import (
    Component,
    ReadinessReport,
    ReadinessRow,
    ReadinessStatus,
    format_readiness,
)
from nosolear.settings import REPO_ROOT

KEY_A = "AzurePlantedKey-0123456789abcdef"
KEY_B = "AnthropicPlantedKey-0123456789abcdef"


def _by(report: ReadinessReport) -> dict[Component, ReadinessRow]:
    return {r.component: r for r in report.rows}


def test_fresh_clone_reports_missing_keys_and_writes_nothing(tmp_path: Path):
    data = tmp_path / "data"
    report = check_readiness(make_settings(data_dir=data), FakeEnvironment())
    rows = _by(report)
    assert rows[Component.AZURE_SPEECH].status is ReadinessStatus.MISSING
    assert rows[Component.ANTHROPIC].status is ReadinessStatus.MISSING
    assert rows[Component.DATA_DIR].status is ReadinessStatus.READY
    assert report.ready is False
    assert list(tmp_path.iterdir()) == []


def test_invalid_pack_is_one_missing_row_and_the_rest_still_compute(tmp_path: Path):
    report = check_readiness(make_settings(data_dir=tmp_path, pack="nosuchpack"), FakeEnvironment())
    assert len(report.rows) == 8
    row = _by(report)[Component.LANGUAGE_PACK]
    assert row.status is ReadinessStatus.MISSING and "nosuchpack" in row.reason


def test_valid_pack_row(tmp_path: Path):
    report = check_readiness(make_settings(data_dir=tmp_path, pack="nepali"), FakeEnvironment())
    row = _by(report)[Component.LANGUAGE_PACK]
    assert row.status is ReadinessStatus.READY and row.reason.startswith("nepali (")


@pytest.mark.parametrize(
    "keys",
    [
        {"azure_speech_key": KEY_A, "azure_speech_region": "westus2"},
        {"anthropic_api_key": KEY_B},
        {"azure_speech_key": KEY_A, "azure_speech_region": "westus2", "anthropic_api_key": KEY_B},
        {"azure_speech_key": KEY_A, "anthropic_api_key": KEY_B},
    ],
)
@pytest.mark.parametrize("transcriber", ["auto", "azure_stt"])
@pytest.mark.parametrize("pack", ["neutral", "nosuchpack"])
def test_planted_keys_never_appear(
    tmp_path: Path, keys: dict[str, str], transcriber: str, pack: str
):
    settings = make_settings(data_dir=tmp_path, transcriber=transcriber, pack=pack, **keys)
    report = check_readiness(settings, FakeEnvironment())
    text = repr(report) + format_readiness(report)
    assert KEY_A not in text and KEY_B not in text


key_text = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=16,
    max_size=40,
)


@given(azure=key_text, claude=key_text)
def test_generated_keys_never_appear(azure: str, claude: str):
    settings = make_settings(
        data_dir=Path("/nonexistent-nosolear"),
        azure_speech_key=azure,
        azure_speech_region="westus2",
        anthropic_api_key=claude,
    )
    report = check_readiness(settings, FakeEnvironment())
    text = repr(report) + format_readiness(report)
    # a key that is a substring of an ordinary word ("neutral") would be a false alarm; 16+
    # characters of mixed alphabet cannot be, except by being copied from the report itself
    assert azure not in text and claude not in text


def test_configured_settings_are_ready(tmp_path: Path):
    settings = make_settings(
        data_dir=tmp_path,
        azure_speech_key=KEY_A,
        azure_speech_region="westus2",
        anthropic_api_key=KEY_B,
    )
    report = check_readiness(settings, FakeEnvironment())
    assert report.ready is True


def test_probe_results_flow_into_rows(tmp_path: Path):
    env = FakeEnvironment(
        modules={"torch", "transformers"},
        executables={"espeak-ng"},
        platform=("darwin", "arm64"),
    )
    rows = _by(check_readiness(make_settings(data_dir=tmp_path), env))
    assert rows[Component.PHONE_PROBE].status is ReadinessStatus.READY


def test_field_mapping_uses_the_settings_values(tmp_path: Path):
    settings = make_settings(
        data_dir=tmp_path,
        cap_azure_audio_hours=1.5,
        cap_azure_tts_chars=2000,
        cap_claude_tokens=3000,
        azure_locale="en-GB",
        coach_model="claude-test-9",
        azure_speech_key=KEY_A,
        azure_speech_region="westus2",
        anthropic_api_key=KEY_B,
    )
    env = FakeEnvironment(modules={"mlx_whisper"}, platform=("darwin", "arm64"))
    rows = _by(check_readiness(settings, env))
    usage = rows[Component.USAGE].reason
    assert "Azure 1.5 h" in usage and "TTS 2k chars" in usage and "Claude 3k tokens" in usage
    assert "en-GB" in rows[Component.AZURE_SPEECH].reason
    assert "claude-test-9" in rows[Component.ANTHROPIC].reason
    assert "auto -> mlx_whisper" in rows[Component.TRANSCRIBER].reason


def test_explicit_transcriber_with_module_present(tmp_path: Path):
    settings = make_settings(data_dir=tmp_path, transcriber="faster_whisper")
    env = FakeEnvironment(modules={"faster_whisper"})
    assert (
        _by(check_readiness(settings, env))[Component.TRANSCRIBER].status is ReadinessStatus.READY
    )


def test_permissions_come_from_path_mode(tmp_path: Path):
    settings = make_settings(data_dir=tmp_path)
    env = FakeEnvironment(modes={tmp_path: 0o755})
    row = _by(check_readiness(settings, env))[Component.DATA_DIR]
    assert row.status is ReadinessStatus.DEGRADED and row.fix and "chmod 700" in row.fix


def test_env_file_mode_is_read_from_the_repo_root(tmp_path: Path):
    env = FakeEnvironment(modes={REPO_ROOT / ".env": 0o644})
    row = _by(check_readiness(make_settings(data_dir=tmp_path), env))[Component.DATA_DIR]
    assert row.status is ReadinessStatus.DEGRADED and row.fix and "chmod 600 .env" in row.fix


def test_missing_data_dir_with_loose_env_is_degraded(tmp_path: Path):
    env = FakeEnvironment(modes={REPO_ROOT / ".env": 0o644})
    row = _by(check_readiness(make_settings(data_dir=tmp_path / "data"), env))[Component.DATA_DIR]
    assert row.status is ReadinessStatus.DEGRADED and row.fix == "chmod 600 .env"


def test_an_unreadable_data_dir_is_missing_not_ready(tmp_path: Path):
    data = tmp_path / "data"
    env = FakeEnvironment(raises={data: NotADirectoryError(20, "Not a directory")})
    row = _by(check_readiness(make_settings(data_dir=data), env))[Component.DATA_DIR]
    assert row.status is ReadinessStatus.MISSING
    assert f"cannot inspect {data}: Not a directory" in row.reason


def test_an_unreadable_env_file_is_reported(tmp_path: Path):
    env = FakeEnvironment(raises={REPO_ROOT / ".env": PermissionError(13, "Permission denied")})
    report = check_readiness(make_settings(data_dir=tmp_path), env)
    row = _by(report)[Component.DATA_DIR]
    assert row.status is ReadinessStatus.MISSING and "Permission denied" in row.reason
