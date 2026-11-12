from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nosolear.domain.estimates import Prior
from nosolear.domain.packs import (
    MAX_PRIOR_MASS,
    LanguagePack,
    PackError,
    parse_pack,
    validate_pack,
)
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY


def raw_pack(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "demo",
        "name": "Demo",
        "description": "A demo pack.",
        "hypotheses": [{"key": "sound.sub.v.w", "reason": "one v-w sound"}],
        "calibration": {"emphasis": ["sound.sub.v.w"]},
    }
    base.update(overrides)
    return base


def problems_for(raw: dict[str, Any]) -> tuple[str, ...]:
    """Every problem a pack file would report, from parse or validate."""
    try:
        pack = parse_pack(raw)
    except PackError as err:
        return (str(err),)
    return validate_pack(pack, DEFAULT_TAXONOMY)


def test_prior_for_uses_hypothesis_then_default():
    pack = parse_pack(raw_pack())
    assert pack.prior_for("sound.sub.v.w") == Prior(1, 3)
    assert pack.prior_for("sound.sub.f.p") == Prior(1, 9)


def test_valid_pack_has_no_problems():
    assert problems_for(raw_pack()) == ()


def test_explicit_priors_are_kept():
    pack = parse_pack(
        raw_pack(
            default_prior={"a0": 2, "b0": 8},
            hypotheses=[{"key": "sound.sub.v.w", "reason": "r", "prior": {"a0": 2, "b0": 2.5}}],
        )
    )
    assert pack.default_prior == Prior(2, 8)
    assert pack.prior_for("sound.sub.v.w") == Prior(2, 2.5)


def test_minimal_pack_defaults():
    pack = parse_pack({"id": "x", "name": "X", "description": "d", "calibration": {"emphasis": []}})
    assert pack.hypotheses == ()
    assert pack.calibration_extras == ()
    assert pack.default_prior == Prior(1, 9)


def _without(field: str) -> dict[str, Any]:
    raw = raw_pack()
    del raw[field]
    return raw


BAD_PACKS: list[dict[str, Any]] = [
    _without("id"),
    raw_pack(id="NEPALI"),
    raw_pack(id="a/b"),
    raw_pack(id=""),
    raw_pack(name=""),
    raw_pack(name="   "),
    raw_pack(hypotheses=[{"key": "sound.sub.v.w", "reason": ""}]),
    raw_pack(hypotheses=[{"key": "grammar.artcle", "reason": "typo"}]),
    raw_pack(hypotheses=[{"key": "sound.sub.v", "reason": "malformed"}]),
    raw_pack(
        hypotheses=[
            {"key": "sound.sub.v.w", "reason": "a"},
            {"key": "sound.sub.v.w", "reason": "b"},
        ]
    ),
    raw_pack(default_prior={"a0": 0, "b0": 9}),
    raw_pack(default_prior={"a0": 1, "b0": -1}),
    raw_pack(default_prior={"a0": float("nan"), "b0": 9}),
    raw_pack(default_prior={"a0": float("inf"), "b0": 9}),
    raw_pack(default_prior={"a0": 11, "b0": 10}),
    raw_pack(default_prior={"a0": "1", "b0": 9}),
    raw_pack(default_prior={"a0": True, "b0": 9}),
    raw_pack(hypotheses=[{"key": "sound.sub.v.w", "reason": "r", "prior": {"a0": 15, "b0": 6}}]),
    raw_pack(calibration={"emphasis": ["grammar.artcle"]}),
    raw_pack(calibration={"emphasis": ["sound.sub.v.w", "sound.sub.v.w"]}),
    raw_pack(calibration={"emphasis": [], "extras": [{"key": "sound.sub.v.w", "word": "   "}]}),
    raw_pack(calibration={"emphasis": [], "extras": [{"key": "sound.sub.v.w", "word": "x" * 41}]}),
    raw_pack(calibration={"emphasis": [], "extras": [{"key": "sound.sub.v.w", "word": "a\x00b"}]}),
    raw_pack(calibration={"emphasis": [], "extras": [{"key": "nope", "word": "vine"}]}),
    raw_pack(name=5),
    raw_pack(hypotheses="nope"),
    raw_pack(calibration={"emphasis": "sound.sub.v.w"}),
    raw_pack(calibration=None),
]


# The field each BAD_PACKS case must name in its report, in the same order.
BAD_FIELDS: list[str] = [
    "id",
    "id",
    "id",
    "id",
    "name",
    "name",
    "hypotheses[0].reason",
    "hypotheses[0].key",
    "hypotheses[0].key",
    "hypotheses[1].key",
    "default_prior.a0",
    "default_prior.b0",
    "default_prior",
    "default_prior",
    "default_prior",
    "default_prior.a0",
    "default_prior.a0",
    "hypotheses[0].prior",
    "calibration.emphasis[0]",
    "calibration.emphasis[1]",
    "calibration.extras[0].word",
    "calibration.extras[0].word",
    "calibration.extras[0].word",
    "calibration.extras[0].key",
    "name",
    "hypotheses",
    "calibration.emphasis",
    "calibration",
]


@pytest.mark.parametrize(
    ("bad", "field"), list(zip(BAD_PACKS, BAD_FIELDS, strict=True)), ids=range(len(BAD_PACKS))
)
def test_parse_or_validate_reports(bad: dict[str, Any], field: str):
    reported = problems_for(bad)
    assert reported
    assert any(field in problem for problem in reported)


def test_validate_returns_every_problem_not_just_the_first():
    pack = parse_pack(
        raw_pack(
            name="",
            hypotheses=[{"key": "grammar.artcle", "reason": ""}],
            default_prior={"a0": 0, "b0": 9},
        )
    )
    assert len(validate_pack(pack, DEFAULT_TAXONOMY)) >= 4


def test_parse_collects_every_structure_problem():
    with pytest.raises(PackError) as err:
        parse_pack({"id": 1, "name": 2, "description": 3, "calibration": {"emphasis": []}})
    assert all(field in str(err.value) for field in ("id", "name", "description"))


def test_pack_error_messages_name_fields_not_values():
    secret = "sk-very-secret-value"
    with pytest.raises(PackError) as err:
        parse_pack(raw_pack(name=secret + "\x00", description=[secret]))
    assert secret not in str(err.value)


def _pack_with_prior(a0: float, b0: float) -> LanguagePack:
    return parse_pack(raw_pack(default_prior={"a0": a0, "b0": b0}))


_positive = st.floats(min_value=1e-6, max_value=MAX_PRIOR_MASS * 3, allow_nan=False)


@given(a0=_positive, b0=_positive)
def test_prior_mass_boundary(a0: float, b0: float):
    # Includes single values above MAX_PRIOR_MASS, which must always be rejected.
    ok = validate_pack(_pack_with_prior(a0, b0), DEFAULT_TAXONOMY) == ()
    assert ok == (a0 + b0 <= MAX_PRIOR_MASS)
