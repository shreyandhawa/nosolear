from factories import NOW, TAX
from nosolear.dev.seed import seed_observations
from nosolear.domain.observations import Outcome
from nosolear.domain.taxonomy import Detector

KEYS = {
    "sound.sub.v.w",
    "sound.sub.f.p",
    "sound.sub.θ.t",
    "sound.ins.epenthesis_sC",
    "fluency.slow_start",
    "grammar.article",
}


def test_seed_is_deterministic() -> None:
    assert seed_observations(days=14, seed=7, end=NOW) == seed_observations(
        days=14, seed=7, end=NOW
    )


def test_seed_differs_by_seed() -> None:
    assert seed_observations(days=14, seed=7, end=NOW) != seed_observations(
        days=14, seed=8, end=NOW
    )


def test_seed_covers_six_keys_within_window() -> None:
    obs = seed_observations(days=14, seed=7, end=NOW)
    assert {o.error_key for o in obs} == KEYS
    assert all(o.observed_at <= NOW for o in obs)
    assert all(o.observed_at.utcoffset() is not None for o in obs)
    for o in obs:
        assert o.detector in TAX.get(o.error_key).detectors


def test_seed_detectors_and_falling_miss_rate() -> None:
    obs = seed_observations(days=14, seed=7, end=NOW)
    assert {o.detector for o in obs if o.error_key == "sound.ins.epenthesis_sC"} == {
        Detector.PHONE_PROBE
    }
    assert {o.detector for o in obs if o.error_key == "fluency.slow_start"} == {
        Detector.ASR_METRICS
    }
    assert {o.detector for o in obs if o.error_key == "grammar.article"} == {Detector.COACH}
    mid = NOW.timestamp() - 7 * 86400
    early = [o for o in obs if o.observed_at.timestamp() < mid]
    late = [o for o in obs if o.observed_at.timestamp() >= mid]

    def rate(xs: list) -> float:
        return sum(o.outcome == Outcome.MISS for o in xs) / len(xs)

    assert rate(early) > rate(late)
