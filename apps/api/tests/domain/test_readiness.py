from dataclasses import replace
from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nosolear.domain.readiness import (
    COMPONENT_LABELS,
    CapabilityFindings,
    Caps,
    Component,
    PackStatus,
    ReadinessInputs,
    ReadinessReport,
    ReadinessStatus,
    UsageSnapshot,
    build_readiness,
    format_readiness,
)

S = ReadinessStatus
C = Component


def make_inputs(**overrides: object) -> ReadinessInputs:
    base = ReadinessInputs(
        azure_key_set=True,
        azure_region="westus2",
        azure_locale="en-US",
        anthropic_key_set=True,
        coach_model="claude-opus-5-5",
        transcriber="auto",
        modules=frozenset({"faster_whisper"}),
        espeak_installed=False,
        system="linux",
        machine="x86_64",
        pack=PackStatus(pack_id="neutral", name="Neutral", hypotheses=0, problems=()),
        data_dir="/data",
        data_dir_mode=0o700,
        env_file_mode=0o600,
        caps=Caps(azure_audio_hours=4.5, tts_chars=450000, claude_tokens=100000),
        usage=None,
        capabilities=None,
    )
    return replace(base, **overrides)  # pyright: ignore[reportArgumentType]


def row(inputs: ReadinessInputs, component: Component):
    return next(r for r in build_readiness(inputs).rows if r.component is component)


def test_azure_ready():
    r = row(make_inputs(), C.AZURE_SPEECH)
    assert r.status is S.READY and "westus2" in r.reason and "en-US" in r.reason


@pytest.mark.parametrize("kw", [{"azure_key_set": False}, {"azure_region": None}])
def test_azure_missing_names_variables(kw: dict[str, object]):
    r = row(make_inputs(**kw), C.AZURE_SPEECH)
    assert r.status is S.MISSING
    assert r.fix is not None
    assert "NOSOLEAR_AZURE_SPEECH_KEY" in r.fix and "NOSOLEAR_AZURE_SPEECH_REGION" in r.fix
    assert ".env" in r.fix


def test_capabilities_not_probed_when_azure_missing():
    r = row(make_inputs(azure_key_set=False), C.AZURE_CAPABILITIES)
    assert r.status is S.NOT_PROBED and r.fix and "Azure" in r.fix


def test_capabilities_not_probed_without_findings():
    r = row(make_inputs(), C.AZURE_CAPABILITIES)
    assert r.status is S.NOT_PROBED
    assert r.fix == "run `nosolear doctor --probe` (available from Phase 0d)"


def test_capabilities_ready_and_degraded():
    ok = CapabilityFindings(nbest=True, prosody=True, probed_on=date(2026, 11, 12))
    r = row(make_inputs(capabilities=ok), C.AZURE_CAPABILITIES)
    assert r.status is S.READY
    assert r.reason == "n-best yes, prosody yes (probed 2026-11-12)"
    bad = replace(ok, prosody=False)
    r = row(make_inputs(capabilities=bad), C.AZURE_CAPABILITIES)
    assert r.status is S.DEGRADED and "prosody no" in r.reason


def test_anthropic_ready_and_missing():
    r = row(make_inputs(), C.ANTHROPIC)
    assert r.status is S.READY and "claude-opus-5-5" in r.reason
    r = row(make_inputs(anthropic_key_set=False), C.ANTHROPIC)
    assert r.status is S.MISSING and r.fix and "NOSOLEAR_ANTHROPIC_API_KEY" in r.fix


def test_transcriber_azure_stt_needs_azure():
    assert row(make_inputs(transcriber="azure_stt"), C.TRANSCRIBER).status is S.READY
    r = row(make_inputs(transcriber="azure_stt", azure_key_set=False), C.TRANSCRIBER)
    assert r.status is S.MISSING


@pytest.mark.parametrize(
    ("transcriber", "modules", "fix"),
    [
        ("mlx_whisper", frozenset[str](), "uv sync --extra apple"),
        ("faster_whisper", frozenset[str](), "uv sync --extra local"),
        ("crisper_whisper", frozenset({"torch"}), "uv sync --extra local"),
    ],
)
def test_transcriber_missing_library_is_not_installed(
    transcriber: str, modules: frozenset[str], fix: str
):
    r = row(make_inputs(transcriber=transcriber, modules=modules), C.TRANSCRIBER)
    assert r.status is S.NOT_INSTALLED and r.fix and fix in r.fix


