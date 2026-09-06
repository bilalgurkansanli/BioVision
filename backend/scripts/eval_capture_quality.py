"""Does a blurry claim photograph actually cost the specialist anything?

    uv run python -m scripts.eval_capture_quality --against-specialist

Before telling a user their photograph is too blurry, it is worth knowing what
"too blurry" costs on the photographs this system already handles. A number
invented at the keyboard would reject good uploads and pass bad ones, and nobody
would find out: **a capture gate fails silently by definition**, because the
analysis it prevented never happened.

Three cheap signals, measured over VehiDE -- the images the specialist was
trained and evaluated on, and therefore by construction the ones it copes with:

    blur       variance of the Laplacian, the standard sharpness proxy. Low is
               soft. It scales with contrast and resolution, so it is comparable
               only within one corpus at one working size, which is exactly why
               it has to be measured here rather than borrowed.
    clipped    share of pixels crushed to black or blown to white. A photograph
               can be sharp and still show nothing.
    contrast   standard deviation of luminance. Separates "dark photograph" from
               "photograph of a dark car", which the clipped figure alone does
               not.

**One pass, by construction.** An earlier version measured the signals in one
loop and ran the detector in another, then paired them by index. A single
unreadable JPEG slid every later photograph onto the wrong measurement -- caught
by a `strict=True` zip, which is the only reason it was caught at all. Reading
each image once and producing both numbers together makes that class of bug
unrepresentable rather than tested for.

Findings per image is a proxy for recall, not recall: a blurry photograph may
genuinely contain less damage. It is directional evidence over one corpus and it
is reported as that.
"""

from __future__ import annotations

import argparse
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
#: The long edge the pipeline stores at. Blur must be measured at the size the
#: system will see, because the variance of the Laplacian moves with resolution.
WORKING_LONG_EDGE = 1280

#: Pixels at or below / at or above these count as crushed and blown.
BLACK, WHITE = 8, 247

SIGNALS = ("blur", "clipped", "contrast")


@dataclass(frozen=True)
class Sample:
    """One photograph's signals and, optionally, what the detector found in it."""

    blur: float
    clipped: float
    contrast: float
    findings: int | None


def to_working_size(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= WORKING_LONG_EDGE:
        return image
    scale = WORKING_LONG_EDGE / longest
    return cv2.resize(
        image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA
    )


def sample(path: Path, specialist: VehicleYoloSpecialist | None) -> Sample | None:
    """Signals and findings from a single read, or None if unreadable."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return None
    resized = to_working_size(image)
    grey = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    findings = None
    if specialist is not None:
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        findings = len(specialist.analyze_pixels(rgb))
    return Sample(
        blur=float(cv2.Laplacian(grey, cv2.CV_64F).var()),
        clipped=float(((grey <= BLACK) | (grey >= WHITE)).mean()),
        contrast=float(grey.std()),
        findings=findings,
    )


def load_specialist() -> VehicleYoloSpecialist | None:
    from biovision.config import Settings

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    return build_vehicle_specialist(
        settings.weights_path,
        settings.torch_num_threads,
        confidence_threshold=settings.specialist_min_confidence,
        region_confidence=settings.specialist_region_confidence,
        vehicle_extent=None,
        mirror_view=False,
    )


def distribution(samples: list[Sample]) -> None:
    points = (1, 5, 10, 25, 50, 75, 95)
    print(f"{'percentile':<12}" + "".join(f"{point:>10}" for point in points))
    for name, form in (("blur", "{:>10.0f}"), ("clipped", "{:>10.2%}"), ("contrast", "{:>10.1f}")):
        values = np.asarray([getattr(item, name) for item in samples], dtype=np.float64)
        row = [float(np.percentile(values, point)) for point in points]
        print(f"{name:<12}" + "".join(form.format(value) for value in row))


def against_findings(samples: list[Sample]) -> None:
    """Findings per image by quartile of each signal, from the same samples."""
    scored = [item for item in samples if item.findings is not None]
    if not scored:
        return
    print(f"\n{len(scored)} images scored by the specialist")

    for name in SIGNALS:
        values = np.asarray([getattr(item, name) for item in scored], dtype=np.float64)
        edges = np.percentile(values, [25, 50, 75])
        buckets: dict[int, list[int]] = {index: [] for index in range(4)}
        for item, value in zip(scored, values, strict=True):
            assert item.findings is not None  # filtered above; keeps mypy honest
            buckets[int(np.searchsorted(edges, value))].append(item.findings)

        print(f"\nfindings per image by {name} quartile (Q1 = lowest {name})")
        print(f"  {'quartile':<10}{'images':>8}{'findings/img':>14}{'found nothing':>16}")
        for index in sorted(buckets):
            counts = buckets[index]
            if not counts:
                continue
            empty = sum(1 for count in counts if count == 0) / len(counts)
            mean = sum(counts) / len(counts)
            print(f"  Q{index + 1:<9}{len(counts):>8}{mean:>14.2f}{empty:>15.0%}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--folder", type=Path, default=VEHIDE)
    parser.add_argument(
        "--against-specialist",
        action="store_true",
        help="also run the detector and report findings per image by quartile",
    )
    arguments = parser.parse_args()

    paths = sorted(
        p for p in arguments.folder.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )[: arguments.limit]
    if not paths:
        print(f"no images under {arguments.folder}")
        return 1

    specialist = load_specialist() if arguments.against_specialist else None
    if arguments.against_specialist and specialist is None:
        print("no vehicle checkpoint; measuring the distribution only")

    samples = [item for item in (sample(path, specialist) for path in paths) if item is not None]
    print(f"{len(samples)} of {len(paths)} photographs read, at {WORKING_LONG_EDGE}px\n")
    distribution(samples)
    against_findings(samples)

    print(
        "\nThese are photographs the specialist was trained and evaluated on, so they\n"
        "are by construction the ones this system copes with. A warning set at the\n"
        "1st percentile fires on the worst 1% of images LIKE THESE, and says nothing\n"
        "about a photograph unlike any of them -- the gate's out-of-distribution\n"
        "check remains the layer for that."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
