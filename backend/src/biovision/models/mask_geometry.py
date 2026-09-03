"""Putting two models' masks into one frame so they can be intersected.

The damage specialist and the vehicle extent model are separate networks with
separate input sizes, and both report masks two ways: `masks.data`, a tensor at
whatever shape the letterbox produced, and `masks.xy`, polygons in the source
image's own coordinates. Only the second is unambiguous, so everything here goes
through polygons.

**Why a reduced working plane rather than the full image.** The ratios this
supports -- damaged area over vehicle area -- are stable to a pixel or two, and
rasterising a dozen polygons at 4000x3000 costs real milliseconds on the CPU this
runs on. A 640-long-edge plane preserves the aspect ratio, so a ratio computed in
it equals the ratio in the source frame up to rounding at the boundary.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np
from PIL import Image, ImageDraw

#: A closed outline as (x, y) pairs. Both forms appear in practice: Ultralytics
#: hands back numpy arrays, and hand-written call sites use plain sequences.
#: Naming the union keeps the two from needing separate code paths.
Polygon = Sequence[Sequence[float]] | np.ndarray

#: Long edge of the plane every mask is rasterised into. Not configurable: two
#: masks compared in different planes would silently produce a wrong ratio, and
#: the only safe way to guarantee one plane is to have exactly one number.
WORKING_LONG_EDGE = 640


def working_size(source: tuple[int, int]) -> tuple[int, int]:
    """Plane size for a source image, preserving aspect ratio.

    Never upscales: a small photograph is rasterised at its own size, because
    growing it would add precision the source does not have.
    """
    width, height = source
    if width <= 0 or height <= 0:
        raise ValueError(f"source size must be positive, got {source}")
    longest = max(width, height)
    if longest <= WORKING_LONG_EDGE:
        return width, height
    scale = WORKING_LONG_EDGE / longest
    return max(1, round(width * scale)), max(1, round(height * scale))


def rasterise(
    polygons: Iterable[Polygon],
    source: tuple[int, int],
    plane: tuple[int, int],
) -> np.ndarray:
    """Union of polygons given in source coordinates, as a boolean plane.

    A union rather than a list of instances: overlapping detections of the same
    damage would otherwise be counted twice, and double-counting area is exactly
    the failure that would inflate a severity band.
    """
    canvas = Image.new("1", plane, 0)
    draw = ImageDraw.Draw(canvas)
    scale_x = plane[0] / source[0]
    scale_y = plane[1] / source[1]
    for polygon in polygons:
        if len(polygon) < 3:
            continue
        draw.polygon(
            [(float(point[0]) * scale_x, float(point[1]) * scale_y) for point in polygon],
            fill=1,
            outline=1,
        )
    return np.array(canvas, dtype=bool)


def mirror_polygons(polygons: Iterable[Polygon], width: int) -> list[np.ndarray]:
    """Map polygons found in a mirrored image back to the original frame.

    Pulled out of the specialist and given a test of its own because it is the
    one step of the mirror-view pass that can fail silently and look like a win:
    leaving the polygons in mirror coordinates unions the damage with its own
    reflection, which raises pixel coverage without finding anything.

    `x -> width - x`; `y` is untouched, since the flip is horizontal.
    """
    if width <= 0:
        raise ValueError(f"width must be positive, got {width}")
    mirrored = []
    for polygon in polygons:
        points = np.asarray(polygon, dtype=float)
        if len(points) < 3:
            continue
        mirrored.append(np.column_stack((width - points[:, 0], points[:, 1])))
    return mirrored


def share(covered: np.ndarray, of: np.ndarray | None = None) -> float:
    """Fraction of `of` that `covered` occupies, or of the whole plane when None.

    Returns 0.0 for an empty denominator rather than raising: an image where no
    vehicle was found is a normal outcome, and the caller distinguishes it by
    passing `None` for the ratio it could not compute -- not by catching an error.
    """
    if of is None:
        total = float(covered.size)
        return float(covered.sum()) / total if total else 0.0
    denominator = float(of.sum())
    if denominator <= 0:
        return 0.0
    return min(1.0, float((covered & of).sum()) / denominator)
