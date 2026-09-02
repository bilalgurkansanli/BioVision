"""Can a zero-shot prompt tell konut damage types apart?

    uv run python -m scripts.eval_building_type

**Why this exists and why it is not a specialist.** A survey of every openly
available building-damage dataset found that the large ones -- xBD, RescueNet,
FloodNet, Ida-BD -- are satellite or drone imagery of disaster zones. A homeowner
photographing a damp patch on a bedroom ceiling is a different problem, and a
model trained on overhead disaster imagery is useless for it. At claimant scale
the only licence-clean ground-level data is for **cracks**: METU/Özgenel (458
images, CC BY 4.0, verified, Turkish campus buildings) and Ultralytics Crack-Seg.
For water, mould, fire-soot and broken glass there is nothing usable at all --
every "fire" dataset detects active flames, which is wildfire monitoring, not a
soot-blackened wall after the fire is out.

The uncomfortable part: **the readiest sub-problem is the least useful one**.
Cracks map to earthquake damage, which DASK already sends a registered eksper to
grade. `dahili su` -- a burst pipe -- is the most common voluntary-policy claim
and is exactly the class with no data.

So this does not attempt a specialist. It asks whether the CLIP embedding the
gate and router have **already computed** can name the *kind* of damage, at no
extra inference cost. That is a classification of the photograph, never a
measurement of extent, and if it measures badly nothing ships.

`none` is in the class list from the start. The vehicle severity band shipped
without it and told a user their intact car was lightly damaged, because a
three-way softmax had nowhere else to put an undamaged photograph. That lesson
cost a release; it is not being learned twice.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path("C:/Users/bilal/Desktop/BioVision/backend/src")))

KONUT = Path("C:/Users/bilal/Desktop/BioVision/data/_sources/konut")
#: The 61 masonry-crack photographs already in the repo, used for the gate work.
EXISTING_CRACK = Path("C:/Users/bilal/Desktop/BioVision/data/_sources/building")

#: Ordered by how often the peril actually generates a Turkish konut claim --
#: dahili su first -- rather than by how much data exists for it, which is the
#: reverse order. Naming them this way keeps the gap visible.
CANDIDATE: dict[str, list[str]] = {
    "none": [
        "a photo of an undamaged room",
        "a clean intact wall in good condition",
        "a normal photo of a house interior, nothing broken",
        "an ordinary building facade in good repair",
    ],
    "water": [
        "a photo of water damage on a ceiling",
        "a damp stain spreading across a wall",
        "a wall with mould and peeling paint from moisture",
        "water leaking damage inside a house",
    ],
    "fire": [
        "a photo of fire damage inside a building",
        "a wall blackened by soot after a fire",
        "a burnt room with charred walls",
        "smoke damage on a ceiling",
    ],
    "glass": [
        "a photo of a broken window",
        "a shattered pane of glass in a building",
        "a smashed window with cracked glass",
    ],
    "crack": [
        "a photo of a cracked wall",
        "a structural crack in masonry",
        "a large crack running through concrete",
        "a fractured building facade",
    ],
}


def band_vectors(encoder, classes: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    names, vectors = [], []
    for name, prompts in classes.items():
        mean = np.asarray(encoder.encode_texts(prompts), dtype=np.float32).mean(axis=0)
        names.append(name)
        vectors.append(mean / np.linalg.norm(mean))
    return names, np.stack(vectors)


def embed(encoder, path: Path) -> np.ndarray | None:  # type: ignore[no-untyped-def]
    try:
        rgb = np.array(Image.open(path).convert("RGB"))
    except Exception:
        return None
    vector = np.asarray(encoder.encode_image(rgb), dtype=np.float32)
    normalised: np.ndarray = vector / np.linalg.norm(vector)
    return normalised


def images(folder: Path, limit: int) -> list[Path]:
    return sorted(
        p for p in folder.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=40, help="images per class")
    arguments = parser.parse_args()

    from biovision.config import Settings
    from biovision.models.clip import ClipEncoder

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    encoder = ClipEncoder(
        model_name=settings.clip_model,
        pretrained=settings.clip_pretrained,
        cache_dir=Path("C:/Users/bilal/Desktop/BioVision/backend/weights"),
        num_threads=settings.torch_num_threads,
    )
    names, text = band_vectors(encoder, CANDIDATE)

    truth: dict[str, list[Path]] = {}
    for label in names:
        found = images(KONUT / label, arguments.limit) if (KONUT / label).is_dir() else []
        if label == "crack" and EXISTING_CRACK.is_dir():
            # The 61 masonry photographs already in the repo. Folded in rather
            # than fetched again: they are the same kind of evidence and the
            # licences are already recorded in their sidecar.
            found = (found + images(EXISTING_CRACK, arguments.limit))[: arguments.limit]
        if found:
            truth[label] = found

    if not truth:
        print("no konut images found; run scripts/fetch_commons.py first")
        return 1

    matrix: dict[str, Counter[str]] = {label: Counter() for label in truth}
    for label, paths in truth.items():
        for path in paths:
            vector = embed(encoder, path)
            if vector is None:
                continue
            matrix[label][names[int(np.argmax(text @ vector))]] += 1

    present = [n for n in names if n in matrix]
    total = sum(sum(row.values()) for row in matrix.values())
    correct = sum(matrix[label][label] for label in present)

    print(f"\n{total} images across {len(present)} classes\n")
    header = " | ".join(f"{n:>7}" for n in names)
    print(f"{'true \\ predicted':<18} | {header} | recall")
    print("-" * (20 + 10 * len(names) + 10))
    for label in present:
        row = matrix[label]
        n = sum(row.values())
        cells = " | ".join(f"{row[p]:>7}" for p in names)
        print(f"{label:<18} | {cells} | {row[label] / n:>5.0%} ({n})")

    print(f"\noverall accuracy {correct / total:.1%}")

    print("\ncolumns -- what a predicted class turned out to mean:")
    for predicted in names:
        column = {label: matrix[label][predicted] for label in present}
        support = sum(column.values())
        if support:
            share = column.get(predicted, 0) / support
            print(f"  {predicted:<7} support {support:>3}  correct {share:>5.0%}")

    print(
        "\nThis is a classification of the photograph, not a measurement of damage.\n"
        "If it does not separate the classes it does not ship, and the building\n"
        "domain keeps saying `specialist_model: null`."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
