"""Where on the vehicle the damage sits — and why it cannot say "left front".

**The claim this refuses to make.** A photograph does not say which side of a car
you are standing on. The same dent appears on the left of the frame whether it is
the driver's door photographed from outside or the passenger's door photographed
across the bonnet, and nothing in a single image resolves that: it needs the
vehicle's orientation, which needs another model and another measurement nobody
here has made. So this reports position **in the photograph, relative to the
vehicle's own footprint**, and the names say so.

That is less than an assessor wants and more than the system currently says. The
existing answer is "a dent covering 36% of the vehicle", which is true and
useless for finding it; "a dent in the lower third of the vehicle, toward the
left of the frame" is something a person can act on. Combined with several
photographs of one claim it becomes something closer to what a claim form asks,
which is the point of doing this before multi-photo rather than after.

**Everything here is arithmetic on masks that already exist.** The damage plane
and the vehicle plane are both computed for `DamageRegion`; this adds no model,
no download and no measurable latency. It is also why there is no accuracy
number attached: there is nothing to be accurate about. The zones are a
description of a mask, not a prediction, and a description cannot be wrong in the
way a prediction can — it can only be reported in units that mislead, which is
what the naming is for.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from biovision.schemas.enums import Band, Level

#: Damage covering less of a zone than this is not called out. A stray pixel
#: clipping into the next third would otherwise list a zone the reader cannot
#: see anything in. Stated rather than fitted: it is one part in fifty of the
#: vehicle's footprint, chosen for being legible, and no evaluation set was
#: consulted in picking it.
MIN_ZONE_SHARE = 0.02

#: `Band` and `Level` are defined in `schemas.enums` -- they are strings a
#: client branches on, and keeping them there is what stops the response
#: contract from having to import this package. Re-exported because this is
#: the module that produces the values and every caller reaches for them here.
__all__ = ["Band", "DamagePosition", "Level", "ZoneShare", "locate"]


@dataclass(frozen=True)
class ZoneShare:
    """How much of one zone of the vehicle the damage covers."""

    band: Band
    level: Level
    #: Damaged pixels in this zone as a fraction of the zone's vehicle pixels.
    #: Divided by the VEHICLE's area in the zone rather than the zone's whole
    #: rectangle: a corner zone is mostly background, and dividing by the
    #: rectangle would make the same dent look smaller there than in the middle.
    share: float


@dataclass(frozen=True)
class DamagePosition:
    """Where the damage sits within the vehicle, as this photograph frames it."""

    zones: tuple[ZoneShare, ...]
    #: The heaviest zone, or None when the damage is too diffuse to have one.
    dominant: ZoneShare | None

    @property
    def spans_whole_vehicle(self) -> bool:
        """True when damage reaches every zone.

        Worth reporting on its own: it usually means the detector has smeared
        rather than that the car is uniformly wrecked, and a reader who sees six
        zones listed should be told that rather than left to notice it.
        """
        return len(self.zones) == len(Band) * len(Level)


def _bounds(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Tight box around the True pixels, as (top, left, bottom, right)."""
    rows = np.flatnonzero(mask.any(axis=1))
    columns = np.flatnonzero(mask.any(axis=0))
    if rows.size == 0 or columns.size == 0:
        return None
    return int(rows[0]), int(columns[0]), int(rows[-1]) + 1, int(columns[-1]) + 1


def locate(damage: np.ndarray, vehicle: np.ndarray) -> DamagePosition | None:
    """Split the vehicle's footprint into six zones and report where damage is.

    Returns `None` when the vehicle could not be located or carries no damage.
    That null is the same load-bearing null as `area_ratio_vehicle`: without a
    vehicle there is no frame of reference, and positions relative to the
    photograph instead would be a different measurement wearing the same name.

    Zones are cut from the vehicle's **bounding box**, not from the frame. A car
    at the left edge of a wide shot has its own left, middle and right, and using
    the frame's thirds would report the photographer's composition instead of the
    car's geometry.
    """
    if damage.shape != vehicle.shape:
        raise ValueError(
            f"damage plane {damage.shape} and vehicle plane {vehicle.shape} must match; "
            "both come from mask_geometry.working_size and a mismatch means one was "
            "rasterised against the wrong image"
        )

    box = _bounds(vehicle)
    if box is None:
        return None
    top, left, bottom, right = box

    inside = damage & vehicle
    if not inside.any():
        return None

    height, width = bottom - top, right - left
    # Thirds by pixel index rather than by area: an even split of the box is
    # what a reader pictures when told "the middle third of the car".
    columns = [left, left + width // 3, left + (2 * width) // 3, right]
    rows = [top, top + height // 2, bottom]

    zones: list[ZoneShare] = []
    for level_index, level in enumerate(Level):
        for band_index, band in enumerate(Band):
            row_slice = slice(rows[level_index], rows[level_index + 1])
            column_slice = slice(columns[band_index], columns[band_index + 1])
            vehicle_here = float(vehicle[row_slice, column_slice].sum())
            if vehicle_here <= 0:
                continue
            damaged_here = float(inside[row_slice, column_slice].sum())
            share = damaged_here / vehicle_here
            if share >= MIN_ZONE_SHARE:
                zones.append(ZoneShare(band=band, level=level, share=round(share, 4)))

    if not zones:
        return None

    ordered = tuple(sorted(zones, key=lambda zone: zone.share, reverse=True))
    return DamagePosition(zones=ordered, dominant=ordered[0])
