"""The outline is for drawing, and the tests bound what that costs.

The specialist measures area from a segmentation mask and the UI drew a
rectangle, so `area_ratio` was a number nobody looking at the screen could check.
The box is also the shape `_area_ratio` deliberately refuses to measure: a thin
diagonal scratch's box is large and mostly empty, which is exactly the
overstatement the mask exists to avoid — and it was the only thing on screen.

Sending the mask solves that and introduces two ways to be wrong, both tested
here:

* **Payload.** Ultralytics returns a point per boundary pixel. A claim of six
  photographs with eight findings each would put the outlines far above
  everything else in the response.
* **Disagreement.** A simplified outline does not enclose the same area as the
  contour `area_ratio` was measured from. "Slightly" is not a claim, so it is
  bounded here at 5% — the measured worst case, on a 20 px circle where the
  binding error is not the simplification at all but rounding each vertex to a
  whole pixel. `mask_geometry.simplify` carries the table.

Area is compared with the shoelace formula rather than by rasterising both
shapes. Rasterising a 20 px circle into the 640 px working plane moves its area
by more than the simplification does, so a rasterised comparison would report on
the discretisation and call it drift.
"""

from __future__ import annotations

import numpy as np
import pytest

from biovision.models.mask_geometry import (
    OUTLINE_MAX_POINTS,
    rasterise,
    share,
    simplify,
    working_size,
)

SOURCE = (1280, 960)


def _circle(cx: float, cy: float, radius: float, points: int = 720) -> np.ndarray:
    angles = np.linspace(0, 2 * np.pi, points, endpoint=False)
    return np.column_stack((cx + radius * np.cos(angles), cy + radius * np.sin(angles)))


def _ragged_strip(length: int = 600) -> np.ndarray:
    """A long thin scratch with pixel-level jitter along both edges.

    The shape simplification is meant for, and the one whose bounding box lies
    about its area.
    """
    xs = np.linspace(100, 1100, length)
    top = np.column_stack((xs, 400 + np.sin(xs) * 1.5))
    bottom = np.column_stack((xs[::-1], 430 + np.cos(xs[::-1]) * 1.5))
    return np.vstack((top, bottom))


# ---------------------------------------------------------------------------
# Payload
# ---------------------------------------------------------------------------


def test_a_dense_contour_becomes_a_shape_worth_sending() -> None:
    dense = _circle(640, 480, 200)

    outline = simplify(dense, SOURCE)

    assert outline is not None
    assert len(dense) == 720
    assert len(outline) < 60, "a circle should not need sixty points at this tolerance"


def test_no_outline_may_exceed_the_cap() -> None:
    """A pathological contour degrades in shape rather than in payload."""
    outline = simplify(_ragged_strip(), SOURCE)

    assert outline is not None
    assert len(outline) <= OUTLINE_MAX_POINTS


def test_a_shape_already_simple_is_left_alone() -> None:
    square = np.array([[10.0, 10.0], [110.0, 10.0], [110.0, 110.0], [10.0, 110.0]])

    outline = simplify(square, SOURCE)

    assert outline == [(10, 10), (110, 10), (110, 110), (10, 110)]


# ---------------------------------------------------------------------------
# Agreement with the measurement
# ---------------------------------------------------------------------------


def _shoelace(polygon: np.ndarray) -> float:
    """Exact area of a closed polygon, so the comparison isolates simplification."""
    points = np.asarray(polygon, dtype=float)
    x, y = points[:, 0], points[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


@pytest.mark.parametrize(
    ("name", "polygon"),
    [
        ("large circle", _circle(640, 480, 200)),
        ("medium circle", _circle(300, 300, 80)),
        ("small circle", _circle(300, 300, 40)),
        ("tiny circle", _circle(100, 100, 20)),
        ("ragged strip", _ragged_strip()),
    ],
)
def test_the_drawn_shape_encloses_what_the_measured_one_does_within_five_percent(
    name: str, polygon: np.ndarray
) -> None:
    """`area_ratio` comes from the full contour; the outline only draws it.

    They are allowed to differ -- the field description says so -- but not by
    enough that a reader checking the picture against the number would be right
    to think one of them is wrong. 5% is the measured worst case, not a hope: the
    table in `mask_geometry.simplify` says which shape produces it and why.
    """
    outline = simplify(polygon, SOURCE)
    assert outline is not None

    measured = _shoelace(polygon)
    drawn = _shoelace(np.asarray(outline, dtype=float))

    assert measured > 0
    assert abs(drawn - measured) / measured < 0.05, f"{name}: outline drifted from the mask"


def test_a_bigger_finding_is_drawn_more_faithfully_than_a_tiny_one() -> None:
    """The error is dominated by whole-pixel rounding, so it shrinks with size.

    Asserted as a direction rather than a pair of numbers: the point is that the
    drift is a quantisation artefact of small shapes, not a tolerance that grows
    with the damage.
    """
    big = _circle(640, 480, 200)
    small = _circle(100, 100, 20)

    def drift(polygon: np.ndarray) -> float:
        outline = simplify(polygon, SOURCE)
        assert outline is not None
        exact = _shoelace(polygon)
        return abs(_shoelace(np.asarray(outline, dtype=float)) - exact) / exact

    assert drift(big) < drift(small)


def test_the_outline_lands_on_the_damage_it_came_from() -> None:
    """Rasterised, the drawn shape and the mask must be the same region.

    The area bound above would pass for a shape of the right size in the wrong
    place. This is the assertion that it is the same damage.
    """
    plane = working_size(SOURCE)
    polygon = _circle(640, 480, 200)
    outline = simplify(polygon, SOURCE)
    assert outline is not None

    mask = rasterise([polygon], SOURCE, plane)
    drawn = rasterise([np.asarray(outline, dtype=float)], SOURCE, plane)

    overlap = float((mask & drawn).sum()) / float((mask | drawn).sum())
    assert overlap > 0.95, "the outline is not on top of the mask it simplifies"
    assert share(mask) > 0


def test_the_outline_stays_inside_the_photograph() -> None:
    """A contour touching the edge must not simplify into a negative coordinate."""
    edge = np.array([[0.0, 0.0], [1280.0, 0.0], [1280.0, 40.0], [0.0, 40.0]])

    outline = simplify(edge, SOURCE)

    assert outline is not None
    assert all(0 <= x <= SOURCE[0] and 0 <= y <= SOURCE[1] for x, y in outline)


# ---------------------------------------------------------------------------
# Degenerate input
# ---------------------------------------------------------------------------


def test_fewer_than_three_points_is_not_an_outline() -> None:
    assert simplify(np.array([[0.0, 0.0], [10.0, 10.0]]), SOURCE) is None


def test_a_contour_that_collapses_to_a_line_returns_nothing() -> None:
    """A shape with no area cannot be drawn, and null is how the schema says so."""
    flat = np.array([[10.0, 10.0], [200.0, 10.0], [400.0, 10.0], [600.0, 10.0]])

    assert simplify(flat, SOURCE) is None


def test_every_point_is_an_integer_pixel_in_the_source_frame() -> None:
    outline = simplify(_circle(640, 480, 100), SOURCE)

    assert outline is not None
    assert all(isinstance(x, int) and isinstance(y, int) for x, y in outline)
