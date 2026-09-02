"""The gate an evaluation image must pass before it counts as evidence.

    uv run python -m scripts.review_set --set konut --sheet
    uv run python -m scripts.review_set --set konut --accept crack:0,3,6 --why "wall cracks"
    uv run python -m scripts.review_set --set konut --status

**Why this exists.** A konut damage classifier was built, measured at 69.4%,
wired into the API with a published confusion matrix, and reverted two commits
before release -- because the evaluation set turned out to hold a Ravi Varma
painting in the `water` class and freeze-dried ice cream in `crack`. The
Wikimedia category names had been trusted and the images had never been looked
at. README section 7.11 keeps the retraction.

The lesson is not "look at the images". Everyone means to. The lesson is that
meaning to is not a mechanism, so this is the mechanism: candidates land in
`_candidates/`, and **the only way into the set is a recorded verdict**. Every
decision, accept or reject, is written to `verdicts.csv` with a reason and a
content hash, so a later reader can audit what was thrown away as easily as what
was kept -- which is the direction bias usually hides in.

`tests/unit/test_eval_set_integrity.py` asserts that no file sits in an
evaluation set without a verdict, and that no verdict points at bytes that have
since changed. An unreviewed image is a test failure, not a judgement call.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2] / "data"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
VERDICT_COLUMNS = ["set", "class", "file", "sha256", "verdict", "reason", "decided_at"]


def images_in(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def verdict_path(root: Path) -> Path:
    return root / "verdicts.csv"


def load_verdicts(root: Path) -> dict[tuple[str, str], dict[str, str]]:
    path = verdict_path(root)
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {(row["class"], row["file"]): row for row in csv.DictReader(handle)}


def save_verdicts(root: Path, rows: dict[tuple[str, str], dict[str, str]]) -> None:
    path = verdict_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=VERDICT_COLUMNS)
        writer.writeheader()
        for key in sorted(rows):
            writer.writerow(rows[key])


def contact_sheet(paths: list[Path], destination: Path, columns: int = 5, cell: int = 320) -> None:
    """A numbered grid, because the index is what a verdict refers to.

    Numbered rather than named: a filename is a claim by whoever uploaded it,
    and reading `Cracks_in_ceiling.jpg` primes the reviewer toward the answer
    that label already asserts. A number carries no such suggestion.
    """
    if not paths:
        return
    rows = (len(paths) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell, rows * (cell + 24)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        try:
            picture = Image.open(path).convert("RGB")
        except Exception:
            continue
        picture.thumbnail((cell, cell))
        x, y = (index % columns) * cell, (index // columns) * (cell + 24)
        sheet.paste(picture, (x + (cell - picture.width) // 2, y))
        draw.text((x + 4, y + cell + 6), str(index), fill="black")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination)


def parse_selection(values: list[str]) -> dict[str, set[int]]:
    """Turn `crack:0,3,6-9` into a class name and a set of sheet positions."""
    out: dict[str, set[int]] = {}
    for value in values:
        name, _, indices = value.partition(":")
        chosen: set[int] = out.setdefault(name, set())
        for part in indices.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                low, _, high = part.partition("-")
                chosen.update(range(int(low), int(high) + 1))
            else:
                chosen.add(int(part))
    return out


def record(
    root: Path,
    name: str,
    candidates: Path,
    accept: list[str],
    reject: list[str],
    why: str,
) -> int:
    verdicts = load_verdicts(root)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    moved = 0
    for verdict, selection in (
        ("accept", parse_selection(accept)),
        ("reject", parse_selection(reject)),
    ):
        for damage_class, indices in selection.items():
            paths = images_in(candidates / damage_class)
            for index in sorted(indices):
                if index >= len(paths):
                    print(f"  {damage_class}:{index} out of range ({len(paths)} candidates)")
                    continue
                source = paths[index]
                verdicts[(damage_class, source.name)] = {
                    "set": name,
                    "class": damage_class,
                    "file": source.name,
                    "sha256": digest(source),
                    "verdict": verdict,
                    "reason": why,
                    "decided_at": now,
                }
                if verdict == "accept":
                    target = root / damage_class / source.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(source.read_bytes())
                    moved += 1
    save_verdicts(root, verdicts)
    return moved


def report(root: Path, candidates: Path, classes: list[str], name: str) -> None:
    verdicts = load_verdicts(root)
    print(f"\n{name} evaluation set at {root}\n")
    print(f"{'class':<10} {'candidates':>10} {'accepted':>9} {'rejected':>9} {'undecided':>10}")
    for damage_class in classes:
        paths = images_in(candidates / damage_class)
        decided = [verdicts.get((damage_class, p.name)) for p in paths]
        accepted = sum(1 for v in decided if v and v["verdict"] == "accept")
        rejected = sum(1 for v in decided if v and v["verdict"] == "reject")
        undecided = len(paths) - accepted - rejected
        flag = "  <-- unreviewed" if undecided else ""
        print(
            f"{damage_class:<10} {len(paths):>10} {accepted:>9} "
            f"{rejected:>9} {undecided:>10}{flag}"
        )
    print(
        "\nAn undecided image is not evidence. It is not in the set, and "
        "tests/unit/test_eval_set_integrity.py fails if one ever is."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", dest="name", required=True, help="e.g. konut")
    parser.add_argument("--sheet", action="store_true", help="render contact sheets")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--accept", action="append", default=[], metavar="CLASS:INDICES")
    parser.add_argument("--reject", action="append", default=[], metavar="CLASS:INDICES")
    parser.add_argument("--why", default="", help="reason recorded against this batch")
    parser.add_argument("--sheets-into", type=Path, default=Path("."))
    arguments = parser.parse_args()

    root = ROOT / f"{arguments.name}_eval"
    candidates = root / "_candidates"
    if not candidates.is_dir():
        print(f"no candidates at {candidates}; fetch some first")
        return 1

    classes = sorted(p.name for p in candidates.iterdir() if p.is_dir())

    if arguments.sheet:
        for damage_class in classes:
            paths = images_in(candidates / damage_class)
            out = arguments.sheets_into / f"sheet_{arguments.name}_{damage_class}.png"
            contact_sheet(paths, out)
            print(f"  {damage_class:<8} {len(paths):>3} candidates -> {out}")
        print("\nNumbers are positions in this sheet. Decide with --accept/--reject.")
        return 0

    if arguments.accept or arguments.reject:
        if not arguments.why:
            print("--why is required: a verdict with no reason cannot be audited")
            return 1
        moved = record(
            root, arguments.name, candidates, arguments.accept, arguments.reject, arguments.why
        )
        print(f"recorded; {moved} images accepted into {root}")

    report(root, candidates, classes, arguments.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
