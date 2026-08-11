"""Per-class mAP for the vehicle specialist on the CarDD test split.

    uv run python -m scripts.eval_specialist --data path/to/cardd.yaml

Prints the markdown table the README carries. **Copy it verbatim, including the bad
rows.** The literature consistently finds dent, scratch and crack to be the hard
classes; if our numbers show the same, that is a correct result being reported
honestly, not a defect to hide behind an average.

Delegates to Ultralytics' validator rather than reimplementing mAP. A hand-rolled
metric that disagrees with the standard one by a few points is indistinguishable
from a model that is a few points better, and this table is the project's headline
claim.

Requires the CarDD test split, which is obtained through the dataset's own access
process and is never redistributed here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from biovision.config import Settings
from biovision.models.specialists.vehicle_yolo import (
    CARDD_CLASSES,
    VEHICLE_WEIGHTS_FILENAME,
)


def markdown_table(rows: list[tuple[str, float, float, float, float]]) -> str:
    lines = [
        "| Class | mAP@50 | mAP@50-95 | Precision | Recall |",
        "|---|---|---|---|---|",
    ]
    for name, map50, map5095, precision, recall in rows:
        emphasis = "**" if name == "all" else ""
        lines.append(
            f"| {emphasis}{name}{emphasis} | {map50:.3f} | {map5095:.3f} | "
            f"{precision:.3f} | {recall:.3f} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        required=True,
        help="dataset YAML with a `test:` split (written by the training notebook)",
    )
    parser.add_argument("--weights", default=None, help="checkpoint; defaults to weights/")
    parser.add_argument("--split", default="test", choices=["test", "val"])
    parser.add_argument("--imgsz", type=int, default=640)
    args = parser.parse_args()

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    weights = (
        Path(args.weights)
        if args.weights
        else settings.weights_path / VEHICLE_WEIGHTS_FILENAME
    )

    if not weights.is_file():
        print(f"No checkpoint at {weights}.")
        print("Train it with notebooks/train_cardd_yolo.ipynb. Nothing is reported.")
        return 1

    data = Path(args.data)
    if not data.is_file():
        print(f"No dataset YAML at {data}.")
        print("CarDD is obtained through its own access process and not redistributed here.")
        return 1

    from ultralytics import YOLO

    model = YOLO(str(weights), task="segment")
    print(f"evaluating {weights.name} on the '{args.split}' split of {data}\n")

    metrics = model.val(
        data=str(data), split=args.split, imgsz=args.imgsz, device="cpu", verbose=False
    )

    # Segmentation metrics are what this model is for: a box that overlaps a scratch
    # says much less than a mask that traces it, and area_ratio comes from the mask.
    box = metrics.box
    seg = getattr(metrics, "seg", None)

    for label, source in (("Detection (box)", box), ("Segmentation (mask)", seg)):
        if source is None:
            continue

        rows: list[tuple[str, float, float, float, float]] = []
        for index, damage in enumerate(CARDD_CLASSES):
            try:
                precision, recall, map50, map5095 = source.class_result(index)
            except Exception:
                continue
            rows.append((damage.value, map50, map5095, precision, recall))

        rows.append(("all", source.map50, source.map, source.mp, source.mr))

        print(f"### {label}\n")
        print(markdown_table(rows))
        print()

    print("Paste these into README section 7.3, verbatim, including the weak classes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
