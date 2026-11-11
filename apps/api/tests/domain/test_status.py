from nosolear.domain.estimates import KeyEstimate
from nosolear.domain.status import Status, StatusThresholds, classify

T = StatusThresholds()


def est(p: float, hi: float = 0.5, n: float = 10.0) -> KeyEstimate:
    return KeyEstimate(p_hat=p, ci_low=0.0, ci_high=hi, n_eff=n)


def test_rules():
    assert classify(est(0.3, n=4), previous=None, p_hat_lookback=None, t=T) is Status.UNKNOWN
    assert classify(est(0.20), previous=None, p_hat_lookback=None, t=T) is Status.ACTIVE
    assert classify(est(0.20), previous=Status.ACTIVE, p_hat_lookback=0.30, t=T) is Status.IMPROVING
    assert classify(est(0.22), previous=Status.ACTIVE, p_hat_lookback=0.30, t=T) is Status.ACTIVE
    assert (
        classify(est(0.05, hi=0.08, n=25), previous=None, p_hat_lookback=None, t=T)
        is Status.MASTERED
    )
    assert (
        classify(est(0.05, hi=0.12, n=25), previous=None, p_hat_lookback=None, t=T)
        is Status.WATCHING
    )
    assert (
        classify(est(0.18), previous=Status.MASTERED, p_hat_lookback=None, t=T) is Status.MASTERED
    )
    assert classify(est(0.21), previous=Status.MASTERED, p_hat_lookback=None, t=T) is Status.ACTIVE
