"""Extract one attempt's observations under the newest scoring config and write them (section 6.3).

Re-running it writes nothing new: each (attempt, config, detector) is written once. A stored
analysis that no longer parses is skipped and named, never fatal.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from nosolear.domain.analyses import AnalysisKind, StoredAnalysis
from nosolear.domain.coach import coach_keys, coach_task_for_step, parse_coach_analysis
from nosolear.domain.extraction.extract import ProviderResults, extract
from nosolear.domain.packs import LanguagePack
from nosolear.domain.results import parse_azure_pa, parse_phone_probe, parse_transcript
from nosolear.domain.speech import RawResult, Transcript, raw_result_of
from nosolear.domain.taxonomy import Taxonomy
from nosolear.ports.clock import Clock
from nosolear.ports.scoring_stores import ExtractionInputs, ExtractionWriter, ScoringConfigReader


@dataclass(frozen=True, slots=True)
class ExtractSummary:
    attempt_id: str
    scoring_config_id: str
    written: int
    undecodable: tuple[str, ...]


def _decode[T](
    stored: StoredAnalysis | None,
    parse: Callable[[RawResult], T],
    undecodable: list[str],
) -> T | None:
    if stored is None:
        return None
    try:
        return parse(raw_result_of(stored))
    except ValueError:
        undecodable.append(stored.kind.value)
        return None


def collect_results(
    analyses: Iterable[StoredAnalysis], *, step: str, taxonomy: Taxonomy
) -> tuple[ProviderResults, tuple[str, ...]]:
    """Parses each stored kind. The coach is read after the transcript, against the transcript's
    text, with the keys its step allows. A kind whose parser raises `ValueError` is skipped and
    named in the second element."""
    by_kind = {stored.kind: stored for stored in analyses}
    undecodable: list[str] = []
    pronunciation = _decode(by_kind.get(AnalysisKind.PRONUNCIATION), parse_azure_pa, undecodable)
    transcript: Transcript | None = _decode(
        by_kind.get(AnalysisKind.TRANSCRIPT), parse_transcript, undecodable
    )
    phone_probe = _decode(by_kind.get(AnalysisKind.PHONE_PROBE), parse_phone_probe, undecodable)
    coach = None
    if transcript is not None:
        allowed = coach_keys(taxonomy, coach_task_for_step(step))
        coach = _decode(
            by_kind.get(AnalysisKind.COACH),
            lambda raw: parse_coach_analysis(raw, transcript=transcript.text, allowed_keys=allowed),
            undecodable,
        )
    results = ProviderResults(
        pronunciation=pronunciation,
        transcript=transcript,
        phone_probe=phone_probe,
        coach=coach,
    )
    return results, tuple(undecodable)


def extract_attempt(
    *,
    attempt_id: str,
    inputs: ExtractionInputs,
    configs: ScoringConfigReader,
    extractions: ExtractionWriter,
    pack: LanguagePack,
    taxonomy: Taxonomy,
    clock: Clock,
) -> ExtractSummary:
    item = inputs.item(attempt_id)
    if item is None:
        raise ValueError("No attempt has this id.")
    config = configs.newest()
    results, undecodable = collect_results(
        inputs.analyses(attempt_id), step=item.step, taxonomy=taxonomy
    )
    written = 0
    observations = extract(item, results, config=config, pack=pack, taxonomy=taxonomy)
    for detector, found in observations.items():
        if extractions.write(
            attempt_id=attempt_id,
            scoring_config_id=config.id,
            detector=detector,
            observations=found,
            created_at=clock.now(),
        ):
            written += len(found)
    return ExtractSummary(
        attempt_id=attempt_id,
        scoring_config_id=config.id,
        written=written,
        undecodable=undecodable,
    )
