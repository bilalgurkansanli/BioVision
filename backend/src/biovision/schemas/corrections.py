"""What a user says the model got wrong.

`docs/OPEN_QUESTIONS.md` has given the same answer since the first evaluation set
was built: what this project lacks is not code, it is **photographs from a real
intake**. §7.1 says `phone_screen` scores 100% from one source in one
photographic style. §7.7 says the whole published evaluation was measured on
close-ups, because VehiDE is close-ups, so it cannot see the failure that matters
most. §7.7 again says the part-based comparison cannot be settled without
whole-vehicle photographs carrying damage annotations.

Those are one missing thing, and the product has been throwing away the only
source of it. The user is looking at the photograph and at the findings drawn on
it, and knows which ones are wrong.

**Nothing here retrains anything.** These are rows in an evaluation set being
assembled by hand. The moment a correction closes a loop automatically, the
system starts learning from whatever somebody was willing to click, and every
number in the README was measured against data a person looked at first.

**A correction never edits the analysis.** `analyses` has no UPDATE policy
because it records what a model said at a point in time; that reasoning does not
weaken because the edit would come from a user. The correction sits beside it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from biovision.schemas.enums import CorrectionKind, DamageType, Severity

#: Kinds that are a statement about ONE finding, and therefore have to name it.
#: The database carries the same rule as a check constraint; this is the copy
#: that produces a 422 with a sentence rather than a 500 from PostgREST.
FINDING_KINDS = frozenset(
    {
        CorrectionKind.WRONG_FINDING,
        CorrectionKind.WRONG_TYPE,
        CorrectionKind.WRONG_SEVERITY,
    }
)


class CorrectionRequest(BaseModel):
    """One disagreement with one analysis."""

    model_config = ConfigDict(extra="forbid")

    kind: CorrectionKind
    finding_index: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Which finding, by its position in `findings`. Required for the kinds "
            "that are about one finding, and rejected for the kinds that are "
            "about the list as a whole -- `finding_index: 0` on `missed_damage` "
            "would read as 'finding 0 is missing', which is not a sentence "
            "anybody meant."
        ),
    )
    expected_type: DamageType | None = Field(
        default=None,
        description=(
            "What the damage actually is. Required for `wrong_type`, where saying "
            "the class is wrong without saying the right one records a complaint "
            "rather than a label. Optional for `missed_damage`: a user who can "
            "see damage the model missed is still worth hearing from when they "
            "cannot name it."
        ),
    )
    expected_severity: Severity | None = Field(
        default=None,
        description="The band it should have carried. Required for `wrong_severity`.",
    )
    note: str | None = Field(
        default=None,
        max_length=1000,
        description="Free text. Never parsed; read by a person building an evaluation set.",
    )
    retain_image: bool = Field(
        default=False,
        description=(
            "Explicit consent to keep the photograph past the retention window "
            "so the correction stays attached to something. Defaults to false: a "
            "correction must not quietly become a consent form. Deleting the "
            "analysis withdraws it and removes the correction with it."
        ),
    )

    @model_validator(mode="after")
    def _the_kind_decides_what_else_is_required(self) -> Self:
        names_a_finding = self.kind in FINDING_KINDS
        if names_a_finding and self.finding_index is None:
            raise ValueError(f"'{self.kind.value}' is about one finding and must name its index")
        if not names_a_finding and self.finding_index is not None:
            raise ValueError(
                f"'{self.kind.value}' is about the whole result, so it cannot name a finding"
            )
        if self.kind is CorrectionKind.WRONG_TYPE and self.expected_type is None:
            raise ValueError("'wrong_type' must say which type it should have been")
        if self.kind is CorrectionKind.WRONG_SEVERITY and self.expected_severity is None:
            raise ValueError("'wrong_severity' must say which band it should have been")
        return self


class CorrectionOut(BaseModel):
    """A stored correction, as it is read back."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    analysis_id: UUID
    created_at: datetime
    kind: CorrectionKind
    finding_index: int | None = None
    expected_type: DamageType | None = None
    expected_severity: Severity | None = None
    note: str | None = None
    retain_image: bool = False


class CorrectionAccepted(BaseModel):
    """The answer to filing one.

    `image_retained` echoes what was actually agreed to rather than what was
    asked for: a correction filed against an analysis whose image was never
    stored -- the anonymous path, or a Supabase-less deployment -- cannot retain
    anything, and reporting `true` there would be a consent receipt for something
    that did not happen.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    stored: bool = Field(
        description=(
            "False when no storage backend is configured. The API still accepts "
            "the correction rather than failing the user's click, and says here "
            "that nothing was written."
        )
    )
    image_retained: bool = Field(
        description="Whether the photograph will be kept past the ordinary window."
    )
    retention_days: int = Field(description="The window that now applies to this analysis.")
