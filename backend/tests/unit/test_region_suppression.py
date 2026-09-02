"""When every signal says the car is fine, the area must stop arguing.

A user uploaded a showroom photograph of an intact Audi. The specialist listed
nothing, correctly. The response still carried "2% of the vehicle is damaged",
built from a single detection the system had itself judged too weak to name.

The region floor sits below the finding floor on purpose -- it catches damage the
list misses, measured in README 7.9 -- but it also fires on **60% of intact
cars**. On its own it is not evidence. These tests pin the narrow rule that
resolves that, and, more importantly, pin how narrow it is: the region must
survive every case where it is the thing doing useful work.
"""

from __future__ import annotations

import pytest

from biovision.models.base import DamageRegion
from biovision.pipeline.orchestrator import _region_unless_nothing_is_wrong
from biovision.schemas.analyze import Finding
from biovision.schemas.enums import DamageType, Severity

REGION = DamageRegion(
    area_ratio_image=0.02,
    area_ratio_vehicle=0.02,
    vehicle_frame_share=0.25,
    instances=1,
    confidence_floor=0.10,
)

FINDING = Finding(
    type=DamageType.DENT,
    score=0.42,
    bbox=(10, 10, 60, 60),
    area_ratio=0.01,
    severity=Severity.MODERATE,
)


def test_the_region_is_dropped_when_the_band_and_the_list_both_say_nothing() -> None:
    """The reported defect. Two stronger signals against one weaker one."""
    assert _region_unless_nothing_is_wrong(REGION, Severity.NONE, []) is None


@pytest.mark.parametrize("band", [Severity.MINOR, Severity.MODERATE, Severity.SEVERE])
def test_an_empty_finding_list_alone_never_drops_the_region(band: Severity) -> None:
    """The wide-shot case, which is the entire reason the region exists.

    A written-off car photographed from twenty metres can produce no finding
    above 0.20 while the band correctly reads `severe`. Dropping the area there
    would delete the only measurement that survived, and would be a far worse
    bug than the one this rule fixes.
    """
    assert _region_unless_nothing_is_wrong(REGION, band, []) is REGION


def test_a_none_band_with_findings_keeps_the_region() -> None:
    """The band is 84% right, not certain.

    If the specialist named damage confidently enough to list it, the band being
    wrong is likelier than three layers being wrong together.
    """
    assert _region_unless_nothing_is_wrong(REGION, Severity.NONE, [FINDING]) is REGION


def test_a_missing_band_leaves_the_region_alone() -> None:
    """`None` here means the estimator did not run -- the mock backend, say.

    Silence is not agreement, and treating "nothing was asked" the same as
    "the answer was undamaged" would suppress on a request that made no
    judgement at all.
    """
    assert _region_unless_nothing_is_wrong(REGION, None, []) is REGION


def test_no_region_stays_no_region() -> None:
    assert _region_unless_nothing_is_wrong(None, Severity.NONE, []) is None
    assert _region_unless_nothing_is_wrong(None, Severity.SEVERE, []) is None
