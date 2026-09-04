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

import math
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


def crop_box(
    mask: np.ndarray,
    plane: tuple[int, int],
    source: tuple[int, int],
    margin: float,
) -> tuple[int, int, int, int] | None:
    """The mask's bounding box, in SOURCE coordinates, grown by `margin`.

    Two frames meet here and getting the direction wrong is the failure this
    function is separated out to make testable: the vehicle mask lives in the
    reduced working plane, and a crop has to be taken from the full-resolution
    pixels. Scaling the wrong way produces a box that is plausible, in frame, and
    around the wrong part of the photograph.

    `margin` is a fraction of the box's own width and height, added on every side
    and then clamped to the frame. It is not decoration: a crop cutting exactly at
    the mask boundary removes the panel edges that tell the detector what it is
    looking at, and the vehicle mask is itself approximate.

    Returns None for an empty mask -- the same first-class "no vehicle" answer the
    rest of this pipeline carries rather than a zero-area box.
    """
    if margin < 0:
        raise ValueError(f"margin must not be negative, got {margin}")

    rows = np.flatnonzero(mask.any(axis=1))
    columns = np.flatnonzero(mask.any(axis=0))
    if rows.size == 0 or columns.size == 0:
        return None

    # Plane -> source. `working_size` only ever shrinks and preserves the aspect
    # ratio, so one scale per axis is exact up to the rounding it already did.
    scale_x = source[0] / plane[0]
    scale_y = source[1] / plane[1]
    left = float(columns[0]) * scale_x
    right = float(columns[-1] + 1) * scale_x
    top = float(rows[0]) * scale_y
    bottom = float(rows[-1] + 1) * scale_y

    pad_x = (right - left) * margin
    pad_y = (bottom - top) * margin

    # Out, never in: floor the near edges and ceil the far ones. Rounding to
    # nearest lets the box cut half a pixel into the vehicle at the far edge,
    # which means the second pass is looking at slightly less than the car. The
    # cost of erring outwards is a few background pixels; the cost of erring
    # inwards is a crop that silently excludes damage.
    x1 = max(0, math.floor(left - pad_x))
    y1 = max(0, math.floor(top - pad_y))
    x2 = min(source[0], math.ceil(right + pad_x))
    y2 = min(source[1], math.ceil(bottom + pad_y))

    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def offset_polygons(polygons: Iterable[Polygon], dx: float, dy: float) -> list[np.ndarray]:
    """Map polygons found inside a crop back to the whole image.

    A sibling of `mirror_polygons`, separated for the same reason: leaving crop
    detections in crop coordinates piles the car's damage into the top-left corner
    of the frame, which raises coverage and looks like the crop worked.
    """
    moved = []
    for polygon in polygons:
        points = np.asarray(polygon, dtype=float)
        if len(points) < 3:
            continue
        moved.append(np.column_stack((points[:, 0] + dx, points[:, 1] + dy)))
    return moved


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Intersection over union of two (x1, y1, x2, y2) boxes.

    Here rather than in the specialist because it is geometry, and because the
    cross-view merge that uses it is the step that decides whether a second look
    adds a finding or repeats one.
    """
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    if right <= left or bottom <= top:
        return 0.0
    overlap = (right - left) * (bottom - top)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - overlap
    return overlap / union if union > 0 else 0.0


#: How far a simplified outline may stray from the mask it came from, as a share
#: of the image's long edge. 0.002 is ~2.5 px on a 1280 px photograph -- below
#: what a viewer can see against a 2 px stroke, and enough to take a mask contour
#: from several hundred points to a few dozen.
OUTLINE_TOLERANCE = 0.002

#: Hard cap on points per outline. A pathological contour -- a scratch traced
#: pixel by pixel across a bumper -- must not be able to put a kilobyte of JSON
#: into a response per finding. Reached by raising the tolerance until it fits,
#: so the shape degrades rather than being truncated into an open curve.
OUTLINE_MAX_POINTS = 64


def _perpendicular_distance(
    points: np.ndarray, start: np.ndarray, end: np.ndarray
) -> np.ndarray:
    """Distance from each point to the infinite line through start and end."""
    line = end - start
    length = float(np.hypot(*line))
    if length == 0.0:
        collapsed: np.ndarray = np.hypot(*(points - start).T)
        return collapsed
    # 2-D cross product: |(p - a) x (b - a)| / |b - a|.
    offsets = points - start
    distances: np.ndarray = (
        np.abs(offsets[:, 0] * line[1] - offsets[:, 1] * line[0]) / length
    )
    return distances


def _douglas_peucker(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Ramer-Douglas-Peucker, iteratively.

    Iteratively rather than recursively because a mask contour can carry several
    thousand points and Python's recursion limit is not a property of the
    photograph.
    """
    if len(points) < 3:
        return points

    keep = np.zeros(len(points), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]

    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        segment = points[first + 1 : last]
        distances = _perpendicular_distance(segment, points[first], points[last])
        index = int(np.argmax(distances))
        if distances[index] > tolerance:
            split = first + 1 + index
            keep[split] = True
            stack.append((first, split))
            stack.append((split, last))

    return points[keep]


