"""Cropping to the car and looking again — the wiring, not the benefit.

Whether a second look at the vehicle finds more damage is a question for
`scripts/eval_framing.py --vehicle-crop` and a dataset. What is testable without
either is everything that can be wrong even when the benefit is real:

* the crop runs when the car is small and does not when it is not;
* it runs even when the first pass found nothing, which is the case it exists for;
* detections come back in the PHOTOGRAPH's coordinates, not the crop's;
* a damage both passes saw is listed once, and two classes in one place are two;
* the area a crop detection contributes is its share of the whole picture.

All of that is driven through a stub detector. A test that needed
`vehide_yolo_seg.pt` would skip in CI, which is the one place a regression here
has to be caught -- and the checkpoint is not redistributable anyway.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from biovision.models.specialists.vehicle_yolo import (
    VEHIDE_CLASSES,
    VehicleYoloSpecialist,
)
from biovision.models.vehicle_extent import FrameClipping, VehicleExtent
from biovision.schemas.enums import DamageType

SOURCE = (1000, 800)


# ---------------------------------------------------------------------------
# Stubs shaped like the pieces of Ultralytics this module actually reads
# ---------------------------------------------------------------------------


class _Boxes:
    def __init__(self, cls: list[int], conf: list[float], xyxy: list[list[float]]) -> None:
        self.cls = np.asarray(cls)
        self.conf = np.asarray(conf, dtype=float)
        self.xyxy = np.asarray(xyxy, dtype=float)

    def __len__(self) -> int:
        return len(self.cls)


class _Masks:
    def __init__(self, polygons: list[np.ndarray]) -> None:
        self.xy = polygons


class _Result:
    def __init__(self, boxes: _Boxes | None, masks: _Masks | None) -> None:
        self.boxes = boxes
        self.masks = masks


def _rect(x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
    return np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=float)


def _detection(
    damage: DamageType, score: float, box: tuple[float, float, float, float]
) -> _Result:
    x1, y1, x2, y2 = box
    return _Result(
        _Boxes([VEHIDE_CLASSES.index(damage)], [score], [[x1, y1, x2, y2]]),
        _Masks([_rect(x1, y1, x2, y2)]),
    )


def _nothing() -> _Result:
    return _Result(None, None)


class _Model:
    """Answers by frame size: the full image gets one reply, a crop another."""

    def __init__(self, whole: _Result, cropped: _Result) -> None:
        self._whole = whole
        self._cropped = cropped
        self.calls: list[tuple[int, int]] = []

    def predict(self, image: np.ndarray, **_: Any) -> list[_Result]:
        height, width = image.shape[:2]
        self.calls.append((width, height))
        whole = (width, height) == SOURCE
        return [self._whole if whole else self._cropped]


class _Extent:
    """A located vehicle, in the reduced working plane like the real one."""

    def __init__(self, box: tuple[int, int, int, int], plane: tuple[int, int]) -> None:
        self._box = box
        self._plane = plane

    def extent(self, rgb: np.ndarray) -> VehicleExtent:
        width, height = self._plane
        mask = np.zeros((height, width), dtype=bool)
        x1, y1, x2, y2 = self._box
        mask[y1:y2, x1:x2] = True
        return VehicleExtent(
            mask=mask,
            frame_share=round(float(mask.sum()) / mask.size, 4),
            instances=1,
            clipped=FrameClipping(top=False, bottom=False, left=False, right=False),
        )


def _specialist(model: _Model, extent: _Extent | None, **overrides: Any) -> VehicleYoloSpecialist:
    """The state `__init__` would have left behind, without the checkpoint.

    `__init__` loads torch and a 20 MB file that this repository does not
    redistribute. Everything under test lives after that.
    """
    specialist = VehicleYoloSpecialist.__new__(VehicleYoloSpecialist)
    specialist._model = model  # type: ignore[assignment]
    specialist._confidence = overrides.get("confidence", 0.20)
    specialist._iou = 0.45
    specialist._region_confidence = overrides.get("region_confidence", 0.10)
    specialist._vehicle_extent = extent  # type: ignore[assignment]
    specialist._mirror_view = False
    specialist._vehicle_crop = overrides.get("vehicle_crop", True)
    specialist._crop_trigger_share = overrides.get("trigger", 0.25)
    specialist._crop_margin = overrides.get("margin", 0.0)
    specialist._crop_merge_iou = overrides.get("merge_iou", 0.5)
    specialist._classes = VEHIDE_CLASSES
    specialist._ready = True
    return specialist


def _image() -> np.ndarray:
    return np.zeros((SOURCE[1], SOURCE[0], 3), dtype=np.uint8)


#: The vehicle occupies a 200x160 patch of a 640x512 plane -- 10% of the frame,
#: comfortably under the 0.25 trigger. In source pixels that is x 250..562,
#: y 250..500.
SMALL_CAR = _Extent((160, 160, 360, 320), (640, 512))

#: Nearly the whole plane: the car fills the frame and there is nothing to crop.
BIG_CAR = _Extent((0, 0, 640, 512), (640, 512))


# ---------------------------------------------------------------------------
# When the second pass runs
# ---------------------------------------------------------------------------


def test_a_car_filling_the_frame_is_not_cropped_and_looked_at_twice() -> None:
    """The crop would be the frame, and the pass would repeat the first one."""
    model = _Model(whole=_detection(DamageType.DENT, 0.5, (10, 10, 90, 90)), cropped=_nothing())

    _specialist(model, BIG_CAR).assess_pixels(_image())

    assert model.calls == [SOURCE], "the crop pass ran on a car that fills the frame"


def test_a_small_car_gets_a_second_look_at_its_own_scale() -> None:
    model = _Model(whole=_nothing(), cropped=_nothing())

    _specialist(model, SMALL_CAR).assess_pixels(_image())

    assert len(model.calls) == 2
    assert model.calls[1] != SOURCE, "the second pass was handed the whole frame"


def test_the_crop_still_runs_when_the_first_pass_found_nothing() -> None:
    """The case the whole feature exists for.

    README 7.7's reported photograph is a wide shot that returned almost nothing.
    An early return on an empty first pass would skip exactly the images that need
    the second one.
    """
    model = _Model(
        whole=_nothing(), cropped=_detection(DamageType.MISSING_PART, 0.51, (10, 10, 60, 60))
    )

    findings = _specialist(model, SMALL_CAR).assess_pixels(_image()).findings

    assert [finding.type for finding in findings] == [DamageType.MISSING_PART]


def test_no_vehicle_model_means_no_crop_pass() -> None:
    """Cropping to a guess is how the tiled experiment invented damage."""
    model = _Model(whole=_nothing(), cropped=_nothing())

    _specialist(model, None).assess_pixels(_image())

    assert model.calls == [SOURCE]


def test_the_feature_off_is_a_single_pass() -> None:
    model = _Model(whole=_nothing(), cropped=_nothing())

    _specialist(model, SMALL_CAR, vehicle_crop=False).assess_pixels(_image())

    assert model.calls == [SOURCE]


# ---------------------------------------------------------------------------
# Where the second pass's detections land
# ---------------------------------------------------------------------------


def test_a_crop_detection_is_reported_in_photograph_coordinates() -> None:
    """The silent failure: crop coordinates escaping into the response.

    The car sits at x 250..562, y 250..500. A detection 10 px into the crop must
    be reported near 260, not at 10 -- which would put the box on empty tarmac in
    the top-left corner and still look like a plausible finding.
    """
    model = _Model(
        whole=_nothing(), cropped=_detection(DamageType.TORN, 0.4, (10, 10, 60, 60))
    )

    (finding,) = _specialist(model, SMALL_CAR).assess_pixels(_image()).findings

    x1, y1, x2, y2 = finding.bbox
    assert (x1, y1) == (260, 260)
    assert (x2, y2) == (310, 310)


def test_the_area_of_a_crop_detection_is_its_share_of_the_whole_picture() -> None:
    """Not of the crop. A 50x50 damage in a 1000x800 photograph is 0.3%."""
    model = _Model(
        whole=_nothing(), cropped=_detection(DamageType.TORN, 0.4, (10, 10, 60, 60))
    )

    (finding,) = _specialist(model, SMALL_CAR).assess_pixels(_image()).findings

    assert finding.area_ratio == pytest.approx((50 * 50) / (1000 * 800), abs=0.001)


def test_the_region_counts_the_crop_polygon_where_it_actually_sits() -> None:
    """Unmapped polygons would raise coverage without finding anything."""
    model = _Model(
        whole=_nothing(), cropped=_detection(DamageType.TORN, 0.4, (10, 10, 60, 60))
    )

    region = _specialist(model, SMALL_CAR).assess_pixels(_image()).region

    assert region is not None
    assert region.area_ratio_image == pytest.approx((50 * 50) / (1000 * 800), abs=0.001)
    # Entirely inside the car, so it is a much larger share OF the car.
    assert region.area_ratio_vehicle is not None
    assert region.area_ratio_vehicle > region.area_ratio_image


# ---------------------------------------------------------------------------
# Merging the two views
# ---------------------------------------------------------------------------


def test_damage_both_passes_saw_is_listed_once() -> None:
    """The crop's copy is dropped and the full-frame score is left untouched."""
    seen = (260.0, 260.0, 360.0, 360.0)
    model = _Model(
        whole=_detection(DamageType.DENT, 0.42, seen),
        # The same damage in crop coordinates: the car starts at (250, 250).
        cropped=_detection(DamageType.DENT, 0.73, (10, 10, 110, 110)),
    )

    findings = _specialist(model, SMALL_CAR).assess_pixels(_image()).findings

    assert len(findings) == 1
    assert findings[0].score == 0.42, "the full-frame finding was amended, not preserved"


