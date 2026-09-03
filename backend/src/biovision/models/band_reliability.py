"""What the overall-severity band turned out to mean, measured.

**This is the only probability this system publishes, and it is measured rather
than modelled.** A claimant asks "how likely is it that my car is badly damaged".
The zero-shot band answers with a word. This module answers with the frequency
that word was right, taken from the confusion matrix in README section 7.8 --
319 images, the same table, read down its columns instead of across its rows.

Reading it down the columns is the whole point. A row says *of the truly severe
photographs, how many did we catch* (recall, 51%), which is the developer's
question. A column says *of the photographs we called severe, how many were*
(81%), which is the reader's. Only the second one can be put next to a result,
because at the moment a user sees a band, the band is what they have.

The column that matters most is `moderate`. Of 76 photographs the system called
moderate, **37 were severe and 34 were moderate** -- the modal truth behind
"orta" is "ağır". A product that printed "orta hasar" and stopped would be
misleading in the most expensive direction, and nothing in the model can fix
that; only saying it can.

**The `none` column is the newest and the one worth checking hardest**, because
telling a claimant their wrecked car looks undamaged would be the worst error
this system could make. It has not happened: of 62 photographs called `none`,
**not one was truly severe**. 52 were genuinely undamaged, 7 were moderate and 3
minor -- so the band errs toward under-calling light damage, never toward
missing a wreck.

**What this is conditional on, and it matters.** These are frequencies on one
evaluation set, whose mix is not the mix a claims queue sees -- and it is now two
sets bolted together, 248 damaged cars from Kaggle and 71 intact ones from
Commons, so the *ratio* of damaged to undamaged in it is an artefact of how it
was built rather than a fact about claimants. P(true | predicted) moves with the
prior. So these are the measured numbers for a stated set, not universal
accuracies, and `evaluation_note_tr` carries that sentence into every response
that shows them.
"""

from __future__ import annotations

from dataclasses import dataclass

from biovision.schemas.analyze import BandOutcomeOut, SeverityReliabilityOut
from biovision.schemas.enums import Severity

#: The confusion matrix from README 7.8, verbatim: rows are the TRUE band, columns
#: the predicted one. A unit test asserts these cells still sum to the published
#: 319 images and 65.5% accuracy, so the table and this dict cannot drift apart.
CONFUSION: dict[Severity, dict[Severity, int]] = {
    Severity.NONE: {
        Severity.NONE: 52,
        Severity.MINOR: 13,
        Severity.MODERATE: 3,
        Severity.SEVERE: 3,
    },
    Severity.MINOR: {
        Severity.NONE: 3,
        Severity.MINOR: 77,
        Severity.MODERATE: 2,
        Severity.SEVERE: 0,
    },
    Severity.MODERATE: {
        Severity.NONE: 7,
        Severity.MINOR: 26,
        Severity.MODERATE: 34,
        Severity.SEVERE: 8,
    },
    Severity.SEVERE: {
        Severity.NONE: 0,
        Severity.MINOR: 8,
        Severity.MODERATE: 37,
        Severity.SEVERE: 46,
    },
}

EVALUATION_SET = (
    "prajwalbhamere/car-damage-severity-dataset (248 damaged) + 71 intact "
    "vehicles from Wikimedia Commons = 319 images"
)

EVALUATION_NOTE_TR = (
    "Bu oranlar 319 görselden ölçüldü: 248 hasarlı araç ve 71 sağlam araç. Bir "
    "olasılık modelinden değil, sayımdan geliyorlar. Ölçüm setindeki dağılım "
    "gerçek bir hasar kuyruğunun dağılımı değildir; dağılım değişirse bu oranlar "
    "da değişir."
)


@dataclass(frozen=True)
class BandOutcome:
    """One possible truth behind a predicted band, and how often it occurred."""

    band: Severity
    count: int
    share: float


@dataclass(frozen=True)
class BandReliability:
    """The measured distribution of truths behind one predicted band."""

    predicted: Severity
    support: int
    outcomes: tuple[BandOutcome, ...]

    @property
    def correct_share(self) -> float:
        """How often this band was the true one. Precision, from the reader's side."""
        for outcome in self.outcomes:
            if outcome.band is self.predicted:
                return outcome.share
        return 0.0

    @property
    def worse_share(self) -> float:
        """How often the truth was WORSE than this band.

        Reported separately because the errors are not symmetric: the estimator
        under-calls, so the probability that a reader is being told something
        milder than reality is the one with a cost attached.
        """
        order = list(Severity)
        position = order.index(self.predicted)
        return round(
            sum(outcome.share for outcome in self.outcomes if order.index(outcome.band) > position),
            4,
        )


def _column(predicted: Severity) -> BandReliability:
    counts = {true: CONFUSION[true][predicted] for true in Severity}
    support = sum(counts.values())
    return BandReliability(
        predicted=predicted,
        support=support,
        outcomes=tuple(
            BandOutcome(
                band=true,
                count=count,
                share=round(count / support, 4) if support else 0.0,
            )
            for true, count in counts.items()
        ),
    )


#: Precomputed: four columns, no arithmetic at request time.
BAND_RELIABILITY: dict[Severity, BandReliability] = {band: _column(band) for band in Severity}


def reliability_for(band: Severity | None) -> BandReliability | None:
    """The measured column for a predicted band, or None when nothing was predicted."""
    return BAND_RELIABILITY.get(band) if band is not None else None


def reliability_out(band: Severity | None) -> SeverityReliabilityOut | None:
    """The response form of the same column.

    Lives here rather than in whichever route needs it, because two of them do --
    `/v1/analyze` attaches it to the band, and `/v1/claims/assessment` carries it
    beside the money. Two conversions would be two chances for the numbers on the
    two screens to disagree.
    """
    measured = reliability_for(band)
    if measured is None:
        return None
    return SeverityReliabilityOut(
        predicted=measured.predicted,
        support=measured.support,
        outcomes=[
            BandOutcomeOut(band=outcome.band, count=outcome.count, share=outcome.share)
            for outcome in measured.outcomes
        ],
        correct_share=measured.correct_share,
        worse_share=measured.worse_share,
        evaluation_set=EVALUATION_SET,
        evaluation_note_tr=EVALUATION_NOTE_TR,
    )
