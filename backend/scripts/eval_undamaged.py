"""Does the severity band have anywhere to put an undamaged car?

    uv run python -m scripts.eval_undamaged

A user uploaded a showroom photograph of a pristine Audi. The specialist found
nothing, which was correct. The severity band said **hafif** at 72%, which was
not -- and could not have been anything else, because the band is a three-way
softmax over minor/moderate/severe with no fourth option. An undamaged car has
to come out as one of the three, and `minor` is the nearest.

So the fix is obvious and the cost is not: adding a `none` band gives the
estimator somewhere to put a clean car, and it also gives it somewhere to lose a
damaged one. `severe` already recalls at 51% (README 7.8) and the errors run
downward; a fourth band below `minor` is a new place for that bias to drain into.

This measures **both directions before anything ships**:

* on undamaged cars, how often the new band is chosen (the benefit);
* on the 248 genuinely damaged images behind the published matrix, how many get
  pulled into `none` (the cost, and the one that matters -- a written-off car
  reported as undamaged is far worse than a clean car reported as lightly
  damaged).

Nothing here writes to `severity.yaml`. The candidate prompts live in this file
until the numbers justify them.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path("C:/Users/bilal/Desktop/BioVision/backend/src")))

DAMAGED = Path("C:/Users/bilal/Desktop/BioVision/data/.cache/severity/data3a/validation")
#: Intact vehicles, filtered from the raw Commons pull by requiring a COCO
#: vehicle mask over 15% of the frame. The raw pull was NOT usable: the
#: categories returned 1908 town postcards, trains, and -- worst -- a night
#: photograph captioned "Rescue of a car", which is an accident scene. Filtering
#: removed 54 of 125. What remains is intact cars, a third of them vintage or
#: museum pieces, and that composition is stated rather than curated away:
#: dropping images the model finds hard would be measuring the answer.
UNDAMAGED = Path("C:/Users/bilal/Desktop/BioVision/data/_sources/vehicle_clean")

#: The shipped three, copied from `severity.yaml` so this script measures the
#: live prompts rather than a paraphrase of them.
SHIPPED: dict[str, list[str]] = {
    "minor": [
        "a photo of a car with minor damage",
        "a car with a small scratch or a shallow dent",
        "a lightly damaged car, cosmetic damage only",
        "a car with a scuffed bumper",
    ],
    "moderate": [
        "a photo of a car with moderate damage",
        "a car with a crumpled panel or a broken headlight",
        "a damaged car that is repairable",
        "a car with a dented door and broken glass",
    ],
    "severe": [
        "a photo of a severely damaged car",
        "a wrecked car, written off, beyond repair",
        "a car destroyed in a serious collision",
        "a totalled vehicle with a crushed front end",
    ],
}

#: The candidate fourth band. Phrased for the case that actually arrives -- a
#: showroom or listing photograph -- as well as the plain "no damage" wording,
#: because a clean car is usually photographed deliberately rather than after an
#: accident.
CANDIDATE_NONE: list[str] = [
    "a photo of an undamaged car",
    "a car in perfect condition, no damage",
    "a clean intact car with no dents or scratches",
    "a new car in a showroom",
    "a car advertisement photo, flawless bodywork",
]


def band_vectors(encoder, bands: dict[str, list[str]]) -> tuple[list[str], np.ndarray]:  # type: ignore[no-untyped-def]
    names, vectors = [], []
    for name, prompts in bands.items():
        embedded = np.asarray(encoder.encode_texts(prompts), dtype=np.float32).mean(axis=0)
        names.append(name)
        vectors.append(embedded / np.linalg.norm(embedded))
    return names, np.stack(vectors)


def embed(encoder, path: Path) -> np.ndarray | None:  # type: ignore[no-untyped-def]
    """One encode per image, scored against both candidate band sets.

    Encoding twice would double the only expensive step here for two answers
    that must come from the same vector anyway -- and if they ever did not, the
    comparison would be measuring image noise rather than the prompts.
    """
    try:
        rgb = np.array(Image.open(path).convert("RGB"))
    except Exception:
        return None
    vector = np.asarray(encoder.encode_image(rgb), dtype=np.float32)
    normalised: np.ndarray = vector / np.linalg.norm(vector)
    return normalised


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--undamaged", type=Path, default=UNDAMAGED)
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument(
        "--specialist",
        action="store_true",
        help=(
            "Also run the damage specialist over the undamaged set. The band is "
            "only half the complaint: the same clean car reported 'aracin %2 "
            "kadari' from one sub-threshold detection, so the region floor needs "
            "its own false-positive rate."
        ),
    )
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

    three_names, three_text = band_vectors(encoder, SHIPPED)
    four_names, four_text = band_vectors(encoder, {**SHIPPED, "none": CANDIDATE_NONE})

    undamaged = sorted(
        p for p in arguments.undamaged.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )[: arguments.limit]
    damaged = sorted(
        p for p in DAMAGED.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )

    print(f"\nundamaged cars: {len(undamaged)}    damaged (published set): {len(damaged)}")

    for label, paths, is_damaged in (
        ("UNDAMAGED", undamaged, False),
        ("DAMAGED", damaged, True),
    ):
        if not paths:
            print(f"\n{label}: no images found")
            continue
        three: Counter[str] = Counter()
        four: Counter[str] = Counter()
        for path in paths:
            vector = embed(encoder, path)
            if vector is None:
                continue
            three[three_names[int(np.argmax(three_text @ vector))]] += 1
            four[four_names[int(np.argmax(four_text @ vector))]] += 1
        total = sum(three.values())
        print(f"\n{label}  ({total} images)")
        print(f"  {'band':<10} {'shipped (3)':>13} {'candidate (4)':>15}")
        for band in ("none", "minor", "moderate", "severe"):
            a = three.get(band, 0)
            b = four.get(band, 0)
            print(f"  {band:<10} {a:>8} {a / total:>5.0%} {b:>9} {b / total:>5.0%}")
        if is_damaged:
            lost = four.get("none", 0)
            print(
                f"\n  COST: {lost}/{total} ({lost / total:.1%}) genuinely damaged cars "
                f"would be called undamaged"
            )
        else:
            print(
                f"\n  BENEFIT: {four.get('none', 0)}/{total} "
                f"({four.get('none', 0) / total:.1%}) correctly called undamaged; "
                f"shipped calls {three.get('minor', 0) / total:.0%} of them 'minor'"
            )
    if arguments.specialist and undamaged:
        from biovision.models.specialists.vehicle_yolo import build_vehicle_specialist

        model = build_vehicle_specialist(
            Path("C:/Users/bilal/Desktop/BioVision/backend/weights"), mirror_view=False
        )
        if model is None:
            print("\nno specialist checkpoint; skipping")
            return 0

        with_findings = with_region = 0
        areas: list[float] = []
        for path in undamaged:
            try:
                rgb = np.array(Image.open(path).convert("RGB"))
            except Exception:
                continue
            assessment = model.assess_pixels(rgb)
            if assessment.findings:
                with_findings += 1
            if assessment.region is not None:
                with_region += 1
                areas.append(assessment.region.area_ratio_image)

        total = len(undamaged)
        print(f"\nSPECIALIST on the same {total} undamaged cars")
        print(f"  at least one FINDING   (floor 0.20)  {with_findings}/{total}"
              f"  ({with_findings / total:.1%})")
        print(f"  a damage REGION        (floor 0.10)  {with_region}/{total}"
              f"  ({with_region / total:.1%})")
        if areas:
            print(f"  median frame area when a region fired  {float(np.median(areas)):.3%}")

        # What a suppression rule would cost. If the band says `none` AND the
        # finding list is empty, the damaged region is the only thing claiming
        # damage -- built from detections the system itself judged too weak to
        # list, and contradicted by both stronger signals. Hiding it is only
        # defensible if it almost never fires on a genuinely damaged car, so
        # that is counted rather than assumed.
        silent_and_none = 0
        for path in damaged:
            vector = embed(encoder, path)
            if vector is None:
                continue
            if four_names[int(np.argmax(four_text @ vector))] != "none":
                continue
            try:
                rgb = np.array(Image.open(path).convert("RGB"))
            except Exception:
                continue
            if not model.assess_pixels(rgb).findings:
                silent_and_none += 1
        print(
            f"\n  SUPPRESSION COST: on the {len(damaged)} damaged images, "
            f"{silent_and_none} would have BOTH an empty finding list and a "
            f"`none` band ({silent_and_none / len(damaged):.1%})"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
