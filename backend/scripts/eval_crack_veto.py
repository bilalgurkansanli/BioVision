"""Can a second signal stop the crack model calling a sofa a crack?

    uv run python -m scripts.eval_crack_veto

The screenshot that prompted this shows the failure exactly: a photograph half
living room and half damaged wall, and the model reports `crack` at 100% on the
window, the floor, the sofa and the pot plant as well as on the wall.

Two fixes were considered and one was measured away first. **Raising the
threshold cannot work** -- every tile is already at 1.00 -- and **ranking by raw
logit cannot work either**, which was checked before writing this: intact rooms
score medians of 7 to 17 and cracked walls -5 to 26, so the ordering carries no
signal the sigmoid destroyed. The model has nothing to say off its distribution,
at any scale.

So this tests the vehicle side's move from README 7.10: do not tune the
specialist, **veto it where an independent signal disagrees**. The independent
signal is the CLIP encoder already loaded for the gate and router, and the
question it is asked is far easier than the specialist's. Not "is there a crack
here" but "is this tile a wall at all" -- a sofa is not a wall, and a crack in a
sofa is not a weak claim, it is a category error.

Measured on the same reviewed sets: 15 intact rooms and 60 cracked walls.
If the veto does not keep the walls while dropping the rooms, it does not ship
and the specialist goes back to `null`.
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

#: What a tile has to look like for a crack claim about it to mean anything.
#: Deliberately about the SURFACE, not about damage: asking CLIP to spot cracks
#: would just be a second weak crack detector, and the whole point is to ask a
#: question the second model is good at.
SURFACE = [
    "a close-up of a bare wall surface",
    "a plastered masonry wall",
    "a concrete or stucco surface",
    "the surface of a building wall",
]

#: What the specialist keeps mistaking for a wall. Not an exhaustive list of
#: everything in a house -- the four things the screenshot showed it firing on.
NOT_SURFACE = [
    "furniture, a sofa or a table",
    "a window with daylight coming through",
    "a wooden or tiled floor",
    "a houseplant in a pot",
    "a doorway or a staircase",
    "a picture frame on a wall",
]

#: For the ARGMAX rule: the tile keeps its finding only if `wall surface` beats
#: every one of these outright. A vocabulary rather than a threshold, which is
#: what the router already does -- and which cannot be tuned, only extended with
#: things a room actually contains.
SCENE = {
    "wall": SURFACE,
    "furniture": ["a sofa", "a table or a chair", "a rug or a carpet"],
    "window": ["a window with daylight", "a curtain or a blind"],
    "floor": ["a wooden floor", "a tiled floor", "a floor covered in debris"],
    "plant": ["a houseplant in a pot", "flowers in a vase"],
    "tools": ["a ladder", "paint tins and decorating tools", "a bucket"],
    "opening": ["a doorway", "a staircase", "a skirting board"],
    "ceiling": ["a ceiling", "a light fitting"],
    "clutter": ["ornaments and books on a shelf", "a picture frame"],
}


def build(grid: int):  # type: ignore[no-untyped-def]
    import timm

    from biovision.config import Settings
    from biovision.models.clip import ClipEncoder

    torch.set_num_threads(4)
    saved = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    model = timm.create_model(saved["model_name"], pretrained=False, num_classes=1)
    model.load_state_dict(saved["state_dict"])
    model.eval()

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    encoder = ClipEncoder(
        model_name=settings.clip_model,
        pretrained=settings.clip_pretrained,
        cache_dir=Path("C:/Users/bilal/Desktop/BioVision/backend/weights"),
        num_threads=settings.torch_num_threads,
    )

    def mean_vector(prompts: list[str]) -> np.ndarray:
        embedded = np.asarray(encoder.encode_texts(prompts), dtype=np.float32).mean(axis=0)
        normalised: np.ndarray = embedded / np.linalg.norm(embedded)
        return normalised

    scene_names = list(SCENE)
    scene = np.stack([mean_vector(SCENE[name]) for name in scene_names])
    return (
        model,
        int(saved["imgsz"]),
        encoder,
        mean_vector(SURFACE),
        mean_vector(NOT_SURFACE),
        scene_names,
        scene,
    )


def tile_boxes(rgb: np.ndarray, grid: int) -> list[tuple[int, int, int, int]]:
    height, width = rgb.shape[:2]
    boxes = [(0, 0, width, height)]
    step_x, step_y = width / grid, height / grid
    for row in range(grid):
        for column in range(grid):
            left = max(0, int(column * step_x - step_x / 2))
            top = max(0, int(row * step_y - step_y / 2))
            right = min(width, int((column + 1.5) * step_x))
            bottom = min(height, int((row + 1.5) * step_y))
            if right - left > 32 and bottom - top > 32:
                boxes.append((left, top, right, bottom))
    return boxes


def images_in(folder: Path, limit: int) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})[
        :limit
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", type=int, default=4)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument(
        "--margin",
        type=float,
        default=0.0,
        help="how much more wall-like than not-wall-like a tile must look",
    )
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--rule", default="sign", choices=("sign", "argmax"))
    arguments = parser.parse_args()

    model, size, encoder, surface, other, scene_names, scene = build(arguments.grid)
    wall_index = scene_names.index("wall")

    def run(folder: Path, label: str, wanted: bool) -> None:
        paths = images_in(folder, arguments.limit)
        raw_photos = veto_photos = 0
        raw_tiles = veto_tiles = total_tiles = 0
        elapsed = 0.0
        for path in paths:
            try:
                rgb = np.array(Image.open(path).convert("RGB"))
            except Exception:
                continue
            boxes = tile_boxes(rgb, arguments.grid)
            crops = [rgb[top:bottom, left:right] for left, top, right, bottom in boxes]

            start = time.perf_counter()
            batch = []
            for crop in crops:
                resized = Image.fromarray(crop).resize(
                    (size, size), Image.Resampling.BILINEAR
                )
                array = np.asarray(resized, dtype=np.float32) / 255.0
                batch.append(((array - MEAN) / STD).transpose(2, 0, 1))
            with torch.no_grad():
                scores = torch.sigmoid(model(torch.from_numpy(np.stack(batch))).squeeze(1)).numpy()

            vectors = np.asarray(encoder.encode_images(crops), dtype=np.float32)
            if arguments.rule == "sign":
                keep_tile = (vectors @ surface - vectors @ other) > arguments.margin
            else:
                keep_tile = np.argmax(vectors @ scene.T, axis=1) == wall_index
            elapsed += time.perf_counter() - start

            fires = [
                index
                for index in range(1, len(boxes))
                if scores[index] > arguments.threshold
            ]
            kept = [index for index in fires if keep_tile[index]]

            raw_tiles += len(fires)
            veto_tiles += len(kept)
            total_tiles += len(boxes) - 1
            raw_photos += bool(fires)
            veto_photos += bool(kept)

        n = len(paths)
        verdict = "found" if wanted else "FALSE ALARM"
        print(
            f"  {label:<20} {verdict:<12}"
            f"  before {raw_photos}/{n}  after {veto_photos}/{n}"
            f"   tiles {raw_tiles}->{veto_tiles} of {total_tiles}"
            f"   {elapsed / n * 1000:.0f} ms/photo"
        )

    print(f"{arguments.grid}x{arguments.grid} tiles, crack>{arguments.threshold}, "
          f"wall margin>{arguments.margin}\n")
    run(ROOMS, "intact rooms", wanted=False)
    run(CRACKS, "cracked walls", wanted=True)
    print(
        "\nThe veto ships only if the walls survive it. A filter that drops the "
        "false alarms\nby dropping everything is not a fix, it is the specialist "
        "turned off with extra steps."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
