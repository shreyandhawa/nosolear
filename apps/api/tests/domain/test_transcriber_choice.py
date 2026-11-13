import pytest
from hypothesis import given
from hypothesis import strategies as st

from nosolear.domain.transcriber_choice import (
    MAX_REAL_TIME_FACTOR,
    Platform,
    TranscriberName,
    choose_transcriber,
)

ALL = frozenset(TranscriberName)


def choose(setting="auto", platform=Platform.MACOS_ARM64, installed=ALL, rtf=None):
    return choose_transcriber(
        setting, platform=platform, installed=installed, real_time_factors=rtf or {}
    )


def test_auto_on_apple_prefers_mlx():
    assert choose().name is TranscriberName.MLX_WHISPER


def test_auto_skips_slow_mlx_then_uses_faster():
    c = choose(rtf={TranscriberName.MLX_WHISPER: 0.52})
    assert c.name is TranscriberName.FASTER_WHISPER
    assert c.skipped == ((TranscriberName.MLX_WHISPER, "too slow: 0.52\u00d7 real time"),)


def test_auto_on_linux_without_extras_falls_back_to_azure():
    c = choose(platform=Platform.LINUX, installed=frozenset({TranscriberName.AZURE_STT}))
    assert c.name is TranscriberName.AZURE_STT


def test_auto_skips_uninstalled_candidates_with_a_reason():
    c = choose(platform=Platform.MACOS_ARM64, installed=frozenset({TranscriberName.AZURE_STT}))
    assert c.name is TranscriberName.AZURE_STT
    assert [reason for _, reason in c.skipped] == ["not installed", "not installed"]


def test_explicit_slow_choice_is_honoured_with_warning():
    c = choose("faster_whisper", rtf={TranscriberName.FASTER_WHISPER: 0.5})
    assert c.name is TranscriberName.FASTER_WHISPER
    assert not c.auto
    assert c.warning is not None and "slower than 1/3 real time" in c.warning


def test_explicit_uninstalled_choice_is_honoured_with_install_hint():
    c = choose("mlx_whisper", installed=frozenset({TranscriberName.AZURE_STT}))
    assert c.name is TranscriberName.MLX_WHISPER
    assert c.warning is not None and "uv sync --extra apple" in c.warning


def test_unknown_setting_is_refused():
    with pytest.raises(ValueError):
        choose("whisperx")


@given(
    st.sampled_from(list(Platform)),
    st.sets(st.sampled_from(list(TranscriberName))),
    st.dictionaries(st.sampled_from(list(TranscriberName)), st.floats(0.01, 5)),
)
def test_auto_never_picks_crisper_and_picks_something_usable(platform, installed, rtf):
    c = choose_transcriber(
        "auto", platform=platform, installed=frozenset(installed), real_time_factors=rtf
    )
    assert c.name is not TranscriberName.CRISPER_WHISPER
    assert c.name is TranscriberName.AZURE_STT or (
        c.name in installed and rtf.get(c.name, 0) <= MAX_REAL_TIME_FACTOR
    )