def test_two_classes_in_one_place_are_two_findings() -> None:
    """A dent and a tear on one panel are two damages, not a duplicate."""
    seen = (260.0, 260.0, 360.0, 360.0)
    model = _Model(
        whole=_detection(DamageType.DENT, 0.42, seen),
        cropped=_detection(DamageType.TORN, 0.61, (10, 10, 110, 110)),
    )

    findings = _specialist(model, SMALL_CAR).assess_pixels(_image()).findings

    assert {finding.type for finding in findings} == {DamageType.DENT, DamageType.TORN}


def test_a_crop_finding_elsewhere_on_the_car_is_added() -> None:
    """Different damage, far from the one already listed, is what this is for."""
    model = _Model(
        whole=_detection(DamageType.DENT, 0.42, (260.0, 260.0, 300.0, 300.0)),
        cropped=_detection(DamageType.MISSING_PART, 0.37, (200, 180, 300, 240)),
    )

    findings = _specialist(model, SMALL_CAR).assess_pixels(_image()).findings

    assert len(findings) == 2
    assert findings[0].score >= findings[1].score, "findings are not most-confident-first"


def test_a_crop_detection_below_the_finding_floor_still_contributes_area() -> None:
    """Two floors, both passes. The region floor is 0.10, the finding floor 0.20."""
    model = _Model(
        whole=_nothing(), cropped=_detection(DamageType.SCRATCH, 0.15, (10, 10, 60, 60))
    )

    assessment = _specialist(model, SMALL_CAR).assess_pixels(_image())

    assert assessment.findings == []
    assert assessment.region is not None
    assert assessment.region.instances == 1
