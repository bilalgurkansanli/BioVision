"""Whole-photograph severity: the confusion matrix behind `overall_severity`.

    uv run python -m scripts.eval_severity

Prints the table README section 7.8 carries. **Copy it verbatim.** The headline
is 64.5%, and the row that matters is `severe` at 51% recall -- the band a user
most needs to be right is the one this is worst at.

**Why the layer exists.** The specialist reports instances. Asked about a
written-off car it returned one `dent` at 42%: true about that dent, and not an
assessment. Cropping to the car raised it to four findings, which is also not an
assessment -- a total is not a sum of parts, and ADR-030 and ADR-033 record the
two attempts to make it into one.

**Why zero-shot.** The encoder is already loaded for the gate and the router, and
the image embedding is already computed for this request. The whole layer is a dot
product against 12 cached text vectors. If that is enough, a fine-tuned head is
weight and training time bought for nothing -- so it is measured first.

**The evaluation set is borrowed and imperfect**, and the number inherits that:
`prajwalbhamere/car-damage-severity-dataset` on Kaggle, 248 held-out images at a
median 275x183 px, some carrying stock-photo watermarks -- which makes its
CC-BY-NC-SA-4.0 declaration one this project does not rely on. It is used to
measure, never redistributed, and no image from it ships here. A better set would
be whole-vehicle photographs labelled by an assessor; that does not exist here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path("C:/Users/bilal/Desktop/BioVision/backend/src")))

from biovision.config import Settings
from biovision.domains.severity import SeverityPrompts
from biovision.models.clip import ClipEncoder
from biovision.models.clip_severity import ClipSeverityEstimator

settings = Settings(_env_file=None)  # type: ignore[call-arg]
encoder = ClipEncoder(
    settings.clip_model, settings.clip_pretrained, settings.weights_path,
    settings.torch_num_threads,
)

estimator = ClipSeverityEstimator(
    encoder, SeverityPrompts.load(settings.severity_prompts_path)
)
labels = [band.value for band in estimator._bands]


def classify(path: Path) -> tuple[str, float]:
    """Exactly what the API would return for this image."""
    pixels = np.asarray(Image.open(path).convert("RGB"))
    band, confidence = estimator.estimate(pixels)
    return band.value, confidence


root = Path("C:/Users/bilal/Desktop/BioVision/data/.cache/severity/data3a/validation")
folders = {"minor": "01-minor", "moderate": "02-moderate", "severe": "03-severe"}

matrix = {t: dict.fromkeys(labels, 0) for t in labels}
for truth, folder in folders.items():
    for path in sorted((root / folder).glob("*")):
        predicted, _ = classify(path)
        matrix[truth][predicted] += 1

print(r"| true \ predicted | " + " | ".join(labels) + " | recall |")
print("|" + "---|" * (len(labels) + 2))
correct = total = 0
for truth in labels:
    row = matrix[truth]
    n = sum(row.values())
    correct += row[truth]
    total += n
    cells = " | ".join(str(row[p]) for p in labels)
    print(f"| **{truth}** | {cells} | {row[truth]/n:.0%} |")
print(f"\noverall accuracy: {correct/total:.1%} over {total} images\n")

if len(sys.argv) > 1:
    # Optional: a single photograph, for the case that prompted this layer.
    target = Path(sys.argv[1])
    print(f"--- {target.name} ---")
    predicted, confidence = classify(target)
    print(f"   -> {predicted.upper()}  ({confidence:.1%})")
