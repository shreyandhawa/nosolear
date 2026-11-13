import pytest
from hypothesis import given
from hypothesis import strategies as st

from nosolear.domain.phone_alignment import align_phones
from nosolear.domain.phones import AZURE_PHONES


def ops(edits):
    return [(e.op, e.expected, e.heard, e.expected_index) for e in edits]


def test_epenthesis_before_s_cluster_is_an_insertion():
    assert ops(align_phones(["s", "k", "u", "l"], ["ɪ", "s", "k", "u", "l"]))[0] == (
        "ins",
        None,
        "ɪ",
        0,
    )


def test_v_for_w_is_a_substitution():
    assert ops(align_phones(["v", "ɛ", "s", "t"], ["w", "ɛ", "s", "t"]))[0] == (
        "sub",
        "v",
        "w",
        0,
    )


def test_dropped_final_consonant_is_a_deletion():
    assert ops(align_phones(["t", "ɛ", "s", "t"], ["t", "ɛ", "s"]))[-1] == ("del", "t", None, 3)


def test_insertion_at_the_end_points_past_the_last_phone():
    assert ops(align_phones(["t"], ["t", "s"]))[-1] == ("ins", None, "s", 1)


def test_substitution_beats_delete_and_insert_even_across_classes():
    # A sub costs 1.0 within a class and 1.5 across classes, both less than a delete plus an
    # insert (2.0), so each single-phone swap stays one substitution.
    assert ops(align_phones(["ɛ"], ["ɪ"])) == [("sub", "ɛ", "ɪ", 0)]
    assert ops(align_phones(["ɛ"], ["t"])) == [("sub", "ɛ", "t", 0)]


def test_an_unknown_phone_is_refused():
    with pytest.raises(ValueError):
        align_phones(["q"], ["t"])


phones = st.lists(st.sampled_from(sorted(AZURE_PHONES)), max_size=12)


@given(phones, phones)
def test_alignment_reproduces_both_sides(expected, heard):
    edits = align_phones(expected, heard)
    assert [e.expected for e in edits if e.op != "ins"] == expected
    assert [e.heard for e in edits if e.op != "del"] == heard


@given(phones)
def test_identical_lists_are_all_matches(p):
    assert all(e.op == "match" for e in align_phones(p, p))


@given(phones, phones)
def test_insertions_and_deletions_are_consistent(expected, heard):
    edits = align_phones(expected, heard)
    for e in edits:
        assert 0 <= e.expected_index <= len(expected)
        if e.op == "del":
            assert e.expected == expected[e.expected_index]
