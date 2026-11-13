"""Re-score every stored attempt under the newest scoring config, with no provider call (section
9). Only stored analyses are read: the provider ports are not in this signature, so a re-score
spends no quota."""

from collections.abc import Callable
from dataclasses import dataclass

from nosolear.app.extract_attempt import extract_attempt
from nosolear.app.rebuild_profile import rebuild_profile
from nosolear.domain.packs import LanguagePack
from nosolear.domain.taxonomy import Taxonomy
from nosolear.ports.clock import Clock
from nosolear.ports.scoring_stores import (
    ExtractionInputs,
    ExtractionWriter,
    ScoringConfigReader,
)
from nosolear.ports.stores import ObservationReader, ProfileWriter


@dataclass(frozen=True, slots=True)
class RescoreSummary:
    scoring_config_id: str
    attempts: int
    observations: int
    undecodable: int


def _ignore(fraction: float) -> None:
    del fraction


def rescore(
    *,
    inputs: ExtractionInputs,
    configs: ScoringConfigReader,
    extractions: ExtractionWriter,
    observations: ObservationReader,
    profiles: ProfileWriter,
    pack: LanguagePack,
    taxonomy: Taxonomy,
    clock: Clock,
    on_progress: Callable[[float], None] = _ignore,
) -> RescoreSummary:
    config = configs.newest()
    attempt_ids = inputs.rescorable_attempt_ids()
    written = 0
    undecodable = 0
    for position, attempt_id in enumerate(attempt_ids, start=1):
        summary = extract_attempt(
            attempt_id=attempt_id,
            inputs=inputs,
            configs=configs,
            extractions=extractions,
            pack=pack,
            taxonomy=taxonomy,
            clock=clock,
        )
        written += summary.written
        undecodable += len(summary.undecodable)
        on_progress(position / len(attempt_ids))
    rebuild_profile(
        observations=observations,
        profiles=profiles,
        taxonomy=taxonomy,
        pack=pack,
        clock=clock,
        reason="rebuild",
    )
    return RescoreSummary(
        scoring_config_id=config.id,
        attempts=len(attempt_ids),
        observations=written,
        undecodable=undecodable,
    )
