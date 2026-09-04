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
  image the user actually sees. Everything here measures from `masks.xy`, which is
  in source-image coordinates; `masks.data` is shaped by the letterbox and its
  padding is not part of the photograph.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from biovision.models.base import DamageRegion, SpecialistAssessment
from biovision.models.class_performance import VEHICLE_CLASS_PERFORMANCE
from biovision.models.damage_position import locate
from biovision.models.mask_geometry import (
    crop_box,
    iou,
    mirror_polygons,
    offset_polygons,
    rasterise,
    share,
    simplify,
    working_size,
)
from biovision.models.severity import severity_for
from biovision.models.vehicle_extent import VehicleExtent, VehicleExtentModel
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
    DamageType.DENT,  # mop_lom       -- moc lom, dent
    DamageType.GLASS_SHATTER,  # vo_kinh       -- vo kinh, broken glass
    DamageType.LAMP_BROKEN,  # be_den        -- be den, broken lights
    DamageType.MISSING_PART,  # mat_bo_phan   -- mat bo phan, lost part
    DamageType.PUNCTURED,  # thung         -- thung, punctured
    DamageType.SCRATCH,  # tray_son      -- tray son, paint scratch
    DamageType.TORN,  # rach          -- rach, torn
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

#: Below this share of the frame, the vehicle is worth cropping to and looking
#: again. Above it the crop IS the frame and the second pass would cost ~113 ms
#: to re-run the same inference.
#:
#: Stated, not fitted. §7.7's reported photograph has the car at roughly a fifth
#: of the frame; §7.5's padding test moves the same damage thirtyfold across four
#: crops. A quarter sits between them and no evaluation set was consulted, which
#: is why `scripts/eval_framing.py --vehicle-crop` sweeps it.
DEFAULT_CROP_TRIGGER_SHARE = 0.25

#: Grown by this share of the vehicle's own box on every side. A crop cutting
#: exactly at the mask boundary removes the panel edges that give the detector its
#: context, and the COCO vehicle mask is itself approximate.
DEFAULT_CROP_MARGIN = 0.08

#: A crop detection overlapping a full-frame one of the SAME class by at least
#: this much is the same damage seen twice, and is dropped. Matches the IoU the
#: evaluation scores at, so "one finding" means the same thing in both places.
DEFAULT_CROP_MERGE_IOU = 0.5

