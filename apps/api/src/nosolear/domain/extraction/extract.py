"""One pure entry point from a finished attempt's typed results to its observations (section 6.3).

Calibration attempts yield nothing. Each detector whose input is present gets one entry, even when
it holds no observations. Pure: no I/O.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from nosolear.domain.coach import CoachAnalysis
from nosolear.domain.extraction.coach import coach_opportunities
from nosolear.domain.extraction.fluency import fluency_opportunities
from nosolear.domain.extraction.opportunities import Opportunity, ThresholdsFor, tracked_keys
from nosolear.domain.extraction.sounds import azure_opportunities, probe_opportunities
from nosolear.domain.observations import Context, Observation, Outcome, make_observation
from nosolear.domain.packs import LanguagePack
from nosolear.domain.scoring import ScoringConfig, Thresholds, enabled_keys
from nosolear.domain.speech import PhoneProbeResult, PronunciationAssessment, Transcript
from nosolear.domain.taxonomy import Detector, Taxonomy

CALIBRATION_STEP: Final = "calibration"
DETECTOR_INPUT: Final[Mapping[Detector, str]] = {
    Detector.AZURE_PA: "pronunciation",
    Detector.PHONE_PROBE: "phone_probe",
    Detector.ASR_METRICS: "transcript",
    Detector.COACH: "coach",
}


@dataclass(frozen=True, slots=True)
class ExtractionItem:
    attempt_id: str
    step: str
    scripted: bool
    reference_text: str | None
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class ProviderResults:
    pronunciation: PronunciationAssessment | None = None
    transcript: Transcript | None = None
    phone_probe: PhoneProbeResult | None = None
    coach: CoachAnalysis | None = None


def _thresholds_for(config: ScoringConfig, detector: Detector, taxonomy: Taxonomy) -> ThresholdsFor:
    def thresholds_for(key: str) -> Thresholds:
        rule = config.rule_for(detector, taxonomy.get(key))
        if rule is None:
            raise ValueError(f"{key} is not scored by {detector}")
        return rule.thresholds

    return thresholds_for


def _opportunities(
    detector: Detector,
    item: ExtractionItem,
    results: ProviderResults,
    keys: frozenset[str],
    thresholds_for: ThresholdsFor,
    taxonomy: Taxonomy,
) -> list[Opportunity]:
    if detector is Detector.AZURE_PA and results.pronunciation is not None:
        return azure_opportunities(results.pronunciation, keys=keys, thresholds_for=thresholds_for)
    if detector is Detector.PHONE_PROBE and results.phone_probe is not None:
        return probe_opportunities(
            results.phone_probe, reference_text=item.reference_text, keys=keys
        )
    if detector is Detector.ASR_METRICS and results.transcript is not None:
        return fluency_opportunities(
            results.transcript, step=item.step, keys=keys, thresholds_for=thresholds_for
        )
    if detector is Detector.COACH and results.coach is not None and results.transcript is not None:
        return coach_opportunities(
            results.coach,
            results.transcript,
            step=item.step,
            keys=keys,
            taxonomy=taxonomy,
        )
    return []


def extract(
    item: ExtractionItem,
    results: ProviderResults,
    *,
    config: ScoringConfig,
    pack: LanguagePack,
    taxonomy: Taxonomy,
) -> dict[Detector, tuple[Observation, ...]]:
    if item.step == CALIBRATION_STEP:
        return {}
    context = Context.SCRIPTED if item.scripted else Context.UNSCRIPTED
    tracked = tracked_keys(taxonomy, pack)
    out: dict[Detector, tuple[Observation, ...]] = {}
    for detector in Detector:
        if getattr(results, DETECTOR_INPUT[detector]) is None:
            continue
        keys = enabled_keys(config, detector, tracked, taxonomy)
        thresholds_for = _thresholds_for(config, detector, taxonomy)
        observations: list[Observation] = []
        for opportunity in _opportunities(detector, item, results, keys, thresholds_for, taxonomy):
            rule = config.rule_for(detector, taxonomy.get(opportunity.error_key))
            if rule is None:
                raise ValueError(f"{opportunity.error_key} is not scored by {detector}")
            observations.append(
                make_observation(
                    taxonomy=taxonomy,
                    error_key=opportunity.error_key,
                    outcome=Outcome.MISS if opportunity.missed else Outcome.OK,
                    detector=detector,
                    context=context,
                    observed_at=item.observed_at,
                    confidence=1.0,
                    attempt_id=item.attempt_id,
                    evidence=opportunity.evidence,
                    scoring_config_id=config.id,
                    provisional=rule.provisional,
                )
            )
        out[detector] = tuple(observations)
    return out
