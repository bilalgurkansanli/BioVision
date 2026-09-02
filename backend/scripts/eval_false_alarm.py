"""How often does the specialist find damage that is not there?

    uv run python -m scripts.eval_false_alarm

**The floor was chosen without ever asking this.** README 7.3 swept the detection
floor over annotated VehiDE images and README 7.9 swept it again on pixel
coverage -- both sets contain only damaged cars. Neither could see a false alarm,
because a false alarm needs a photograph with nothing wrong in it, and there were
none. 0.20 was picked on evidence that structurally excluded the failure a user
notices first: being told their intact car is damaged.

So this sweeps the same parameter against both sides at once:

* **false alarm** -- the share of INTACT cars that produce at least one finding;
* **recall** -- the share of annotated damage instances still matched on VehiDE,
  greedy at IoU >= 0.5 with the class required to agree, which is the same
  matching `eval_framing.py` uses so the numbers are comparable.

A floor that silences clean cars by silencing everything is not an improvement,
which is why both columns are printed and neither is optimised alone.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

ROOT = Path("C:/Users/bilal/Desktop/BioVision/data/vehide")
WEIGHTS = Path("C:/Users/bilal/Desktop/BioVision/backend/weights/vehide_yolo_seg.pt")
INTACT = Path("C:/Users/bilal/Desktop/BioVision/data/_sources/vehicle_clean")

#: VehiDE ships Vietnamese class names. `mop_lom`, not `mop` -- the short form
#: was guessed once and silently unmatched all 5,681 dent ground truths.
VIETNAMESE = {
    "mop_lom": "dent",
    "vo_kinh": "glass_shatter",
    "be_den": "lamp_broken",
    "mat_bo_phan": "missing_part",
    "thung": "punctured",
    "tray_son": "scratch",
    "rach": "torn",
}

Box = tuple[float, float, float, float]


def iou(a: Box, b: Box) -> float:
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    if right <= left or bottom <= top:
        return 0.0
    overlap = (right - left) * (bottom - top)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - overlap
    return overlap / union if union > 0 else 0.0


def truth_boxes(regions: list[dict[str, Any]]) -> list[tuple[str, Box]]:
    out: list[tuple[str, Box]] = []
    for region in regions:
        label = VIETNAMESE.get(region["class"])
        if label is None or not region["all_x"]:
            continue
        xs, ys = region["all_x"], region["all_y"]
        out.append((label, (min(xs), min(ys), max(xs), max(ys))))
    return out


def predictions(model: Any, image: Image.Image, floor: float, names: dict[int, str]) -> list[
    tuple[str, float, Box]
]:
    result = next(
        iter(model.predict(np.array(image), conf=floor, verbose=False, device="cpu"))
    )
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []
    return [
        (
            names[int(boxes.cls[i].item())],
            float(boxes.conf[i].item()),
            tuple(float(v) for v in boxes.xyxy[i].tolist()),  # type: ignore[misc]
        )
        for i in range(len(boxes))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=90, help="annotated damaged images")
    parser.add_argument("--intact", type=Path, default=INTACT)
    parser.add_argument("--floors", type=float, nargs="+", default=[0.20, 0.25, 0.30, 0.40, 0.50])
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument(
        "--adaptive",
        type=float,
        default=None,
        metavar="STRICT_FLOOR",
        help=(
            "Raise the floor to STRICT_FLOOR on images the severity band calls "
            "`none`, and leave it at the sweep value everywhere else. The band is "
            "independent evidence: asking for more confidence when a second "
            "signal says there is nothing here is cheaper than asking for more "
            "everywhere. Costs recall only on the images the band gets wrong."
        ),
    )
    arguments = parser.parse_args()

    from ultralytics import YOLO

    model = YOLO(str(WEIGHTS), task="segment")
    names = {int(k): str(v) for k, v in model.names.items()}

    band_of = None
    if arguments.adaptive is not None:
        import sys

        sys.path.insert(0, str(Path("C:/Users/bilal/Desktop/BioVision/backend/src")))
        from biovision.config import Settings
        from biovision.domains.severity import SeverityPrompts
        from biovision.models.clip import ClipEncoder
        from biovision.models.clip_severity import ClipSeverityEstimator

        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        encoder = ClipEncoder(
            model_name=settings.clip_model,
            pretrained=settings.clip_pretrained,
            cache_dir=Path("C:/Users/bilal/Desktop/BioVision/backend/weights"),
            num_threads=settings.torch_num_threads,
        )
        estimator = ClipSeverityEstimator(
            encoder,
            SeverityPrompts.load(
                Path("C:/Users/bilal/Desktop/BioVision/backend/src/biovision/domains/severity.yaml")
            ),
        )

        def band_of(image: Image.Image) -> str:
            return estimator.estimate(np.array(image))[0].value

    annotations = json.loads((ROOT / "0Val_via_annos.json").read_text(encoding="utf-8"))
    keys = sorted(annotations)
    random.Random(arguments.seed).shuffle(keys)

    damaged: list[tuple[Image.Image, list[tuple[str, Box]]]] = []
    for key in keys:
        if len(damaged) >= arguments.count:
            break
        path = ROOT / "validation" / "validation" / key
        if not path.is_file():
            continue
        truth = truth_boxes(annotations[key]["regions"])
        if not truth:
            continue
        try:
            damaged.append((Image.open(path).convert("RGB"), truth))
        except Exception:
            continue

    intact = [
        Image.open(p).convert("RGB")
        for p in sorted(arguments.intact.rglob("*"))
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]

    print(f"\n{len(damaged)} damaged images, {len(intact)} intact vehicles")
    print(
        f"\n{'floor':>6} {'false alarm':>13} {'boxes/clean car':>17} "
        f"{'recall':>8} {'precision':>10}"
    )

    for floor in arguments.floors:
        # `floor` bound as a default argument rather than closed over: the loop
        # rebinds it each iteration, and a late-binding closure would score every
        # row at the last floor in the sweep.
        def floor_for(image: Image.Image, floor: float = floor) -> float:
            if band_of is None or arguments.adaptive is None:
                return floor
            return arguments.adaptive if band_of(image) == "none" else floor

        alarms = 0
        spurious = 0
        for image in intact:
            found = predictions(model, image, floor_for(image), names)
            spurious += len(found)
            if found:
                alarms += 1

        matched = total_truth = total_pred = 0
        for image, truth in damaged:
            found = sorted(
                predictions(model, image, floor_for(image), names), key=lambda p: -p[1]
            )
            total_truth += len(truth)
            total_pred += len(found)
            taken: set[int] = set()
            for label, _score, box in found:
                best, best_iou = -1, 0.5
                for index, (true_label, true_box) in enumerate(truth):
                    if index in taken or true_label != label:
                        continue
                    overlap = iou(box, true_box)
                    if overlap >= best_iou:
                        best, best_iou = index, overlap
                if best >= 0:
                    taken.add(best)
                    matched += 1

        recall = matched / total_truth if total_truth else 0.0
        precision = matched / total_pred if total_pred else 0.0
        print(
            f"{floor:>6.2f} {alarms}/{len(intact)} ({alarms / len(intact):>5.0%})"
            f" {spurious / len(intact):>16.2f} {recall:>8.3f} {precision:>10.3f}"
        )

    print(
        "\nA floor that silences clean cars by silencing everything is not an "
        "improvement.\nBoth columns move together; the question is the exchange rate."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
