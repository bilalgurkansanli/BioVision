"""Measure what VehiDE actually contains, before deciding to train on it.

    uv run python -m scripts.inspect_vehide

The dataset was chosen (ADR-026) on its published description: 13,945 images,
32,000+ instances, eight damage types, insurance-grade annotation. Every one of
those is a claim until it is counted. This script counts them, and reports the
two things that decide whether the choice was right:

* **Resolution.** CarDD's advantage over its rivals was resolution -- an average
  of 684k pixels against roughly 50k. Thin scratches are exactly what resolution
  buys, and `scratch` is the hardest class. If VehiDE's images are small, that is
  the trade being made and it should be a number, not a hope.
* **Class balance.** A type with two hundred instances will produce a bad row in
  the per-class table. Better to know which row before training than after.

Nothing here is published as a project metric -- it describes the input, not the
system. It exists so the decision in ADR-026 rests on counts rather than on a
dataset card.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

from biovision.config import BACKEND_ROOT

DATA = BACKEND_ROOT.parent / "data" / "vehide"

#: How many images to open for the resolution sample. Opening 14,000 files to
#: compute a mean is minutes of IO for a number three decimals of which do not
#: matter.
RESOLUTION_SAMPLE = 400


def find_annotations(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.json") if "via" in p.name.lower())


def find_image_dirs(root: Path) -> list[Path]:
    """Directories holding images, deepest first so `image/image` wins."""
    directories = {
        p.parent for p in root.rglob("*.jpg")
    } | {p.parent for p in root.rglob("*.jpeg")} | {p.parent for p in root.rglob("*.png")}
    return sorted(directories, key=lambda p: len(p.parts), reverse=True)


def region_class(region: dict[str, Any]) -> str | None:
    """VehiDE's regions are flatter than a standard VIA export.

    A VIA file normally nests `shape_attributes` and `region_attributes`. VehiDE
    writes `{"all_x": [...], "all_y": [...], "class": "..."}` directly. Reading
    it as standard VIA parses without error and finds nothing -- which is how
    the first run of this script reported 36,081 regions and zero classes.
    Both shapes are accepted so the script says what is there rather than what
    was expected.
    """
    if isinstance(region.get("class"), str):
        return str(region["class"]).strip().lower().replace(" ", "_").replace("-", "_")

    attributes: dict[str, Any] = region.get("region_attributes") or {}
    for value in attributes.values():
        if isinstance(value, str) and value.strip():
            return value.strip().lower().replace(" ", "_").replace("-", "_")
    return None


def region_shape(region: dict[str, Any]) -> str:
    if "all_x" in region and "all_y" in region:
        return "polygon"
    shape: dict[str, Any] = region.get("shape_attributes") or {}
    return str(shape.get("name", "?"))


def region_points(region: dict[str, Any]) -> tuple[list[float], list[float]]:
    if "all_x" in region:
        return list(region.get("all_x") or []), list(region.get("all_y") or [])
    shape: dict[str, Any] = region.get("shape_attributes") or {}
    return list(shape.get("all_points_x") or []), list(shape.get("all_points_y") or [])


def describe_annotations(
    path: Path,
) -> tuple[int, Counter[str], Counter[str], Counter[str], int]:
    via = json.loads(path.read_text(encoding="utf-8"))
    classes: Counter[str] = Counter()
    shapes: Counter[str] = Counter()
    keys: Counter[str] = Counter()
    per_image: Counter[int] = Counter()
    degenerate = [0]

    for entry in via.values():
        regions = entry.get("regions", [])
        per_image[len(regions)] += 1
        for region in regions:
            xs, _ = region_points(region)
            if len(xs) < 3:
                degenerate[0] += 1
            keys.update(k for k in region if k not in {"all_x", "all_y"})
            shapes[region_shape(region)] += 1
            name = region_class(region)
            if name:
                classes[name] += 1

    return len(via), classes, shapes, keys, degenerate[0]


def main() -> int:
    if not DATA.is_dir():
        print(f"no dataset at {DATA}")
        return 1

    annotations = find_annotations(DATA)
    if not annotations:
        print(f"no VIA annotation files under {DATA}")
        print("files present:", sorted(p.name for p in DATA.iterdir())[:10])
        return 1

    print(f"dataset root: {DATA}")
    print()

    grand_images = 0
    grand_classes: Counter[str] = Counter()

    for path in annotations:
        count, classes, shapes, keys, degenerate_count = describe_annotations(path)
        grand_images += count
        grand_classes.update(classes)

        print(f"--- {path.relative_to(DATA)} ---")
        print(f"  images:              {count:,}")
        print(f"  instances:           {sum(classes.values()):,}")
        print(f"  attribute keys:      {dict(keys)}")
        print(f"  shape types:         {dict(shapes)}")
        non_polygon = sum(v for k, v in shapes.items() if k != "polygon")
        if degenerate_count:
            print(f"  degenerate polygons: {degenerate_count:,} (<3 points, unusable)")
        if non_polygon:
            share = non_polygon / max(1, sum(shapes.values()))
            print(f"  NON-POLYGON:         {non_polygon:,} ({share:.1%}) -- unusable as masks")
        print()

    print("=== totals ===")
    print(f"images:    {grand_images:,}")
    print(f"instances: {sum(grand_classes.values()):,}")
    print()
    print("class distribution")
    total = sum(grand_classes.values()) or 1
    for name, count in grand_classes.most_common():
        bar = "#" * max(1, round(40 * count / grand_classes.most_common(1)[0][1]))
        print(f"  {name:22s} {count:7,}  {count / total:6.1%}  {bar}")

    rare = [n for n, c in grand_classes.items() if c < 300]
    if rare:
        print()
        print(f"  thin classes (<300 instances): {', '.join(sorted(rare))}")
        print("  expect these to be the weak rows in the per-class table.")

    # --- resolution --------------------------------------------------------
    image_dirs = find_image_dirs(DATA)
    if not image_dirs:
        print("\nno image files found; cannot measure resolution")
        return 0

    images = [p for p in image_dirs[0].iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
    print()
    sampled = min(RESOLUTION_SAMPLE, len(images))
    print(f"=== resolution (sample of {sampled} from {image_dirs[0].name}/) ===")
    print(f"image files on disk: {len(images):,}")

    pixels = []
    for path in images[:RESOLUTION_SAMPLE]:
        try:
            with Image.open(path) as image:
                pixels.append(image.width * image.height)
        except Exception:
            continue

    if pixels:
        pixels.sort()
        mean = sum(pixels) / len(pixels)
        print(f"  mean:   {mean:12,.0f} px")
        print(f"  median: {pixels[len(pixels) // 2]:12,} px")
        print(f"  min:    {pixels[0]:12,} px")
        print(f"  max:    {pixels[-1]:12,} px")
        print()
        print("  CarDD reports a mean of 684,231 px; the sets it was benchmarked")
        print(f"  against averaged about 50,334 px. VehiDE sits at {mean:,.0f}.")
        if mean < 200_000:
            print("  LOW -- thin scratches are what resolution buys. Consider training at")
            print("  960 px rather than 640, and measure the scratch row specifically.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
