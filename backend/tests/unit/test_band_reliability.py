"""The one probability this system publishes, and the table it comes from.

Not an accuracy test -- these are counts, and counts cannot be wrong. They exist
so the confusion matrix in the code and the confusion matrix in README section
7.8 cannot drift apart, because the moment they do, the product is printing a
probability that nothing published supports.
"""

from __future__ import annotations

import re

import pytest

from biovision.config import BACKEND_ROOT
from biovision.models.band_reliability import (
    BAND_RELIABILITY,
    CONFUSION,
    EVALUATION_NOTE_TR,
    reliability_for,
)
from biovision.schemas.enums import Severity

README = BACKEND_ROOT.parent / "README.md"


def test_the_matrix_still_sums_to_the_published_sample() -> None:
    total = sum(count for row in CONFUSION.values() for count in row.values())
    assert total == 319, "README 7.8 reports 319 images: 248 damaged + 71 intact"


def test_accuracy_matches_the_published_figure() -> None:
    correct = sum(CONFUSION[band][band] for band in Severity)
    assert round(correct / 319, 3) == 0.655, "README 7.8 reports 65.5% overall accuracy"


def test_the_fourth_band_did_not_cost_severe_recall() -> None:
    """The one number that had to survive adding an `undamaged` band.

    A band below `minor` is a new place for a downward bias to drain into, and
    the whole fix would be a bad trade if wrecks started landing in it. They did
    not: `severe` recalls 46 of 91, cell for cell what it did with three bands.
    """
    row = CONFUSION[Severity.SEVERE]
    assert row[Severity.SEVERE] == 46
    assert sum(row.values()) == 91
    assert round(row[Severity.SEVERE] / 91, 2) == 0.51


def test_no_truly_severe_car_is_ever_called_undamaged() -> None:
    """The worst error this system could make, asserted rather than hoped for.

    Telling a claimant their written-off car looks undamaged would be worse than
    every other mistake in this table combined. The `none` column holds 52
    undamaged, 7 moderate, 3 minor -- and zero severe.
    """
    assert CONFUSION[Severity.SEVERE][Severity.NONE] == 0
    assert BAND_RELIABILITY[Severity.NONE].worse_share < 0.20


def test_every_column_is_a_distribution() -> None:
    for band, reliability in BAND_RELIABILITY.items():
        shares = sum(outcome.share for outcome in reliability.outcomes)
        assert abs(shares - 1.0) < 1e-3, f"{band} column does not sum to 1"
        assert reliability.support == sum(outcome.count for outcome in reliability.outcomes)


def test_moderate_is_more_often_severe_than_moderate() -> None:
    """The most important thing this module says, asserted so it cannot be lost.

    Of the photographs called `moderate`, more were truly severe than truly
    moderate. Any future change that makes the UI print "orta hasar" without the
    number beside it is a change that has to delete this test first.
    """
    moderate = BAND_RELIABILITY[Severity.MODERATE]
    assert moderate.worse_share > moderate.correct_share
    assert round(moderate.worse_share, 2) == 0.49


def test_severe_never_understates() -> None:
    """Nothing is worse than `severe`, so its `worse_share` must be exactly zero.

    A non-zero value would mean the ordering of the bands had been broken.
    """
    assert BAND_RELIABILITY[Severity.SEVERE].worse_share == 0.0


def test_no_band_means_no_reliability() -> None:
    """A missing prediction must not silently borrow another band's numbers."""
    assert reliability_for(None) is None


@pytest.mark.parametrize("band", list(Severity))
def test_the_readme_still_carries_these_cells(band: Severity) -> None:
    """The published table is the source. If it changes, this fails loudly."""
    text = README.read_text(encoding="utf-8")
    # Split on a real h3 rather than any run of hashes: section 7.8 now carries
    # `####` subsections, and splitting on "###" truncated it before the table.
    section = text.split("### 7.8")[1].split("\n### ")[0]
    row = CONFUSION[band]
    pattern = r"\|\s*\*\*" + band.value + r"\*\*\s*\|\s*" + r"\s*\|\s*".join(
        str(row[other]) for other in Severity
    )
    assert re.search(pattern, section), f"README 7.8 no longer carries the {band.value} row"


def test_the_note_names_the_limit_that_makes_these_conditional() -> None:
    """These are frequencies on one set, not universal accuracies.

    P(true | predicted) moves with the prior, and a claims queue is not this
    evaluation set. The sentence saying so travels with the numbers.
    """
    assert "dağılım" in EVALUATION_NOTE_TR
    assert "319" in EVALUATION_NOTE_TR
