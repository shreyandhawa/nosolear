"""Fixtures for the `local_models` tests, which need the local/apple extras and espeak-ng.

Excluded by default (pyproject addopts); CI's `local-models` job and `make test-local-models`
run them. Audio is generated here with espeak-ng, never a recording of a person.
"""

import itertools
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from nosolear.adapters.local_env import espeak_ng_path
from nosolear.domain.audio import encode_wav, parse_wav, to_16k


@pytest.fixture
def espeak_wav(tmp_path: Path) -> Callable[[str], Path]:
    """A factory: text in, a 16 kHz mono 16-bit WAV of espeak-ng saying it, out."""
    exe = espeak_ng_path()
    counter = itertools.count()

    def make(text: str) -> Path:
        if exe is None:
            pytest.skip("espeak-ng is not installed")
        raw = tmp_path / f"espeak-{next(counter)}.wav"
        subprocess.run(
            [str(exe), "-v", "en-us", "-w", str(raw), "--stdin"],
            input=text,
            text=True,
            capture_output=True,
            check=True,
            timeout=30,
        )
        out = tmp_path / f"clip-{raw.stem}.wav"
        out.write_bytes(encode_wav(to_16k(parse_wav(raw.read_bytes()))))
        return out

    return make
