"""Temperature scaling for the router.

A softmax output is not a probability. Left uncalibrated it is systematically
overconfident, and "93% confident this is a vehicle" would be a number with no
defensible meaning -- which is the one thing this project cannot ship.

Temperature scaling is the minimal honest fix: divide the logits by a single scalar
fitted on a held-out split. It cannot change which class wins, so accuracy is
untouched; it only rescales how sure the model claims to be.

**This module loads a fitted temperature; it does not fit one.** Fitting happens in
`scripts/calibrate_router.py` during Phase 4. Until that artifact exists,
:func:`load_calibration` returns ``None``, the router reports
``domain_confidence_calibrated: false``, and every response says so.
"""

from __future__ import annotations

import itertools
import json
import logging
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

CALIBRATION_FILENAME = "router_calibration.json"

#: Below this many calibration samples the fitted temperature is refused.
#:
#: Found by running `calibrate_router.py` for the first time, against a throwaway
#: synthetic set: twelve images produced a temperature, an ECE, and a file that
#: made every subsequent response report `calibrated: true`. Nothing was wrong
#: with the arithmetic -- ECE over twelve samples spread across fifteen bins is
#: simply noise, and a label saying "calibrated" attached to noise is the exact
#: failure this project exists to avoid.
#:
#: 100 is a floor, not a recommendation. Temperature scaling fits one parameter,
#: so a few hundred samples is the usual guidance; the planned set (~50 images
#: per domain, split between fitting and evaluation) clears this comfortably. It
#: is set where it is to catch an accidental run, not to bless a small one.
MIN_CALIBRATION_SAMPLES = 100


class Calibration(BaseModel):
    """A fitted temperature and the evidence that justifies it.

    The metrics are stored alongside the parameter deliberately. A temperature with
    no record of what it improved is a magic number, and the README quotes these
    figures -- so they travel with the artifact rather than living in a commit
    message that will drift.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: float = Field(gt=0.0, description="Logits are divided by this.")
    ece_before: float = Field(ge=0.0, le=1.0)
    ece_after: float = Field(ge=0.0, le=1.0)
    accuracy: float = Field(ge=0.0, le=1.0)
    n_samples: int = Field(gt=0)
    fitted_on: str = Field(description="Identifier of the calibration split.")
    model_id: str = Field(description="Encoder this was fitted for; a mismatch is fatal.")

    def apply(self, logits: np.ndarray) -> np.ndarray:
        return (logits / self.temperature).astype(np.float32)


def load_calibration(path: Path, expected_model_id: str) -> Calibration | None:
    """Load a fitted calibration, or ``None`` if there is not a valid one.

    Returns ``None`` rather than raising: an uncalibrated router is a supported
    state that the API reports truthfully, not a failure. The one thing that must
    not happen is claiming calibration that does not apply -- so a temperature
    fitted for a different encoder is refused, not used.
    """
    if not path.is_file():
        logger.info("no calibration at %s; confidences will be reported uncalibrated", path)
        return None

    try:
        calibration = Calibration.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        logger.exception("calibration at %s is unreadable; continuing uncalibrated", path)
        return None

    if calibration.n_samples < MIN_CALIBRATION_SAMPLES:
        # Refused rather than used with a caveat: `calibrated` is a boolean the UI
        # renders as a claim, and there is no way to render "calibrated, but on
        # too little data to mean anything". Uncalibrated is the truthful state.
        logger.error(
            "calibration was fitted on %d samples, below the %d-sample floor; ignoring it. "
            "Confidences will be reported uncalibrated, which is the honest answer for a "
            "temperature this thinly evidenced.",
            calibration.n_samples,
            MIN_CALIBRATION_SAMPLES,
        )
        return None

    if calibration.model_id != expected_model_id:
        # Temperature is a property of a specific model's logit distribution.
        # Reusing one across encoders would produce confident nonsense.
        logger.error(
            "calibration was fitted for %r but the loaded encoder is %r; ignoring it",
            calibration.model_id,
            expected_model_id,
        )
        return None

    logger.info(
        "calibration loaded: T=%.4f, ECE %.4f -> %.4f on %d samples",
        calibration.temperature,
        calibration.ece_before,
        calibration.ece_after,
        calibration.n_samples,
    )
    return calibration


def expected_calibration_error(
    confidences: np.ndarray, correct: np.ndarray, n_bins: int = 15
) -> float:
    """Expected Calibration Error: the gap between claimed and actual accuracy.

    Predictions are binned by confidence; within each bin, |mean confidence - mean
    accuracy| is weighted by the bin's share of samples. A perfectly calibrated
    model scores 0: when it says 70%, it is right 70% of the time.

    Lives here rather than in the fitting script so that the number in the README
    and the number a regression test asserts come from the same implementation.
    """
    if confidences.shape != correct.shape:
        raise ValueError("confidences and correct must have the same shape")
    if confidences.size == 0:
        raise ValueError("cannot compute ECE over an empty set")

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = confidences.size
    error = 0.0

    for lower, upper in itertools.pairwise(edges):
        # Half-open bins, with the top bin closed so confidence exactly 1.0 counts.
        in_bin = (confidences > lower) & (confidences <= upper)
        if upper == edges[-1]:
            in_bin |= confidences == lower
        count = int(in_bin.sum())
        if count == 0:
            continue
        error += (count / total) * abs(
            float(confidences[in_bin].mean()) - float(correct[in_bin].mean())
        )

    return error
