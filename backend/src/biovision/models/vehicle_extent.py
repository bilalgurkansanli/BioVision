"""How much of the frame is the car, so a damage percentage can mean something.

A user looked at "dent 42%" and asked the right question: **42% of what?** Of the
photograph. Which makes the number a measure of where the photographer stood --
README 7.5 measures the same damage moving thirty-fold across four crops of one
image.

Dividing by the vehicle instead of the frame is the obvious repair and it has one
real cost: it needs a second network, and the second network sometimes finds no
vehicle. That failure is not hidden here. `extent()` returns `None`, the ratio it
would have produced is reported as `null`, and the response says the vehicle was
not located rather than quietly falling back to the frame -- a silent fallback
would make the same field mean two different things between two requests, which
is worse than the field being absent.

**Stock COCO weights, deliberately.** `yolo11n-seg` already segments car, truck,
bus and motorcycle, and nothing about a claim photograph makes those harder than
the images it was trained on. Fine-tuning would add a checkpoint to maintain and
a number to justify for no expected gain; if the availability measured in
`scripts/eval_vehicle_normalisation.py` were the bottleneck, that would be the
moment to reconsider, and it is measured for exactly that reason.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from biovision.models.mask_geometry import rasterise, working_size

logger = logging.getLogger(__name__)

VEHICLE_EXTENT_FILENAME = "yolo11n-seg.pt"
MODEL_NAME = "yolo11n-seg-coco"

#: car, motorcycle, bus, truck. A claimant photographing "my vehicle" photographs
#: one of these; the remaining 76 COCO classes are noise for this question and
#: passing the filter to `predict` also saves the postprocessing on them.
VEHICLE_COCO_IDS = (2, 3, 5, 7)

#: Lower than a detection threshold would normally be. A partly-visible car in a
#: close-up is a weak detection but a real one, and the cost of a false vehicle
#: mask is bounded -- the damage is intersected with it, so a spurious mask can
#: only shrink the reported ratio, never invent damage.
DEFAULT_CONFIDENCE = 0.15


@dataclass(frozen=True)
class VehicleExtent:
    """The vehicle's footprint, in the shared working plane."""

    #: Boolean plane, `mask_geometry.working_size` of the source image.
    mask: np.ndarray
    #: Fraction of the photograph the vehicle occupies. Reported because it is
    #: the framing measurement itself: 0.9 is a close-up, 0.05 is a street scene.
    frame_share: float
    instances: int


class VehicleExtentModel:
    """Stock COCO segmentation, filtered to vehicles."""

    def __init__(
        self,
        weights_path: Path,
        confidence: float = DEFAULT_CONFIDENCE,
        num_threads: int = 2,
    ) -> None:
        import torch
        from ultralytics import YOLO

        torch.set_num_threads(max(1, num_threads))
        logger.info("loading vehicle extent model from %s", weights_path)
        self._model = YOLO(str(weights_path), task="segment")
        self._confidence = confidence
        self._ready = True

    @property
    def name(self) -> str:
        return MODEL_NAME

    @property
    def ready(self) -> bool:
        return self._ready

    def extent(self, rgb: np.ndarray) -> VehicleExtent | None:
        """The vehicle footprint, or None when no vehicle was located.

        None is a first-class answer. Close-ups of a wing are the case it fails
        on -- and they are also the case where dividing by the frame is nearly
        right, because the frame is nearly all car. The two failures cancel, but
        only if the caller is told which one it has.
        """
        height, width = rgb.shape[:2]
        results = list(
            self._model.predict(
                rgb,
                conf=self._confidence,
                classes=list(VEHICLE_COCO_IDS),
                verbose=False,
                device="cpu",
            )
        )
        if not results:
            return None
        masks = getattr(results[0], "masks", None)
        if masks is None or masks.xy is None or len(masks.xy) == 0:
            return None

        plane = working_size((width, height))
        mask = rasterise(list(masks.xy), (width, height), plane)
        covered = float(mask.sum())
        if covered <= 0:
            return None

        return VehicleExtent(
            mask=mask,
            frame_share=round(covered / float(mask.size), 4),
            instances=len(masks.xy),
        )


def build_vehicle_extent(
    weights_dir: Path, num_threads: int = 2, confidence: float = DEFAULT_CONFIDENCE
) -> VehicleExtentModel | None:
    """Load it if the checkpoint is there, else ``None``.

    ``None`` degrades the product by exactly one field: `area_ratio_vehicle` comes
    back null and the response says the vehicle was not measured. Nothing else
    changes, which is why this is optional rather than required.
    """
    path = weights_dir / VEHICLE_EXTENT_FILENAME
    if not path.is_file():
        logger.warning(
            "no vehicle extent checkpoint at %s -- damage area will be reported "
            "against the frame only. Fetch it with scripts/fetch_weights.py.",
            path,
        )
        return None
    try:
        return VehicleExtentModel(path, confidence=confidence, num_threads=num_threads)
    except Exception:
        logger.exception("vehicle extent checkpoint failed to load; area stays frame-relative")
        return None
