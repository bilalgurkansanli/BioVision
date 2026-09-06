"""Does framing break the specialist, and does tiled inference repair it?

    uv run python -m scripts.eval_framing --count 60

**Why this exists.** A user uploaded a wide shot of a written-off car and got one
finding. The same photograph cropped to the car returns four. Every number in
README section 7.3 was measured on VehiDE's validation split, which is close-ups
like its training split -- so the published evaluation cannot see this failure at
all. An evaluation set drawn from the training distribution cannot report a
distribution failure.

**The wide-shot set is constructed, and that is a real limitation.** Each VehiDE
photograph is padded so the car occupies a quarter of the frame, with its
ground-truth polygons shifted by the same offset. It isolates exactly one
variable -- framing -- but padding a close-up is not the same as a photograph
taken from twenty metres, where the damage is also blurrier and lower contrast.
The measured gap is therefore a floor on the real one.

**Matching is precision and recall at a fixed operating point**, greedy at
IoU >= 0.5 with the class required to agree. Not mAP: the question is whether an
extra detection tends to be real, and mAP would average that away across
thresholds. `eval_specialist.py` remains the source for the published per-class
table, because a hand-rolled mAP that disagrees with Ultralytics by a few points
is indistinguishable from a model that is a few points better.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import numpy as np
from PIL import Image
from ultralytics import YOLO

from scripts._paths import DATA, WEIGHTS

#: (class name, confidence, [x1, y1, x2, y2]).
Box = tuple[float, float, float, float]
Detection = tuple[str, float, Box]

ROOT = DATA / "vehide"
CHECKPOINT = str(WEIGHTS / "vehide_yolo_seg.pt")

#: VehiDE ships Vietnamese class names; this is the mapping the notebook uses.
VIETNAMESE = {
    # `mop_lom`, not `mop`. The first version of this file guessed the short form,
    # so every `dent` ground truth silently failed to match and the model's dent
    # detections were all counted as false positives -- 5,681 instances, the
    # second largest class. The names are taken from the notebook's VIA_TO_CLASS,
    # which is the mapping the model was actually trained with.
    "mop_lom": "dent",
    "vo_kinh": "glass_shatter",
    "be_den": "lamp_broken",
    "mat_bo_phan": "missing_part",
    "thung": "punctured",
    "tray_son": "scratch",
    "rach": "torn",
}

_parser = argparse.ArgumentParser(description=__doc__)
_parser.add_argument("--count", type=int, default=60, help="annotated images to evaluate")
_arguments = _parser.parse_args()
SAMPLE = _arguments.count

model = YOLO(CHECKPOINT, task="segment")
names = model.names


def boxes_from(regions: list[dict[str, Any]]) -> list[tuple[str, Box]]:
    out = []
    for region in regions:
        label = VIETNAMESE.get(region["class"])
        if label is None or not region["all_x"]:
            continue
        xs, ys = region["all_x"], region["all_y"]
        out.append((label, (min(xs), min(ys), max(xs), max(ys))))
    return out


def detect(pixels: np.ndarray, conf: float) -> list[Detection]:
    result = next(iter(model.predict(pixels, conf=conf, iou=0.45, verbose=False, device="cpu")))
    boxes = result.boxes  # type: ignore[union-attr]
    if boxes is None:
        return []

    found: list[Detection] = []
    for i in range(len(boxes)):
        x1, y1, x2, y2 = (float(v) for v in boxes.xyxy[i].tolist())
        found.append(
            (names[int(boxes.cls[i].item())], float(boxes.conf[i].item()), (x1, y1, x2, y2))
        )
    return found


def iou(a: Box, b: Box) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    return float(inter) / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def merge(dets: list[Detection]) -> list[Detection]:
    kept: list[Detection] = []
    for label, score, box in sorted(dets, key=lambda d: -d[1]):
        if any(o[0] == label and iou(box, o[2]) > 0.5 for o in kept):
            continue
        kept.append((label, score, box))
    return kept


def tiled(image: Image.Image, base_conf: float, tile_conf: float) -> list[Detection]:
    w, h = image.size
    found = detect(np.asarray(image), base_conf)
    tw, th = int(w / 2 * 1.2), int(h / 2 * 1.2)
    for r in range(2):
        for c in range(2):
            left = max(0, min(int(c * w / 2), w - tw))
            top = max(0, min(int(r * h / 2), h - th))
            crop = image.crop((left, top, left + tw, top + th))
            for label, score, (x1, y1, x2, y2) in detect(np.asarray(crop), tile_conf):
                found.append((label, score, (x1 + left, y1 + top, x2 + left, y2 + top)))
    return merge(found)


def score(truth: list[tuple[str, Box]], predicted: list[Detection]) -> tuple[int, int, int]:
    """(matched, predicted, actual) by greedy IoU >= 0.5 with class agreement."""
    unused = list(truth)
    matched = 0
    for label, _, box in sorted(predicted, key=lambda d: -d[1]):
        for candidate in unused:
            if candidate[0] == label and iou(box, candidate[1]) >= 0.5:
                unused.remove(candidate)
                matched += 1
                break
    return matched, len(predicted), len(truth)


ground_truth = json.loads((ROOT / "0Val_via_annos.json").read_text(encoding="utf-8"))

# Refuse to score against a mapping that does not cover the file. A name this
# script does not know contributes no ground truth, so the model's correct
# detections of that class are counted as false positives and precision is
# reported far below the truth -- silently, with every number still plausible.
_present = {r["class"] for e in ground_truth.values() for r in e["regions"]}
_unmapped = _present - set(VIETNAMESE)
if _unmapped:
    raise SystemExit(
        f"annotation classes with no mapping: {sorted(_unmapped)}\n"
        f"known: {sorted(VIETNAMESE)}\n"
        "Scoring would count every instance of those as a false positive."
    )
images_dir = ROOT / "validation" / "validation"
usable = [(n, a) for n, a in ground_truth.items() if (images_dir / n).is_file()][:SAMPLE]
print(f"{len(usable)} annotated images\n")

#: (label, tile_conf, base_conf). `tile_conf=None` means whole-image only.
#:
#: The base-confidence rows were added after a user asked why a written-off car
#: showed one finding at 42%. Lowering the floor to 0.20 turns that photograph's
#: single dent into three real findings including the torn-off bumper -- but one
#: photograph cannot choose a threshold, which is the same error this file
#: already refused once for tiling. So the floor is swept and measured.
CONFIGS = [
    ("whole image, floor 0.25", None, 0.25),
    ("whole image, floor 0.20", None, 0.20),
    ("whole image, floor 0.15", None, 0.15),
    ("whole image, floor 0.10", None, 0.10),
    ("tiled, floor 0.25", 0.25, 0.25),
    ("tiled, floor 0.45", 0.45, 0.25),
]

for regime, pad in (("CLOSE-UP (as shipped)", 0.0), ("WIDE (padded, car = 1/4 frame)", 1.0)):
    print(f"=== {regime}")
    totals = {label: [0, 0, 0] for label, _, _ in CONFIGS}

    for name, entry in usable:
        image = Image.open(images_dir / name).convert("RGB")
        truth = boxes_from(entry["regions"])
        if not truth:
            continue

        if pad:
            w, h = image.size
            pw, ph = int(w * (1 + pad)), int(h * (1 + pad))
            canvas = Image.new("RGB", (pw, ph), (128, 128, 128))
            ox, oy = (pw - w) // 2, (ph - h) // 2
            canvas.paste(image, (ox, oy))
            image = canvas
            truth = [(c, (b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy)) for c, b in truth]

        pixels = np.asarray(image)
        for label, tile_conf, base_conf in CONFIGS:
            found = (
                detect(pixels, base_conf)
                if tile_conf is None
                else tiled(image, base_conf, tile_conf)
            )
            m, p, a = score(truth, found)
            totals[label][0] += m
            totals[label][1] += p
            totals[label][2] += a

    print(f"{'setting':22s} {'precision':>10s} {'recall':>8s} {'F1':>7s}   found/actual")
    for label, _, _ in CONFIGS:
        m, p, a = totals[label]
        precision = m / p if p else 0.0
        recall = m / a if a else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        print(f"{label:22s} {precision:10.3f} {recall:8.3f} {f1:7.3f}   {p}/{a}")
    print()