def test_transcriber_explicit_ready_and_crisper_licence():
    r = row(
        make_inputs(transcriber="crisper_whisper", modules=frozenset({"torch", "transformers"})),
        C.TRANSCRIBER,
    )
    assert r.status is S.READY and "non-commercial licence, opt-in" in r.reason
    r = row(
        make_inputs(transcriber="mlx_whisper", modules=frozenset({"mlx_whisper"})), C.TRANSCRIBER
    )
    assert r.status is S.READY


@pytest.mark.parametrize(
    ("system", "machine", "modules", "azure", "expected"),
    [
        ("darwin", "arm64", {"mlx_whisper", "faster_whisper"}, True, "mlx_whisper"),
        ("darwin", "arm64", {"faster_whisper"}, True, "faster_whisper"),
        ("darwin", "arm64", set[str](), True, "azure_stt"),
        ("darwin", "x86_64", {"mlx_whisper", "faster_whisper"}, True, "azure_stt"),
        ("darwin", "x86_64", {"mlx_whisper"}, True, "azure_stt"),
        ("linux", "x86_64", {"mlx_whisper", "faster_whisper"}, True, "faster_whisper"),
        ("linux", "x86_64", {"mlx_whisper"}, True, "azure_stt"),
        ("win32", "AMD64", {"faster_whisper"}, True, "azure_stt"),
        ("linux", "x86_64", set[str](), False, None),
    ],
)
def test_auto_transcriber_order(
    system: str, machine: str, modules: set[str], azure: bool, expected: str | None
):
    r = row(
        make_inputs(
            transcriber="auto",
            system=system,
            machine=machine,
            modules=frozenset(modules),
            azure_key_set=azure,
        ),
        C.TRANSCRIBER,
    )
    if expected is None:
        assert r.status is S.MISSING
    else:
        assert r.status is S.READY
        assert r.reason == f"auto -> {expected} (speed not yet checked)"


def test_phone_probe():
    r = row(
        make_inputs(modules=frozenset({"torch", "transformers"}), espeak_installed=True),
        C.PHONE_PROBE,
    )
    assert r.status is S.READY
    for kw in (
        {"modules": frozenset({"torch"}), "espeak_installed": True},
        {"modules": frozenset({"torch", "transformers"}), "espeak_installed": False},
        {},
    ):
        r = row(make_inputs(**kw), C.PHONE_PROBE)
        assert r.status is S.NOT_INSTALLED
        assert r.fix == "run `uv sync --extra local`, then install espeak-ng"


def test_language_pack():
    r = row(make_inputs(pack=PackStatus("nepali", "Nepali", 12, ())), C.LANGUAGE_PACK)
    assert r.status is S.READY and r.reason == "nepali (Nepali), 12 hypotheses"
    r = row(
        make_inputs(pack=PackStatus("bad", None, 0, ("x is wrong", "y is wrong"))), C.LANGUAGE_PACK
    )
    assert r.status is S.MISSING
    assert r.reason.startswith("pack 'bad' is invalid: ") and "x is wrong" in r.reason
    assert r.fix and "content/packs/bad/pack.toml" in r.fix and "NOSOLEAR_PACK" in r.fix


def test_data_dir_rows():
    assert row(make_inputs(), C.DATA_DIR).status is S.READY
    r = row(make_inputs(data_dir_mode=None), C.DATA_DIR)
    assert r.status is S.READY and "will be created on first start" in r.reason
    r = row(make_inputs(data_dir_mode=0o755), C.DATA_DIR)
    assert r.status is S.DEGRADED and r.fix and "chmod 700 /data" in r.fix
    r = row(make_inputs(env_file_mode=0o644), C.DATA_DIR)
    assert r.status is S.DEGRADED and r.fix and "chmod 600 .env" in r.fix
    r = row(make_inputs(data_dir_mode=0o770, env_file_mode=0o604), C.DATA_DIR)
    assert r.status is S.DEGRADED and r.fix and "chmod 700" in r.fix and "chmod 600 .env" in r.fix
    assert row(make_inputs(env_file_mode=None), C.DATA_DIR).status is S.READY


