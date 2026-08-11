"""The severity heuristic.

These tests pin the published thresholds. They are not accuracy tests -- there is
nothing to be accurate against -- they exist so the numbers in the README and the
numbers in the code cannot drift apart.
"""

from __future__ import annotations

import pytest

from biovision.models.severity import (
    SEVERITY_MODERATE_MIN_AREA,
    SEVERITY_SEVERE_MIN_AREA,
    severity_for,
)
from biovision.schemas.enums import Severity


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
def test_thresholds_match_the_documented_bands(area_ratio: float, expected: Severity) -> None:
    assert severity_for(area_ratio) is expected


def test_published_thresholds_are_what_the_readme_says() -> None:
    assert SEVERITY_MODERATE_MIN_AREA == 0.02
    assert SEVERITY_SEVERE_MIN_AREA == 0.08


@pytest.mark.parametrize("area_ratio", [-0.01, 1.5])
def test_out_of_range_input_is_a_bug_not_a_band(area_ratio: float) -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        severity_for(area_ratio)
