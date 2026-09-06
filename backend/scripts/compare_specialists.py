"""Two damage models on the same photographs, scored the same way.

    uv run python -m scripts.compare_specialists 60

Run after a candidate replacement looks good on one image. It will not be.

The models answer different questions -- ours names the damage type and segments
it, the alternative names the damaged part -- so their class labels cannot be
compared, and their boxes are not the same size either: a part box covers a whole
bonnet, a damage polygon covers the dent in it. Matching those at IoU 0.5 would
punish both for the wrong reason.

So this scores **coverage**, class-agnostic:

* found     -- a ground-truth damage whose centre falls inside some detection
* useful    -- a detection containing at least one ground-truth damage
* silent    -- images where a model returned nothing at all

`found` is recall's question: did the model point at the damage. `useful` is
precision's: was the box about damage rather than about road or sky.

**The alternative model has never seen VehiDE.** This is a cross-dataset test and
it is disadvantaged by that. Ours was trained on exactly these photographs, in
this framing -- so the close-up regime is its home ground.

**What this found, and why the script is kept.** A part-based model
(vineetsarpal/yolov11n-car-damage, Apache 2.0) read one reported accident photo
far better than ours: bonnet-dent 0.71, front-bumper-dent 0.47, headlight 0.40,
all correctly placed, against our single `dent` 0.42. Measured across 60 images
it is worse in both regimes and much worse in the wide one -- silent on 25 of 60.

The explanation is in what each model looks for. Part classes need the part
visible; VehiDE photographs are close-ups of damage where no whole bonnet or
bumper appears, so it finds nothing. The reported photograph showed a whole car,
which is why it worked there.

**So neither result generalises to the other, and this project does not have the
set that would settle it** -- whole-vehicle photographs with damage annotations.
Choosing a model from one image is the same error as choosing a confidence floor
from one image, which ADR-033 rejected two hours earlier.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from ultralytics import YOLO

from scripts._paths import DATA, WEIGHTS

#: [x1, y1, x2, y2] in pixels.
Box = tuple[float, float, float, float]

ROOT = DATA / "vehide"

#: The competitor checkpoint is not part of this repository -- it was downloaded
#: once to be measured against. Point this at wherever you put it; the comparison
#: is reproducible, the download is yours to make.
CONTENDER = Path(os.environ.get("BIOVISION_CONTENDER_WEIGHTS", "contender/best.pt"))
SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 60

MODELS = {
    "ours (VehiDE, damage-type)": YOLO(str(WEIGHTS / "vehide_yolo_seg.pt"), task="segment"),
    "HF yolov11n (part-based)": YOLO(str(CONTENDER)),
}


def truth_boxes(regions: list[dict[str, Any]]) -> list[Box]:
    out: list[Box] = []
    for r in regions:
        if not r.get("all_x"):
            continue
        xs, ys = r["all_x"], r["all_y"]
        out.append((min(xs), min(ys), max(xs), max(ys)))
    return out


def detect(model: YOLO, pixels: np.ndarray, conf: float = 0.25) -> list[Box]:
    result = next(iter(model.predict(pixels, conf=conf, verbose=False, device="cpu")))
    boxes = result.boxes  # type: ignore[union-attr]
    if boxes is None:
        return []
    found: list[Box] = []
    for i in range(len(boxes)):
        x1, y1, x2, y2 = (float(v) for v in boxes.xyxy[i].tolist())
        found.append((x1, y1, x2, y2))
    return found


def centre_inside(inner: Box, outer: Box) -> bool:
    cx, cy = (inner[0] + inner[2]) / 2, (inner[1] + inner[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def overlaps(a: Box, b: Box) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


ground_truth = json.loads((ROOT / "0Val_via_annos.json").read_text(encoding="utf-8"))
images_dir = ROOT / "validation" / "validation"
usable = [(n, e) for n, e in ground_truth.items() if (images_dir / n).is_file()][:SAMPLE]
print(f"{len(usable)} images\n")

for regime, pad in (("CLOSE-UP (as VehiDE ships)", 0.0), ("WIDE (car = 1/4 frame)", 1.0)):
    print(f"=== {regime}")
    print(f"{'model':30s} {'found':>8s} {'useful':>8s} {'silent':>8s}   boxes")
    for label, model in MODELS.items():
        found = total_truth = useful = total_boxes = silent = 0
        for name, entry in usable:
            image = Image.open(images_dir / name).convert("RGB")
            truth = truth_boxes(entry["regions"])
            if not truth:
                continue
            if pad:
                w, h = image.size
                pw, ph = int(w * (1 + pad)), int(h * (1 + pad))
                canvas = Image.new("RGB", (pw, ph), (128, 128, 128))
                ox, oy = (pw - w) // 2, (ph - h) // 2
                canvas.paste(image, (ox, oy))
                image = canvas
                truth = [(b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy) for b in truth]

            dets = detect(model, np.asarray(image))
            total_truth += len(truth)
            total_boxes += len(dets)
            silent += int(not dets)
            found += sum(1 for t in truth if any(centre_inside(t, d) for d in dets))
            useful += sum(1 for d in dets if any(overlaps(d, t) for t in truth))

        print(
            f"{label:30s} {found / total_truth:7.1%} {useful / max(total_boxes, 1):8.1%} "
            f"{silent:5d}/{len(usable):<3d} {total_boxes:6d}"
        )
    print()
