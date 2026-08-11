"""Redaction behaviour and, just as importantly, honest reporting of its absence."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from biovision.pipeline.redact import (
    FACE_DETECTOR_NAME,
    YUNET_FILENAME,
    Redactor,
    build_redactor,
)
from tests.conftest import ExplodingDetector, FixedDetector, make_image

FACE_BOX = (100, 80, 120, 120)
PLATE_BOX = (300, 300, 160, 50)


def _pixels() -> np.ndarray:
    return np.asarray(make_image(seed=9), dtype=np.uint8)


def _region(pixels: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = box
    return pixels[y : y + h, x : x + w]


# ---------------------------------------------------------------------------
# Honest absence
# ---------------------------------------------------------------------------


def test_a_redactor_with_no_detectors_reports_null_not_zero() -> None:
    """`null` means "not redacted". `0` with a named detector means "none found"."""
    original = _pixels()

    output, privacy = Redactor().apply(original)

    assert privacy.face_detector is None
    assert privacy.plate_detector is None
    assert privacy.faces_blurred == 0
    assert np.array_equal(output, original), "nothing should have been touched"


def test_a_detector_that_finds_nothing_is_still_named() -> None:
    """Distinguishes "we looked and found none" from "we did not look"."""
    _, privacy = Redactor(face_detector=FixedDetector("yunet-2023mar", [])).apply(_pixels())

    assert privacy.face_detector == "yunet-2023mar"
    assert privacy.faces_blurred == 0


def test_build_redactor_without_weights_disables_faces(tmp_path: Path) -> None:
    redactor = build_redactor(tmp_path)

    assert redactor.face_detector_name is None
    assert redactor.plate_detector_name is None


def test_plates_are_never_redacted_in_v1(tmp_path: Path) -> None:
    """ADR: OpenCV 5 removed CascadeClassifier, and an unmeasured detector may not
    be shipped as a privacy guarantee. Deferred to Phase 5 with Ultralytics."""
    assert build_redactor(tmp_path).plate_detector_name is None


# ---------------------------------------------------------------------------
# Redaction actually destroys information
# ---------------------------------------------------------------------------


def test_detected_regions_are_altered() -> None:
    original = _pixels()
    detector = FixedDetector(FACE_DETECTOR_NAME, [FACE_BOX])

    output, privacy = Redactor(face_detector=detector).apply(original)

    assert privacy.faces_blurred == 1
    assert privacy.face_detector == FACE_DETECTOR_NAME
    assert not np.array_equal(_region(output, FACE_BOX), _region(original, FACE_BOX))


def test_redaction_discards_detail_rather_than_smoothing_it() -> None:
    """Mosaic, not Gaussian blur: a convolution is at least partly invertible.

    Within one mosaic block every pixel is identical, so the fine structure is gone
    rather than attenuated.
    """
    original = _pixels()
    output, _ = Redactor(face_detector=FixedDetector("d", [FACE_BOX])).apply(original)

    before = _region(original, FACE_BOX)
    after = _region(output, FACE_BOX)

    assert after.std() < before.std(), "redacted region should carry less variation"
    # A 2x2 patch well inside the region falls within one mosaic block.
    patch = after[10:12, 10:12]
    assert len(np.unique(patch.reshape(-1, 3), axis=0)) == 1


def test_pixels_outside_the_box_are_untouched() -> None:
    original = _pixels()
    output, _ = Redactor(face_detector=FixedDetector("d", [FACE_BOX])).apply(original)

    far_corner = (slice(400, 460), slice(500, 600))
    assert np.array_equal(output[far_corner], original[far_corner])


def test_the_input_array_is_not_mutated() -> None:
    """The caller's buffer is still needed -- the hash was taken from it."""
    original = _pixels()
    snapshot = original.copy()

    Redactor(face_detector=FixedDetector("d", [FACE_BOX])).apply(original)

    assert np.array_equal(original, snapshot)


def test_multiple_regions_are_all_redacted() -> None:
    boxes = [(50, 50, 60, 60), (200, 150, 80, 80), (400, 300, 100, 90)]
    _, privacy = Redactor(face_detector=FixedDetector("d", boxes)).apply(_pixels())

    assert privacy.faces_blurred == 3


def test_faces_and_plates_are_counted_separately() -> None:
    output, privacy = Redactor(
        face_detector=FixedDetector("face-model", [FACE_BOX]),
        plate_detector=FixedDetector("plate-model", [PLATE_BOX]),
    ).apply(_pixels())

    assert privacy.faces_blurred == 1
    assert privacy.plates_blurred == 1
    assert privacy.face_detector == "face-model"
    assert privacy.plate_detector == "plate-model"
    assert output.shape == _pixels().shape


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "box",
    [
        (-40, -40, 100, 100),  # partly off the top-left
        (600, 440, 200, 200),  # partly off the bottom-right
        (0, 0, 640, 480),  # the entire image
    ],
)
def test_boxes_crossing_the_border_are_clipped(box: tuple[int, int, int, int]) -> None:
    """Padding pushes boxes outside the frame; a naive slice would wrap or crash."""
    output, privacy = Redactor(face_detector=FixedDetector("d", [box])).apply(_pixels())

    assert privacy.faces_blurred == 1
    assert output.shape == (480, 640, 3)


def test_a_degenerate_box_is_ignored_without_crashing() -> None:
    output, _ = Redactor(face_detector=FixedDetector("d", [(700, 500, 10, 10)])).apply(
        _pixels()
    )

    assert output.shape == (480, 640, 3)


def test_a_crashing_detector_does_not_take_the_request_down() -> None:
    """It must also not be mistaken for "found nothing" -- hence the log."""
    original = _pixels()

    output, privacy = Redactor(face_detector=ExplodingDetector()).apply(original)

    assert privacy.faces_blurred == 0
    assert np.array_equal(output, original)


def test_a_crashing_detector_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("ERROR"):
        Redactor(face_detector=ExplodingDetector()).apply(_pixels())

    assert "face detector failed" in caplog.text


# ---------------------------------------------------------------------------
# The real detector, when its weights are present
# ---------------------------------------------------------------------------


@pytest.mark.weights
def test_yunet_loads_when_the_checkpoint_is_present() -> None:
    """Skipped in CI, which deliberately has no weights."""
    from biovision.config import BACKEND_ROOT

    model_path = BACKEND_ROOT / "weights" / YUNET_FILENAME
    if not model_path.is_file():
        pytest.skip(f"{YUNET_FILENAME} not downloaded")

    redactor = build_redactor(model_path.parent)

    assert redactor.face_detector_name == FACE_DETECTOR_NAME
    # A synthetic gradient contains no faces; the assertion is that it runs and
    # reports zero rather than that it detects anything.
    _, privacy = redactor.apply(_pixels())
    assert privacy.faces_blurred == 0
    assert privacy.face_detector == FACE_DETECTOR_NAME
