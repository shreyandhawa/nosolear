from datetime import timedelta

import pytest
from factories import NEPALI, NEUTRAL, PACK, T0, TAX, mk
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from nosolear.domain.estimates import (
    DEFAULT_PRIOR,
    HYPOTHESIS_PRIOR,
    BetaState,
    Prior,
    apply,
    decay,
    estimate,
)
from nosolear.domain.observations import Context, Observation, Outcome
from nosolear.domain.profile import build_profile

HALF_LIFE = 14.0
LEVEL = 0.8
TOL = 1e-12

priors = st.sampled_from([HYPOTHESIS_PRIOR, DEFAULT_PRIOR])
outcomes = st.sampled_from([Outcome.MISS, Outcome.OK])
contexts = st.sampled_from([Context.SCRIPTED, Context.UNSCRIPTED])
confidences = st.floats(min_value=0.05, max_value=1.0)
keys = st.sampled_from(["sound.sub.v.w", "sound.sub.p.b", "sound.sub.θ.t"])


@st.composite
def beta_states(draw: st.DrawFn) -> tuple[Prior, BetaState]:
    prior = draw(priors)
    a = draw(st.floats(min_value=prior.a0, max_value=prior.a0 + 1000))
    b = draw(st.floats(min_value=prior.b0, max_value=prior.b0 + 1000))
    return prior, BetaState(a, b, T0)


offsets = st.integers(min_value=0, max_value=60 * 24).map(lambda h: timedelta(hours=h))


@st.composite
def observation_lists(draw: st.DrawFn) -> list[Observation]:
    n = draw(st.integers(min_value=0, max_value=30))
    return [
        mk(
            draw(keys),
            draw(outcomes),
            T0 + draw(offsets),
            context=draw(contexts),
            confidence=draw(confidences),
        )
        for _ in range(n)
    ]


@given(ps=beta_states(), at_offset=offsets, outcome=outcomes, context=contexts, c=confidences)
def test_miss_never_lowers_and_ok_never_raises_p_hat(ps, at_offset, outcome, context, c):
    prior, state = ps
    before = estimate(state, prior=prior, level=LEVEL).p_hat
    after = estimate(
        apply(state, mk("sound.sub.v.w", outcome, T0 + at_offset, context=context, confidence=c)),
        prior=prior,
        level=LEVEL,
    ).p_hat
    if outcome is Outcome.MISS:
        assert after >= before * (1 - TOL)
    else:
        assert after <= before * (1 + TOL)


@given(ps=beta_states(), d1=offsets, d2=offsets)
def test_decay_stays_above_prior_and_n_eff_never_grows(ps, d1, d2):
    prior, state = ps
    lo, hi = sorted((d1, d2))
    near = decay(state, to=T0 + lo, prior=prior, half_life_days=HALF_LIFE)
    far = decay(state, to=T0 + hi, prior=prior, half_life_days=HALF_LIFE)
    assert far.a >= prior.a0 and far.b >= prior.b0
    n_near = estimate(near, prior=prior, level=LEVEL).n_eff
    n_far = estimate(far, prior=prior, level=LEVEL).n_eff
    assert n_far <= n_near * (1 + TOL)
    base = BetaState(prior.a0, prior.b0, T0)
    assert decay(base, to=T0 + hi, prior=prior, half_life_days=HALF_LIFE).a == prior.a0
    assert decay(base, to=T0 + hi, prior=prior, half_life_days=HALF_LIFE).b == prior.b0


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(obs_list=observation_lists())
def test_estimates_are_finite_and_ordered(obs_list):
    profile = build_profile(obs_list, as_of=T0 + timedelta(days=60), taxonomy=TAX, pack=PACK)
    for e in profile.entries:
        est = e.estimate
        assert 0 < est.p_hat < 1
        assert 0 <= est.ci_low <= est.ci_high <= 1
        assert est.n_eff >= 0
        assert e.priority == e.priority and e.priority < float("inf")


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(obs_list=observation_lists(), seed=st.randoms())
def test_build_profile_is_order_independent(obs_list, seed):
    shuffled = list(obs_list)
    seed.shuffle(shuffled)
    as_of = T0 + timedelta(days=60)
    assert build_profile(shuffled, as_of=as_of, taxonomy=TAX, pack=PACK) == build_profile(
        obs_list, as_of=as_of, taxonomy=TAX, pack=PACK
    )


@settings(suppress_health_check=[HealthCheck.too_slow])
@given(obs_list=observation_lists())
def test_changing_pack_changes_only_priors(obs_list):
    as_of = T0 + timedelta(days=60)
    nepali = build_profile(obs_list, as_of=as_of, taxonomy=TAX, pack=NEPALI).entries
    neutral = build_profile(obs_list, as_of=as_of, taxonomy=TAX, pack=NEUTRAL).entries
    by_key = {e.definition.key: e for e in neutral}
    assert {e.definition.key for e in nepali} == by_key.keys()
    for e in nepali:
        other = by_key[e.definition.key]
        key = e.definition.key
        p, q = NEPALI.prior_for(key), NEUTRAL.prior_for(key)
        assert e.state.a - p.a0 == pytest.approx(other.state.a - q.a0, abs=TOL)
        assert e.state.b - p.b0 == pytest.approx(other.state.b - q.b0, abs=TOL)
        assert e.last_seen_at == other.last_seen_at
