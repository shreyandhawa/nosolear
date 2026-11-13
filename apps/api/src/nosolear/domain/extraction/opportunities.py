"""Opportunities: one scored chance for a key to be missed, before it becomes an observation."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from nosolear.domain.packs import LanguagePack
from nosolear.domain.scoring import Thresholds
from nosolear.domain.taxonomy import Taxonomy


@dataclass(frozen=True, slots=True)
class Opportunity:
    error_key: str
    missed: bool
    evidence: Mapping[str, object]


ThresholdsFor = Callable[[str], Thresholds]


def tracked_keys(taxonomy: Taxonomy, pack: LanguagePack) -> frozenset[str]:
    keys = {definition.key for definition in taxonomy.defined()}
    keys.update(hypothesis.key for hypothesis in pack.hypotheses)
    keys.update(pack.calibration_emphasis)
    return frozenset(keys)
