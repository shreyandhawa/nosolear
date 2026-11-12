from pathlib import Path

from factories import FakeEnvironment, make_settings

from nosolear.app.check_readiness import check_readiness
from nosolear.domain.readiness import Component, ReadinessStatus

KEY_A = "AzurePlantedKey-0123456789abcdef"
KEY_B = "AnthropicPlantedKey-0123456789abcdef"


def _by(report):  # type: ignore[no-untyped-def]
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


def test_planted_keys_never_appear(tmp_path: Path):
    settings = make_settings(
        data_dir=tmp_path,
        azure_speech_key=KEY_A,
        azure_speech_region="westus2",
        anthropic_api_key=KEY_B,
    )
    report = check_readiness(settings, FakeEnvironment())
    text = repr(report)
    assert KEY_A not in text and KEY_B not in text
    rows = _by(report)
    assert rows[Component.AZURE_SPEECH].status is ReadinessStatus.READY
    assert rows[Component.ANTHROPIC].status is ReadinessStatus.READY
    assert report.ready is True


def test_probe_results_flow_into_rows(tmp_path: Path):
    env = FakeEnvironment(
        modules={"torch", "transformers"},
        executables={"espeak-ng"},
        platform=("darwin", "arm64"),
    )
    rows = _by(check_readiness(make_settings(data_dir=tmp_path), env))
    assert rows[Component.PHONE_PROBE].status is ReadinessStatus.READY


def test_permissions_come_from_path_mode(tmp_path: Path):
    settings = make_settings(data_dir=tmp_path)
    env = FakeEnvironment(modes={tmp_path: 0o755})
    row = _by(check_readiness(settings, env))[Component.DATA_DIR]
    assert row.status is ReadinessStatus.DEGRADED and row.fix and "chmod 700" in row.fix
