"""Folding several photographs of one vehicle into one claim-level answer.

Pure functions over responses the pipeline already produced, so the whole of this
is testable without a model and the route stays thin.

Two judgements are made here and both are stated rather than buried:

* **Severity is the maximum, not the mean.** A claim is as severe as its worst
  view. A wide establishing shot that shows nothing must not dilute a close-up
  showing a torn panel, and an average would do exactly that -- the more
  photographs a careful claimant sends, the milder their claim would look.
* **Disagreement is reported, not resolved.** Where some photographs find damage
  and others do not, that is said plainly. It is measured at 9% of claims, and it
  is *not* necessarily an error: one frame may honestly show an undamaged panel
  of a damaged car. Deciding which is which needs the vehicle's orientation,
  which this system does not have -- the same limit that keeps `damage_position`
  from saying "left front".
"""

from __future__ import annotations

from biovision.schemas.analyze import AnalyzeResponse
from biovision.schemas.enums import DamageType, Severity
from biovision.schemas.photoset import ClaimResponse, ClaimSummary, PhotoAgreement

#: Worst last. `Severity` is declared none < minor < moderate < severe, so this
#: is the enum's own order -- restating it here would be a second source of truth
#: that could drift from the first.
_ORDER = list(Severity)


def worst_band(photos: list[AnalyzeResponse]) -> Severity | None:
    """The most serious band any photograph reported, or None if none did."""
    bands = [photo.overall_severity for photo in photos if photo.overall_severity is not None]
    if not bands:
        return None
    return max(bands, key=_ORDER.index)


def agreement_of(photos: list[AnalyzeResponse]) -> PhotoAgreement:
    """Did the photographs tell the same story?"""
    with_findings = sum(1 for photo in photos if photo.findings)
    if with_findings == 0:
        return PhotoAgreement.NONE
    if with_findings == len(photos):
        return PhotoAgreement.ALL
    return PhotoAgreement.PARTIAL


def damage_types(photos: list[AnalyzeResponse]) -> list[DamageType]:
    """The union across photographs, in the enum's fixed order.

    Sorted by the enum rather than by first appearance: the same claim uploaded
    in a different order must produce the same list, or a client diffing two
    submissions would see a change that is not one.
    """
    found = {finding.type for photo in photos for finding in photo.findings}
    return [damage for damage in DamageType if damage in found]


def summarise(photos: list[AnalyzeResponse]) -> ClaimResponse:
    """One claim-level answer, with every per-photograph result kept intact."""
    if not photos:
        raise ValueError("a claim needs at least one photograph")

    return ClaimResponse(
        summary=ClaimSummary(
            photo_count=len(photos),
            photos_with_findings=sum(1 for photo in photos if photo.findings),
            agreement=agreement_of(photos),
            damage_types=damage_types(photos),
            overall_severity=worst_band(photos),
        ),
        photos=photos,
    )
