"""Does a purpose-trained crack model beat zero-shot tiled CLIP on our images?

    uv run python -m scripts.eval_crack_model

The model hunt across nine hubs found exactly one licence-clean, CPU-feasible,
ground-level checkpoint for any konut damage class: `OpenSistemas/YOLOv8-crack-seg`
(AGPL-3.0, matching this product; trained on Ultralytics Crack-seg, Public Domain
Mark 1.0, which covers walls as well as roads). For water, mould, fire, roof and
glass damage there was nothing at all -- not gated, not badly licensed, absent.

Its published mask mAP50 is 0.639. That number is on ITS test split, and a
number from a model card is a claim, not a measurement. What matters here is
whether it beats the thing that already runs for free: the zero-shot 4x4 tiled
CLIP router, which on this same set gets crack recall 80% at precision 79%.

So both are asked the same two questions on the same images:

    recall      of 60 crack photographs, how many does it find?
    false alarm of 45 intact rooms, how many does it fire on?

The second question is the one the vehicle specialist got wrong for a whole
release (7.10): a floor chosen on damaged images only cannot see a false alarm,
because no intact image was ever in the sweep. That mistake is not repeated.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path("C:/Users/bilal/Desktop/BioVision/backend/src")))

from scripts.eval_building_type import EXISTING_CRACK, KONUT, images

WEIGHTS = Path("C:/Users/bilal/Desktop/BioVision/backend/weights/crack/yolov8n-crack-seg.pt")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--conf", type=float, default=0.25, help="Ultralytics default")
    arguments = parser.parse_args()

    from ultralytics import YOLO

    model = YOLO(str(WEIGHTS))

    cracked = (images(KONUT / "crack", arguments.limit) + images(EXISTING_CRACK, arguments.limit))[
        : arguments.limit
    ]
    intact = images(KONUT / "none", arguments.limit)

    print(f"{len(cracked)} crack photographs, {len(intact)} intact rooms, conf {arguments.conf}\n")

    for name, paths, wanted in (("crack", cracked, True), ("intact", intact, False)):
        fired = 0
        elapsed = 0.0
        for path in paths:
            start = time.perf_counter()
            results = list(model.predict(str(path), conf=arguments.conf, verbose=False))
            elapsed += time.perf_counter() - start
            boxes = getattr(results[0], "boxes", None) if results else None
            if boxes is not None and len(boxes) > 0:
                fired += 1
        n = len(paths)
        label = "recall" if wanted else "FALSE ALARM"
        print(
            f"  {name:<7} {label:<12} {fired}/{n} = {fired / n:>4.0%}"
            f"   {elapsed / n * 1000:.0f} ms/image"
        )

    print(
        "\nCompare with the zero-shot 4x4 tiled CLIP already running for free:\n"
        "  crack recall 80% at precision 79%, intact rooms held at 76%.\n"
        "A trained specialist has to beat that to be worth a second model."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
