"""The building specialist, and the two numbers it is obliged to carry.

It was nearly not connected, on a measurement that skipped two layers. Fed the
fifteen reviewed intact rooms directly, the checkpoint flags **15 of 15**. Posted
through the live pipeline the same fifteen produce **1 of 15**, because the gate
rejects seven as not-damage photographs and the router sends seven to `other`;
on 60 cracked walls it finds 59. The first number is about the checkpoint, the
second about the product, and only the second is what a claimant meets.

These tests pin the carrying of both, and the caveat that goes with sets this
small — not the model's accuracy, which lives in README 7.11.
"""

from __future__ import annotations

import numpy as np
import pytest

from biovision.models.specialists.building_crack import (
    FALSE_ALARM_ROOMS,
    FALSE_ALARM_TOTAL,
    GRID,
    HELD_OUT_ACCURACY,
    ISOLATED_FALSE_ALARM_ROOMS,
    ISOLATED_FALSE_ALARM_TOTAL,
    RECALL_FOUND,
    RECALL_TOTAL,
    THRESHOLD,
    WARNING_TR,
    tiles,
)
from biovision.pipeline.orchestrator import SMALL_EVALUATION_BELOW, _specialist_caveat
from biovision.schemas.analyze import Finding
from biovision.schemas.enums import DamageType, Severity, WarningCode

EVALUATION_SIZE = RECALL_TOTAL + FALSE_ALARM_TOTAL


def a_finding() -> Finding:
    return Finding(
        type=DamageType.CRACK,
        score=0.9,
        bbox=(0, 0, 10, 10),
        area_ratio=0.01,
        severity=Severity.MINOR,
        class_recall=RECALL_FOUND / RECALL_TOTAL,
        class_reliable=True,
    )


def test_both_false_alarm_numbers_are_kept() -> None:
    """Quoting only the friendlier one would be choosing the measurement that
    flatters the decision, which is the move this project refuses elsewhere."""
    assert (FALSE_ALARM_ROOMS, FALSE_ALARM_TOTAL) == (1, 15)
    assert (ISOLATED_FALSE_ALARM_ROOMS, ISOLATED_FALSE_ALARM_TOTAL) == (15, 15)


def test_the_end_to_end_recall_is_what_was_measured() -> None:
    assert (RECALL_FOUND, RECALL_TOTAL) == (59, 60)


def test_the_held_out_score_is_kept_beside_the_field_numbers() -> None:
    """0.9986 on METU's own split, against 1/15 and 59/60 through the pipeline.
    Separating them would let either be quoted alone."""
    assert HELD_OUT_ACCURACY > 0.99


def test_the_turkish_warning_states_both_measurements_and_the_legal_limit() -> None:
    assert f"{RECALL_FOUND}" in WARNING_TR and f"{RECALL_TOTAL}" in WARNING_TR
    assert "eksper" in WARNING_TR
    assert "tespiti değil" in WARNING_TR


def test_the_threshold_is_the_trained_default() -> None:
    """Not tuned. The sweep showed no threshold separates rooms from walls in
    isolation, so a number picked from those fifteen rooms would be picked by
    looking at the answer."""
    assert THRESHOLD == 0.5


def test_a_small_evaluation_earns_a_caveat() -> None:
    assert EVALUATION_SIZE < SMALL_EVALUATION_BELOW
    caveat = _specialist_caveat([a_finding()], EVALUATION_SIZE)
    assert caveat is WarningCode.SPECIALIST_SMALL_EVALUATION


def test_a_larger_evaluation_earns_silence() -> None:
    """Driven by the size of the evidence rather than a specialist's name, so a
    future model earns quiet by being measured on more, not by being trusted."""
    assert _specialist_caveat([a_finding()], SMALL_EVALUATION_BELOW) is None


def test_a_specialist_that_declares_no_size_is_not_caveated_by_guesswork() -> None:
    assert _specialist_caveat([a_finding()], None) is None


def test_no_findings_means_no_warning() -> None:
    """A photograph the model said nothing about needs no caveat about what it
    would have said."""
    assert _specialist_caveat([], EVALUATION_SIZE) is None


def test_a_crack_finding_can_never_be_severe() -> None:
    """AFAD's yönetmelik m.6/3 requires settlement, wear and construction
    defects to be excluded from a damage grade, and a photograph cannot do that.
    So the class floor is the lowest available and area cannot raise it."""
    from biovision.models.severity import CLASS_FLOOR, severity_for

    assert CLASS_FLOOR[DamageType.CRACK] is Severity.MINOR
    assert severity_for(DamageType.CRACK, 0.0) is Severity.MINOR


@pytest.mark.parametrize(("grid", "expected"), [(0, 1), (1, 1), (2, 5), (3, 10), (4, 17)])
def test_tile_count_is_the_grid_plus_the_whole_frame(grid: int, expected: int) -> None:
    assert len(tiles(np.zeros((480, 640, 3), dtype=np.uint8), grid)) == expected


def test_the_default_grid_matches_the_published_measurement() -> None:
    """README 7.11's tables are 4x4. A different grid here would make the shipped
    behaviour and the published numbers describe different procedures."""
    assert GRID == 4


def test_the_whole_frame_is_first_so_it_can_be_excluded_from_findings() -> None:
    """A box around the entire photograph locates nothing, and reporting it
    would make the damaged-area ratio 1.0 on any photograph the model dislikes."""
    assert tiles(np.zeros((400, 600, 3), dtype=np.uint8), 4)[0] == (0, 0, 600, 400)


def test_a_tiny_image_degrades_to_the_whole_frame() -> None:
    assert len(tiles(np.zeros((40, 40, 3), dtype=np.uint8), 4)) == 1
