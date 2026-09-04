"""The frame changes twice on the crop path, so both mappings get their own test.

Cropping to the vehicle and detecting again is the one remedy §7.7 measured and
did not try: the same photograph cropped to the car returns four findings where
the wide frame returns one. What makes it worth separating out is that both steps
fail *quietly*:

* `crop_box` reads a mask in the reduced working plane and has to return a box in
  full-resolution source pixels. Scale it the wrong way and the box is still
  plausible and still in frame -- around the wrong part of the photograph.
* `offset_polygons` maps detections found inside the crop back to the whole
  image. Skip it and every crop detection piles into the top-left corner, which
  raises pixel coverage and looks exactly like the crop having worked.

Neither is caught by a coverage number going up, which is the only signal the
measurement produces. So they are tested here, not inferred from an evaluation.
"""

from __future__ import annotations

import numpy as np
import pytest

from biovision.models.mask_geometry import (
    WORKING_LONG_EDGE,
    crop_box,
    iou,
    offset_polygons,
    rasterise,
    working_size,
)


def _mask(plane: tuple[int, int], box: tuple[int, int, int, int]) -> np.ndarray:
    """A True rectangle (x1, y1, x2, y2) in a plane of `plane` size."""
    width, height = plane
    mask = np.zeros((height, width), dtype=bool)
    x1, y1, x2, y2 = box
    mask[y1:y2, x1:x2] = True
    return mask


# ---------------------------------------------------------------------------
# crop_box: plane -> source
# ---------------------------------------------------------------------------


def test_the_box_is_returned_in_source_pixels_not_plane_pixels() -> None:
    """The whole point. A 4000x3000 photograph works a 640x480 plane.

    A vehicle filling the middle of the plane must come back as a box in the
    thousands, not in the hundreds.
    """
    source = (4000, 3000)
    plane = working_size(source)
    assert plane == (640, 480)

    mask = _mask(plane, (160, 120, 480, 360))  # the middle half of the plane

    box = crop_box(mask, plane, source, margin=0.0)

    assert box == (1000, 750, 3000, 2250)


def test_the_margin_grows_the_box_by_a_share_of_itself() -> None:
    """A crop cutting exactly at the mask edge removes the panel edges.

    10% of a 2000x1500 box is 200x150 on every side.
    """
    source = (4000, 3000)
    plane = working_size(source)
    mask = _mask(plane, (160, 120, 480, 360))

    box = crop_box(mask, plane, source, margin=0.1)

    assert box == (800, 600, 3200, 2400)


def test_the_margin_is_clamped_to_the_frame_rather_than_running_past_it() -> None:
    """A vehicle already touching the edge cannot be padded outside the image."""
    source = (1280, 960)
    plane = working_size(source)
    mask = _mask(plane, (0, 0, plane[0], plane[1]))

    box = crop_box(mask, plane, source, margin=0.5)

    assert box == (0, 0, 1280, 960)


def test_an_empty_mask_has_no_box_rather_than_a_zero_area_one() -> None:
    """`None` is the same first-class "no vehicle" answer the rest of this carries."""
    plane = (640, 480)
    assert crop_box(np.zeros((480, 640), dtype=bool), plane, (1280, 960), margin=0.1) is None


def test_a_small_photograph_is_its_own_plane_and_the_box_is_unscaled() -> None:
    """`working_size` never upscales, so below the working edge the frames agree."""
    source = (400, 300)
    plane = working_size(source)
    assert plane == source

    box = crop_box(_mask(plane, (100, 50, 200, 150)), plane, source, margin=0.0)

    assert box == (100, 50, 200, 150)


def test_a_negative_margin_is_rejected_rather_than_shrinking_the_crop() -> None:
    plane = (640, 480)
    with pytest.raises(ValueError, match="margin"):
        crop_box(_mask(plane, (10, 10, 20, 20)), plane, (640, 480), margin=-0.1)


def test_the_box_covers_the_vehicle_it_was_built_from() -> None:
    """The property that matters, asserted without arithmetic.

    Whatever the scaling, every True pixel of the vehicle must fall inside the
    crop -- otherwise the second pass is looking at part of the car.
    """
    source = (3000, 2000)
    plane = working_size(source)
    assert max(plane) == WORKING_LONG_EDGE

    mask = _mask(plane, (37, 41, 300, 211))
    x1, y1, x2, y2 = crop_box(mask, plane, source, margin=0.0)  # type: ignore[misc]

    scale_x, scale_y = source[0] / plane[0], source[1] / plane[1]
    assert x1 <= 37 * scale_x and x2 >= 300 * scale_x
    assert y1 <= 41 * scale_y and y2 >= 211 * scale_y


# ---------------------------------------------------------------------------
# offset_polygons: crop -> whole image
# ---------------------------------------------------------------------------


def test_a_polygon_found_in_a_crop_lands_where_the_crop_was() -> None:
    inside = np.array([[10.0, 20.0], [30.0, 20.0], [30.0, 40.0], [10.0, 40.0]])

    (moved,) = offset_polygons([inside], 500, 300)

    assert moved.tolist() == [[510.0, 320.0], [530.0, 320.0], [530.0, 340.0], [510.0, 340.0]]


def test_forgetting_the_offset_would_move_the_damage_somewhere_else_entirely() -> None:
    """The failure this function exists to prevent, asserted as non-overlap.

    Crop coordinates left unmapped put the car's damage in the top-left of the
    frame. Rasterised, the two do not intersect at all -- so coverage rises and
    nothing was found.
    """
    source = (1000, 1000)
    plane = working_size(source)
    inside = np.array([[10.0, 10.0], [90.0, 10.0], [90.0, 90.0], [10.0, 90.0]])

    unmapped = rasterise([inside], source, plane)
    mapped = rasterise(offset_polygons([inside], 600, 600), source, plane)

    assert unmapped.any() and mapped.any()
    assert not (unmapped & mapped).any()


def test_a_degenerate_polygon_is_dropped_rather_than_moved() -> None:
    """Same rule as `mirror_polygons`: fewer than three points is not an outline."""
    assert offset_polygons([np.array([[0.0, 0.0], [1.0, 1.0]])], 10, 10) == []


def test_a_zero_offset_is_the_identity() -> None:
    polygon = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])

    (moved,) = offset_polygons([polygon], 0, 0)

    assert np.array_equal(moved, polygon)


# ---------------------------------------------------------------------------
# iou: the cross-view merge depends on it
# ---------------------------------------------------------------------------


def test_a_box_against_itself_is_one() -> None:
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == pytest.approx(1.0)


def test_boxes_that_do_not_touch_are_zero() -> None:
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0


def test_boxes_sharing_only_an_edge_are_zero_rather_than_a_sliver() -> None:
    """Touching is not overlapping, and a merge must not fold two neighbours."""
    assert iou((0, 0, 10, 10), (10, 0, 20, 10)) == 0.0


def test_a_half_overlap_is_a_third_by_construction() -> None:
    """Two 10x10 boxes sharing half their area: 50 over 150."""
    assert iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(1 / 3)


def test_a_box_inside_another_is_the_ratio_of_their_areas() -> None:
    assert iou((0, 0, 10, 10), (0, 0, 5, 5)) == pytest.approx(0.25)
