"""Calibration loading and the ECE metric.

Fitting happens in Phase 4. What is tested here is the part that ships now: that an
absent or inapplicable calibration degrades to "uncalibrated" rather than to a
confident lie.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from biovision.models.calibration import (
    Calibration,
    expected_calibration_error,
    load_calibration,
)
from biovision.models.scoring import softmax

MODEL_ID = "ViT-B-32/laion2b_s34b_b79k"


def _write(path: Path, **overrides: object) -> Path:
    payload = {
        "temperature": 1.35,
        "ece_before": 0.184,
        "ece_after": 0.041,
        "accuracy": 0.88,
        "n_samples": 200,
        "fitted_on": "router_calib_v1",
        "model_id": MODEL_ID,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def test_a_valid_calibration_loads(tmp_path: Path) -> None:
    calibration = load_calibration(_write(tmp_path / "c.json"), MODEL_ID)

    assert calibration is not None
    assert calibration.temperature == 1.35
    assert calibration.ece_after < calibration.ece_before


def test_a_missing_file_yields_none_rather_than_raising(tmp_path: Path) -> None:
    """An uncalibrated router is a supported state the API reports truthfully."""
    assert load_calibration(tmp_path / "absent.json", MODEL_ID) is None


def test_a_calibration_for_a_different_encoder_is_refused(tmp_path: Path) -> None:
    """Temperature is a property of one model's logit distribution.

    Reusing it across encoders would produce confident nonsense -- worse than no
    calibration, because the response would claim to be calibrated.
    """
    path = _write(tmp_path / "c.json", model_id="ViT-L-14/openai")

    assert load_calibration(path, MODEL_ID) is None


def test_a_corrupt_file_degrades_to_uncalibrated(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    path.write_text("{ not json at all", encoding="utf-8")

    assert load_calibration(path, MODEL_ID) is None


def test_a_non_positive_temperature_is_rejected(tmp_path: Path) -> None:
    assert load_calibration(_write(tmp_path / "c.json", temperature=0.0), MODEL_ID) is None


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------


def test_temperature_scaling_cannot_reorder_classes() -> None:
    """The whole point: accuracy is untouched, only confidence moves."""
    logits = np.array([4.0, 1.0, 2.5, 0.2], dtype=np.float32)
    calibration = Calibration(
        temperature=2.5,
        ece_before=0.2,
        ece_after=0.05,
        accuracy=0.9,
        n_samples=100,
        fitted_on="test",
        model_id=MODEL_ID,
    )

    scaled = calibration.apply(logits)

    assert np.argmax(scaled) == np.argmax(logits)
    assert np.argsort(scaled).tolist() == np.argsort(logits).tolist()


def test_a_temperature_above_one_reduces_confidence() -> None:
    """Overconfidence is the failure temperature scaling exists to correct."""
    logits = np.array([6.0, 2.0, 1.0], dtype=np.float32)
    calibration = Calibration(
        temperature=3.0,
        ece_before=0.2,
        ece_after=0.05,
        accuracy=0.9,
        n_samples=100,
        fitted_on="test",
        model_id=MODEL_ID,
    )

    assert softmax(calibration.apply(logits)).max() < softmax(logits).max()


# ---------------------------------------------------------------------------
# ECE
# ---------------------------------------------------------------------------


def test_perfect_calibration_scores_zero() -> None:
    """Claiming 100% and being right every time is ECE 0."""
    confidences = np.ones(100, dtype=np.float32)
    correct = np.ones(100, dtype=np.float32)

    assert expected_calibration_error(confidences, correct) == pytest.approx(0.0)


def test_total_overconfidence_scores_one() -> None:
    """Claiming 100% and being wrong every time is the worst possible score."""
    confidences = np.ones(100, dtype=np.float32)
    correct = np.zeros(100, dtype=np.float32)

    assert expected_calibration_error(confidences, correct) == pytest.approx(1.0)


def test_a_well_calibrated_model_scores_near_zero() -> None:
    """Says 70%, right 70% of the time."""
    confidences = np.full(100, 0.7, dtype=np.float32)
    correct = np.array([1.0] * 70 + [0.0] * 30, dtype=np.float32)

    assert expected_calibration_error(confidences, correct) < 0.01


def test_overconfidence_is_detected() -> None:
    """Says 95%, right 60% of the time -- a gap of roughly 0.35."""
    confidences = np.full(100, 0.95, dtype=np.float32)
    correct = np.array([1.0] * 60 + [0.0] * 40, dtype=np.float32)

    assert expected_calibration_error(confidences, correct) == pytest.approx(0.35, abs=0.01)


def test_mismatched_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="same shape"):
        expected_calibration_error(np.ones(5), np.ones(3))


def test_an_empty_set_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        expected_calibration_error(np.array([]), np.array([]))
