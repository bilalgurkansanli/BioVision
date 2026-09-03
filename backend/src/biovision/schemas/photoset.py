"""A claim is several photographs of one car, and the answer is not per photograph.

**Why this exists, measured rather than assumed.** VehiDE's filenames carry an
upload timestamp, and 885 of its groups hold more than one photograph of the same
vehicle -- verified by eye on a contact sheet before any of this was written.
Over 250 such claims, running the specialist on every photograph and taking the
union surfaced **2.04 damage types against 1.57 from any single one**, a 30% gain
that grows with the number of photographs (+0.43 at two, +0.64 at three).

That is the same effect two other results already pointed at: this project's
mirror-view TTA (README 7.9), where the same weights shown a flipped copy find
damage the original missed, and Esparza et al., who took building-damage accuracy
from 0.65 on one frontal photograph to 0.90-0.96 on two or three.

**The gain is an upper bound and the schema says so.** These views are of
different parts at different zooms, so a claim showing a wheel arch in one frame
and a headlight in another unions to more types without any single photograph
having been wrong. What the union is definitely not is a bigger claim: finding
two types instead of one does not mean twice the damage.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from biovision.schemas.analyze import AnalyzeResponse
from biovision.schemas.enums import DamageType, Severity


class PhotoAgreement(StrEnum):
    """Whether the photographs of one claim told the same story.

    **A confidence signal the model cannot produce about itself.** A detector's
    score says how sure it is about one box; the severity band is 64.5% accurate
    and uncalibrated. Neither can say whether a second look agreed, and over 250
    measured claims the photographs disagreed in 23 of them -- 9%, which is
    frequent enough to be worth a word.
    """

    #: Every photograph found damage. 224 of 250 claims measured.
    ALL = "all"
    #: Some found damage and some did not. 23 of 250. **Not necessarily a
    #: contradiction**: one frame may show an undamaged panel of a damaged car.
    PARTIAL = "partial"
    #: No photograph found anything. 3 of 250.
    NONE = "none"


class ClaimSummary(BaseModel):
    """What the photographs say together, as distinct from one at a time."""

    model_config = ConfigDict(extra="forbid")

    photo_count: int = Field(ge=1)
    photos_with_findings: int = Field(ge=0)
    agreement: PhotoAgreement
    damage_types: list[DamageType] = Field(
        description=(
            "The union across every photograph. Measured at 2.04 types per claim "
            "against 1.57 from a single photograph. It is a wider VIEW of the "
            "damage, not more damage -- two types instead of one is not twice the "
            "loss."
        )
    )
    overall_severity: Severity | None = Field(
        default=None,
        description=(
            "The WORST band across the photographs, not the average. A claim is "
            "as severe as its worst view: a wide shot that shows nothing does not "
            "dilute a close-up that shows a torn panel. Null when no photograph "
            "produced a band."
        ),
    )
    overall_severity_calibrated: bool = Field(
        default=False,
        description="Always false. Taking a maximum of uncalibrated bands does not calibrate them.",
    )


class ClaimResponse(BaseModel):
    """Per-photograph results, and what they say together.

    The per-photograph responses are returned in full and unchanged. A claim
    summary that replaced them would hide which photograph a finding came from,
    and "the boot is dented" is worth less to an assessor than "the boot is
    dented, in the third photograph, here".
    """

    model_config = ConfigDict(extra="forbid")

    summary: ClaimSummary
    photos: list[AnalyzeResponse]
