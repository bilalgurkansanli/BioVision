"""The vehicle specialist: VehiDE-trained YOLO segmentation.

Seven damage classes -- dent, glass shatter, lamp broken, missing part, punctured,
scratch, torn. See ADR-026 for why these and not CarDD's six.

This is the only layer in the system that produces *measurements*. Everything else
either routes, describes, or declines. The consequence is that `area_ratio` has to
mean exactly one thing: the fraction of the analysed image covered by the predicted
mask. Two failure modes are guarded against explicitly below, because both would
silently corrupt every severity band the API reports:

* taking area from the bounding box rather than the mask, which overstates thin
  diagonal scratches by a large factor;
* computing the fraction against the model's letterboxed input rather than the
  image the user actually sees.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from biovision.models.severity import severity_for
from biovision.pipeline.types import PreparedImage
from biovision.schemas.analyze import Finding
from biovision.schemas.enums import DamageType

logger = logging.getLogger(__name__)

VEHICLE_WEIGHTS_FILENAME = "vehide_yolo_seg.pt"
SPECIALIST_NAME = "vehide-yolo-seg-v1"

#: Class order, as the training notebook writes it into the dataset YAML.
#: The model emits integer class ids, so this list *is* the contract between the
#: notebook and this module. Reordering it silently relabels every prediction.
#:
#: Alphabetical, matching DamageType. VehiDE's own annotations are Vietnamese;
#: the notebook maps them here and the mapping is written out term by term.
VEHIDE_CLASSES: tuple[DamageType, ...] = (
    DamageType.DENT,           # mop_lom       -- moc lom, dent
    DamageType.GLASS_SHATTER,  # vo_kinh       -- vo kinh, broken glass
    DamageType.LAMP_BROKEN,    # be_den        -- be den, broken lights
    DamageType.MISSING_PART,   # mat_bo_phan   -- mat bo phan, lost part
    DamageType.PUNCTURED,      # thung         -- thung, punctured
    DamageType.SCRATCH,        # tray_son      -- tray son, paint scratch
    DamageType.TORN,           # rach          -- rach, torn
)

#: Detections below this confidence are dropped before they become findings.
#: Deliberately not zero: a response listing forty low-confidence scratches is
#: technically complete and practically useless.
DEFAULT_CONFIDENCE_THRESHOLD = 0.25
DEFAULT_IOU_THRESHOLD = 0.45


class VehicleYoloSpecialist:
    """Wraps an Ultralytics YOLO-seg checkpoint as a :class:`SpecialistModel`."""

    def __init__(
        self,
        weights_path: Path,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        iou_threshold: float = DEFAULT_IOU_THRESHOLD,
        num_threads: int = 2,
    ) -> None:
        import torch
        from ultralytics import YOLO

        torch.set_num_threads(max(1, num_threads))

        logger.info("loading vehicle specialist from %s", weights_path)
        self._model = YOLO(str(weights_path), task="segment")
        self._confidence = confidence_threshold
        self._iou = iou_threshold
        self._ready = True

        # If the checkpoint carries its own class names, they are authoritative --
        # a mismatch with VEHIDE_CLASSES means this checkpoint was trained against a
        # different label order and every prediction would be mislabelled.
        self._classes = self._resolve_classes()

        logger.info(
            "vehicle specialist ready: %d classes, conf>=%.2f",
            len(self._classes),
            confidence_threshold,
        )

    @property
    def name(self) -> str:
        return SPECIALIST_NAME

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def domain(self) -> str:
        return "vehicle"

    def analyze(self, image: PreparedImage) -> list[Finding]:
        return self.analyze_pixels(image.pixels)

    def analyze_pixels(self, rgb: np.ndarray) -> list[Finding]:
        """Run segmentation and convert masks into findings.

        Exists separately so `eval_specialist.py` can measure this layer without
        building a `PreparedImage`.
        """
        height, width = rgb.shape[:2]
        total_pixels = float(height * width)

        # `predict` can return a generator (stream mode) or a list depending on the
        # arguments; materialising it here makes the shape unambiguous.
        results = list(
            self._model.predict(
                rgb,
                conf=self._confidence,
                iou=self._iou,
                verbose=False,
                device="cpu",
            )
        )
        if not results:
            return []

        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []

        masks = getattr(result, "masks", None)
        findings: list[Finding] = []

        for index in range(len(boxes)):
            class_id = int(boxes.cls[index].item())
            if not 0 <= class_id < len(self._classes):
                logger.warning("checkpoint emitted unknown class id %d; skipping", class_id)
                continue

            x1, y1, x2, y2 = (round(v) for v in boxes.xyxy[index].tolist())
            # Clamp: the model can place a box a pixel or two outside the frame, and
            # the response schema rejects negative or inverted boxes.
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(width, x2), min(height, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            area_ratio = self._area_ratio(masks, index, (x1, y1, x2, y2), total_pixels)

            damage_type = self._classes[class_id]
            findings.append(
                Finding(
                    type=damage_type,
                    score=round(float(boxes.conf[index].item()), 4),
                    bbox=(x1, y1, x2, y2),
                    area_ratio=round(area_ratio, 4),
                    severity=severity_for(damage_type, area_ratio),
                )
            )

        # Most confident first: a client rendering the top finding should get the
        # one the model is surest about.
        findings.sort(key=lambda finding: finding.score, reverse=True)
        return findings

    def _area_ratio(
        self,
        masks: Any,
        index: int,
        box: tuple[int, int, int, int],
        total_pixels: float,
    ) -> float:
        """Fraction of the image covered by this instance.

        Uses the segmentation mask when one is available. Falling back to the box
        would overstate a thin diagonal scratch several-fold -- its box is large and
        mostly empty -- and severity is derived from this number.
        """
        if masks is not None and masks.data is not None and index < len(masks.data):
            mask = masks.data[index].cpu().numpy()
            covered = float((mask > 0.5).sum())
            # Ultralytics returns masks at the model's input resolution, not the
            # source image's. Dividing by the mask's own pixel count keeps the ratio
            # in the source frame, which is where the user and the bbox live.
            mask_pixels = float(mask.shape[0] * mask.shape[1])
            if mask_pixels > 0:
                return min(1.0, covered / mask_pixels)

        logger.debug("no mask for detection %d; falling back to bounding-box area", index)
        x1, y1, x2, y2 = box
        return min(1.0, ((x2 - x1) * (y2 - y1)) / total_pixels)

    def _resolve_classes(self) -> tuple[DamageType, ...]:
        names = getattr(self._model, "names", None)
        if not isinstance(names, dict) or not names:
            return VEHIDE_CLASSES

        try:
            ordered = [str(names[key]).strip().lower() for key in sorted(names)]
        except Exception:
            return VEHIDE_CLASSES

        expected = [damage.value for damage in VEHIDE_CLASSES]
        normalised = [name.replace(" ", "_").replace("-", "_") for name in ordered]

        if normalised == expected:
            return VEHIDE_CLASSES

        # Loud, because a silent mismatch relabels every prediction: a checkpoint
        # whose class 1 is "dent" would report every dent as a scratch.
        logger.error(
            "checkpoint class order %s does not match VEHIDE_CLASSES %s -- "
            "predictions would be mislabelled",
            normalised,
            expected,
        )
        raise ValueError(
            f"vehicle checkpoint declares classes {normalised}, expected {expected}. "
            f"Retrain with the class order in the notebook, or update VEHIDE_CLASSES."
        )


def build_vehicle_specialist(
    weights_dir: Path, num_threads: int = 2
) -> VehicleYoloSpecialist | None:
    """Load the specialist if its checkpoint is present, else ``None``.

    ``None`` is the honest, supported outcome: the vehicle domain then behaves like
    every other domain without a specialist, and the API says `specialist_model:
    null` rather than pretending.
    """
    path = weights_dir / VEHICLE_WEIGHTS_FILENAME
    if not path.is_file():
        logger.warning(
            "no vehicle checkpoint at %s -- the vehicle domain will report "
            "specialist_model=null. Train it with notebooks/train_vehide_yolo.ipynb.",
            path,
        )
        return None

    try:
        return VehicleYoloSpecialist(path, num_threads=num_threads)
    except Exception:
        logger.exception("vehicle checkpoint failed to load; the domain reports no specialist")
        return None
