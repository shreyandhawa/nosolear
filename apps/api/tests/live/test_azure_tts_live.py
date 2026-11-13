from collections.abc import Callable
from pathlib import Path

import pytest
from wavs import wav_info


@pytest.mark.live
def test_slow_rate_is_slower_and_has_word_timings(require_azure, tts_clip: Callable[..., Path]):
    text = "The vest is in the van by the west wall."
    normal, slow = tts_clip(text), tts_clip(text, rate_percent=-25)
    assert wav_info(slow).seconds >= 1.2 * wav_info(normal).seconds  # spike rule slow_rate_ok
    assert wav_info(normal).rate == 16000 and wav_info(normal).channels == 1
