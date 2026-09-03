"""The severity heuristic.

These tests pin the published bands. They are not accuracy tests -- there is
nothing to be accurate against -- they exist so the numbers in the README and the
numbers in the code cannot drift apart, and so the framing defect below cannot
come back.
"""

from __future__ import annotations

import pytest

from biovision.models.severity import (
    CLASS_FLOOR,
    SEVERITY_MODERATE_MIN_AREA,
    SEVERITY_SEVERE_MIN_AREA,
    severity_for,
    severity_from_area,
)
from biovision.schemas.enums import DamageType, Severity


@pytest.mark.parametrize(
    ("area_ratio", "expected"),
    [
        (0.0, Severity.MINOR),
        (0.019, Severity.MINOR),
        (0.02, Severity.MODERATE),
        (0.079, Severity.MODERATE),
        (0.08, Severity.SEVERE),
        (1.0, Severity.SEVERE),
    ],
)
def test_area_thresholds_match_the_documented_bands(area_ratio: float, expected: Severity) -> None:
    assert severity_from_area(area_ratio) is expected


def test_published_thresholds_are_what_the_readme_says() -> None:
    assert SEVERITY_MODERATE_MIN_AREA == 0.02
    assert SEVERITY_SEVERE_MIN_AREA == 0.08


@pytest.mark.parametrize("area_ratio", [-0.01, 1.5])
def test_out_of_range_input_is_a_bug_not_a_band(area_ratio: float) -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        severity_from_area(area_ratio)


def test_every_damage_class_has_a_floor() -> None:
    """A class absent from the table would silently fall back to minor."""
    assert set(CLASS_FLOOR) == set(DamageType)


@pytest.mark.parametrize("damage_type", list(DamageType))
def test_framing_can_never_lower_a_band(damage_type: DamageType) -> None:
    """The defect this function was rewritten to prevent.

    `area_ratio` divides damaged pixels by the whole image, so photographing the
    same car from further away shrinks it without the damage changing. Measured
    on one VehiDE photograph: 0.2335 as shot, 0.0077 with the frame doubled --
    thirty-fold, and `missing_part` fell from severe to minor. A wrecked car in a
    wide shot, which is what a real claim photograph looks like, reported minor.

    Area may still raise a band. It must never lower one.
    """
    floor = CLASS_FLOOR[damage_type]
    tiny = severity_for(damage_type, 0.0001)  # as if shot from across the road
    close = severity_for(damage_type, 0.9)  # as if shot from arm's length

    assert tiny is floor
    assert _rank(close) >= _rank(tiny)


def test_a_missing_part_is_severe_however_it_was_photographed() -> None:
    """The specific case from the report: a wrecked car in a wide accident scene."""
    for area_ratio in (0.0001, 0.0077, 0.05, 0.2335, 0.9):
        assert severity_for(DamageType.MISSING_PART, area_ratio) is Severity.SEVERE


def test_a_large_scratch_is_raised_by_its_area() -> None:
    """Area still carries information; it is only barred from lowering a band."""
    assert severity_for(DamageType.SCRATCH, 0.001) is Severity.MINOR
    assert severity_for(DamageType.SCRATCH, 0.03) is Severity.MODERATE
    assert severity_for(DamageType.SCRATCH, 0.2) is Severity.SEVERE


def _rank(severity: Severity) -> int:
    return {Severity.MINOR: 0, Severity.MODERATE: 1, Severity.SEVERE: 2}[severity]