#: A crop covering more of the frame than this is not a crop. It happens when a
#: vehicle is small but clipped on opposite edges, so its box spans the picture.
CROP_MAX_FRAME_SHARE = 0.9


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
        mirror_view: bool = False,
        vehicle_crop: bool = False,
        crop_trigger_share: float = DEFAULT_CROP_TRIGGER_SHARE,
        crop_margin: float = DEFAULT_CROP_MARGIN,
        crop_merge_iou: float = DEFAULT_CROP_MERGE_IOU,
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
        self._mirror_view = mirror_view
        # Needs the extent model: without a located vehicle there is nothing to
        # crop to, and cropping to a guess is how the tiled experiment invented a
        # `missing_part` on an ambulance.
        self._vehicle_crop = vehicle_crop and vehicle_extent is not None
        if vehicle_crop and vehicle_extent is None:
            logger.warning(
                "vehicle_crop requested without an extent model; the second pass is off"
            )
        self._crop_trigger_share = crop_trigger_share
        self._crop_margin = crop_margin
        self._crop_merge_iou = crop_merge_iou
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
        """Look at the photograph, then optionally look again, closer.

        The first pass is read twice at two floors: one inference, two answers.
        Predicting at the lower floor and filtering upward costs nothing over
        predicting at the higher one, and predicting twice would double the most
        expensive stage in the request for numbers that must agree anyway.

        The later passes exist because this checkpoint's ceiling is view-dependent
        recall (README 7.9): the same weights, looking again, find damage the first
        look missed. The mirror pass contributes area only; the vehicle crop can
        also add findings, and README 7.7 is why it may need to.
        """
        height, width = rgb.shape[:2]
        source = (width, height)
        # One plane for every answer. The per-finding area and the region area are
        # the same measurement at two floors, so measuring them in two different
        # frames is how they would stop agreeing.
        plane = working_size(source)

        findings, region_polygons = self._read(self._predict(rgb), source, plane, (0, 0))

        # Hoisted out of `_region`: the crop decision needs the vehicle before the
        # region does, and running the extent model twice would pay for it twice.
        vehicle = self._vehicle_extent.extent(rgb) if self._vehicle_extent else None

        # A second look at the mirror image, contributing AREA only.
        #
        # Measured, and it is the strongest evidence about what is actually wrong
        # with this model: simply flipping the photograph finds damage the
        # original view missed. Coverage 0.794 -> 0.854, `torn` 0.493 -> 0.596,
        # blind images 3.3% -> 1.1% (README 7.9). The failure is view-dependent
        # RECALL -- not mask boundaries, which the cut-off sweep ruled out, and
        # not capacity, which a bigger backbone would address.
        #
        # Deliberately not fed into `findings`. Merging two views into instances
        # needs cross-view NMS, which would change the precision/recall numbers
        # section 7.3 publishes; the union of pixels needs nothing of the kind.
        if self._mirror_view:
            region_polygons.extend(self._mirrored_polygons(rgb, width))

        # A third look, at the car alone. This one CAN add findings -- see
        # `_cropped_view` for why that is a different trade from the mirror's.
        if self._vehicle_crop and vehicle is not None:
            extra, extra_polygons = self._cropped_view(rgb, vehicle, source, plane)
            findings.extend(self._only_new(findings, extra))
            region_polygons.extend(extra_polygons)

        # Most confident first: a client rendering the top finding should get the
        # one the model is surest about.
        findings.sort(key=lambda finding: finding.score, reverse=True)
        return SpecialistAssessment(
            findings=findings,
            region=self._region(region_polygons, vehicle, source, plane),
        )

    def _predict(self, rgb: np.ndarray) -> Any:
        """One inference at the region floor, materialised.

        `predict` can return a generator (stream mode) or a list depending on the
        arguments; materialising here makes the shape unambiguous. Returns None
        when nothing was detected, which every caller treats as "no boxes" rather
        than as a failure -- notably the crop pass, which exists precisely for the
        photographs where the first look found nothing.
        """
        results = list(
            self._model.predict(
                rgb,
                conf=self._region_confidence,
                iou=self._iou,
                verbose=False,
                device="cpu",
            )
        )
        return results[0] if results else None

    def _read(
        self,
        result: Any,
        source: tuple[int, int],
        plane: tuple[int, int],
        offset: tuple[int, int],
    ) -> tuple[list[Finding], list[Any]]:
        """Turn one inference into findings and area polygons, in SOURCE pixels.

        `offset` is where this view sat inside the photograph: (0, 0) for a pass
        over the whole image, the crop's top-left corner for a pass over part of
        it. Applied here rather than at the call sites so that a view can only be
        read in one frame -- crop coordinates escaping into a finding would put a
        box on the wrong panel, and into the region would pile the damage into the
        top-left of the picture while coverage went up.
        """
        if result is None:
            return [], []
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return [], []

        masks = getattr(result, "masks", None)
        dx, dy = offset
        width, height = source

        findings: list[Finding] = []
        polygons: list[Any] = []

        for index in range(len(boxes)):
            class_id = int(boxes.cls[index].item())
            if not 0 <= class_id < len(self._classes):
                logger.warning("checkpoint emitted unknown class id %d; skipping", class_id)
                continue

            score = round(float(boxes.conf[index].item()), 4)

            # Everything above the region floor contributes area. `masks.xy` is in
            # this view's own coordinates, which is the only mask form whose frame
            # is unambiguous -- `masks.data` is shaped by the letterbox.
            polygon = None
            if masks is not None and masks.xy is not None and index < len(masks.xy):
                moved = offset_polygons([masks.xy[index]], dx, dy)
                if moved:
                    polygon = moved[0]
                    polygons.append(polygon)

            if score < self._confidence:
                continue

            x1, y1, x2, y2 = (round(v) for v in boxes.xyxy[index].tolist())
            x1, y1, x2, y2 = x1 + dx, y1 + dy, x2 + dx, y2 + dy
            # Clamp: the model can place a box a pixel or two outside the frame, and
            # the response schema rejects negative or inverted boxes.
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(width, x2), min(height, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            area_ratio = self._area_ratio(polygon, (x1, y1, x2, y2), source, plane)

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
                    # The shape behind the box and behind the percentage. Simplified
                    # for transport -- see `mask_geometry.simplify` for what that
                    # costs, measured.
                    outline=simplify(polygon, source) if polygon is not None else None,
                    area_ratio=round(area_ratio, 4),
                    severity=severity_for(damage_type, area_ratio),
                    class_recall=measured.recall if measured else None,
                    class_reliable=measured.reliable if measured else None,
                )
            )

        return findings, polygons

    def _cropped_view(
        self,
        rgb: np.ndarray,
        vehicle: VehicleExtent,
        source: tuple[int, int],
        plane: tuple[int, int],
    ) -> tuple[list[Finding], list[Any]]:
        """Detect again on the car alone, in the photograph's own coordinates.

        **The failure mode README 7.7 measured, and the one remedy it did not
        try.** A wide shot of a written-off car returned one finding; the same
        photograph cropped to the car returned four, including the `missing_part`
        and `torn` that make it a write-off. VehiDE is entirely close-ups, so the
        specialist learned that scale and no other, and in a scene photograph the
        damage is a few hundred pixels before the 640 px resize.

        **Why this is not the tiling that was rejected.** Tiling bought 0.016
        recall for 0.229 precision because it detected in slices of BACKGROUND: it
        invented a `missing_part` on an undamaged ambulance and a `glass_shatter`
        over a third of the frame. A crop to the vehicle removes background rather
        than subdividing it -- there is no slice for the ambulance to be in. The
        direction of the precision effect is therefore the opposite one, and that
        is the claim `scripts/eval_framing.py --vehicle-crop` exists to test.

        **Unmeasured until it is run.** Off by default. Every number in README 7.3
        and 7.7 was produced with this off, and none of them describes the pipeline
        with it on.
        """
        if vehicle.frame_share >= self._crop_trigger_share:
            # The car already fills the frame. The crop would be the frame, and the
            # second inference would cost ~113 ms to repeat the first.
            return [], []

        box = crop_box(vehicle.mask, plane, source, self._crop_margin)
        if box is None:
            return [], []

        x1, y1, x2, y2 = box
        if ((x2 - x1) * (y2 - y1)) / float(source[0] * source[1]) > CROP_MAX_FRAME_SHARE:
            # A small vehicle clipped on opposite edges spans the picture, so its
            # box is not a crop. Nothing to gain, and the cost is a full pass.
            logger.debug("vehicle box spans the frame; skipping the crop pass")
            return [], []

        logger.debug(
            "vehicle fills %.3f of the frame; looking again at %s", vehicle.frame_share, box
        )
        crop = np.ascontiguousarray(rgb[y1:y2, x1:x2])
        return self._read(self._predict(crop), source, plane, (x1, y1))

    def _only_new(self, existing: list[Finding], extra: list[Finding]) -> list[Finding]:
        """Crop findings the full frame did not already report.

        **Add only, never amend.** A crop detection overlapping a full-frame one of
        the same class is the same damage seen twice and is dropped, and the
        full-frame one keeps its score untouched. The alternative -- taking
        whichever scored higher -- would change the score of findings the published
        table describes, so every listed finding would need re-measuring rather
        than only the added ones.

        Class-aware, because a dent and a scratch on one panel are two findings and
        suppressing across classes would delete real damage. The IoU matches what
        the evaluation scores at, so "the same finding" means one thing in both.
        """
        added: list[Finding] = []
        for candidate in extra:
            kept = existing + added
            if any(
                other.type is candidate.type
                and iou(candidate.bbox, other.bbox) >= self._crop_merge_iou
                for other in kept
            ):
                continue
            added.append(candidate)
        if added:
            logger.info("vehicle crop added %d finding(s) the full frame missed", len(added))
        return added

    def _mirrored_polygons(self, rgb: np.ndarray, width: int) -> list[Any]:
        """Damage found in the mirror image, mapped back to the original frame.

        The mapping is the whole risk here: leaving the polygons in mirror
        coordinates would union the damage with its own reflection, which raises
        coverage for entirely the wrong reason and would look like a win.
        """
        results = list(
            self._model.predict(
                rgb[:, ::-1].copy(),
                conf=self._region_confidence,
                iou=self._iou,
                verbose=False,
                device="cpu",
            )
        )
        if not results:
            return []
        masks = getattr(results[0], "masks", None)
        if masks is None or masks.xy is None:
            return []

        return mirror_polygons(masks.xy, width)

    def _region(
        self,
        polygons: list[Any],
        vehicle: VehicleExtent | None,
        source: tuple[int, int],
        plane: tuple[int, int],
    ) -> DamageRegion | None:
        """The union of the damage masks, and its share of the car.

        Returns None when nothing was detected at all -- distinct from a region of
        zero area, which cannot occur here and would mean something different.

        The vehicle is passed in rather than located here: the crop pass needs it
        first, and running the extent model twice would pay for it twice.
        """
        if not polygons:
            return None

        damage = rasterise(polygons, source, plane)

        return DamageRegion(
            area_ratio_image=round(share(damage), 4),
            area_ratio_vehicle=round(share(damage, vehicle.mask), 4) if vehicle else None,
            vehicle_frame_share=vehicle.frame_share if vehicle else None,
            instances=len(polygons),
            confidence_floor=self._region_confidence,
            # Both planes are already here and already aligned. Computing the
            # position anywhere else would mean rasterising them a second time.
            position=locate(damage, vehicle.mask) if vehicle else None,
            clipped=vehicle.clipped if vehicle else None,
        )

    def _area_ratio(
        self,
        polygon: Any,
        box: tuple[int, int, int, int],
        source: tuple[int, int],
        plane: tuple[int, int],
    ) -> float:
        """Fraction of the source image covered by this instance.

        Uses the segmentation mask when one is available. Falling back to the box
        would overstate a thin diagonal scratch several-fold -- its box is large and
        mostly empty -- and severity is derived from this number.

        **Measured from `masks.xy`, not `masks.data`, and that is the whole point.**
        `masks.data` is a tensor at the LETTERBOXED input shape: Ultralytics scales
        the long edge to 640 and pads the short one up to a multiple of 32, so the
        plane carries bars the photograph does not. Dividing by its pixel count --
        which this used to do, while the docstring above claimed the opposite --
        divides by the padding as well, and understates every area by the padding's
        share of the frame. Measured on a 1280x400 image, whose 640x200 content is
        padded to 640x224: **every `area_ratio` came back 1.113x too small.**

        The error is a pure function of aspect ratio, which is exactly the wrong
        thing for it to depend on. A 4:3 photograph pads to nothing and is correct;
        a 3:2 one is 5% low, 16:9 is 6.7% low, and the same damage therefore lands
        in a different severity band depending on which phone took the picture --
        the framing sensitivity §7.5 exists to remove, reintroduced one layer down.

        The polygon handed in comes from `masks.xy` and has already been moved into
        source-image coordinates by `_read`, so rasterising it into the shared
        working plane -- which preserves the aspect ratio -- gives the fraction of
        the image the user actually sees, and gives it in the same plane the region
        is measured in. A detection found inside a crop is therefore a fraction of
        the whole photograph, not of the crop.
        """
        if polygon is not None and len(polygon) >= 3:
            return share(rasterise([polygon], source, plane))

        logger.debug("no mask for this detection; falling back to bounding-box area")
        x1, y1, x2, y2 = box
        return min(1.0, ((x2 - x1) * (y2 - y1)) / float(source[0] * source[1]))

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
    mirror_view: bool = False,
    vehicle_crop: bool = False,
    crop_trigger_share: float = DEFAULT_CROP_TRIGGER_SHARE,
    crop_margin: float = DEFAULT_CROP_MARGIN,
    crop_merge_iou: float = DEFAULT_CROP_MERGE_IOU,
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
            mirror_view=mirror_view,
            vehicle_crop=vehicle_crop,
            crop_trigger_share=crop_trigger_share,
            crop_margin=crop_margin,
            crop_merge_iou=crop_merge_iou,
        )
    except Exception:
        logger.exception("vehicle checkpoint failed to load; the domain reports no specialist")
        return None
