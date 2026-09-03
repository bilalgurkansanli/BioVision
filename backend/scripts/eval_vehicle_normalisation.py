"""Is "42% damaged" a fraction of the car, or of the photograph?

    uv run python -m scripts.eval_vehicle_normalisation --count 80

Today it is the photograph, and a user asked the obvious question: *42% of what?*
The honest answer is "of the frame", which makes the number a measure of how close
the photographer stood -- README 7.5 measures that at thirty-fold on one image.

The fix is to divide by the car instead of the frame, and the reason it is not
already done is that it was tried on six photographs and a COCO detector found no
vehicle in three of them. Six images is not a measurement, so this is the
measurement:

1. **Availability.** On what fraction of real photographs is a vehicle mask found
   at all? A normalisation that is unavailable half the time is worse than none,
   because the number would silently change meaning between requests.
2. **Stability.** The same photograph padded 40% and 100% -- the exact test that
   found the 30x sensitivity. A ratio against the car should barely move; a ratio
   against the frame should collapse.

Both are needed. Availability alone would let an unstable ratio through, and
stability alone would hide that the ratio is often missing.

The vehicle mask comes from a stock COCO `yolo11n-seg` (car / truck / bus /
motorcycle), which is a separate model from the damage specialist and is measured
here before anything depends on it.
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
DAMAGE_WEIGHTS = Path("C:/Users/bilal/Desktop/BioVision/backend/weights/vehide_yolo_seg.pt")

#: COCO ids for things a claimant photographs when they photograph "my vehicle".
VEHICLE_COCO_IDS = {2, 3, 5, 7}  # car, motorcycle, bus, truck

VIETNAMESE = {
    "mop_lom": "dent",
    "vo_kinh": "glass_shatter",
    "be_den": "lamp_broken",
    "mat_bo_phan": "missing_part",
    "thung": "punctured",
    "tray_son": "scratch",
    "rach": "torn",
}


def polygons_to_mask(polygons: list[Any], size: tuple[int, int]) -> np.ndarray:
    plane = Image.new("1", size, 0)
    draw = ImageDraw.Draw(plane)
    for polygon in polygons:
        if len(polygon) >= 3:
            draw.polygon([(float(x), float(y)) for x, y in polygon], fill=1, outline=1)
    return np.array(plane, dtype=bool)


def gt_mask(regions: list[dict[str, Any]], size: tuple[int, int]) -> np.ndarray:
    polygons = [
        list(zip(region["all_x"], region["all_y"], strict=True))
        for region in regions
        if VIETNAMESE.get(region["class"]) and len(region["all_x"]) >= 3
    ]
    return polygons_to_mask(polygons, size)


def vehicle_mask(model: Any, image: Image.Image, conf: float) -> np.ndarray | None:
    """Union of every vehicle instance, or None when COCO sees no vehicle.

    None rather than a full-frame fallback: silently substituting the frame would
    reintroduce exactly the number this script exists to replace, and the caller
    could not tell the two apart.
    """
    result = next(
        iter(
            model.predict(
                np.array(image),
                conf=conf,
                verbose=False,
                device="cpu",
                classes=sorted(VEHICLE_COCO_IDS),
            )
        )
    )
    masks = getattr(result, "masks", None)
    if masks is None or masks.xy is None or len(masks.xy) == 0:
        return None
    return polygons_to_mask(list(masks.xy), image.size)


def pad(image: Image.Image, factor: float) -> Image.Image:
    """Grow the canvas around the photograph, leaving the car where it was.

    The same operation README 7.5 used. Grey rather than black: a black border is
    a strong edge that a detector can latch onto, which would make the test
    measure the border instead of the framing.
    """
    width, height = image.size
    new = (int(width * (1 + factor)), int(height * (1 + factor)))
    canvas = Image.new("RGB", new, (128, 128, 128))
    canvas.paste(image, ((new[0] - width) // 2, (new[1] - height) // 2))
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=80)
    parser.add_argument("--conf", type=float, default=0.10, help="damage detection floor")
    parser.add_argument("--vehicle-conf", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--stability", type=int, default=20, help="images for the padding test")
    arguments = parser.parse_args()

    from ultralytics import YOLO

    damage = YOLO(str(DAMAGE_WEIGHTS), task="segment")
    coco = YOLO("yolo11n-seg.pt", task="segment")

    annotations = json.loads((ROOT / "0Val_via_annos.json").read_text(encoding="utf-8"))
    keys = sorted(annotations)
    random.Random(arguments.seed).shuffle(keys)

    found = 0
    used = 0
    sampled = 0
    availability: dict[float, int] = {}
    vehicle_shares: list[float] = []
    frame_ratios: list[float] = []
    car_ratios: list[float] = []
    stability: list[dict[float, tuple[float, float]]] = []

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

        truth = gt_mask(annotations[key]["regions"], image.size)
        if not truth.any():
            continue
        used += 1

        # Availability is measured per framing, over EVERY sampled image, before
        # anything is allowed to `continue`. Measuring it only on the images that
        # already succeeded as shot would answer a different question -- "does the
        # mask survive padding" -- and the question that decides whether this
        # ships is "how often is there a mask at all", separately for the close-up
        # framing VehiDE contains and the wide framing a claimant sends.
        for factor in (0.0, 0.4, 1.0):
            framed = pad(image, factor) if factor else image
            if vehicle_mask(coco, framed, arguments.vehicle_conf) is not None:
                availability[factor] = availability.get(factor, 0) + 1
        sampled += 1

        car = vehicle_mask(coco, image, arguments.vehicle_conf)
        if car is None or not car.any():
            continue
        found += 1

        frame_pixels = float(image.size[0] * image.size[1])
        car_pixels = float(car.sum())
        vehicle_shares.append(car_pixels / frame_pixels)

        result = next(
            iter(damage.predict(np.array(image), conf=arguments.conf, verbose=False, device="cpu"))
        )
        masks = getattr(result, "masks", None)
        predicted = (
            polygons_to_mask(list(masks.xy), image.size)
            if masks is not None and masks.xy is not None
            else np.zeros_like(car)
        )
        damaged = float(predicted.sum())
        frame_ratios.append(damaged / frame_pixels)
        # Intersected with the car: damage predicted off the vehicle is not
        # damage to the vehicle, and leaving it in would let the ratio exceed 1.
        car_ratios.append(float((predicted & car).sum()) / car_pixels)

        if len(stability) < arguments.stability:
            # Keyed by pad factor so the comparison below reads as itself rather
            # than as tuple indices; an earlier positional version put the 40%
            # column where the 100% one belonged and the bug was invisible.
            row: dict[float, tuple[float, float]] = {}
            for factor in (0.0, 0.4, 1.0):
                framed = pad(image, factor) if factor else image
                framed_car = vehicle_mask(coco, framed, arguments.vehicle_conf)
                framed_result = next(
                    iter(
                        damage.predict(
                            np.array(framed), conf=arguments.conf, verbose=False, device="cpu"
                        )
                    )
                )
                framed_masks = getattr(framed_result, "masks", None)
                framed_damage = (
                    polygons_to_mask(list(framed_masks.xy), framed.size)
                    if framed_masks is not None and framed_masks.xy is not None
                    else np.zeros((framed.size[1], framed.size[0]), dtype=bool)
                )
                total = float(framed.size[0] * framed.size[1])
                against_car = (
                    float((framed_damage & framed_car).sum()) / float(framed_car.sum())
                    if framed_car is not None and framed_car.any()
                    else float("nan")
                )
                row[factor] = (float(framed_damage.sum()) / total, against_car)
            stability.append(row)

    if not used:
        print("no annotated images matched")
        return 1

    print(f"\nimages with damage annotations: {used}")
    print(f"  a COCO vehicle mask was found on {found}/{used}  ({found / used:.1%})")
    if sampled:
        print("\n  availability by framing (same images, canvas grown around them):")
        for factor in sorted(availability):
            hits = availability[factor]
            label = "as shot" if factor == 0.0 else f"padded {factor:.0%}"
            print(f"    {label:<12} {hits}/{sampled}  ({hits / sampled:.1%})")
    if vehicle_shares:
        print(f"  the vehicle occupies a median {np.median(vehicle_shares):.1%} of the frame")
    if frame_ratios:
        print(f"\n  damage / frame  median {np.median(frame_ratios):.4f}")
        print(f"  damage / car    median {np.median(car_ratios):.4f}")
        ratio = np.median(car_ratios) / max(np.median(frame_ratios), 1e-9)
        print(f"  the second is {ratio:.2f}x the first")

    if stability:
        print(f"\n  padding test on {len(stability)} images (as shot -> padded 100%):")
        frame_drop = []
        car_drop = []
        for row in stability:
            (f0, c0), (f100, c100) = row[0.0], row[1.0]
            if f0 > 0:
                frame_drop.append(f100 / f0)
            # NaN-safe: a framing where no vehicle was found contributes nothing
            # rather than poisoning the median.
            if c0 == c0 and c100 == c100 and c0 > 0:
                car_drop.append(c100 / c0)
        if frame_drop:
            print(f"    damage/frame retains a median {np.median(frame_drop):.2f}x of its value")
        if car_drop:
            print(
                f"    damage/car   retains a median {np.median(car_drop):.2f}x of its value"
                f"   (n={len(car_drop)})"
            )
        else:
            print("    damage/car   could not be compared: no vehicle mask on the padded frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
