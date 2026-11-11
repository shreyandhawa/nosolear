import pytest
from factories import DAY, T0, TAX, mk
from nosolear.domain.profile import ALGO_VERSION, build_profile
from nosolear.domain.status import Status

from nosolear.domain.observations import Context, Outcome

MISS, OK = Outcome.MISS, Outcome.OK


def test_counts_without_decay():
    obs = [mk("sound.sub.v.w", MISS, T0)] * 10 + [mk("sound.sub.v.w", OK, T0)] * 30
    e = build_profile(obs, as_of=T0, taxonomy=TAX).entries[0]
    assert (e.state.a, e.state.b) == (11, 33)
    assert e.estimate.p_hat == pytest.approx(0.25) and e.estimate.n_eff == pytest.approx(40)
    assert e.estimate.ci_low < 0.25 < e.estimate.ci_high and e.status is Status.ACTIVE


def test_half_life_decay():
    obs = [mk("sound.sub.v.w", MISS, T0)] * 10 + [mk("sound.sub.v.w", OK, T0)] * 30
    e = build_profile(obs, as_of=T0 + 14 * DAY, taxonomy=TAX).entries[0]
    assert (e.state.a, e.state.b) == (pytest.approx(6), pytest.approx(18))


def test_unscripted_counts_half():
    obs = [mk("sound.sub.v.w", MISS, T0, context=Context.UNSCRIPTED)]
    e = build_profile(obs, as_of=T0, taxonomy=TAX).entries[0]
    assert (e.state.a, e.state.b) == (1.5, 3)


def test_non_hypothesis_prior():
    e = build_profile([mk("sound.sub.p.b", OK, T0)], as_of=T0, taxonomy=TAX).entries[0]
    assert e.estimate.p_hat == pytest.approx(1 / 11)


def test_sorted_by_priority():
    vw = [mk("sound.sub.v.w", MISS, T0)] * 10 + [mk("sound.sub.v.w", OK, T0)] * 30  # 0.25 x 3
    tt = [mk("sound.sub.θ.t", MISS, T0)] * 3 + [mk("sound.sub.θ.t", OK, T0)]  # 0.50 x 2
    keys = [e.definition.key for e in build_profile(vw + tt, as_of=T0, taxonomy=TAX).entries]
    assert keys == ["sound.sub.θ.t", "sound.sub.v.w"]


def test_excludes_observations_after_as_of():
    p = build_profile([mk("sound.sub.v.w", MISS, T0 + DAY)], as_of=T0, taxonomy=TAX)
    assert p.entries == ()


def test_improving_after_two_weeks_of_better_results():
    early = [mk("sound.sub.v.w", MISS, T0)] * 6 + [mk("sound.sub.v.w", OK, T0)] * 4
    late = [mk("sound.sub.v.w", MISS, T0 + 15 * DAY)] * 3 + [
        mk("sound.sub.v.w", OK, T0 + 15 * DAY)
    ] * 17
    e = build_profile(early + late, as_of=T0 + 15 * DAY, taxonomy=TAX).entries[0]
    assert e.status is Status.IMPROVING


def test_profile_metadata_and_last_seen():
    obs = [mk("sound.sub.v.w", MISS, T0), mk("sound.sub.v.w", OK, T0 + 2 * DAY)]
    p = build_profile(obs, as_of=T0 + 5 * DAY, taxonomy=TAX)
    assert (p.as_of, p.taxonomy_version, p.algo_version) == (
        T0 + 5 * DAY,
        TAX.version,
        ALGO_VERSION,
    )
    e = p.entries[0]
    assert e.last_seen_at == T0 + 2 * DAY and e.state.updated_at == T0 + 5 * DAY
    assert e.priority == pytest.approx(e.estimate.p_hat * 3)


def test_naive_as_of_rejected():
    with pytest.raises(ValueError):
        build_profile([], as_of=T0.replace(tzinfo=None), taxonomy=TAX)
