"""Does a second photograph of the same car find damage the first one missed?

    uv run python -m scripts.eval_multi_photo

**Why this is the feature with the best evidence behind it.** Two independent
results already point at it. Esparza et al. graded 500 buildings against CAL FIRE
inspection records and took accuracy from 0.65 on one frontal photograph to
0.90-0.96 on two or three of the same building, with recall on the partial-damage
class going from 13% to 95%. And this project's own mirror-view TTA (README 7.9)
is the same finding in miniature: the same weights, shown the same photograph
flipped, find damage the original view missed.

**VehiDE turns out to contain real claims.** Its filenames carry a
`DDMMYYYY_HHMMSS` prefix, and 885 of its 10,534 groups hold more than one
photograph. A contact sheet of six such groups was checked by eye before any of
this was written: every one is the same vehicle -- same colour, same panel, same
assessor's marker annotations -- photographed at different distances and angles.
That is what a claim actually looks like, and it means the multi-photo question
can be measured rather than assumed.

**What is measured.** For each group, the findings from one photograph against
the union across all of them:

    photo       damage types from a single photograph, averaged over which one
    claim       damage types in the union of the group

The gap is what a second photograph buys. It is an upper bound on the honest
gain, because these views are of different parts at different zooms -- a claim
where one photograph shows a wheel arch and another a headlight will union to
more types without any single photograph having been wrong.
"""

from __future__ import annotations

import argparse
import collections
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from biovision.models.specialists.vehicle_yolo import (
    VehicleYoloSpecialist,
    build_vehicle_specialist,
)
from scripts._paths import DATA

VEHIDE = DATA / "vehide/image/image"
#: `01012020_172204image853193.jpg` -> `01012020_172204`. The upload timestamp,
#: which the contact sheet showed to be a per-vehicle grouping.
CLAIM = re.compile(r"^(\d{8}_\d{6})")
WORKING_LONG_EDGE = 1280


@dataclass(frozen=True)
class Claim:
    """One vehicle's photographs and what each of them yielded."""

    key: str
    per_photo: tuple[frozenset[str], ...]

    @property
    def union(self) -> frozenset[str]:
        return frozenset().union(*self.per_photo) if self.per_photo else frozenset()

    @property
    def mean_single(self) -> float:
        """Types a reader would get from one photograph, averaged over which."""
        if not self.per_photo:
            return 0.0
        return sum(len(types) for types in self.per_photo) / len(self.per_photo)

    @property
    def photos_with_findings(self) -> int:
        return sum(1 for types in self.per_photo if types)


def to_working_size(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= WORKING_LONG_EDGE:
        return image
    scale = WORKING_LONG_EDGE / longest
    return cv2.resize(
        image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA
    )


def types_in(specialist: VehicleYoloSpecialist, path: Path) -> frozenset[str] | None:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return None
    rgb = cv2.cvtColor(to_working_size(image), cv2.COLOR_BGR2RGB)
    return frozenset(finding.type.value for finding in specialist.analyze_pixels(rgb))


def claims(folder: Path, minimum: int, limit: int) -> list[list[Path]]:
    groups: dict[str, list[Path]] = collections.defaultdict(list)
    for path in sorted(folder.glob("*.jpg")):
        match = CLAIM.match(path.name)
        if match:
            groups[match.group(1)].append(path)
    return [paths for paths in groups.values() if len(paths) >= minimum][:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=VEHIDE)
    parser.add_argument("--min-photos", type=int, default=2)
    parser.add_argument("--limit", type=int, default=250, help="claims to evaluate")
    arguments = parser.parse_args()

    from biovision.config import Settings

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    specialist = build_vehicle_specialist(
        settings.weights_path,
        settings.torch_num_threads,
        confidence_threshold=settings.specialist_min_confidence,
        region_confidence=settings.specialist_region_confidence,
        vehicle_extent=None,
        # Off on purpose: the mirror view is the same idea applied to one
        # photograph, and leaving it on would fold part of the answer into the
        # baseline this is trying to measure against.
        mirror_view=False,
    )
    if specialist is None:
        print("no vehicle checkpoint")
        return 1

    groups = claims(arguments.folder, arguments.min_photos, arguments.limit)
    if not groups:
        print(f"no claims with >= {arguments.min_photos} photographs under {arguments.folder}")
        return 1

    evaluated: list[Claim] = []
    for paths in groups:
        per_photo = [found for path in paths if (found := types_in(specialist, path)) is not None]
        if per_photo:
            evaluated.append(Claim(key=paths[0].name[:15], per_photo=tuple(per_photo)))

    photos = sum(len(claim.per_photo) for claim in evaluated)
    print(f"{len(evaluated)} claims, {photos} photographs, {photos / len(evaluated):.1f} each\n")

    print(f"{'photos':<9}{'claims':>8}{'types, 1 photo':>16}{'types, claim':>14}{'gain':>8}")
    by_size: dict[int, list[Claim]] = collections.defaultdict(list)
    for claim in evaluated:
        by_size[len(claim.per_photo)].append(claim)

    for size in sorted(by_size):
        bucket = by_size[size]
        single = sum(claim.mean_single for claim in bucket) / len(bucket)
        union = sum(len(claim.union) for claim in bucket) / len(bucket)
        print(f"{size:<9}{len(bucket):>8}{single:>16.2f}{union:>14.2f}{union - single:>+8.2f}")

    single = sum(claim.mean_single for claim in evaluated) / len(evaluated)
    union = sum(len(claim.union) for claim in evaluated) / len(evaluated)
    print(f"\n{'all':<9}{len(evaluated):>8}{single:>16.2f}{union:>14.2f}{union - single:>+8.2f}")

    silent = [claim for claim in evaluated if claim.photos_with_findings == 0]
    partial = [
        claim
        for claim in evaluated
        if 0 < claim.photos_with_findings < len(claim.per_photo)
    ]
    print(
        f"\nclaims where NO photograph found anything: {len(silent)}/{len(evaluated)}"
        f"\nclaims where only SOME photographs found something: {len(partial)}/{len(evaluated)}"
        "\n\nThe second line is the one the product turns into a confidence signal:"
        "\na claim whose photographs disagree is a different thing from one where"
        "\nthey all agree, and neither the detector's own score nor the severity"
        "\nband can say which you are holding."
    )
    print(
        "\nThe gain is an UPPER bound on what a second photograph is worth. These"
        "\nviews are of different parts at different zooms, so a claim showing a"
        "\nwheel arch in one frame and a headlight in another unions to more types"
        "\nwithout any single photograph having been wrong."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
