"""Build the face-redaction ground truth from WIDER FACE.

    uv run python -m scripts.fetch_wider_faces --count 50

WIDER FACE ships bounding boxes for faces in ordinary photographs, which is
exactly what the privacy claim needs a number against. The annotations are
distributed separately from the images and are small; the validation images are
a 1.8 GB zip.

**Why a subset, and how it is chosen.** The published miss rate has to describe
the photographs this system actually receives -- someone's phone camera pointed
at a damaged car, with a bystander in frame. WIDER FACE is deliberately hard: it
includes crowd scenes with two hundred faces at twelve pixels each, which no
redactor is expected to catch and which would drive the number to a figure that
describes a benchmark rather than a use case.

So the sample is filtered, and the filter is stated in the manifest and the
README: images with **1 to 6 faces**, each at least **40 px** on its shorter
side. That is the regime the privacy promise is actually about. Reporting the
unfiltered WIDER FACE number instead would be a different and much worse claim,
honestly measured -- and this project cares which claim is being made.

Excluded categories are recorded too, so the exclusion is auditable rather than
convenient.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

from biovision.config import BACKEND_ROOT

DEST = BACKEND_ROOT.parent / "data" / "redaction_eval"
CACHE = BACKEND_ROOT.parent / "data" / ".cache"

#: The annotation archive. Small, and the only part with a stable public URL.
ANNOTATIONS_URL = "http://shuoyang1213.me/WIDERFACE/support/bbx_annotation/wider_face_split.zip"

SEED = 20260311

#: The regime the privacy claim is about: a handful of faces, each big enough
#: that a person looking at the photograph would recognise someone.
MIN_FACES = 1
MAX_FACES = 6
MIN_FACE_PX = 40


def parse_wider(path: Path) -> dict[str, list[tuple[int, int, int, int]]]:
    """Parse WIDER FACE's bbx_gt format.

    Layout is: a path line, a count line, then that many box lines of
    `x y w h blur expression illumination invalid occlusion pose`.

    A count of 0 is followed by one all-zero line rather than none, which is the
    detail that breaks naive parsers -- including the first version of this one.
    """
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    annotations: dict[str, list[tuple[int, int, int, int]]] = {}

    index = 0
    while index < len(lines):
        name = lines[index]
        index += 1
        if index >= len(lines):
            break
        try:
            count = int(lines[index])
        except ValueError:
            continue
        index += 1

        boxes = []
        for _ in range(max(count, 1)):
            if index >= len(lines):
                break
            parts = lines[index].split()
            index += 1
            if count == 0:
                continue
            x, y, w, h = (int(float(v)) for v in parts[:4])
            invalid = int(parts[7]) if len(parts) > 7 else 0
            if invalid or w <= 0 or h <= 0:
                continue
            boxes.append((x, y, w, h))

        annotations[name] = boxes

    return annotations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument(
        "--images",
        type=Path,
        help="Directory holding WIDER_val/images (download separately; 1.8 GB)",
    )
    arguments = parser.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / "wider_face_split.zip"

    if not archive.exists():
        print(f"downloading annotations from {ANNOTATIONS_URL}")
        try:
            urllib.request.urlretrieve(ANNOTATIONS_URL, archive)
        except Exception as error:
            print(f"download failed: {error}")
            print("The annotation archive moves occasionally. Check")
            print("http://shuoyang1213.me/WIDERFACE/ for the current link.")
            return 1

    with zipfile.ZipFile(archive) as zf:
        zf.extractall(CACHE)

    ground_truth = next(CACHE.rglob("wider_face_val_bbx_gt.txt"), None)
    if ground_truth is None:
        print("wider_face_val_bbx_gt.txt not found in the archive")
        return 1

    annotations = parse_wider(ground_truth)
    print(f"parsed {len(annotations):,} annotated images")

    # --- the filter, applied and counted --------------------------------------
    eligible = {}
    rejected = {"too_many_faces": 0, "no_faces": 0, "faces_too_small": 0}
    for name, boxes in annotations.items():
        if not boxes:
            rejected["no_faces"] += 1
            continue
        if len(boxes) > MAX_FACES or len(boxes) < MIN_FACES:
            rejected["too_many_faces"] += 1
            continue
        if any(min(w, h) < MIN_FACE_PX for _, _, w, h in boxes):
            rejected["faces_too_small"] += 1
            continue
        eligible[name] = boxes

    print(f"eligible after filtering: {len(eligible):,}")
    for reason, number in rejected.items():
        print(f"  excluded {number:>6,}  {reason}")

    if not arguments.images:
        print()
        print("Annotations are ready. To finish, download the validation images:")
        print("  http://shuoyang1213.me/WIDERFACE/  ->  WIDER Face Validation Images")
        print("then re-run with --images path/to/WIDER_val/images")
        return 0

    rng = random.Random(SEED)
    chosen: list[str] = sorted(eligible)
    rng.shuffle(chosen)

    images_out = DEST / "images"
    images_out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str | int]] = []
    taken = 0

    for name in chosen:
        if taken >= arguments.count:
            break
        source = arguments.images / name
        if not source.is_file():
            continue
        flat = name.replace("/", "_")
        shutil.copy2(source, images_out / flat)
        for x, y, w, h in eligible[name]:
            rows.append({"filename": flat, "class": "face", "x": x, "y": y, "w": w, "h": h})
        taken += 1

    if not taken:
        print(f"no images found under {arguments.images} -- is that the right directory?")
        return 1

    annotations_csv = DEST / "annotations.csv"
    with annotations_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["filename", "class", "x", "y", "w", "h"])
        writer.writeheader()
        writer.writerows(rows)

    manifest = DEST / "manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        handle.write(
            "# WIDER FACE validation subset, filtered to the regime this system\n"
            f"# actually sees: {MIN_FACES}-{MAX_FACES} faces per image, each at least\n"
            f"# {MIN_FACE_PX}px on its shorter side. The filter is part of the claim --\n"
            "# see README section 5.1. Images are not committed.\n"
        )
        writer = csv.DictWriter(handle, fieldnames=["filename", "source", "license", "sha256"])
        writer.writeheader()
        for name in sorted({str(row["filename"]) for row in rows}):
            digest = hashlib.sha256((images_out / name).read_bytes()).hexdigest()
            writer.writerow(
                {
                    "filename": name,
                    "source": "WIDER FACE validation set",
                    "license": "Free for non-commercial research (WIDER FACE terms)",
                    "sha256": digest,
                }
            )

    print()
    print(f"{taken} images, {len(rows)} face boxes -> {DEST}")
    print("now run: uv run python -m scripts.eval_redaction")
    return 0


if __name__ == "__main__":
    sys.exit(main())
