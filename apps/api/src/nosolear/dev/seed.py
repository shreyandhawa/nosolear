"""Deterministic synthetic observations for local development."""

import random
from datetime import datetime, timedelta

from nosolear.domain.observations import Context, Observation, Outcome, make_observation
from nosolear.domain.scoring import SOUND_FAMILIES, V0_CONFIG, V0_CONFIG_ID
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY, Detector

# (error key, detector, miss rate at the start of the window, miss rate at the end)
_SPECS = (
    ("sound.sub.v.w", Detector.PHONE_PROBE, 0.7, 0.3),
    ("sound.sub.f.p", Detector.AZURE_PA, 0.5, 0.2),
    ("sound.sub.θ.t", Detector.PHONE_PROBE, 0.8, 0.6),
    ("sound.ins.epenthesis_sC", Detector.PHONE_PROBE, 0.6, 0.35),
    ("fluency.slow_start", Detector.ASR_METRICS, 0.4, 0.15),
    ("grammar.article", Detector.COACH, 0.5, 0.25),
)
_PER_DAY = 3


def seed_observations(*, days: int, seed: int, end: datetime) -> list[Observation]:
    rng = random.Random(seed)
    observations: list[Observation] = []
    for day in range(days):
        progress = day / (days - 1) if days > 1 else 1.0
        # Day 0 is the oldest; the last day ends at `end`.
        day_end = end - timedelta(days=days - 1 - day)
        for key, detector, start_rate, end_rate in _SPECS:
            miss_rate = start_rate + (end_rate - start_rate) * progress
            for _ in range(_PER_DAY):
                outcome = Outcome.MISS if rng.random() < miss_rate else Outcome.OK
                observed_at = day_end - timedelta(minutes=rng.randrange(0, 12 * 60))
                definition = DEFAULT_TAXONOMY.get(key)
                scored_by_v0 = V0_CONFIG.rule_for(detector, definition) is not None
                observations.append(
                    make_observation(
                        taxonomy=DEFAULT_TAXONOMY,
                        error_key=key,
                        outcome=outcome,
                        detector=detector,
                        context=rng.choice(list(Context)),
                        observed_at=observed_at,
                        confidence=round(rng.uniform(0.6, 1.0), 2),
                        scoring_config_id=V0_CONFIG_ID,
                        provisional=scored_by_v0 and definition.family in SOUND_FAMILIES,
                    )
                )
    return observations
