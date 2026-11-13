"""The local transcriber speed check: real time factor on a passage of about a minute.

The probe sentence is transcribed first, untimed, so a model load or a download is not counted.
Only the passage run is timed. A factor of 1/3 means one minute of speech takes twenty seconds.
"""

import time
from collections.abc import Callable
from pathlib import Path

from nosolear.adapters.local_env import installed_version
from nosolear.domain.capabilities import (
    CLIP_SECONDS,
    PROBE_SENTENCE,
    REAL_TIME_FACTOR,
    SPEED_CHECK_PASSAGE,
)
from nosolear.domain.speech import LOCAL, ProviderCapabilities
from nosolear.domain.transcriber_choice import TranscriberName
from nosolear.ports.clock import Clock
from nosolear.ports.providers import Synthesizer, Transcriber

ADAPTER_VERSION = 1
_DISTRIBUTION = {
    TranscriberName.FASTER_WHISPER: "faster-whisper",
    TranscriberName.MLX_WHISPER: "mlx-whisper",
    TranscriberName.CRISPER_WHISPER: "transformers",
}


class TranscriberSpeedCheck:
    def __init__(
        self,
        *,
        name: TranscriberName,
        synthesizer: Synthesizer,
        transcriber: Transcriber,
        data_dir: Path,
        clock: Clock,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._name = name
        self._synthesizer = synthesizer
        self._transcriber = transcriber
        self._data_dir = data_dir
        self._clock = clock
        self._timer = timer

    @property
    def adapter(self) -> str:
        return self._name.value

    def probe(self) -> ProviderCapabilities:
        warm = self._synthesizer.synthesize(PROBE_SENTENCE, rate_percent=0)
        self._transcriber.transcribe(self._data_dir / warm.path)
        passage = self._synthesizer.synthesize(SPEED_CHECK_PASSAGE, rate_percent=0)
        seconds = passage.duration_ms / 1000
        started = self._timer()
        self._transcriber.transcribe(self._data_dir / passage.path)
        elapsed = self._timer() - started
        return ProviderCapabilities(
            provider=LOCAL,
            adapter=self._name.value,
            adapter_version=ADAPTER_VERSION,
            provider_version=installed_version(_DISTRIBUTION.get(self._name, self._name.value)),
            region=None,
            locale=None,
            capabilities={REAL_TIME_FACTOR: round(elapsed / seconds, 3), CLIP_SECONDS: seconds},
            probed_at=self._clock.now(),
        )