def test_usage_row():
    r = row(make_inputs(), C.USAGE)
    assert r.status is S.READY
    assert r.reason == (
        "caps: Azure 4.5 h and TTS 450k chars a month, Claude 100k tokens a day (UTC);"
        " no usage recorded yet"
    )
    usage = UsageSnapshot(azure_audio_hours=0.4, tts_chars=12000, claude_tokens=3000)
    r = row(make_inputs(usage=usage), C.USAGE)
    assert r.status is S.READY
    assert r.reason == (
        "Azure 0.4 of 4.5 h and TTS 12k of 450k chars this month, Claude 3k of 100k tokens today"
    )


def test_report_has_eight_rows_in_enum_order():
    report = build_readiness(make_inputs())
    assert [r.component for r in report.rows] == list(Component)
    assert len(report.rows) == 8
    assert set(COMPONENT_LABELS) == set(Component)


def test_ready_false_only_when_a_row_is_missing():
    assert build_readiness(make_inputs()).ready is True
    degraded = make_inputs(data_dir_mode=0o755)
    assert build_readiness(degraded).ready is True
    assert build_readiness(make_inputs(anthropic_key_set=False)).ready is False


def test_format_readiness_columns():
    report = build_readiness(make_inputs(anthropic_key_set=False))
    lines = format_readiness(report).splitlines()
    anthropic = next(i for i, line in enumerate(lines) if line.startswith("Anthropic"))
    assert "missing" in lines[anthropic]
    assert lines[anthropic + 1].startswith("    fix: ")
    assert "NOSOLEAR_ANTHROPIC_API_KEY" in lines[anthropic + 1]
    ready = next(line for line in lines if line.startswith("Azure Speech"))
    assert "ready" in ready and "westus2" in ready
    # one non-indented line per row
    assert sum(1 for line in lines if not line.startswith(" ")) == 8


def test_status_text_uses_underscores_as_spaces():
    text = format_readiness(build_readiness(make_inputs()))
    assert "not probed" in text and "not_probed" not in text


def test_report_is_a_plain_value():
    assert isinstance(build_readiness(make_inputs()), ReadinessReport)


safe = st.text(
    alphabet=st.characters(codec="ascii", exclude_categories=["Cc", "Cs"]), min_size=1, max_size=30
)


@given(region=safe, model=safe, locale=safe, pack_name=safe)
def test_no_row_text_contains_a_planted_secret(
    region: str, model: str, locale: str, pack_name: str
):
    secret = "PLANTED-SECRET-KEY-0123456789"
    inputs = make_inputs(
        azure_region=region,
        coach_model=model,
        azure_locale=locale,
        pack=PackStatus("neutral", pack_name, 0, ()),
    )
    text = format_readiness(build_readiness(inputs)) + repr(build_readiness(inputs))
    assert secret not in text
    # the only caller-supplied text that can appear is the exact fields given
    for part in (region, model, locale, pack_name):
        assert part in text


def test_azure_stt_missing_names_both_variables_even_when_only_region_is_missing():
    for kw in ({"azure_key_set": False}, {"azure_region": None}):
        r = row(make_inputs(transcriber="azure_stt", **kw), C.TRANSCRIBER)
        assert r.status is S.MISSING
        assert r.fix and "NOSOLEAR_AZURE_SPEECH_KEY" in r.fix
        assert "NOSOLEAR_AZURE_SPEECH_REGION" in r.fix


def test_azure_reason_says_which_part_is_missing():
    assert "key" in row(make_inputs(azure_key_set=False), C.AZURE_SPEECH).reason
    assert "region" in row(make_inputs(azure_region=None), C.AZURE_SPEECH).reason
    assert "region" not in row(make_inputs(azure_key_set=False), C.AZURE_SPEECH).reason


