"""An evaluation image without a recorded verdict is a test failure.

A konut classifier was built, measured at 69.4%, wired into the API with a
published confusion matrix and reverted two commits before release, because its
evaluation set held a painting in the `water` class and freeze-dried ice cream
in `crack`. The category names had been trusted; the images had never been
looked at (README 7.11).

Intending to look is not a mechanism. This is the mechanism, and these tests are
what make it one: they fail if an image is in a set without a verdict, if a
verdict has no reason, or if the bytes behind a verdict have changed since it
was given. Reviewing 217 photographs is worth nothing if image 218 can walk in
afterwards.

The set is not committed -- `data/` is ignored and the licences are per-file --
so every test here skips when it is absent. A skip means "no set to check on
this machine", never "checked and fine".
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pytest

EVAL_ROOT = Path(__file__).resolve().parents[3] / "data"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def evaluation_sets() -> list[Path]:
    if not EVAL_ROOT.is_dir():
        return []
    return sorted(p for p in EVAL_ROOT.glob("*_eval") if (p / "verdicts.csv").is_file())


def verdicts_of(root: Path) -> dict[tuple[str, str], dict[str, str]]:
    with (root / "verdicts.csv").open(encoding="utf-8", newline="") as handle:
        return {(row["class"], row["file"]): row for row in csv.DictReader(handle)}


def accepted_images(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.suffix.lower() in IMAGE_SUFFIXES and "_candidates" not in path.parts
    )


SETS = evaluation_sets()
requires_a_set = pytest.mark.skipif(not SETS, reason="no evaluation set on this machine")


@requires_a_set
def test_every_image_in_a_set_was_reviewed() -> None:
    """The whole point. An image nobody looked at is not evidence."""
    for root in SETS:
        verdicts = verdicts_of(root)
        unreviewed = [
            f"{path.parent.name}/{path.name}"
            for path in accepted_images(root)
            if (path.parent.name, path.name) not in verdicts
        ]
        assert not unreviewed, (
            f"{root.name}: {len(unreviewed)} image(s) in the set with no verdict, "
            f"first: {unreviewed[:3]}. Run scripts/review_set.py --sheet and look at them."
        )


@requires_a_set
def test_only_accepted_images_are_in_the_set() -> None:
    """A rejected image must not survive in the directory it was rejected from."""
    for root in SETS:
        verdicts = verdicts_of(root)
        wrong = [
            f"{path.parent.name}/{path.name}"
            for path in accepted_images(root)
            if verdicts.get((path.parent.name, path.name), {}).get("verdict") != "accept"
        ]
        assert not wrong, f"{root.name}: rejected image(s) still present: {wrong[:3]}"


@requires_a_set
def test_the_bytes_behind_a_verdict_have_not_changed() -> None:
    """A verdict is about the photograph that was looked at, not about a filename.

    Without this, replacing a file in place would silently inherit the approval
    given to different pixels.
    """
    for root in SETS:
        for (damage_class, name), row in verdicts_of(root).items():
            path = root / damage_class / name
            if not path.is_file():
                continue  # a rejected image; it was never copied in
            current = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            assert current == row["sha256"], (
                f"{root.name}/{damage_class}/{name} has changed since it was reviewed"
            )


@requires_a_set
def test_every_verdict_carries_a_reason() -> None:
    """Including the rejections -- especially the rejections.

    What was thrown out of an evaluation set is where selection bias lives, and
    it is the half nobody publishes. `review_set.py` refuses a verdict without
    `--why` and this asserts the file still holds to that.
    """
    for root in SETS:
        missing = [
            f"{key[0]}/{key[1]}"
            for key, row in verdicts_of(root).items()
            if not row["reason"].strip()
        ]
        assert not missing, f"{root.name}: verdict(s) with no reason: {missing[:3]}"


@requires_a_set
def test_a_class_that_survived_review_is_reported_with_its_size() -> None:
    """Not a threshold -- a receipt.

    The konut set finished review with `water` at zero and `crack` at zero out of
    130 candidates, which is the finding rather than a bug. Asserting a minimum
    size here would only tempt somebody to loosen the review to satisfy it. What
    is asserted instead is that the count is knowable from the verdicts alone.
    """
    for root in SETS:
        verdicts = verdicts_of(root)
        by_class: dict[str, int] = {}
        for (damage_class, _), row in verdicts.items():
            if row["verdict"] == "accept":
                by_class[damage_class] = by_class.get(damage_class, 0) + 1
        on_disk = {
            path.parent.name: 0 for path in accepted_images(root)
        }
        for path in accepted_images(root):
            on_disk[path.parent.name] += 1
        assert by_class == on_disk, (
            f"{root.name}: verdict counts {by_class} disagree with the directory {on_disk}"
        )
