"""Calibration fixtures: two keys with real words, so the oracle hears their respellings.

Import as `from calibration_fixtures import small_content, SMALL_SET`.
"""

from nosolear.domain.calibration_items import CalibrationSpec
from nosolear.domain.content import BaselineProtocol, SeedContent, calibration_set

SMALL_SET = calibration_set(
    [
        CalibrationSpec(
            "sound.sub.v.w",
            "W instead of V",
            (
                ("vest", "west"),
                ("very", "wery"),
                ("van", "wan"),
                ("vine", "wine"),
                ("veil", "wail"),
            ),
        ),
        CalibrationSpec(
            "sound.sub.f.p",
            "P instead of F",
            (
                ("fan", "pan"),
                ("fine", "pine"),
                ("coffee", "coppee"),
                ("fast", "past"),
                ("feel", "peel"),
            ),
        ),
    ]
)
EMPTY_PROTOCOL = BaselineProtocol(version=1, sections=(), stress_pairs=())


def small_content() -> SeedContent:
    return SeedContent(SMALL_SET, EMPTY_PROTOCOL)
