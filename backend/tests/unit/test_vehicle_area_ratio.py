"""`area_ratio` is a fraction of the photograph, not of the letterbox.

The specialist shipped measuring it against `masks.data`, which Ultralytics
returns at the LETTERBOXED input shape: the long edge scaled to 640 and the short
one padded up to a multiple of 32. Dividing by that plane's pixel count divides by
the padding too, so every area came back small by the padding's share of the
frame -- 1.113x on a 1280x400 image, and exactly 1.0x on a 4:3 one, which is how
it survived every eyeball test anyone ran.

The dependence on aspect ratio is the part that matters. `area_ratio` feeds
`severity_for`, so the same damage crossed the 0.02 and 0.08 band thresholds
depending on which phone took the picture -- the framing sensitivity README 7.5
exists to remove, reintroduced one layer below it.

These tests drive `_area_ratio` directly. That is the whole of the arithmetic
under test, and it needs no checkpoint: requiring `vehide_yolo_seg.pt` would make
this test skip in CI, which is where a regression would have to be caught.
"""

from __future__ import annotations

import numpy as np
import pytest

from biovision.models.mask_geometry import working_size
from biovision.models.specialists.vehicle_yolo import VehicleYoloSpecialist


def _specialist() -> VehicleYoloSpecialist:
    """An instance without its checkpoint.

    `__init__` loads several hundred megabytes of torch and a file that is not
    redistributed; `_area_ratio` touches none of it.
    """
    return VehicleYoloSpecialist.__new__(VehicleYoloSpecialist)


def _rect(x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
    return np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=float)


def _ratio(polygon: np.ndarray | None, source: tuple[int, int]) -> float:
    return _specialist()._area_ratio(polygon, (0, 0, 1, 1), source, working_size(source))


@pytest.mark.parametrize(
    "source",
    [
        (640, 640),  # 1:1   -- letterboxes to 640x640, no padding
        (1280, 960),  # 4:3   -- 640x480, no padding: the case that always passed
        (1280, 853),  # 3:2   -- 640x427 padded to 640x448
        (1280, 720),  # 16:9  -- 640x360 padded to 640x384
        (1280, 400),  # 3.2:1 -- 640x200 padded to 640x224, the worst measured case
    ],
)
def test_a_quarter_of_the_image_reads_as_a_quarter_whatever_its_shape(
    source: tuple[int, int],
) -> None:
    """One number, one meaning, across every aspect ratio.

    A rectangle covering exactly a quarter of the photograph must report 0.25
    whether the photograph is square or 3.2:1. Under the old formula the 3.2:1
    case reported 0.223.
    """
    width, height = source

    assert _ratio(_rect(0, 0, width / 2, height / 2), source) == pytest.approx(0.25, abs=0.005)


def test_the_ratio_does_not_move_when_only_the_canvas_shape_does() -> None:
    """The same damage, the same fraction, two shapes of frame.

    This is the property the bug broke: a padded letterbox made the answer a
    function of the photograph's proportions rather than of what was damaged.
    """
    square = _ratio(_rect(0, 0, 320, 320), (640, 640))  # a quarter of a square
    wide = _ratio(_rect(0, 0, 640, 200), (1280, 400))  # a quarter of a 3.2:1 frame

    assert square == pytest.approx(wide, abs=0.005)


def test_a_full_frame_polygon_reads_as_the_whole_image() -> None:
    assert _ratio(_rect(0, 0, 1280, 400), (1280, 400)) == pytest.approx(1.0, abs=0.005)


def test_a_polygon_found_in_a_crop_is_a_fraction_of_the_whole_photograph() -> None:
    """The crop pass hands polygons in already moved into source coordinates.

    A quarter-sized damage sitting far from the origin must still read as its
    share of the picture, not of the crop it was found in.
    """
    source = (2000, 1000)
    far = _rect(1000, 500, 2000, 1000)  # the bottom-right quarter

    assert _ratio(far, source) == pytest.approx(0.25, abs=0.005)


def test_a_degenerate_polygon_falls_back_to_the_box_in_the_same_frame() -> None:
    """Both branches measure against the source image, or they disagree.

    The fallback used to divide by the source area while the mask branch divided
    by the letterbox, so which branch ran changed what the number meant.
    """
    source = (1280, 400)
    two_points = np.array([[0.0, 0.0], [10.0, 10.0]])

    ratio = _specialist()._area_ratio(
        two_points, (0, 0, 640, 200), source, working_size(source)
    )

    assert ratio == pytest.approx((640 * 200) / (1280 * 400))


def test_no_mask_at_all_still_measures_the_box_against_the_image() -> None:
    source = (800, 600)

    ratio = _specialist()._area_ratio(None, (0, 0, 400, 300), source, working_size(source))

    assert ratio == pytest.approx(0.25)
