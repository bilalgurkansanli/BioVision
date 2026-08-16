"""Sample router evaluation images from a local source directory.

    uv run python -m scripts.sample_router_set --domain vehicle \
        --source ../data/vehide/image/image --count 60

Builds the two disjoint splits the router scripts expect, and writes manifest
rows recording where each file came from and its SHA-256.

**Why sampling needs its own script.** The evaluation and calibration splits must
never share an image -- fitting a temperature on the images used to report ECE
produces an excellent number that describes nothing -- and "must never" is not a
property you get by copying files by hand twice. Here it is structural: one
shuffle, one cut, and the two halves cannot overlap because they are slices of
the same list.

The seed is pinned, so the same source directory always yields the same split.
Re-running after adding images changes the split, which is why the manifest
records the SHA-256 of every file: a changed split is visible rather than
silent.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import re
import shutil
import sys
from pathlib import Path

from biovision.config import BACKEND_ROOT

DATA = BACKEND_ROOT.parent / "data"
SEED = 20260311

#: Evaluation gets the larger share. Calibration fits one scalar and needs less
#: data than the split that has to support a per-domain confusion matrix.
EVAL_SHARE = 0.5

FIELDS = ["filename", "domain", "source_url", "license", "sha256", "notes"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def existing_rows(manifest: Path) -> list[dict[str, str]]:
    if not manifest.is_file():
        return []
    lines = [
        line
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return [dict(row) for row in csv.DictReader(lines)]


def header_comment(manifest: Path) -> str:
    """Preserve the explanatory comment block at the top of a manifest."""
    if not manifest.is_file():
        return ""
    kept = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#") or not line.strip():
            kept.append(line)
        elif kept:
            break
    return "\n".join(kept).rstrip() + "\n" if kept else ""


def write_manifest(manifest: Path, rows: list[dict[str, str]]) -> None:
    comment = header_comment(manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        handle.write(comment)
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--count", type=int, default=60, help="total across both splits")
    parser.add_argument("--source-url", default="", help="recorded in the manifest")
    parser.add_argument("--license", default="", help="recorded in the manifest")
    parser.add_argument("--prefix", default="", help="prepended to filenames to avoid collisions")
    parser.add_argument(
        "--attribution",
        type=Path,
        help="CSV of per-file licence and source, as written by fetch_commons.py",
    )
    parser.add_argument(
        "--into",
        default="router",
        choices=["router", "gate"],
        help="router splits into eval and calib; gate writes the single gate_eval set",
    )
    parser.add_argument(
        "--group-regex",
        help=(
            "files whose first capture group matches are kept in the same split; "
            "use when a source holds several photographs of one subject"
        ),
    )
    arguments = parser.parse_args()

    if not arguments.source.is_dir():
        print(f"no such directory: {arguments.source}")
        return 1

    # Per-file attribution, where the source has it. Commons is a collection
    # rather than a corpus: two photographs in one category can carry different
    # terms, so one `--license` for the batch would be a convenient fiction.
    attribution: dict[str, dict[str, str]] = {}
    if arguments.attribution:
        if not arguments.attribution.is_file():
            print(f"no such attribution file: {arguments.attribution}")
            return 1
        with arguments.attribution.open(encoding="utf-8") as handle:
            attribution = {row["filename"]: row for row in csv.DictReader(handle)}
        print(f"attribution for {len(attribution)} files")

    if not arguments.license and not attribution:
        # A manifest row without a licence is a claim nobody can check later.
        print("--license is required: an unrecorded licence is an unanswerable question")
        return 1

    images = sorted(
        p
        for p in arguments.source.rglob("*")
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    if len(images) < arguments.count:
        print(f"only {len(images)} images in {arguments.source}, need {arguments.count}")
        return 1

    # One shuffle, one cut: the splits cannot overlap because they are slices of
    # the same list.
    rng = random.Random(f"{SEED}:{arguments.domain}")

    # Photographs of one subject belong together. An archive that documents a
    # building from six angles will otherwise put three angles in the evaluation
    # split and three in the calibration split, and the two splits stop being
    # independent without ever sharing a file -- which is the form of leakage
    # that a disjointness check cannot see.
    groups: dict[str, list[Path]] = {}
    for image in images:
        key = image.stem
        if arguments.group_regex:
            match = re.search(arguments.group_regex, image.name)
            if match:
                key = match.group(1) if match.groups() else match.group(0)
        groups.setdefault(key, []).append(image)

    order = sorted(groups)
    rng.shuffle(order)

    if arguments.into == "gate":
        # The gate set is scored once and never fitted on, so it has no
        # calibration half to keep separate from.
        chosen: list[Path] = []
        for key in order:
            if len(chosen) >= arguments.count:
                break
            chosen.extend(groups[key])
        splits = {"gate_eval": chosen[: arguments.count]}
    else:
        first: list[Path] = []
        second: list[Path] = []
        eval_target = arguments.count * EVAL_SHARE
        calib_target = arguments.count - eval_target

        # Whole groups go to whichever side is furthest from its target. Filling
        # one side to a threshold first lets a single large group overshoot and
        # starve the other -- 30/10 rather than 20/20, on the first attempt.
        for key in order:
            if len(first) + len(second) >= arguments.count:
                break
            behind = first if len(first) / eval_target <= len(second) / calib_target else second
            behind.extend(groups[key])

        splits = {"router_eval": first, "router_calib": second}

    if arguments.group_regex:
        print(f"{len(images)} files in {len(groups)} groups")

    for split, members in splits.items():
        directory = DATA / split / "images"
        directory.mkdir(parents=True, exist_ok=True)
        manifest = DATA / split / "manifest.csv"

        rows = [row for row in existing_rows(manifest) if row.get("domain") != arguments.domain]
        for source in members:
            name = f"{arguments.prefix}{source.name}" if arguments.prefix else source.name
            target = directory / name
            shutil.copy2(source, target)

            credit = attribution.get(source.name, {})
            author = credit.get("author", "").strip()
            notes = f"sampled seed={SEED}"
            if author:
                # CC BY and CC BY-SA want the author named. Carrying it here
                # keeps the credit attached to the file rather than to a folder.
                notes = f"{notes}; author: {author}"

            rows.append(
                {
                    "filename": name,
                    "domain": arguments.domain,
                    "source_url": credit.get("source_url") or arguments.source_url,
                    "license": credit.get("license") or arguments.license,
                    "sha256": sha256(target),
                    "notes": notes,
                }
            )

        rows.sort(key=lambda row: (row["domain"], row["filename"]))
        write_manifest(manifest, rows)
        print(f"{split}: +{len(members)} {arguments.domain} ({len(rows)} rows total)")

    if arguments.into == "router":
        overlap = {p.name for p in splits["router_eval"]} & {p.name for p in splits["router_calib"]}
        assert not overlap, f"splits overlap on {len(overlap)} file(s)"
        print("splits are disjoint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
