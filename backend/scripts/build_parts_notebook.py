"""Generate `notebooks/train_hitl_parts.ipynb`.

Run it and commit the output:

    uv run python -m scripts.build_parts_notebook

Written as a generator rather than edited as JSON, for the reason the konut one
was: a notebook is a bad thing to hand-edit and a worse thing to review in a
diff. `check()` parses every code cell before writing, because cell text lives
inside triple-quoted strings here and a backslash escape is processed twice --
which produced an unterminated string literal three times while writing the
first of these.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

NOTEBOOK = Path(__file__).resolve().parents[2] / "notebooks" / "train_hitl_parts.ipynb"


def md(text: str) -> dict[str, object]:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip().splitlines(True)}


def code(text: str) -> dict[str, object]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.strip().splitlines(True),
    }


CELLS: list[dict[str, object]] = [
    md(
        """
# Which part is damaged — HITL "Car Parts and Car Damages", CC0 1.0

The system reports damage extent and where it sits on the vehicle. It cannot say
**which part**, and that is what an assessor works in and what a repair estimate
is built from (parts × labour). This trains that layer.

**The dataset, and the one that was rejected.** Ultralytics ships `carparts-seg`
— 3,833 images, 23 classes, CC BY 4.0, one line to train. It is the first result
anyone finds and it is disqualified, measured rather than suspected:

```
3,833 image files, 585 unique SOURCE photographs      (6.6× augmentation)
source photographs appearing in more than one split:   429  (73%)
  ... appearing in all three splits:                    89
```

Its files are Roboflow augmentations named `<source>_jpg.rf.<hash>.jpg`, so the
source behind each is recoverable — and **73% of sources have rotated copies of
themselves in another split.** A held-out mAP there measures memorisation. Its
CC BY badge also traces to `dsmlr/Car-Parts-Segmentation`, which has a null
licence field and no LICENSE file.

So this trains on **Humans in the Loop**, whose own page reads *"dedicated to the
public domain by Humans in the Loop under CC0 1.0 license"* — a first-party
dedication rather than a re-uploader's tag. 1,812 images, 24,851 polygons, 21
part classes that are an assessor's taxonomy one-to-one, and **441 images
carrying part polygons and damage polygons on the same photograph**, which makes
damage-to-part mapping directly supervised instead of stitched together.

**Two things this notebook will not let you skip.**

1. **The split is by source photograph, not by file.** The leak above is the
   reason, and the cell that does it refuses to continue if the grouping looks
   implausible.
2. **The headline is the cross-source number, not the held-out one.** HITL is
   US/UK/EU salvage-auction photography; `carparts-seg` is South-East Asian
   dealer classifieds. They share about fifteen class names and no photograph, no
   camera and no continent. That evaluation is the thing the building domain
   never had (README 7.11), and its absence is what let a 0.9986 score coexist
   with fifteen false alarms out of fifteen.

**Latency settles the architecture before training starts.** Measured at four
threads on the production CPU: `yolo11n-seg` is 83 ms at 640 px against the
vehicle specialist's 139 ms, so damage plus parts in series is ~222 ms — inside
the 150–250 ms budget, at the top of it. 768 px and larger backbones are not
affordable, so they are not offered.
"""
    ),
    code(
        """
import json, os, random, re, shutil, sys, time
from collections import defaultdict
from pathlib import Path

ON_KAGGLE = Path("/kaggle/input").exists()
WORK = Path("/kaggle/working") if ON_KAGGLE else Path.cwd()
print("kaggle" if ON_KAGGLE else "local", "->", WORK)

!pip -q install ultralytics==8.4.117

import numpy as np, torch
from PIL import Image
from ultralytics import YOLO

SEED = 20260903
random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print("torch", torch.__version__, "|", DEVICE)
"""
    ),
    md(
        """
## 1. Find the dataset, and read `meta.json` rather than the folder name

**The two folders are named backwards in at least one mirror.** `Car damages
dataset/meta.json` holds the 21 **part** classes and `Car parts dataset/meta.json`
holds the 8 damage classes. Trusting the directory name would silently train a
part model on damage labels, and the run would look fine — which is exactly the
kind of failure this project keeps finding.

Download from Humans in the Loop directly, or add the Kaggle mirror
`humansintheloop/car-parts-and-car-damages` through *Add Data*. Either way the
cell below searches, checks `meta.json`, and prints what it found.
"""
    ),
    code(
        """
