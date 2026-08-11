"""Face and plate redaction -- step 6 of the ingestion pipeline.

Applied *before* anything is written to storage, so the raw upload never reaches
disk in an identifiable form.

The honesty rule applies to this module as much as to the models. A detector that
is not loaded is reported as ``null`` rather than silently skipped, and the schema
refuses a non-zero blur count without a named detector. The README publishes the
measured miss rate; "we blur faces" is a claim, and a claim needs a number behind it.

**Plates are not redacted in v1.** See ``build_redactor`` for why.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import cv2
import numpy as np

from biovision.schemas.analyze import Privacy

logger = logging.getLogger(__name__)

#: Detectors return a tight box; faces spill past it at the hairline and chin. The
#: box is grown by this fraction on each side before redaction.
_BOX_PADDING = 0.18

#: Target size, in pixels, of one mosaic block. Smaller means coarser redaction.
_MOSAIC_BLOCK = 10

FACE_DETECTOR_NAME = "yunet-2023mar"
YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"


@dataclass(frozen=True)
class Detection:
    """One detected region, as an (x, y, width, height) box in pixels."""

    box: tuple[int, int, int, int]
    score: float


@runtime_checkable
class RegionDetector(Protocol):
    @property
    def name(self) -> str:
        """Identifier recorded in the response, so a result can be traced to a model."""

    def detect(self, bgr: np.ndarray) -> list[Detection]: ...


class YuNetFaceDetector:
    """Face detection via OpenCV's YuNet.

    Chosen because it is small (230 KB), fast enough on CPU to sit in a synchronous
    request, and permissively licensed. It expects BGR, which is why the redactor
    converts once and hands the same buffer to every detector.
    """

    def __init__(self, model_path: Path, score_threshold: float = 0.6) -> None:
        self._detector = cv2.FaceDetectorYN.create(
            str(model_path), "", (320, 320), score_threshold, 0.3, 5000
        )
        self._score_threshold = score_threshold

    @property
    def name(self) -> str:
        return FACE_DETECTOR_NAME

    def detect(self, bgr: np.ndarray) -> list[Detection]:
        height, width = bgr.shape[:2]
        # YuNet requires the input size to be declared before every detect() call;
        # a stale size silently produces boxes in the wrong coordinate frame.
        self._detector.setInputSize((width, height))

        _, raw = self._detector.detect(bgr)
        if raw is None:
            # OpenCV's type stubs declare an ndarray return, but the runtime hands
            # back None when nothing is found -- verified against this build. The
            # check stays; the stub is what is wrong.
            return []  # type: ignore[unreachable]

        detections = []
        for row in raw:
            x, y, w, h = (round(float(v)) for v in row[:4])
            score = float(row[-1])
            if w > 0 and h > 0:
                detections.append(Detection(box=(x, y, w, h), score=score))
        return detections


class Redactor:
    """Applies redaction and reports exactly what it did.

    Either detector may be ``None``. That is a supported state, not a degraded one:
    it means that class of region is not redacted, and the response says so.
    """

    def __init__(
        self,
        face_detector: RegionDetector | None = None,
        plate_detector: RegionDetector | None = None,
    ) -> None:
        self._face = face_detector
        self._plate = plate_detector

    @property
    def face_detector(self) -> RegionDetector | None:
        return self._face

    @property
    def plate_detector(self) -> RegionDetector | None:
        return self._plate

    @property
    def face_detector_name(self) -> str | None:
        return self._face.name if self._face else None

    @property
    def plate_detector_name(self) -> str | None:
        return self._plate.name if self._plate else None

    def apply(self, rgb: np.ndarray) -> tuple[np.ndarray, Privacy]:
        """Redact detected regions and return the result with a privacy report."""
        if self._face is None and self._plate is None:
            return rgb, Privacy()

        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        output = rgb.copy()

        faces = self._run(self._face, bgr, "face")
        plates = self._run(self._plate, bgr, "plate")

        for detection in (*faces, *plates):
            _mosaic_region(output, detection.box)

        return output, Privacy(
            faces_blurred=len(faces),
            plates_blurred=len(plates),
            # Reported only when the count is non-zero *or* the detector ran, so
            # `null` unambiguously means "this class was not redacted".
            face_detector=self.face_detector_name,
            plate_detector=self.plate_detector_name,
        )

    @staticmethod
    def _run(
        detector: RegionDetector | None, bgr: np.ndarray, label: str
    ) -> list[Detection]:
        if detector is None:
            return []
        try:
            return detector.detect(bgr)
        except Exception:
            # A crashing detector must not take the analysis down with it -- but it
            # must also not be mistaken for "found nothing". Phase 6 promotes this
            # to a warning on the response; for now it is loud in the logs.
            logger.exception("%s detector failed; no %s regions were redacted", label, label)
            return []


def _mosaic_region(image: np.ndarray, box: tuple[int, int, int, int]) -> None:
    """Destructively pixelate one region, in place.

    Mosaic rather than Gaussian blur: a blur is a convolution and is at least
    partially invertible, so "blurred" personal data can be recoverable. Downsampling
    to blocks and scaling back up genuinely discards the information.
    """
    height, width = image.shape[:2]
    x, y, w, h = box

    pad_x = round(w * _BOX_PADDING)
    pad_y = round(h * _BOX_PADDING)

    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(width, x + w + pad_x)
    y2 = min(height, y + h + pad_y)

    if x2 <= x1 or y2 <= y1:
        return

    region = image[y1:y2, x1:x2]
    blocks_x = max(1, (x2 - x1) // _MOSAIC_BLOCK)
    blocks_y = max(1, (y2 - y1) // _MOSAIC_BLOCK)

    small = cv2.resize(region, (blocks_x, blocks_y), interpolation=cv2.INTER_AREA)
    image[y1:y2, x1:x2] = cv2.resize(
        small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST
    )


def build_redactor(weights_dir: Path) -> Redactor:
    """Construct the redactor from whatever weights are actually present.

    **Faces:** YuNet, if its checkpoint is on disk. A missing file yields a redactor
    that reports ``face_detector: null`` rather than one that pretends.

    **Plates:** not redacted in v1, and this is a decision rather than an oversight.
    OpenCV 5 removed ``CascadeClassifier``, which takes the bundled Haar plate
    cascade off the table; pinning OpenCV back to 4.x to regain it would trade a
    current dependency for a detector trained on Russian plates whose accuracy on
    Turkish plates is unmeasured. Under the "measure and publish" rule, an
    unmeasured detector may not be shipped as a privacy guarantee.

    Plate redaction is therefore deferred to Phase 5, where Ultralytics arrives for
    the vehicle specialist and brings a YOLO plate detector into reach under a
    licence this project already complies with. Until then every response carries
    ``plate_detector: null``, and the README says plates are not redacted.
    """
    face_detector: RegionDetector | None = None
    model_path = weights_dir / YUNET_FILENAME

    if model_path.is_file():
        try:
            face_detector = YuNetFaceDetector(model_path)
            logger.info("face redaction enabled: %s", FACE_DETECTOR_NAME)
        except Exception:
            logger.exception("YuNet failed to load; faces will NOT be redacted")
    else:
        logger.warning(
            "no face detector at %s -- faces will NOT be redacted. "
            "Run: uv run python scripts/fetch_weights.py",
            model_path,
        )

    return Redactor(face_detector=face_detector, plate_detector=None)
