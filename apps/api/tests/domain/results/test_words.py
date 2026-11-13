import math

from hypothesis import given
from hypothesis import strategies as st

from nosolear.domain.results.words import clean_word_timings

# The brief's `allow_nan=True` with min/max bounds is refused by Hypothesis, so the non-finite
# values are added explicitly.
times = st.one_of(
    st.floats(min_value=-1e6, max_value=1e7),
    st.sampled_from([math.nan, math.inf, -math.inf]),
)


@given(st.lists(st.tuples(st.text(max_size=8), times, times, st.none())))
def test_cleaned_timings_are_sorted_and_sane(words):
    out = clean_word_timings(words)
    assert all(0 <= w.start_ms <= w.end_ms for w in out)
    assert [w.start_ms for w in out] == sorted(w.start_ms for w in out)
    assert all(w.text and w.text == w.text.strip() for w in out)


def test_blank_and_non_finite_words_are_dropped():
    out = clean_word_timings(
        [
            ("  ", 0.0, 10.0, None),
            ("bad", math.nan, 10.0, None),
            ("worse", 0.0, math.inf, None),
            ("  hi ", 12.4, 20.6, 0.9),
        ]
    )
    assert [(w.text, w.start_ms, w.end_ms, w.confidence) for w in out] == [("hi", 12, 21, 0.9)]


def test_negative_times_clamp_to_zero_and_end_never_precedes_start():
    out = clean_word_timings([("a", -5.0, -9.0, None)])
    assert (out[0].start_ms, out[0].end_ms) == (0, 0)
