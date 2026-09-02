"""Is the konut failure spatial dilution, or is it the encoder?

    uv run python -m scripts.eval_building_tiled

The whole-image zero-shot router scored 51.2% and called 59 of 115 damaged
photographs undamaged (README 7.11). Two very different explanations fit that,
and they have opposite fixes:

* **Spatial dilution.** A hairline crack occupies a fraction of a percent of the
  frame. One global embedding of a photograph that is 99% intact wall is an
  embedding of an intact wall. The fix is to look at pieces, which costs more
  forward passes of the *same* model and no new weights.
* **Encoder capacity.** ViT-B-32 is small and old, and telling a damp stain from
  a clean wall is a texture judgement rather than object recognition, which is
  where CLIP-style models are weakest. The fix is a bigger encoder, which costs
  latency on every request in the system, not just this one.

This separates them. Same prompts, same images, same 160-image set as 7.11:

    whole      one embedding of the full frame              (the published 51.2%)
    tiles      max over an NxN grid plus the full frame     (dilution hypothesis)

Tiling is exactly the move that worked on the vehicle side -- the mirror view
found damage the original view missed from the same weights (7.9) -- so the same
question is worth asking here before buying a larger model.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path("C:/Users/bilal/Desktop/BioVision/backend/src")))

from scripts.eval_building_type import (
    CANDIDATE,
    EXISTING_CRACK,
    KONUT,
    band_vectors,
    images,
)


def tiles(image: Image.Image, grid: int) -> list[Image.Image]:
    """The full frame plus an NxN grid over it, with a half-tile overlap.

    Overlapping because a crack that runs along a tile boundary would otherwise
    be split into two fragments, each too small to name -- which would look like
    the dilution the grid exists to fix.
    """
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


def aggregate(scores: np.ndarray, none_index: int, rule: str) -> int:
    """Fold per-tile scores into one class index.

    Three rules, and the differences between them are the whole experiment.
    None of them introduces a fitted threshold: a number chosen because it
    scored well on this set would be a number chosen by looking at the answer,
    which is the mistake sections 7.3, 7.9 and 7.10 each refused.
    """
    if rule == "max":
        return int(np.argmax(np.max(scores, axis=0)))
    if rule == "asymmetric":
        best = np.max(scores, axis=0)
        best[none_index] = float(np.min(scores, axis=0)[none_index])
        return int(np.argmax(best))

    # `vote`: each tile makes its own call and they are counted. A photograph is
    # whatever most of its pieces say it is, which needs no threshold and treats
    # every class alike. Ties break toward the more confident tile.
    votes = np.bincount(np.argmax(scores, axis=1), minlength=scores.shape[1])
    winners = np.flatnonzero(votes == votes.max())
    if len(winners) == 1:
        return int(winners[0])
    return int(winners[np.argmax([np.max(scores[:, w]) for w in winners])])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--grid", type=int, default=3)
    parser.add_argument(
        "--rule",
        default="vote",
        choices=("max", "asymmetric", "vote"),
        help=(
            "How the tiles are combined. `max` is symmetric -- every class takes "
            "its best tile. `asymmetric` lets damage take its best tile and "
            "`none` its worst, which finds all the damage and calls every clean "
            "room damaged. `vote` takes each tile's own argmax and counts them, "
            "which introduces no threshold and no asymmetry."
        ),
    )
    parser.add_argument(
        "--model", default=None, help="override the CLIP architecture, e.g. ViT-L-14"
    )
    parser.add_argument("--pretrained", default=None)
    arguments = parser.parse_args()

    from biovision.config import Settings
    from biovision.models.clip import ClipEncoder

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    encoder = ClipEncoder(
        model_name=arguments.model or settings.clip_model,
        pretrained=arguments.pretrained or settings.clip_pretrained,
        cache_dir=Path("C:/Users/bilal/Desktop/BioVision/backend/weights"),
        num_threads=settings.torch_num_threads,
    )
    names, text = band_vectors(encoder, CANDIDATE)
    none_index = names.index("none")

    truth: dict[str, list[Path]] = {}
    for label in names:
        folder = KONUT / label
        found = images(folder, arguments.limit) if folder.is_dir() else []
        if label == "crack" and EXISTING_CRACK.is_dir():
            found = (found + images(EXISTING_CRACK, arguments.limit))[: arguments.limit]
        if found:
            truth[label] = found

    whole: dict[str, Counter[str]] = {label: Counter() for label in truth}
    tiled: dict[str, Counter[str]] = {label: Counter() for label in truth}

    for label, paths in truth.items():
        for path in paths:
            try:
                image = Image.open(path).convert("RGB")
            except Exception:
                continue

            scores = []
            for piece in tiles(image, arguments.grid):
                vector = np.asarray(encoder.encode_image(np.array(piece)), dtype=np.float32)
                scores.append(text @ (vector / np.linalg.norm(vector)))

            whole[label][names[int(np.argmax(scores[0]))]] += 1
            tiled[label][names[aggregate(np.stack(scores), none_index, arguments.rule)]] += 1

    present = [n for n in names if n in truth]
    grid_label = f"{arguments.grid}x{arguments.grid} TILES ({arguments.rule})"
    for title, matrix in (("WHOLE FRAME", whole), (grid_label, tiled)):
        total = sum(sum(row.values()) for row in matrix.values())
        correct = sum(matrix[label][label] for label in present)
        missed = sum(matrix[label]["none"] for label in present if label != "none")
        damaged = sum(sum(matrix[label].values()) for label in present if label != "none")
        print(f"\n{title}")
        print(f"{'true':<8} | " + " | ".join(f"{n:>6}" for n in names) + " | recall")
        for label in present:
            row = matrix[label]
            n = sum(row.values())
            print(
                f"{label:<8} | "
                + " | ".join(f"{row[p]:>6}" for p in names)
                + f" | {row[label] / n:>4.0%} ({n})"
            )
        print(
            f"  accuracy {correct / total:.1%}   damaged called undamaged: "
            f"{missed}/{damaged} ({missed / damaged:.0%})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
