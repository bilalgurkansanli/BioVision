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
    assert total == 248, "README 7.8 reports 248 held-out images"


def test_accuracy_matches_the_published_figure() -> None:
    correct = sum(CONFUSION[band][band] for band in Severity)
    assert round(correct / 248, 3) == 0.645, "README 7.8 reports 64.5% overall accuracy"


def test_severe_recall_matches_the_published_figure() -> None:
    """The row the README calls the worst one. Read across, not down."""
    row = CONFUSION[Severity.SEVERE]
    recall = row[Severity.SEVERE] / sum(row.values())
    assert round(recall, 2) == 0.51


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
    assert round(moderate.worse_share, 2) == 0.51


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
    section = text.split("### 7.8")[1].split("###")[0]
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
    assert "248" in EVALUATION_NOTE_TR
