import subprocess
from pathlib import Path

import pytest
from wavs import write_wav

from nosolear.adapters import wav2vec2_espeak
from nosolear.adapters.lazy_model import LazyModel
from nosolear.adapters.wav2vec2_espeak import (
    ESPEAK_ARGS,
    Wav2Vec2EspeakProbe,
    ctc_greedy_decode,
    espeak_ipa,
)
from nosolear.domain.errors import ProviderUnavailable
from nosolear.domain.phone_alignment import align_phones

EXE = Path("/usr/bin/espeak-ng")
VERSION = "eSpeak NG text-to-speech: 1.52.0"


def completed(argv, stdout="", returncode=0):
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")


def fail_if_called(*args, **kwargs):
    raise AssertionError("espeak-ng must not run for unsafe text")


def fake_run(stdout="s_k_ˈuː_l\n", returncode=0):
    def run(argv, **kwargs):
        if "--version" in argv:
            return completed(argv, stdout=VERSION + "\n")
        return completed(argv, stdout=stdout, returncode=returncode)

    return run


class FakeRecognizer:
    def __init__(self, tokens):
        self._tokens = tokens

    def tokens(self, wav):
        return list(self._tokens)


def test_espeak_gets_fixed_argv_and_text_on_stdin():
    seen = {}

    def run(argv, **kw):
        seen.update(argv=argv, **kw)
        return completed(argv, stdout="s_k_ˈuː_l\n")

    text = "school; rm -rf ~ $(whoami) --help -w /tmp/x"
    assert espeak_ipa(text, executable=EXE, run=run) == "s_k_ˈuː_l"
    assert seen["argv"] == [str(EXE), *ESPEAK_ARGS] and seen["input"] == text + "\n"
    assert seen.get("shell", False) is False and seen["timeout"] == 10


def test_module_never_uses_a_shell():
    src = Path(wav2vec2_espeak.__file__).read_text()
    assert "shell=True" not in src and "os.system" not in src


@pytest.mark.parametrize("bad", ["", "   ", "x" * 1001, "vest\x00west", "vest\nwest"])
def test_rejects_unsafe_reference_text(bad):
    with pytest.raises(ValueError):
        espeak_ipa(bad, executable=EXE, run=fail_if_called)


def test_a_failing_espeak_is_provider_unavailable():
    def run(argv, **kw):
        return completed(argv, stdout="", returncode=1)

    with pytest.raises(ProviderUnavailable, match="espeak-ng failed; check it is installed"):
        espeak_ipa("school", executable=EXE, run=run)


def test_a_missing_espeak_is_provider_unavailable():
    def run(argv, **kw):
        raise FileNotFoundError(argv[0])

    with pytest.raises(ProviderUnavailable, match="espeak-ng failed") as info:
        espeak_ipa("school", executable=EXE, run=run)
    assert info.value.__cause__ is None


def test_ctc_greedy_decode():
    vocab = {0: "<pad>", 1: "s", 2: "k", 3: "uː", 4: "l"}
    assert ctc_greedy_decode(
        [1, 1, 0, 2, 3, 3, 0, 0, 4], vocab, blank_id=0, special=frozenset({"<s>", "</s>"})
    ) == ["s", "k", "uː", "l"]


def test_ctc_keeps_a_repeated_phone_split_by_a_blank():
    vocab = {0: "<pad>", 1: "s"}
    assert ctc_greedy_decode([1, 0, 1], vocab, blank_id=0, special=frozenset()) == ["s", "s"]


def test_probe_normalizes_both_sides(tmp_path):
    probe = Wav2Vec2EspeakProbe(
        espeak=EXE,
        recognizer=LazyModel(lambda: FakeRecognizer(["ɪ", "s", "k", "uː", "l"])),
        run=fake_run(),
    )
    r = probe.probe(write_wav(tmp_path / "a.wav", 1), reference_text="school")
    assert r.expected_words == (("s", "k", "u", "l"),)
    assert r.heard == ("ɪ", "s", "k", "u", "l")
    assert r.raw.adapter == "wav2vec2_espeak"
    assert r.raw.provider_version.startswith("espeak-ng eSpeak NG")
    assert align_phones(r.expected, r.heard)[0].op == "ins"


def test_unmapped_heard_symbol_is_provider_unavailable(tmp_path, caplog):
    probe = Wav2Vec2EspeakProbe(
        espeak=EXE,
        recognizer=LazyModel(lambda: FakeRecognizer(["q"])),
        run=fake_run(),
    )
    with pytest.raises(
        ProviderUnavailable, match="The phone probe heard a sound symbol Nosolear can't map yet"
    ):
        probe.probe(write_wav(tmp_path / "a.wav", 1), reference_text="school")
    assert "'q'" in caplog.text


def test_espeak_version_is_read_once_per_instance(tmp_path):
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        if "--version" in argv:
            return completed(argv, stdout=VERSION + "\n")
        return completed(argv, stdout="s_k_ˈuː_l")

    probe = Wav2Vec2EspeakProbe(
        espeak=EXE, recognizer=LazyModel(lambda: FakeRecognizer(["s"])), run=run
    )
    wav = write_wav(tmp_path / "a.wav", 1)
    probe.probe(wav, reference_text="school")
    probe.probe(wav, reference_text="school")
    assert sum("--version" in argv for argv in calls) == 1


def test_recognizer_failure_is_provider_unavailable_without_its_message(tmp_path, caplog):
    def broken():
        raise OSError("weights at /private/secret/model.bin are corrupt")

    probe = Wav2Vec2EspeakProbe(espeak=EXE, recognizer=LazyModel(broken), run=fake_run())
    with pytest.raises(ProviderUnavailable, match="The phone probe failed") as info:
        probe.probe(write_wav(tmp_path / "a.wav", 1), reference_text="school")
    assert "secret" not in str(info.value) and "secret" not in caplog.text


def test_probe_declares_the_raw_layer():
    assert Wav2Vec2EspeakProbe.layer == "raw"
    assert wav2vec2_espeak.ADAPTER == "wav2vec2_espeak"
    assert wav2vec2_espeak.ADAPTER_VERSION == 1
