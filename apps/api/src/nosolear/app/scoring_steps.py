"""The scoring steps of the job plans (ARCHITECTURE.md section 13): `extract` on an analyze job,
and the re-score job's only step. Both read stored analyses and call no provider.
"""

from collections.abc import Callable
from dataclasses import dataclass

from nosolear.app.baseline import refresh_completed_baselines
from nosolear.app.extract_attempt import extract_attempt
from nosolear.app.rebuild_profile import rebuild_profile
from nosolear.app.rescore import rescore
from nosolear.app.steps import StepContext
from nosolear.domain.packs import LanguagePack
from nosolear.domain.taxonomy import Taxonomy
from nosolear.ports.baseline_store import BaselineStore
from nosolear.ports.clock import Clock
from nosolear.ports.scoring_stores import ExtractionInputs, ExtractionWriter, ScoringConfigReader
from nosolear.ports.stores import ObservationReader, ProfileWriter


@dataclass(frozen=True, slots=True)
class ScoringDeps:
    inputs: ExtractionInputs
    configs: ScoringConfigReader
    extractions: ExtractionWriter
    observations: ObservationReader
    profiles: ProfileWriter
    pack: Callable[[], LanguagePack]
    """Loaded when a step runs, so a bad pack fails that job and not the whole app."""
    taxonomy: Taxonomy
    clock: Clock
    baselines: BaselineStore


class ExtractStep:
    """Writes this attempt's observations, then replaces the profile entries (no snapshot)."""

    name = "extract"

    def __init__(self, deps: ScoringDeps) -> None:
        self._deps = deps

    def applies(self, ctx: StepContext) -> bool:
        return True

    def run(self, ctx: StepContext) -> None:
        if ctx.attempt_id is None:
            raise ValueError("An analysis job needs an attempt.")
        deps = self._deps
        pack = deps.pack()
        extract_attempt(
            attempt_id=ctx.attempt_id,
            inputs=deps.inputs,
            configs=deps.configs,
            extractions=deps.extractions,
            pack=pack,
            taxonomy=deps.taxonomy,
            clock=deps.clock,
        )
        rebuild_profile(
            observations=deps.observations,
            profiles=deps.profiles,
            taxonomy=deps.taxonomy,
            pack=pack,
            clock=deps.clock,
            reason=None,
        )


class RescoreStep:
    """The whole re-score job: every stored attempt, one profile rebuild, then a refresh of every
    completed baseline's snapshot and scores (which also calls no provider)."""

    name = "extract"

    def __init__(self, deps: ScoringDeps) -> None:
        self._deps = deps

    def applies(self, ctx: StepContext) -> bool:
        return True

    def run(self, ctx: StepContext) -> None:
        deps = self._deps
        rescore(
            inputs=deps.inputs,
            configs=deps.configs,
            extractions=deps.extractions,
            observations=deps.observations,
            profiles=deps.profiles,
            pack=deps.pack(),
            taxonomy=deps.taxonomy,
            clock=deps.clock,
            on_progress=ctx.progress,
        )
        refresh_completed_baselines(
            store=deps.baselines,
            inputs=deps.inputs,
            observations=deps.observations,
            profiles=deps.profiles,
            taxonomy=deps.taxonomy,
            pack=deps.pack(),
        )
