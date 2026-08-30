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

from biovision.models.base import DamageRegion, SpecialistAssessment
from biovision.models.class_performance import VEHICLE_CLASS_PERFORMANCE
from biovision.models.mask_geometry import rasterise, share, working_size
from biovision.models.severity import severity_for
from biovision.models.vehicle_extent import VehicleExtentModel
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
#: Detection floor. Swept and measured, not chosen -- see README section 7.3.
#:
#: The sweep found no F1 optimum: 0.25 and 0.20 are within noise of each other in
#: both framings (0.562/0.556 close-up, 0.488/0.489 wide). So this is not a
#: tuned figure, it is a stated TRADE: 0.20 buys +0.025 recall for -0.070
#: precision.
#:
#: Recall is the side worth buying here. A missed dent leaves a claimant with a
#: thinner finding list than their car deserves, on a class the system already
#: publishes at 25% recall; an extra box costs a reader one glance, and each one
#: arrives carrying its own confidence and its class's measured recall. The
#: direction also matches the rest of the product -- `overall_severity`
#: under-calls, and two layers erring the same way compounds.
DEFAULT_CONFIDENCE_THRESHOLD = 0.20

#: A SECOND, lower floor, used only to build the damage region -- never to add a
#: line to the finding list.
#:
#: Two floors because there are two questions and one threshold cannot serve
#: both. "Which discrete damages are you confident about" is an instance question
#: and its answer is scored by precision/recall at IoU 0.5, where 0.20 sits
#: (README 7.3). "How much of this car is damaged" is an area question, scored by
#: what fraction of the annotated damage pixels the masks cover, and that metric
#: has a knee at 0.10 which the instance metric cannot see:
#:
#:     floor   coverage   spill    dent coverage
#:     0.20      0.715    0.351        0.316
#:     0.10      0.788    0.380        0.476
#:     0.05      0.820    0.465        0.620
#:
#: 0.20 -> 0.10 buys +0.073 coverage for +0.029 spill. 0.10 -> 0.05 buys +0.032
#: for +0.085 -- the trade inverts, so 0.10 is a measured optimum rather than a
#: preference. README section 7.9 carries the table and the method.
#:
#: The two floors are reported to the client. A reader who sees a damaged area
#: larger than the listed findings account for is seeing something real, and the
#: response says which floor produced which number.
DEFAULT_REGION_CONFIDENCE = 0.10
DEFAULT_IOU_THRESHOLD = 0.45


class VehicleYoloSpecialist:
    """Wraps an Ultralytics YOLO-seg checkpoint as a :class:`SpecialistModel`."""

    def __init__(
        self,
        weights_path: Path,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        iou_threshold: float = DEFAULT_IOU_THRESHOLD,
        num_threads: int = 2,
        region_confidence: float = DEFAULT_REGION_CONFIDENCE,
        vehicle_extent: VehicleExtentModel | None = None,
    ) -> None:
        import torch
        from ultralytics import YOLO

        torch.set_num_threads(max(1, num_threads))

        logger.info("loading vehicle specialist from %s", weights_path)
        self._model = YOLO(str(weights_path), task="segment")
        self._confidence = confidence_threshold
        self._iou = iou_threshold
        # A region floor above the finding floor would mean the area was built
        # from fewer detections than the list shows, so findings could describe
        # damage the area does not contain.
        self._region_confidence = min(region_confidence, confidence_threshold)
        self._vehicle_extent = vehicle_extent
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
        return self.assess_pixels(image.pixels).findings

    def assess(self, image: PreparedImage) -> SpecialistAssessment:
        """Findings and the damaged region, from a single inference pass."""
        return self.assess_pixels(image.pixels)

    def analyze_pixels(self, rgb: np.ndarray) -> list[Finding]:
        """Findings only.

        Exists separately so `eval_specialist.py` can measure this layer without
        building a `PreparedImage`.
        """
        return self.assess_pixels(rgb).findings

    def assess_pixels(self, rgb: np.ndarray) -> SpecialistAssessment:
        """Run segmentation once and read it twice, at two floors.

        One inference, two answers. Predicting at the lower floor and filtering
        upward costs nothing over predicting at the higher one, and predicting
        twice would double the most expensive stage in the request for numbers
        that must agree with each other anyway.
        """
        height, width = rgb.shape[:2]
        total_pixels = float(height * width)

        # `predict` can return a generator (stream mode) or a list depending on the
        # arguments; materialising it here makes the shape unambiguous.
        results = list(
            self._model.predict(
                rgb,
                conf=self._region_confidence,
                iou=self._iou,
                verbose=False,
                device="cpu",
            )
        )
        if not results:
            return SpecialistAssessment(findings=[], region=None)

        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return SpecialistAssessment(findings=[], region=None)

        masks = getattr(result, "masks", None)
        findings: list[Finding] = []
        region_polygons: list[Any] = []

        for index in range(len(boxes)):
            class_id = int(boxes.cls[index].item())
            if not 0 <= class_id < len(self._classes):
                logger.warning("checkpoint emitted unknown class id %d; skipping", class_id)
                continue

            score = round(float(boxes.conf[index].item()), 4)

            # Everything above the region floor contributes area. `masks.xy` is in
            # source-image coordinates, which is the only mask form whose frame is
            # unambiguous -- `masks.data` is shaped by the letterbox.
            if masks is not None and masks.xy is not None and index < len(masks.xy):
                region_polygons.append(masks.xy[index])

            if score < self._confidence:
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
            # What was measured for this class, carried with the finding. A score
            # says how sure the model is about this box; recall says how much this
            # class tends to be missed, and only the first was ever on screen.
            measured = VEHICLE_CLASS_PERFORMANCE.get(damage_type)
            findings.append(
                Finding(
                    type=damage_type,
                    score=score,
                    bbox=(x1, y1, x2, y2),
                    area_ratio=round(area_ratio, 4),
                    severity=severity_for(damage_type, area_ratio),
                    class_recall=measured.recall if measured else None,
                    class_reliable=measured.reliable if measured else None,
                )
            )

        # Most confident first: a client rendering the top finding should get the
        # one the model is surest about.
        findings.sort(key=lambda finding: finding.score, reverse=True)
        return SpecialistAssessment(
            findings=findings,
            region=self._region(region_polygons, rgb, (width, height)),
        )

    def _region(
        self, polygons: list[Any], rgb: np.ndarray, source: tuple[int, int]
    ) -> DamageRegion | None:
        """The union of the damage masks, and its share of the car.

        Returns None when nothing was detected at all -- distinct from a region of
        zero area, which cannot occur here and would mean something different.
        """
        if not polygons:
            return None

        plane = working_size(source)
        damage = rasterise(polygons, source, plane)

        vehicle = self._vehicle_extent.extent(rgb) if self._vehicle_extent else None
        return DamageRegion(
            area_ratio_image=round(share(damage), 4),
            area_ratio_vehicle=round(share(damage, vehicle.mask), 4) if vehicle else None,
            vehicle_frame_share=vehicle.frame_share if vehicle else None,
            instances=len(polygons),
            confidence_floor=self._region_confidence,
        )

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
    weights_dir: Path,
    num_threads: int = 2,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    region_confidence: float = DEFAULT_REGION_CONFIDENCE,
    vehicle_extent: VehicleExtentModel | None = None,
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
        return VehicleYoloSpecialist(
            path,
            confidence_threshold=confidence_threshold,
            num_threads=num_threads,
            region_confidence=region_confidence,
            vehicle_extent=vehicle_extent,
        )
    except Exception:
        logger.exception("vehicle checkpoint failed to load; the domain reports no specialist")
        return None
