"""Folding several photographs of one vehicle into one claim-level answer."""

from __future__ import annotations

from uuid import uuid4

import pytest

from biovision.pipeline.photoset import (
    agreement_of,
    damage_types,
    summarise,
    worst_band,
)
from biovision.schemas.analyze import AnalyzeResponse, Finding, TimingMs
from biovision.schemas.enums import DamageType, Severity
from biovision.schemas.photoset import PhotoAgreement


def finding(damage: DamageType, severity: Severity = Severity.MINOR) -> Finding:
    return Finding(
        type=damage,
        score=0.8,
        bbox=(0, 0, 10, 10),
        area_ratio=0.01,
        severity=severity,
    )


def photo(
    *damages: DamageType,
    band: Severity | None = None,
) -> AnalyzeResponse:
    return AnalyzeResponse(
        request_id=uuid4(),
        domain="vehicle",
        domain_confidence=0.99,
        domain_confidence_calibrated=False,
        specialist_model="vehide-yolo-seg-v1",
        calibrated=False,
        overall_severity=band,
        findings=[finding(damage) for damage in damages],
        # `integrity` and `privacy` carry their own defaults; spelling them out
        # here would pin fields this module has no opinion about.
        timing_ms=TimingMs(total=1),
    )


# ---------------------------------------------------------------------------
# Severity is the worst view, not the average
# ---------------------------------------------------------------------------


def test_the_claim_is_as_severe_as_its_worst_photograph() -> None:
    """An average would mean the more photographs a careful claimant sends, the
    milder their claim looks. A wide establishing shot showing nothing must not
    dilute a close-up showing a torn panel."""
    photos = [
        photo(band=Severity.NONE),
        photo(DamageType.TORN, band=Severity.SEVERE),
        photo(band=Severity.MINOR),
    ]
    assert worst_band(photos) is Severity.SEVERE


def test_no_band_anywhere_is_null_rather_than_none_the_band() -> None:
    """`Severity.NONE` means 'the photograph shows no damage'. Absent means 'no
    photograph produced a band at all', and conflating them would turn a missing
    estimator into a clean bill of health."""
    assert worst_band([photo(), photo()]) is None


def test_the_band_order_comes_from_the_enum() -> None:
    """Restating it in the pipeline would be a second source of truth that could
    drift from the first."""
    assert worst_band([photo(band=Severity.NONE), photo(band=Severity.MINOR)]) is Severity.MINOR
    assert (
        worst_band([photo(band=Severity.MODERATE), photo(band=Severity.MINOR)])
        is Severity.MODERATE
    )


# ---------------------------------------------------------------------------
# Agreement is reported, not resolved
# ---------------------------------------------------------------------------


def test_every_photograph_finding_something_is_full_agreement() -> None:
    photos = [photo(DamageType.DENT), photo(DamageType.SCRATCH)]
    assert agreement_of(photos) is PhotoAgreement.ALL


def test_some_photographs_finding_nothing_is_reported_as_partial() -> None:
    """Measured at 23 of 250 claims. Not necessarily an error: one frame may
    honestly show an undamaged panel of a damaged car, and deciding which needs
    the vehicle's orientation, which this system does not have."""
    photos = [photo(DamageType.DENT), photo()]
    assert agreement_of(photos) is PhotoAgreement.PARTIAL


def test_no_photograph_finding_anything_is_its_own_answer() -> None:
    assert agreement_of([photo(), photo()]) is PhotoAgreement.NONE


# ---------------------------------------------------------------------------
# The union
# ---------------------------------------------------------------------------


def test_the_union_is_wider_than_any_single_photograph() -> None:
    """The measured effect: 2.04 types per claim against 1.57 from one."""
    photos = [photo(DamageType.DENT), photo(DamageType.SCRATCH, DamageType.TORN)]
    assert damage_types(photos) == [DamageType.DENT, DamageType.SCRATCH, DamageType.TORN]


def test_the_union_does_not_double_count_a_type_seen_twice() -> None:
    """Two photographs of one dent are one dent. The union is a wider view of the
    damage, not more damage."""
    photos = [photo(DamageType.DENT), photo(DamageType.DENT)]
    assert damage_types(photos) == [DamageType.DENT]


def test_upload_order_cannot_change_the_answer() -> None:
    """A client diffing two submissions of the same claim must not see a change
    that is only a reordering."""
    a = [photo(DamageType.TORN), photo(DamageType.DENT)]
    b = [photo(DamageType.DENT), photo(DamageType.TORN)]
    assert damage_types(a) == damage_types(b)


# ---------------------------------------------------------------------------
# The whole summary
# ---------------------------------------------------------------------------


def test_every_photograph_is_returned_in_full() -> None:
    """A summary that replaced them would hide which photograph a finding came
    from, and that is what an assessor needs to go and look."""
    photos = [photo(DamageType.DENT), photo(DamageType.SCRATCH)]
    result = summarise(photos)

    assert len(result.photos) == 2
    assert result.photos[0] is photos[0]


def test_the_summary_counts_what_it_claims_to_count() -> None:
    photos = [photo(DamageType.DENT, band=Severity.MODERATE), photo(band=Severity.NONE)]
    summary = summarise(photos).summary

    assert summary.photo_count == 2
    assert summary.photos_with_findings == 1
    assert summary.agreement is PhotoAgreement.PARTIAL
    assert summary.overall_severity is Severity.MODERATE


def test_a_claim_level_band_is_never_marked_calibrated() -> None:
    """Taking a maximum of uncalibrated bands does not calibrate them."""
    summary = summarise([photo(band=Severity.SEVERE)]).summary
    assert summary.overall_severity_calibrated is False


def test_an_empty_claim_is_refused_rather_than_summarised() -> None:
    with pytest.raises(ValueError, match="at least one photograph"):
        summarise([])
