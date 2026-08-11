"""Shared loading for the annotated evaluation sets.

Images are not committed (ADR-005). Each set is a directory holding a manifest and
an `images/` subdirectory populated by `fetch_eval_images.py`:

    data/router_eval/manifest.csv     filename,domain,source_url,license,sha256
    data/router_calib/manifest.csv    (same columns, disjoint images)

The calibration and evaluation splits must never overlap. Fitting a temperature on
the images used to report ECE would produce a number that means nothing, so
:func:`assert_disjoint` is called by both scripts rather than left to discipline.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from biovision.config import BACKEND_ROOT

DATA_ROOT = BACKEND_ROOT.parent / "data"


def read_manifest(path: Path) -> list[dict[str, str]]:
    """Parse a manifest, ignoring blank lines and `#` comments.

    Manifests are edited by hand and benefit from notes about where a set came from
    and why an image is in it, so comments are supported rather than tolerated.
    """
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return [dict(row) for row in csv.DictReader(lines)]


@dataclass(frozen=True)
class LabelledImage:
    filename: str
    domain: str
    path: Path


class EvalSetMissingError(RuntimeError):
    """Raised when a set has no manifest.

    Deliberately fatal. A script that quietly produced a table from three images
    would be worse than one that refuses to run.
    """


def load_set(name: str) -> list[LabelledImage]:
    """Load one annotated set, skipping entries whose image is not downloaded."""
    directory = DATA_ROOT / name
    manifest = directory / "manifest.csv"

    if not manifest.is_file():
        raise EvalSetMissingError(
            f"no manifest at {manifest}\n"
            f"See data/README.md. Nothing is measured, so nothing is reported."
        )

    entries: list[LabelledImage] = []
    missing = 0

    for row in read_manifest(manifest):
        filename = row["filename"].strip()
        path = directory / "images" / filename
        if not path.is_file():
            missing += 1
            continue
        entries.append(
            LabelledImage(filename=filename, domain=row["domain"].strip(), path=path)
        )

    if missing:
        print(f"warning: {missing} image(s) listed but not downloaded -- run fetch_eval_images.py")
    if not entries:
        raise EvalSetMissingError(f"{name}: manifest lists no downloaded images")

    return entries


def assert_disjoint(left: list[LabelledImage], right: list[LabelledImage]) -> None:
    """Refuse to proceed if the two splits share an image.

    Overlap between the calibration and evaluation splits is the single mistake
    that would invalidate every calibration number in the README, and it is easy to
    make by copying files around.
    """
    shared = {item.filename for item in left} & {item.filename for item in right}
    if shared:
        raise EvalSetMissingError(
            f"calibration and evaluation splits overlap on {len(shared)} image(s): "
            f"{sorted(shared)[:5]}... Reported metrics would be meaningless."
        )


def load_rgb(path: Path, long_edge: int = 1280) -> np.ndarray:
    """Load an image the same way the pipeline would present it to a model."""
    image = Image.open(path).convert("RGB")
    longest = max(image.size)
    if longest > long_edge:
        scale = long_edge / longest
        image = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
            resample=Image.Resampling.LANCZOS,
        )
    return np.asarray(image, dtype=np.uint8)


def summarise(entries: list[LabelledImage]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.domain] = counts.get(entry.domain, 0) + 1
    return dict(sorted(counts.items()))