def simplify(
    polygon: Polygon,
    source: tuple[int, int],
    tolerance: float = OUTLINE_TOLERANCE,
    max_points: int = OUTLINE_MAX_POINTS,
) -> list[tuple[int, int]] | None:
    """A mask contour reduced to something worth putting in a response.

    Ultralytics returns contours with a point per boundary pixel -- several
    hundred for one dent, and a claim carries several photographs of several
    findings each. Sent raw that is the largest thing in the response, to draw a
    shape whose extra points no viewer can resolve.

    **The outline is for drawing, not for measuring, and the two must not be
    confused.** `area_ratio` is rasterised from the full-resolution contour;
    the area enclosed by these points is not the same number. Measured rather
    than hand-waved, as the share of the contour's own area that the simplified
    outline loses:

    ========================  =========  ========
    shape                     points     drift
    ========================  =========  ========
    circle, 200 px radius     720 -> 33    -0.6%
    circle, 80 px radius      720 -> 17    -2.5%
    circle, 20 px radius      720 -> 17    -3.6%
    circle, 10 px radius      720 -> 17    -4.5%
    ragged 1000x30 scratch   1200 ->  4    +3.3%
    ========================  =========  ========

    **The small end is integer pixels, not simplification.** Below about 40 px
    across, rounding each vertex to a whole pixel moves more area than the point
    dropping does -- the same quantisation `bbox` already carries, and the reason
    the coordinates are integers is that `bbox` is. A finding that small is a few
    ten-thousandths of the frame, so the drift is a large share of a number
    nothing hinges on.

    Coordinates come back as integers in the source frame, because that is the
    frame `bbox` is in and a client should not have to hold two.
    """
    points = np.asarray(polygon, dtype=float)
    if len(points) < 3:
        return None

    # Two bounds, and the tighter one wins.
    #
    # A tolerance set only from the image's long edge is a fixed number of pixels,
    # which a large dent absorbs and a small one does not: at 2.5 px a 40 px
    # radius contour lost 4.3% of its area, against 0.1% for a 200 px one. Since
    # the point of drawing the mask is that a reader can check `area_ratio`
    # against it, an error that grows as the damage shrinks is the wrong way
    # round. So the shape's own diagonal bounds it too, and small findings keep
    # their proportions at the cost of a few more points -- which they can
    # afford, having few boundary pixels to begin with.
    diagonal = float(np.hypot(*(points.max(axis=0) - points.min(axis=0))))
    epsilon = max(0.5, min(max(source) * tolerance, diagonal * 0.008))
    simplified = _douglas_peucker(points, epsilon)

    # Raise the tolerance rather than truncate: dropping the tail of a contour
    # leaves an open curve that renders as a wedge across the panel.
    while len(simplified) > max_points and epsilon < max(source):
        epsilon *= 1.6
        simplified = _douglas_peucker(points, epsilon)

    if len(simplified) < 3:
        return None

    outline = [
        (
            int(min(max(0, round(x)), source[0])),
            int(min(max(0, round(y)), source[1])),
        )
        for x, y in simplified
    ]
    # Rounding can collapse neighbours onto one pixel; a repeated vertex is not
    # wrong but it is payload for nothing.
    deduped = [
        point
        for index, point in enumerate(outline)
        if index == 0 or point != outline[index - 1]
    ]
    return deduped if len(deduped) >= 3 else None


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
