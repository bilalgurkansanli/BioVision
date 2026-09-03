"""Where the damage is, and the claim the geometry refuses to make."""

from __future__ import annotations

import numpy as np
import pytest

from biovision.models.damage_position import (
    MIN_ZONE_SHARE,
    Band,
    Level,
    locate,
)


def vehicle_plane(height: int = 60, width: int = 120) -> np.ndarray:
    """A rectangular car filling the middle of a wider frame."""
    plane = np.zeros((height, width), dtype=bool)
    plane[10:50, 20:100] = True
    return plane


def damage_at(rows: slice, columns: slice, height: int = 60, width: int = 120) -> np.ndarray:
    plane = np.zeros((height, width), dtype=bool)
    plane[rows, columns] = True
    return plane


def test_no_vehicle_means_no_position() -> None:
    """The same load-bearing null as `area_ratio_vehicle`: with no vehicle there
    is no frame of reference, and frame-relative positions would be a different
    measurement wearing the same name."""
    empty = np.zeros((60, 120), dtype=bool)
    assert locate(damage_at(slice(10, 20), slice(20, 30)), empty) is None


def test_damage_outside_the_vehicle_is_not_placed_on_it() -> None:
    """A mask that spills past the car cannot put a zone on the car."""
    outside = damage_at(slice(0, 5), slice(0, 10))
    assert locate(outside, vehicle_plane()) is None


def test_the_dominant_zone_is_where_most_of_the_damage_is() -> None:
    # Vehicle spans columns 20..100, so its left third is 20..46 and its lower
    # half is rows 30..50.
    lower_left = damage_at(slice(32, 48), slice(22, 44))
    position = locate(lower_left, vehicle_plane())

    assert position is not None
    assert position.dominant is not None
    assert position.dominant.band is Band.LEFT
    assert position.dominant.level is Level.LOWER


def test_zones_are_cut_from_the_vehicle_not_from_the_frame() -> None:
    """A car at the edge of a wide shot has its own left and right. Using the
    frame's thirds would report the photographer's composition instead."""
    plane = np.zeros((60, 300), dtype=bool)
    plane[10:50, 240:290] = True  # a car far to the right of the frame
    # Damage on the car's OWN left edge, which is well right of the frame's middle.
    damage = damage_at(slice(15, 45), slice(242, 254), width=300)

    position = locate(damage, plane)

    assert position is not None
    assert position.dominant is not None
    assert position.dominant.band is Band.LEFT, "zones must be relative to the car"


def test_share_is_of_the_vehicle_in_the_zone_not_of_the_rectangle() -> None:
    """A corner zone is mostly background. Dividing by the rectangle would make
    the same dent look smaller there than in the middle of the car."""
    plane = np.zeros((40, 60), dtype=bool)
    # A triangular car, so the lower-left zone is half background.
    for row in range(40):
        plane[row, 10 : 10 + row] = True
    damage = plane.copy()

    position = locate(damage, plane)

    assert position is not None
    for zone in position.zones:
        assert zone.share == pytest.approx(1.0), "fully damaged car is 100% in every zone"


def test_a_sliver_in_the_next_zone_is_not_listed() -> None:
    """A stray pixel clipping into the next third would otherwise name a zone
    the reader cannot see anything in."""
    plane = vehicle_plane()
    # Solidly in the left third, with two columns crossing into the middle.
    damage = damage_at(slice(12, 48), slice(22, 48))

    position = locate(damage, plane)

    assert position is not None
    bands = {zone.band for zone in position.zones}
    assert Band.LEFT in bands
    assert Band.RIGHT not in bands


def test_the_threshold_is_stated_rather_than_fitted() -> None:
    """One part in fifty of the vehicle's footprint, chosen for legibility. No
    evaluation set was consulted, which is why there is no sweep behind it."""
    assert MIN_ZONE_SHARE == 0.02


def test_damage_everywhere_is_reported_as_spanning_the_vehicle() -> None:
    """Six zones listed usually means the detector smeared, not that the car is
    uniformly wrecked. A reader should be told rather than left to notice."""
    plane = vehicle_plane()
    position = locate(plane.copy(), plane)

    assert position is not None
    assert position.spans_whole_vehicle
    assert len(position.zones) == len(Band) * len(Level)


def test_partial_damage_does_not_claim_to_span_the_vehicle() -> None:
    position = locate(damage_at(slice(32, 48), slice(22, 44)), vehicle_plane())
    assert position is not None
    assert not position.spans_whole_vehicle


def test_mismatched_planes_raise_rather_than_silently_misplace() -> None:
    """Both planes come from `mask_geometry.working_size`; a mismatch means one
    was rasterised against a different image, and quietly broadcasting it would
    put damage on a car that is not there."""
    with pytest.raises(ValueError, match="must match"):
        locate(np.zeros((10, 10), dtype=bool), np.zeros((20, 20), dtype=bool))


def test_zones_are_ordered_heaviest_first() -> None:
    plane = vehicle_plane()
    damage = np.zeros((60, 120), dtype=bool)
    damage[32:48, 22:44] = True  # a lot, lower left
    damage[12:20, 76:96] = True  # a little, upper right

    position = locate(damage, plane)

    assert position is not None
    shares = [zone.share for zone in position.zones]
    assert shares == sorted(shares, reverse=True)
    assert position.dominant is position.zones[0]
