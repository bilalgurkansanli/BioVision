"""Does a looser mask cut-off cover more of the dent?

    uv run python -m scripts.eval_mask_threshold --count 120

Ultralytics binarises a segmentation mask at logit 0 -- probability 0.5 -- and
that choice is invisible from outside the library. It is also a free parameter:
moving it costs no latency, no retraining and no weights, which makes it the
cheapest lever available on the complaint that a `dent` mask does not cover the
dent.

The mask head emits a per-pixel logit. Thresholding at 0.5 keeps only pixels the
model is more confident about than not; a dent fades into undamaged panel at its
edge, so its boundary pixels are exactly the ones sitting just under that line.
If the extent problem is a *boundary* problem, a looser cut-off finds it. If the
problem is that whole panels are never detected, this will do almost nothing --
and that is a useful thing to learn, because the two failures have completely
different fixes.

The patch below replaces the library's binarisation. It is confined to this
script: nothing in `biovision` monkeypatches ultralytics, and if a threshold ever
ships it will ship as an explicit argument rather than as a hook.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from scripts._paths import DATA, WEIGHTS

ROOT = DATA / "vehide"
CHECKPOINT = WEIGHTS / "vehide_yolo_seg.pt"

VIETNAMESE = {
    "mop_lom": "dent",
    "vo_kinh": "glass_shatter",
    "be_den": "lamp_broken",
    "mat_bo_phan": "missing_part",
    "thung": "punctured",
    "tray_son": "scratch",
    "rach": "torn",
}


def patch_threshold(probability: float) -> None:
    """Rebind the library's mask binarisation to a different probability.

    The mask head's output is a logit, so a probability threshold p becomes
    logit(p) = ln(p / (1 - p)). At p = 0.5 that is 0, which is what the library
    hard-codes; the patch is a no-op there, which is what makes 0.5 a valid
    control row rather than a separate code path.
    """
    import torch
    from ultralytics.utils import ops

    cut = math.log(probability / (1.0 - probability))

    def process_mask(protos, masks_in, bboxes, shape, upsample: bool = False):  # type: ignore[no-untyped-def]
        c, mh, mw = protos.shape
        if masks_in.shape[0] == 0:
            return torch.zeros(
                (0, *(shape if upsample else (mh, mw))), dtype=torch.uint8, device=masks_in.device
            )
        masks = (masks_in @ protos.float().view(c, -1)).view(-1, mh, mw)
        if upsample:
            masks = torch.nn.functional.interpolate(masks[None], shape, mode="bilinear")[0]
        else:
            ratios = torch.tensor(
                [[mw / shape[1], mh / shape[0], mw / shape[1], mh / shape[0]]],
                device=bboxes.device,
            )
            bboxes = bboxes * ratios
        return ops.crop_mask(masks.gt_(cut).byte(), bboxes)

    ops.process_mask = process_mask


def gt_masks(regions: list[dict[str, Any]], size: tuple[int, int]) -> dict[str, np.ndarray]:
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
        ImageDraw.Draw(plane).polygon([(float(x), float(y)) for x, y in polygon], fill=1, outline=1)
    return {label: np.array(plane, dtype=bool) for label, plane in planes.items()}


def union(planes: dict[str, np.ndarray], size: tuple[int, int]) -> np.ndarray:
    total = np.zeros((size[1], size[0]), dtype=bool)
    for plane in planes.values():
        total |= plane
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--conf", type=float, default=0.10)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--thresholds", type=float, nargs="+", default=[0.5, 0.4, 0.3, 0.2, 0.1])
    arguments = parser.parse_args()

    from ultralytics import YOLO

    annotations = json.loads((ROOT / "0Val_via_annos.json").read_text(encoding="utf-8"))
    keys = sorted(annotations)
    random.Random(arguments.seed).shuffle(keys)

    print(f"\nconf={arguments.conf}, {arguments.count} images, mask cut-off swept")
    print(f"{'cut-off':>8} {'coverage':>9} {'spill':>7} {'dent':>7} {'scratch':>8} {'blind':>7}")

    for probability in arguments.thresholds:
        patch_threshold(probability)
        model = YOLO(str(CHECKPOINT), task="segment")
        names = {int(k): str(v) for k, v in model.names.items()}

        inter_total = gt_total = pred_total = 0.0
        per_class: dict[str, list[float]] = {}
        blind = 0
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

            result = next(
                iter(
                    model.predict(np.array(image), conf=arguments.conf, verbose=False, device="cpu")
                )
            )
            predicted = pred_masks(result, image.size, names)

            gt_union = union(truth, image.size)
            pred_union = union(predicted, image.size)
            intersection = float((gt_union & pred_union).sum())
            gt_area = float(gt_union.sum())

            inter_total += intersection
            gt_total += gt_area
            pred_total += float(pred_union.sum())
            if gt_area and intersection / gt_area < 0.05:
                blind += 1

            for label, plane in truth.items():
                area = float(plane.sum())
                if not area:
                    continue
                hit = predicted.get(label)
                per_class.setdefault(label, []).append(
                    (float((plane & hit).sum()) if hit is not None else 0.0) / area
                )

        coverage = inter_total / gt_total if gt_total else 0.0
        spill = (pred_total - inter_total) / pred_total if pred_total else 0.0
        dent = float(np.mean(per_class.get("dent", [0.0])))
        scratch = float(np.mean(per_class.get("scratch", [0.0])))
        print(
            f"{probability:>8.2f} {coverage:>9.3f} {spill:>7.3f} {dent:>7.3f}"
            f" {scratch:>8.3f} {blind / max(used, 1):>6.1%}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