# Search rather than assume a path. A hardcoded mount ended a run at cell 2 in
# the konut notebook, and the fix there is the fix here.
def find_supervisely_root(bases, depth=4):
    for base in bases:
        if not base.exists():
            continue
        frontier, level = [base], 0
        while frontier and level <= depth:
            nxt = []
            for d in frontier:
                if (d / "meta.json").is_file() and (d / "ann").is_dir():
                    return d.parent
                nxt.extend(c for c in d.iterdir() if c.is_dir())
            frontier, level = nxt, level + 1
    return None

ROOT = find_supervisely_root([Path("/kaggle/input"), WORK])
if ROOT is None:
    print("dataset not found. What IS mounted:")
    for base in (Path("/kaggle/input"), WORK):
        if base.exists():
            for d in sorted(base.iterdir()):
                print("  ", d)
    raise SystemExit("mount the HITL dataset and re-run")
print("found at", ROOT)

# `meta.json` is the authority on which folder is which -- the folder NAMES are
# swapped in at least one mirror, and believing them trains a part model on
# damage labels without anything looking wrong.
PART_NAMES = {
    "Windshield", "Back-windshield", "Front-window", "Back-window", "Front-door",
    "Back-door", "Front-wheel", "Back-wheel", "Front-bumper", "Back-bumper",
    "Headlight", "Tail-light", "Hood", "Trunk", "License-plate", "Mirror",
    "Roof", "Grille", "Rocker-panel", "Quarter-panel", "Fender",
}

folders = {}
for child in sorted(p for p in ROOT.iterdir() if p.is_dir()):
    meta_path = child / "meta.json"
    if not meta_path.is_file():
        continue
    classes = [c["title"] for c in json.loads(meta_path.read_text())["classes"]]
    kind = "parts" if len(set(classes) & PART_NAMES) >= 10 else "damage"
    folders[kind] = (child, classes)
    print(f"  {child.name!r} -> {kind}: {len(classes)} classes")

assert "parts" in folders, "no folder whose meta.json holds the part taxonomy"
PARTS_DIR, PART_CLASSES = folders["parts"]
PART_CLASSES = sorted(PART_CLASSES)
print(f"\\ntraining {len(PART_CLASSES)} part classes from {PARTS_DIR.name!r}")
"""
    ),
    md(
        """
## 2. Split by source photograph, not by file

The non-negotiable one. HITL is not augmented the way `carparts-seg` is, so the
grouping is simpler — but it is done explicitly and asserted rather than assumed,
because "one photograph, one row" is exactly the assumption that was false in the
dataset this notebook exists to avoid.

Any near-duplicate group — the same vehicle photographed twice in one listing —
must land on one side of the cut. Grouping is by image stem with a trailing index
stripped, and the cell prints the group-size distribution so an implausible
result is visible rather than silent.
"""
    ),
    code(
        """