@pytest.mark.parametrize(
    ("system", "machine", "present", "absent"),
    [
        (
            "darwin",
            "arm64",
            [
                "uv sync --extra apple",
                "uv sync --extra local",
                "NOSOLEAR_AZURE_SPEECH_KEY",
                "NOSOLEAR_AZURE_SPEECH_REGION",
            ],
            [],
        ),
        (
            "linux",
            "x86_64",
            ["uv sync --extra local", "NOSOLEAR_AZURE_SPEECH_KEY", "NOSOLEAR_AZURE_SPEECH_REGION"],
            ["--extra apple"],
        ),
        (
            "win32",
            "AMD64",
            ["NOSOLEAR_AZURE_SPEECH_KEY", "NOSOLEAR_AZURE_SPEECH_REGION"],
            ["--extra"],
        ),
        ("darwin", "x86_64", ["NOSOLEAR_AZURE_SPEECH_KEY"], ["--extra"]),
    ],
)
def test_auto_missing_fix_only_suggests_what_helps_here(
    system: str, machine: str, present: list[str], absent: list[str]
):
    r = row(
        make_inputs(
            transcriber="auto",
            system=system,
            machine=machine,
            modules=frozenset(),
            azure_key_set=False,
        ),
        C.TRANSCRIBER,
    )
    assert r.status is S.MISSING and r.fix
    assert all(p in r.fix for p in present)
    assert not any(a in r.fix for a in absent)


def test_auto_never_picks_crisper_whisper():
    r = row(
        make_inputs(modules=frozenset({"torch", "transformers"}), azure_key_set=False),
        C.TRANSCRIBER,
    )
    assert r.status is S.MISSING


@pytest.mark.parametrize("modules", [frozenset({"transformers"}), frozenset[str]()])
def test_crisper_not_installed_keeps_the_licence_note(modules: frozenset[str]):
    r = row(make_inputs(transcriber="crisper_whisper", modules=modules), C.TRANSCRIBER)
    assert r.status is S.NOT_INSTALLED and "non-commercial licence, opt-in" in r.reason


def test_capabilities_degraded_cases_and_missing_region():
    day = date(2026, 11, 12)
    for nbest, prosody in ((False, True), (False, False)):
        r = row(
            make_inputs(capabilities=CapabilityFindings(nbest, prosody, day)), C.AZURE_CAPABILITIES
        )
        assert r.status is S.DEGRADED
        assert r.fix is None
    r = row(make_inputs(azure_region=None), C.AZURE_CAPABILITIES)
    assert r.status is S.NOT_PROBED


@pytest.mark.parametrize("mode", [0o750, 0o707, 0o701])
def test_data_dir_any_group_or_other_bit_is_degraded(mode: int):
    r = row(make_inputs(data_dir_mode=mode), C.DATA_DIR)
    assert r.status is S.DEGRADED


def test_data_dir_combined_reason_names_both_and_ready_reason():
    r = row(make_inputs(data_dir_mode=0o755, env_file_mode=0o644), C.DATA_DIR)
    assert "/data" in r.reason and ".env" in r.reason
    assert "group or other users have access" in r.reason
    ok = row(make_inputs(), C.DATA_DIR)
    assert ok.reason == "/data exists, owner-only" and ok.fix is None


def test_data_dir_missing_with_loose_env_is_degraded_for_env_only():
    r = row(make_inputs(data_dir_mode=None, env_file_mode=0o644), C.DATA_DIR)
    assert r.status is S.DEGRADED and r.fix == "chmod 600 .env"


def test_data_dir_fix_quotes_the_path():
    r = row(make_inputs(data_dir="/my data", data_dir_mode=0o755), C.DATA_DIR)
    assert r.fix == "chmod 700 '/my data'"


def test_inspect_errors_make_the_data_dir_row_missing():
    err = "cannot inspect /data: Not a directory"
    r = row(make_inputs(data_dir_mode=None, inspect_errors=(err,)), C.DATA_DIR)
    assert r.status is S.MISSING and err in r.reason
    assert r.fix and "directory you own and can open" in r.fix
    assert build_readiness(make_inputs(inspect_errors=(err,))).ready is False


def test_invalid_pack_reason_does_not_repeat_the_prefix():
    r = row(
        make_inputs(pack=PackStatus("bad", None, 0, ("pack bad: id is wrong",))), C.LANGUAGE_PACK
    )
    assert r.reason == "pack 'bad' is invalid: id is wrong"


def test_key_named_inputs_are_booleans():
    import dataclasses
    import typing

    hints = typing.get_type_hints(ReadinessInputs)
    keyed = [f.name for f in dataclasses.fields(ReadinessInputs) if "key" in f.name]
    assert keyed and all(hints[name] is bool for name in keyed)
