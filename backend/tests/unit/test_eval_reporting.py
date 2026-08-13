"""The arithmetic behind the tables the README publishes.

These functions had no tests until the evaluation scripts were run for the first
time. That gap mattered more than it looks: they are the last step between a
model's behaviour and a number a reader takes on trust, and an error here is
invisible -- the table still renders, still looks measured, and is wrong. The
models themselves are not the risk; a miscounted confusion cell is.

Nothing here needs weights or images, so it runs in CI on every commit.
"""

from __future__ import annotations

import numpy as np
import pytest
from scripts.eval_redaction import Tally, iou, score
from scripts.eval_router import confusion, markdown_matrix, threshold_sweep

from biovision.models.calibration import MIN_CALIBRATION_SAMPLES
from biovision.pipeline.redact import Detection

KEYS = ["vehicle", "building", "other"]


# ---------------------------------------------------------------------------
# Confusion matrix
# ---------------------------------------------------------------------------


def test_a_perfect_classifier_fills_only_the_diagonal() -> None:
    truth = ["vehicle", "building", "other"]
    matrix = confusion(truth, list(truth), KEYS)

    assert np.array_equal(matrix, np.eye(3, dtype=int))


def test_rows_are_truth_and_columns_are_predictions() -> None:
    """Transposing this matrix would swap recall and precision silently."""
    matrix = confusion(["vehicle", "vehicle"], ["building", "building"], KEYS)

    assert matrix[0, 1] == 2, "two vehicles predicted as building"
    assert matrix[1, 0] == 0


def test_a_prediction_outside_the_catalogue_is_not_counted_as_correct() -> None:
    """`unknown` is what the router returns below its threshold. Counting it
    anywhere on the diagonal would turn an abstention into a success."""
    matrix = confusion(["vehicle"], ["unknown"], KEYS)

    assert matrix.sum() == 0


def test_recall_is_computed_per_row_not_overall() -> None:
    """The whole point of the table is that a strong row cannot hide a weak one."""
    matrix = confusion(
        ["vehicle"] * 10 + ["building"] * 10,
        ["vehicle"] * 10 + ["vehicle"] * 10,
        KEYS,
    )
    rendered = markdown_matrix(matrix, KEYS)

    assert "| **vehicle** | 10 | 0 | 0 | 100% |" in rendered
    assert "| **building** | 10 | 0 | 0 | 0% |" in rendered, "the bad row must appear"


def test_a_class_with_no_examples_reports_na_rather_than_zero() -> None:
    """0% would read as "the model fails at this", when nothing was tested."""
    matrix = confusion(["vehicle"], ["vehicle"], KEYS)

    assert "| **other** | 0 | 0 | 0 | n/a |" in markdown_matrix(matrix, KEYS)


# ---------------------------------------------------------------------------
# Threshold sweep
# ---------------------------------------------------------------------------


def test_coverage_falls_and_accuracy_rises_as_the_threshold_climbs() -> None:
    confidences = np.array([0.2, 0.4, 0.6, 0.9])
    correct = np.array([False, False, True, True])

    rendered = threshold_sweep(confidences, correct, [0.0, 0.5])

    assert "| 0.00 | 100% | 50.0% |" in rendered
    assert "| 0.50 | 50% | 100.0% |" in rendered


def test_a_threshold_nothing_reaches_reports_nan_not_perfection() -> None:
    """An empty numerator must never render as 100%: refusing everything would
    look like the best row in the table."""
    rendered = threshold_sweep(np.array([0.1]), np.array([True]), [0.9])

    assert "| 0.90 | 0% |" in rendered
    assert "100.0%" not in rendered


# ---------------------------------------------------------------------------
# Redaction scoring
# ---------------------------------------------------------------------------


def test_iou_is_zero_for_disjoint_boxes() -> None:
    assert iou((0, 0, 10, 10), (50, 50, 10, 10)) == 0.0


def test_iou_is_one_for_identical_boxes() -> None:
    assert iou((5, 5, 20, 20), (5, 5, 20, 20)) == pytest.approx(1.0)


def test_touching_edges_do_not_count_as_overlap() -> None:
    assert iou((0, 0, 10, 10), (10, 0, 10, 10)) == 0.0


def test_a_detection_is_consumed_by_the_box_it_matches() -> None:
    """Two faces and one detection must be one hit and one miss.

    Without consumption the single detection would match both boxes and the
    miss rate -- the number the privacy claim rests on -- would read zero.
    """
    tally = Tally()
    detections = [Detection(box=(0, 0, 10, 10), score=0.9)]

    score(detections, [(0, 0, 10, 10), (100, 100, 10, 10)], tally)

    assert (tally.hits, tally.misses, tally.false_positives) == (1, 1, 0)


def test_an_unmatched_detection_is_a_false_positive_not_a_hit() -> None:
    tally = Tally()
    detections = [Detection(box=(200, 200, 10, 10), score=0.9)]

    score(detections, [(0, 0, 10, 10)], tally)

    assert (tally.hits, tally.misses, tally.false_positives) == (0, 1, 1)


def test_recall_is_none_when_nothing_was_annotated() -> None:
    """`n/a` and `0%` are different claims. Plates are currently the former."""
    assert Tally().recall is None
    assert Tally().miss_rate is None


def test_miss_rate_and_recall_are_complements() -> None:
    tally = Tally(hits=3, misses=1)

    assert tally.recall == pytest.approx(0.75)
    assert tally.miss_rate == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# The floor under "calibrated"
# ---------------------------------------------------------------------------


def test_the_calibration_floor_is_high_enough_to_reject_an_accidental_run() -> None:
    """Guards the constant itself.

    A first run of calibrate_router.py against twelve throwaway images produced
    a temperature, an ECE, and a file that made every response report
    `calibrated: true`. ECE over that many samples is noise; a label reading
    "calibrated" attached to noise is the failure this project exists to avoid.
    """
    assert MIN_CALIBRATION_SAMPLES >= 100