IMAGES = PARTS_DIR / "img"
ANNOTATIONS = PARTS_DIR / "ann"
files = sorted(p for p in IMAGES.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
print(f"{len(files)} images, {len(list(ANNOTATIONS.iterdir()))} annotation files")

# `Car damages 1709.jpg` and `Car damages 1709 (2).jpg` are the same listing.
DUPLICATE_SUFFIX = re.compile(r"\\s*\\(\\d+\\)$")
def source_of(path):
    return DUPLICATE_SUFFIX.sub("", path.stem).strip().lower()

groups = defaultdict(list)
for path in files:
    groups[source_of(path)].append(path)

sizes = sorted((len(v) for v in groups.values()), reverse=True)
print(f"{len(groups)} source photographs | largest groups {sizes[:5]}")
assert len(groups) >= len(files) * 0.5, (
    "grouping collapsed more than half the dataset into shared sources; "
    "check `source_of` before training, or the split will leak"
)

keys = sorted(groups)
random.Random(SEED).shuffle(keys)
n_test, n_val = int(len(keys) * 0.20), int(len(keys) * 0.10)
split_keys = {
    "test": keys[:n_test],
    "val": keys[n_test:n_test + n_val],
    "train": keys[n_test + n_val:],
}
assert not (set(split_keys["train"]) & set(split_keys["test"]))

print(f"\\n{'split':<7}{'sources':>9}{'images':>9}")
for name in ("train", "val", "test"):
    images = [p for k in split_keys[name] for p in groups[k]]
    print(f"{name:<7}{len(split_keys[name]):>9}{len(images):>9}")

import hashlib
FINGERPRINT = hashlib.sha256(
    json.dumps({k: sorted(v) for k, v in split_keys.items()}, sort_keys=True).encode()
).hexdigest()[:16]
print("\\nsplit fingerprint", FINGERPRINT, "- record it beside every number from this run")
"""
    ),
    md(
        """
## 3. Supervisely polygons into YOLO segmentation labels

Nothing is dropped silently: unmapped classes, non-polygon shapes and empty
annotations are all counted and printed, with a warning past 5%. A converter that
quietly discards a class produces a model that has simply never seen it, and the
per-class table then reports a real zero for an unreal reason.
"""
    ),
    code(
        """
DATA = WORK / "hitl_parts"
shutil.rmtree(DATA, ignore_errors=True)
for split in ("train", "val", "test"):
    (DATA / "images" / split).mkdir(parents=True, exist_ok=True)
    (DATA / "labels" / split).mkdir(parents=True, exist_ok=True)

index = {name: i for i, name in enumerate(PART_CLASSES)}
skipped = defaultdict(int)
written = defaultdict(int)

for split, group_keys in split_keys.items():
    for key in group_keys:
        for image_path in groups[key]:
            ann_path = ANNOTATIONS / (image_path.name + ".json")
            if not ann_path.is_file():
                skipped["missing annotation"] += 1
                continue
            ann = json.loads(ann_path.read_text())
            height, width = ann["size"]["height"], ann["size"]["width"]

            rows = []
            for obj in ann.get("objects", []):
                if obj.get("geometryType") != "polygon":
                    skipped[f"shape {obj.get('geometryType')}"] += 1
                    continue
                title = obj["classTitle"]
                if title not in index:
                    skipped[f"class {title}"] += 1
                    continue
                points = obj["points"]["exterior"]
                if len(points) < 3:
                    skipped["degenerate polygon"] += 1
                    continue
                flat = []
                for x, y in points:
                    flat += [min(max(x / width, 0.0), 1.0), min(max(y / height, 0.0), 1.0)]
                rows.append(f"{index[title]} " + " ".join(f"{v:.6f}" for v in flat))

            if not rows:
                skipped["no usable polygon"] += 1
                continue
            shutil.copy(image_path, DATA / "images" / split / image_path.name)
            (DATA / "labels" / split / (image_path.stem + ".txt")).write_text("\\n".join(rows))
            written[split] += 1

total_written = sum(written.values())
print("written:", dict(written))
if skipped:
    print("skipped:", dict(skipped))
    share = sum(skipped.values()) / max(total_written + sum(skipped.values()), 1)
    if share > 0.05:
        print(f"WARNING: {share:.1%} of annotations were skipped -- check the reasons above")

(DATA / "data.yaml").write_text(
    "path: " + str(DATA) + "\\ntrain: images/train\\nval: images/val\\ntest: images/test\\n"
    + "names:\\n" + "".join(f"  {i}: {n}\\n" for i, n in enumerate(PART_CLASSES))
)
print("\\n" + (DATA / "data.yaml").read_text()[:300])
"""
    ),
    md(
        """
## 4. Train

`yolo11n-seg` at 640 px, and the reason is latency rather than taste: measured at
four threads on the production CPU it is **83 ms**, against the vehicle
specialist's 139 ms, so damage plus parts in series is ~222 ms — inside the
150–250 ms budget, at the top of it. A larger backbone or 768 px does not fit,
so neither is offered here.
"""
    ),
    code(
        """
MODEL, IMGSZ, EPOCHS, BATCH = "yolo11n-seg.pt", 640, 120, 16

model = YOLO(MODEL)
results = model.train(
    data=str(DATA / "data.yaml"),
    epochs=EPOCHS,
    imgsz=IMGSZ,
    batch=BATCH,
    seed=SEED,
    deterministic=True,
    patience=25,
    project=str(WORK / "runs"),
    name="hitl_parts",
    exist_ok=True,
)
print("best:", results.save_dir)
"""
    ),
    md(
        """
## 5. The two numbers, in the order that matters

The held-out number is about HITL. The cross-source number is about the world,
and it goes first — a lesson this project paid for once already (README 7.11).
"""
    ),
    code(
        """
best = YOLO(str(Path(results.save_dir) / "weights" / "best.pt"))

held_out = best.val(data=str(DATA / "data.yaml"), split="test", imgsz=IMGSZ)
print(f"\\nHELD OUT (HITL sources never trained on)  mask mAP50 {held_out.seg.map50:.4f}"
      f"  mAP50-95 {held_out.seg.map:.4f}   fingerprint {FINGERPRINT}")

print("\\nper class, worst rows included:")
for i, name in enumerate(PART_CLASSES):
    try:
        print(f"  {name:<18}{held_out.seg.ap50[i]:>8.3f}")
    except Exception:
        print(f"  {name:<18}{'n/a':>8}")
"""
    ),
    code(
        """
# The cross-source probe. Ultralytics `carparts-seg` is South-East Asian dealer
# classifieds; HITL is US/UK/EU salvage auctions. They share class names and
# share no photograph, camera or continent -- which is what makes this the number
# to lead with, and it is also why it will be the LOWER one.
#
# Used as an evaluation set ONLY. Its own splits leak (73% of its source
# photographs appear in more than one), so it can never be trained on here.
import io, urllib.request, zipfile

CROSS = WORK / "carparts_seg"
if not CROSS.exists():
    CROSS.mkdir(parents=True)
    url = "https://github.com/ultralytics/assets/releases/download/v0.0.0/carparts-seg.zip"
    payload = urllib.request.urlopen(url, timeout=300).read()
    zipfile.ZipFile(io.BytesIO(payload)).extractall(CROSS)
    print(f"fetched {len(payload) / 1e6:.0f} MB")

# Confirm the leak here rather than trusting the README: the same count, on the
# machine that is about to use this as an evaluation set.
source_of_cross = re.compile(r"^(.*?)_jpg\\.rf\\.", re.I)
seen = defaultdict(set)
for path in CROSS.rglob("*.jpg"):
    split = next((p for p in path.parts if p in ("train", "valid", "val", "test")), None)
    if split:
        match = source_of_cross.match(path.name)
        seen[match.group(1) if match else path.name].add(split)
leaked = sum(1 for splits in seen.values() if len(splits) > 1)
print(f"{len(seen)} source photographs, {leaked} ({leaked / len(seen):.0%}) in more than one split")
print("-> evaluation only. Never train on this.")
print(
    "\\nEvaluate on it with a name mapping, and publish THAT number first.\\n"
    "A held-out score says how well the model learned one corpus. Section 7.11\\n"
    "of the README is what happens when only that number exists: 0.9986 on the\\n"
    "dataset's own split, and fifteen false alarms out of fifteen in the world."
)
"""
    ),
    md(
        """
## 6. Before any of this reaches the product

1. Publish the **cross-source** number first and the held-out number second, with
   its caveat attached.
2. Record the **split fingerprint** and seed beside every figure.
3. Publish the **per-class table including the worst rows**. `Rocker-panel` and
   `Back-windshield` are rare and will be weak; that is the useful part.
4. Measure **CPU latency at four threads** before wiring anything in. The budget
   for the part stage is ~110 ms on top of the existing 139 ms.
5. **HITL states who annotated its images and not who supplied them.** No stock
   watermarks were found in the frames opened, unlike ADR-034's findings, but the
   provenance is unconfirmed — send that email before a checkpoint is published.
6. There is **no left/right distinction** in the labels. `Front-door`, not
   `left-front-door`, which is the same limit `damage_position` already refuses
   to guess past. Do not let the UI imply otherwise.
"""
    ),
]


def check(cells: list[dict[str, object]]) -> None:
    """Every code cell must parse before the notebook is written."""
    newline = chr(10)
    for index, cell in enumerate(cells):
        if cell["cell_type"] != "code":
            continue
        lines = "".join(cell["source"]).split(newline)  # type: ignore[arg-type]
        parseable = newline.join(
            (line[: len(line) - len(line.lstrip())] + "pass  # " + line.strip())
            if line.strip().startswith("!")
            else line
            for line in lines
        )
        try:
            ast.parse(parseable)
        except SyntaxError as error:
            offending = lines[(error.lineno or 1) - 1] if lines else ""
            raise SystemExit(
                f"cell {index} does not parse: {error}"
                f"{newline}  line {error.lineno}: {offending!r}"
                f"{newline}  a backslash escape in the generator is the usual cause"
                " -- it needs doubling, or removing."
            ) from error


def main() -> int:
    check(CELLS)
    NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)
    NOTEBOOK.write_text(
        json.dumps(
            {
                "cells": CELLS,
                "metadata": {
                    "kernelspec": {
                        "display_name": "Python 3",
                        "language": "python",
                        "name": "python3",
                    },
                    "language_info": {"name": "python", "version": "3.11"},
                },
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {NOTEBOOK} ({len(CELLS)} cells, every code cell parses)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
