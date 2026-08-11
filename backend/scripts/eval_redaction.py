"""Measure the redaction miss rate and print the table the README publishes.

The privacy claim in this project is only as strong as the detector behind it, so
the detector gets a number rather than an assertion. **Recall is the metric that
matters here**: a missed face is a privacy failure, while a false positive merely
mosaics some bodywork. Precision is reported for context, not as a target.

    uv run python scripts/eval_redaction.py

Expects an annotated set at `data/redaction_eval/`:

    images/<name>.jpg
    annotations.csv    filename,class,x,y,w,h

`class` is `face` or `plate`. Boxes are in pixels of the image as stored on disk.
Absent that directory this script exits without printing numbers -- an unmeasured
detector must not produce a table that looks measured.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from biovision.config import BACKEND_ROOT
from biovision.pipeline.redact import Detection, RegionDetector, build_redactor

EVAL_DIR = BACKEND_ROOT.parent / "data" / "redaction_eval"

#: Intersection-over-union above which a detection counts as covering a ground-truth
#: box. Deliberately loose: redaction pads its boxes, so covering the region matters
#: far more than tracing it precisely.
IOU_THRESHOLD = 0.3


@dataclass
class Tally:
    hits: int = 0
    misses: int = 0
    false_positives: int = 0

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def recall(self) -> float | None:
        return self.hits / self.total if self.total else None

    @property
    def miss_rate(self) -> float | None:
        return self.misses / self.total if self.total else None


def iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b

    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)

    if right <= left or bottom <= top:
        return 0.0

    overlap = (right - left) * (bottom - top)
    return overlap / (aw * ah + bw * bh - overlap)


def load_annotations(path: Path) -> dict[str, dict[str, list[tuple[int, int, int, int]]]]:
    truth: dict[str, dict[str, list[tuple[int, int, int, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            truth[row["filename"]][row["class"]].append(
                (int(row["x"]), int(row["y"]), int(row["w"]), int(row["h"]))
            )
    return truth


def score(
    detections: list[Detection], expected: list[tuple[int, int, int, int]], tally: Tally
) -> None:
    unmatched = list(detections)
    for box in expected:
        match = next((d for d in unmatched if iou(box, d.box) >= IOU_THRESHOLD), None)
        if match is None:
            tally.misses += 1
        else:
            tally.hits += 1
            unmatched.remove(match)
    tally.false_positives += len(unmatched)


def main() -> int:
    annotations_path = EVAL_DIR / "annotations.csv"
    if not annotations_path.is_file():
        print(f"No annotated set at {EVAL_DIR}.")
        print("Nothing measured, so nothing is reported. See data/README.md.")
        return 1

    redactor = build_redactor(BACKEND_ROOT / "weights")
    detectors: dict[str, RegionDetector | None] = {
        "face": redactor.face_detector,
        "plate": redactor.plate_detector,
    }

    truth = load_annotations(annotations_path)
    tallies: dict[str, Tally] = defaultdict(Tally)

    import cv2  # local: only this script needs the colour conversion

    for filename, per_class in sorted(truth.items()):
        image_path = EVAL_DIR / "images" / filename
        if not image_path.is_file():
            print(f"missing image, skipped: {filename}")
            continue

        rgb = np.asarray(Image.open(image_path).convert("RGB"), dtype=np.uint8)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        for label, expected in per_class.items():
            detector = detectors.get(label)
            found = detector.detect(bgr) if detector is not None else []
            score(found, expected, tallies[label])

    print(f"\nIoU threshold: {IOU_THRESHOLD}\n")
    print(f"{'class':<8} {'detector':<20} {'boxes':>6} {'recall':>8} {'miss rate':>10} {'FP':>5}")
    print("-" * 62)

    for label in ("face", "plate"):
        tally = tallies[label]
        detector = detectors.get(label)
        name = detector.name if detector is not None else "-- not redacted --"
        recall = f"{tally.recall:.1%}" if tally.recall is not None else "n/a"
        miss = f"{tally.miss_rate:.1%}" if tally.miss_rate is not None else "n/a"
        print(
            f"{label:<8} {name:<20} {tally.total:>6} {recall:>8} {miss:>10} "
            f"{tally.false_positives:>5}"
        )

    print("\nPaste this table into README section 5.1, verbatim, including the bad rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
