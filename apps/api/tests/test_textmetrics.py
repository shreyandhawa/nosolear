import pytest
from textmetrics import word_error_rate


@pytest.mark.parametrize(
    ("reference", "hypothesis", "expected"),
    [
        ("a b c", "a b c", 0.0),
        ("A, B c!", "a b C", 0.0),
        ("a b c", "a c", 1 / 3),
        ("a b", "x y z", 1.5),
        ("", "", 0.0),
        ("", "hello", 1.0),
    ],
)
def test_word_error_rate(reference, hypothesis, expected):
    assert word_error_rate(reference, hypothesis) == pytest.approx(expected)
