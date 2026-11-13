"""The Azure capability probe: what the pronunciation tier returns for a known sentence.

It runs through the wrapped synthesizer and scorer (retry, metered, cache), so the probe spends
quota exactly as a real attempt would, and its failures are the failures a user would see.
"""

from pathlib import Path

from nosolear.adapters.azure_pa import ADAPTER_VERSION
from nosolear.domain.capabilities import (
    AZURE_PA_ADAPTER,
    AZURE_PROVIDER,
    NBEST_PHONEMES,
    PROBE_SENTENCE,
    PROSODY,
)
from nosolear.domain.speech import ProviderCapabilities
from nosolear.ports.clock import Clock
from nosolear.ports.providers import PronunciationScorer, Synthesizer


class AzureCapabilityProbe:
    def __init__(
        self,
        *,
        synthesizer: Synthesizer,
        scorer: PronunciationScorer,
        data_dir: Path,
        region: str | None,
        locale: str,
        clock: Clock,
    ) -> None:
        self._synthesizer = synthesizer
        self._scorer = scorer
        self._data_dir = data_dir
        self._region = region
        self._locale = locale
        self._clock = clock

    @property
    def adapter(self) -> str:
        return AZURE_PA_ADAPTER

    def probe(self) -> ProviderCapabilities:
        clip = self._synthesizer.synthesize(PROBE_SENTENCE, rate_percent=0)
        assessment = self._scorer.score(self._data_dir / clip.path, reference_text=PROBE_SENTENCE)
        return ProviderCapabilities(
            provider=AZURE_PROVIDER,
            adapter=AZURE_PA_ADAPTER,
            adapter_version=ADAPTER_VERSION,
            provider_version=assessment.raw.provider_version,
            region=self._region,
            locale=self._locale,
            capabilities={NBEST_PHONEMES: assessment.has_nbest, PROSODY: assessment.has_prosody},
            probed_at=self._clock.now(),
        )
