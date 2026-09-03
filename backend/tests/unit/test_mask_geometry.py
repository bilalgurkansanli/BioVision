"""Putting two views and two models into one frame.

These are the coordinate transforms the damaged-area figure is built on. None of
them is clever, and all three fail in the same quiet way: the ratio still comes
out between 0 and 1, so a wrong frame looks exactly like a right one.

The mirror mapping is the sharpest case. Forgetting it unions the damage with
its own reflection, which *raises* pixel coverage — the metric would improve and
the system would be finding nothing new.
"""

from __future__ import annotations

import numpy as np
import pytest

from biovision.models.mask_geometry import (
    WORKING_LONG_EDGE,
    mirror_polygons,
    rasterise,
    share,
    working_size,
)

# ---------------------------------------------------------------------------
# The working plane
# ---------------------------------------------------------------------------


def test_the_plane_preserves_aspect_ratio() -> None:
    """A ratio computed in a squashed plane is not the ratio in the source."""
    width, height = working_size((4000, 3000))
    assert max(width, height) == WORKING_LONG_EDGE
    assert abs(width / height - 4000 / 3000) < 0.01


def test_a_small_photograph_is_not_upscaled() -> None:
    """Growing it would add precision the source does not have."""
    assert working_size((320, 240)) == (320, 240)


def test_a_degenerate_size_is_refused() -> None:
    with pytest.raises(ValueError):
        working_size((0, 100))


# ---------------------------------------------------------------------------
# The mirror mapping
# ---------------------------------------------------------------------------


def test_mirroring_twice_returns_the_original() -> None:
    """The cheapest possible check that the transform is the right one."""
    polygon = np.array([[10.0, 20.0], [90.0, 20.0], [50.0, 80.0]])
    there = mirror_polygons([polygon], width=100)
    back = mirror_polygons(there, width=100)
    assert np.allclose(back[0], polygon)


def test_mirroring_leaves_the_vertical_axis_alone() -> None:
    """The flip is horizontal; a y that moves means the wrong axis was used."""
    polygon = np.array([[10.0, 20.0], [90.0, 35.0], [50.0, 80.0]])
    mirrored = mirror_polygons([polygon], width=100)[0]
    assert np.allclose(mirrored[:, 1], polygon[:, 1])
    assert np.allclose(mirrored[:, 0], [90.0, 10.0, 50.0])


def test_an_unmapped_mirror_would_double_the_area_and_this_does_not() -> None:
    """The failure this function exists to prevent, asserted directly.

    A polygon on the left of the frame, mirrored and mapped back, must land on
    the RIGHT — overlapping the original not at all. Skipping the mapping would
    leave it on the left, union to itself, and report the same pixels twice as
    though a second view had confirmed them.
    """
    plane = (200, 100)
    left = np.array([[10.0, 10.0], [60.0, 10.0], [60.0, 90.0], [10.0, 90.0]])

    original = rasterise([left], (200, 100), plane)
    mapped_back = rasterise(mirror_polygons([left], width=200), (200, 100), plane)

    assert not (original & mapped_back).any(), "the mirrored copy overlaps the original"
    assert mapped_back[:, 100:].any(), "the mirrored copy did not move to the other side"


def test_a_degenerate_width_is_refused() -> None:
    with pytest.raises(ValueError):
        mirror_polygons([np.zeros((3, 2))], width=0)


def test_a_two_point_polygon_is_dropped() -> None:
    """It encloses no area, so it can only add noise to a union."""
    assert mirror_polygons([np.array([[0.0, 0.0], [1.0, 1.0]])], width=10) == []


# ---------------------------------------------------------------------------
# Rasterising and the ratio
# ---------------------------------------------------------------------------


def test_overlapping_polygons_are_a_union_rather_than_a_sum() -> None:
    """Double-counting shared pixels is what would let an area exceed 100%."""
    plane = (100, 100)
    first = np.array([[0.0, 0.0], [60.0, 0.0], [60.0, 60.0], [0.0, 60.0]])
    second = np.array([[40.0, 40.0], [100.0, 40.0], [100.0, 100.0], [40.0, 100.0]])

    separately = rasterise([first], (100, 100), plane).sum() + (
        rasterise([second], (100, 100), plane).sum()
    )
    together = rasterise([first, second], (100, 100), plane).sum()

    assert together < separately, "the overlap was counted twice"


def test_the_share_of_a_missing_denominator_is_zero_rather_than_an_error() -> None:
    """An image with no vehicle found is a normal outcome, not a failure.

    The caller distinguishes it by passing `None` for the ratio it could not
    compute — not by catching an exception.
    """
    covered = np.ones((10, 10), dtype=bool)
    assert share(covered, of=np.zeros((10, 10), dtype=bool)) == 0.0


def test_a_ratio_against_the_vehicle_cannot_exceed_one() -> None:
    """Damage predicted off the car must not inflate the fraction OF the car."""
    damage = np.ones((10, 10), dtype=bool)
    vehicle = np.zeros((10, 10), dtype=bool)
    vehicle[:5, :5] = True
    assert share(damage, of=vehicle) == 1.0
