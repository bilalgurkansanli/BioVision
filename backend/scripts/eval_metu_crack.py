"""What the trained METU crack classifier does to a room it has never seen.

    uv run python -m scripts.eval_metu_crack

The Kaggle run reported **99.86% accuracy, 99.73% precision, 100% recall** on
held-out clusters, with a leakage gap of +0.0001. Those are METU's numbers about
METU: 458 facades photographed on one campus, cropped 87 ways each.

This asks the only other question available, on the production CPU rather than a
T4: pointed at an ordinary residential interior with nothing wrong, how often
does it say crack? Recall cannot be measured here -- nothing in the set is
cracked -- and that is fine, because the failure that ships is the other one.
The vehicle specialist shipped a 44% false-alarm rate for a whole release
(README 7.10), and the one public crack checkpoint fired on 64% of intact rooms
(7.11). Both were found this way and neither was visible in a held-out score.

The rooms are the 15 that survived review in `konut_eval`, each recorded in
`verdicts.csv`. Fifteen is a small number and the result is reported as a count,
never as a rate with a decimal point it has not earned.

**Eleven of the fifteen are photographs; four are paintings and one engraving.**
The review verdicts recorded all four as photographs, which was wrong, and a
later audit caught it by opening the files. The verdicts now say what they are.
The result does not depend on them: separated, the checkpoint scores 1.0000 on
all eleven photographs and on all four paintings, so the honest headline is
11/11 on photographs and the paintings are surplus. They are kept in the set,
named rather than quietly dropped, because dropping images after seeing what
they scored is choosing a set by looking at the answer.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(Path("C:/Users/bilal/Desktop/BioVision/backend/src")))

CHECKPOINT = Path("C:/Users/bilal/Desktop/BioVision/backend/weights/konut/metu_crack_patch.pt")
ROOMS = Path("C:/Users/bilal/Desktop/BioVision/data/konut_eval/none")
CRACKS = Path("C:/Users/bilal/Desktop/BioVision/data/_sources/building")

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def tiles(image: Image.Image, grid: int) -> list[Image.Image]:
    """The same overlapping grid the zero-shot work used, so the two compare."""
    width, height = image.size
    out = [image]
    if grid < 2:
        return out
    step_x, step_y = width / grid, height / grid
    for row in range(grid):
        for column in range(grid):
            left = max(0, int(column * step_x - step_x / 2))
            top = max(0, int(row * step_y - step_y / 2))
            right = min(width, int((column + 1.5) * step_x))
            bottom = min(height, int((row + 1.5) * step_y))
            if right - left > 32 and bottom - top > 32:
                out.append(image.crop((left, top, right, bottom)))
    return out


def batch_of(pieces: list[Image.Image], size: int) -> torch.Tensor:
    arrays = []
    for piece in pieces:
        resample = Image.Resampling.BILINEAR
        resized = np.asarray(piece.resize((size, size), resample), dtype=np.float32) / 255.0
        arrays.append(((resized - MEAN) / STD).transpose(2, 0, 1))
    return torch.from_numpy(np.stack(arrays))


def images_in(folder: Path, limit: int) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})[
        :limit
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", type=int, default=4)
    parser.add_argument("--threshold", type=float, default=0.5, help="the trained default")
    parser.add_argument("--limit", type=int, default=60)
    arguments = parser.parse_args()

    import timm

    torch.set_num_threads(4)
    saved = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    model = timm.create_model(saved["model_name"], pretrained=False, num_classes=1)
    model.load_state_dict(saved["state_dict"])
    model.eval()
    size = int(saved["imgsz"])

    print(f"{saved['model_name']}  fingerprint {saved['split_fingerprint']}")
    print(
        f"METU held-out clusters: accuracy {saved['test_accuracy']:.4f}  "
        f"precision {saved['test_precision']:.4f}  recall {saved['test_recall']:.4f}"
    )
    print(f"  {saved['evaluation_caveat']}\n")

    def run(folder: Path, label: str, wanted: bool) -> None:
        paths = images_in(folder, arguments.limit)
        if not paths:
            print(f"  {label}: no images at {folder}")
            return
        fired = 0
        tile_hits = 0
        tile_total = 0
        elapsed = 0.0
        for path in paths:
            try:
                image = Image.open(path).convert("RGB")
            except Exception:
                continue
            pieces = tiles(image, arguments.grid)
            start = time.perf_counter()
            with torch.no_grad():
                scores = torch.sigmoid(model(batch_of(pieces, size)).squeeze(1))
            elapsed += time.perf_counter() - start
            hits = int((scores > arguments.threshold).sum())
            tile_hits += hits
            tile_total += len(pieces)
            fired += hits > 0
        n = len(paths)
        verdict = "recall" if wanted else "FALSE ALARM"
        print(
            f"  {label:<22} {verdict:<12} {fired}/{n}"
            f"   tiles {tile_hits}/{tile_total} ({tile_hits / tile_total:.1%})"
            f"   {elapsed / n * 1000:.0f} ms/photo"
        )

    print(f"{arguments.grid}x{arguments.grid} tiles, threshold {arguments.threshold}")
    run(ROOMS, "intact rooms", wanted=False)
    run(CRACKS, "masonry with cracks", wanted=True)

    print(
        "\nThe first line is the one that decides. A held-out score of 0.9986 says\n"
        "the model learned 458 Ankara facades; it says nothing about a living room,\n"
        "and only this does. For comparison, measured the same way: the public\n"
        "OpenSistemas crack checkpoint fired on 64% of intact rooms at its default."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
