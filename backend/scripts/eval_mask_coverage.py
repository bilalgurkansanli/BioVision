"""How much of the annotated damage does the predicted mask actually cover?

    uv run python -m scripts.eval_mask_coverage --count 200

**Why this metric and not mAP.** A user pointed at a crushed car and said the
`dent` finding "does not cover the dent". mAP cannot answer that: a mask scoring
IoU 0.5 against a polygon is a true positive, and a mask covering half the
crushed region is exactly that. The published table (README 7.3) can therefore be
correct while the complaint is also correct.

So this measures the thing the complaint is about, over the union of all damage
in a photograph rather than instance by instance:

    coverage = |predicted ∩ annotated| / |annotated|
    spill    = |predicted minus annotated| / |predicted|

Coverage is what a claimant sees as "it missed most of it". Spill is what stops
the obvious fix -- painting the whole car -- from scoring well. Both are reported
because either alone can be gamed by moving one threshold.

Class-agnostic by default: the question is whether the system points at the
damaged region at all. `--per-class` splits it, which is where the dent number
lives.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path("C:/Users/bilal/Desktop/BioVision/data/vehide")
WEIGHTS = Path("C:/Users/bilal/Desktop/BioVision/backend/weights/vehide_yolo_seg.pt")

VIETNAMESE = {
    "mop_lom": "dent",
    "vo_kinh": "glass_shatter",
    "be_den": "lamp_broken",
    "mat_bo_phan": "missing_part",
    "thung": "punctured",
    "tray_son": "scratch",
    "rach": "torn",
}


def gt_masks(regions: list[dict[str, Any]], size: tuple[int, int]) -> dict[str, np.ndarray]:
    """Rasterise VIA polygons, one boolean plane per class."""
    planes: dict[str, Image.Image] = {}
    for region in regions:
        label = VIETNAMESE.get(region["class"])
        if label is None or len(region["all_x"]) < 3:
            continue
        plane = planes.setdefault(label, Image.new("1", size, 0))
        ImageDraw.Draw(plane).polygon(
            list(zip(region["all_x"], region["all_y"], strict=True)), fill=1, outline=1
        )
    return {label: np.array(plane, dtype=bool) for label, plane in planes.items()}


def pred_masks(result: Any, size: tuple[int, int], names: dict[int, str]) -> dict[str, np.ndarray]:
    """Predicted masks as boolean planes in the SOURCE image frame.

    Uses `masks.xy` -- polygons already scaled back to the original image -- rather
    than `masks.data`, whose shape depends on `retina_masks` and on the letterbox.
    Rasterising the polygon is the only form that is unambiguously in the frame
    the user and the ground truth live in.
    """
    planes: dict[str, Image.Image] = {}
    masks = getattr(result, "masks", None)
    boxes = getattr(result, "boxes", None)
    if masks is None or boxes is None or masks.xy is None:
        return {}
    for index, polygon in enumerate(masks.xy):
        if len(polygon) < 3:
            continue
        label = names[int(boxes.cls[index].item())]
        plane = planes.setdefault(label, Image.new("1", size, 0))
        ImageDraw.Draw(plane).polygon(
            [(float(x), float(y)) for x, y in polygon], fill=1, outline=1
        )
    return {label: np.array(plane, dtype=bool) for label, plane in planes.items()}


def union(planes: dict[str, np.ndarray], size: tuple[int, int]) -> np.ndarray:
    total = np.zeros((size[1], size[0]), dtype=bool)
    for plane in planes.values():
        total |= plane
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--conf", type=float, default=0.20)
    parser.add_argument("--iou", type=float, default=0.45)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--retina", action="store_true", help="retina_masks=True")
    parser.add_argument("--per-class", action="store_true")
    parser.add_argument("--weights", type=Path, default=WEIGHTS)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument(
        "--vehicle-gate",
        action="store_true",
        help=(
            "Intersect predictions with a COCO vehicle mask before scoring. "
            "Damage predicted off the car is definitionally wrong, so this should "
            "cut spill for free -- and if it does, a lower floor becomes affordable. "
            "Scored only on images where a vehicle was found, which is a subset."
        ),
    )
    arguments = parser.parse_args()

    from ultralytics import YOLO

    model = YOLO(str(arguments.weights), task="segment")
    names = {int(k): str(v) for k, v in model.names.items()}
    coco = YOLO("yolo11n-seg.pt", task="segment") if arguments.vehicle_gate else None

    annotations = json.loads((ROOT / "0Val_via_annos.json").read_text(encoding="utf-8"))
    keys = sorted(annotations)
    random.Random(arguments.seed).shuffle(keys)

    inter_total = gt_total = pred_total = 0.0
    ungated = {"inter": 0.0, "gt": 0.0, "pred": 0.0}
    per_class: dict[str, list[float]] = {}
    covered_images = 0
    blind_images = 0
    used = 0

    for key in keys:
        if used >= arguments.count:
            break
        path = ROOT / "validation" / "validation" / key
        if not path.is_file():
            continue
        try:
            image = Image.open(path).convert("RGB")
        except Exception:
            continue

        truth = gt_masks(annotations[key]["regions"], image.size)
        if not truth:
            continue
        used += 1

        result = next(iter(
            model.predict(
                np.array(image),
                conf=arguments.conf,
                iou=arguments.iou,
                imgsz=arguments.imgsz,
                retina_masks=arguments.retina,
                verbose=False,
                device="cpu",
            )
        ))
        predicted = pred_masks(result, image.size, names)

        if coco is not None:
            car = next(
                iter(
                    coco.predict(
                        np.array(image),
                        conf=0.15,
                        classes=[2, 3, 5, 7],
                        verbose=False,
                        device="cpu",
                    )
                )
            )
            car_masks = getattr(car, "masks", None)
            if car_masks is None or car_masks.xy is None or len(car_masks.xy) == 0:
                # No vehicle: excluded from BOTH rows, so the comparison below is
                # like-for-like. Scoring the ungated row on images the gate never
                # saw would compare two different samples and the difference
                # would be unattributable.
                used -= 1
                continue
            # `car_plane`, not `plane`: the per-class loop below binds `plane` to a
            # rasterised array, and reusing the name here made it an Image there.
            car_plane = Image.new("1", image.size, 0)
            drawer = ImageDraw.Draw(car_plane)
            for polygon in car_masks.xy:
                if len(polygon) >= 3:
                    drawer.polygon([(float(x), float(y)) for x, y in polygon], fill=1, outline=1)
            car_mask = np.array(car_plane, dtype=bool)

            # The ungated numbers on exactly these images, accumulated alongside.
            ungated_union = union(predicted, image.size)
            truth_union = union(truth, image.size)
            ungated["inter"] += float((truth_union & ungated_union).sum())
            ungated["gt"] += float(truth_union.sum())
            ungated["pred"] += float(ungated_union.sum())

            predicted = {label: mask & car_mask for label, mask in predicted.items()}

        gt_union = union(truth, image.size)
        pred_union = union(predicted, image.size)

        intersection = float((gt_union & pred_union).sum())
        gt_area = float(gt_union.sum())
        pred_area = float(pred_union.sum())

        inter_total += intersection
        gt_total += gt_area
        pred_total += pred_area
        if gt_area:
            share = intersection / gt_area
            if share >= 0.5:
                covered_images += 1
            if share < 0.05:
                blind_images += 1

        if arguments.per_class:
            for label, plane in truth.items():
                area = float(plane.sum())
                if not area:
                    continue
                hit = predicted.get(label)
                overlap = float((plane & hit).sum()) if hit is not None else 0.0
                per_class.setdefault(label, []).append(overlap / area)

    if not used:
        print("no annotated images matched")
        return 1

    coverage = inter_total / gt_total if gt_total else 0.0
    spill = (pred_total - inter_total) / pred_total if pred_total else 0.0

    print(
        f"\nimages: {used}   conf={arguments.conf}  imgsz={arguments.imgsz} "
        f" retina={arguments.retina}"
    )
    print(f"  coverage (pixels of annotated damage found)  {coverage:.3f}")
    print(f"  spill    (predicted pixels outside the truth) {spill:.3f}")
    print(
        f"  images with >=50% of the damage covered       {covered_images}/{used}"
        f"  ({covered_images / used:.1%})"
    )
    print(f"  images with  <5% covered (effectively blind)  {blind_images}/{used}"
          f"  ({blind_images / used:.1%})")

    if coco is not None and ungated["gt"]:
        # The control row, on exactly the same images. Without it, a gated figure
        # could only be compared against a different sample.
        print(
            f"  WITHOUT the vehicle gate, same {used} images:"
            f"  coverage {ungated['inter'] / ungated['gt']:.3f}"
            f"  spill {(ungated['pred'] - ungated['inter']) / ungated['pred']:.3f}"
        )

    if arguments.per_class:
        print("\n  per class, mean fraction of that class's annotated area covered:")
        for label in sorted(per_class, key=lambda item: -len(per_class[item])):
            shares = per_class[label]
            print(f"    {label:<15} {np.mean(shares):.3f}   n={len(shares)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
