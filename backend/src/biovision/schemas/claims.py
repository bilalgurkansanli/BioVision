"""The claim-outcome contract.

Every field here is either a **regulation** or **arithmetic over a regulation**.
There is no model output in this file and no estimate, which is why none of these
types carry a `calibrated` flag: there is nothing to calibrate. A rule is not
more or less accurate — it either cites its article or it does not belong here.

The one thing this schema deliberately lacks is a verdict. A claimant wants to
know whether their car will be written off; that needs the VAT-inclusive repair
cost, which nothing can produce from a photograph with published accuracy. So the
response carries the lines and says who is allowed to place a car against them.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Citation(BaseModel):
    """A statement and the instrument it comes from.

    Inseparable on purpose: a regulatory claim without its article looks
    authoritative and cannot be checked, which is worse than no claim.
    """

    model_config = ConfigDict(extra="forbid")

    text_tr: str
    source: str = Field(min_length=3)


class GapOut(BaseModel):
    """Something this system deliberately does not know.

    Distinct from `Citation` on purpose, and the distinction was found by the
    schema rejecting an em-dash as a source: a gap has no article to cite, it has
    a REASON. Forcing one into a Citation would have meant inventing a source for
    the absence of one.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    question_tr: str
    reason_tr: str


class ThresholdLineOut(BaseModel):
    """One write-off line, in lira, for the vehicle the caller described."""

    model_config = ConfigDict(extra="forbid")

    key: Literal["agir_hasar", "tam_hasar"]
    label_tr: str
    ratio: float = Field(gt=0.0, le=2.0)
    amount_try: Decimal = Field(gt=0)
    source: str
    basis_tr: str
    requires_expert_finding: bool = Field(
        description=(
            "True for tam hasar: exceeding the value is not sufficient, an expert "
            "must also find the vehicle beyond repair (m.4/1). The two conditions "
            "are cumulative."
        )
    )


class WriteOffLinesOut(BaseModel):
    """Where the lines fall — and nothing about which side the vehicle is on."""

    model_config = ConfigDict(extra="forbid")

    vehicle_value_try: Decimal = Field(gt=0)
    value_source: str = Field(
        description="Where the value came from — a TSB list revision, or the caller."
    )
    value_basis_tr: str
    value_basis_source: str
    lines: list[ThresholdLineOut] = Field(min_length=2)
    corrections: list[Citation] = Field(
        description=(
            "Widely repeated figures the regulation does not contain, carried with "
            "their correction. The 70% write-off threshold is the notable one."
        )
    )
    determined_by_tr: str
    determined_by_source: str

    @model_validator(mode="after")
    def _no_verdict_may_be_added(self) -> Self:
        """Guards the shape rather than a value.

        `extra="forbid"` already rejects an unknown field, but the intent is
        worth stating where a future reader will meet it: this type must never
        gain `verdict`, `probability` or `will_be_written_off`. The determination
        belongs exclusively to a registered eksper.
        """
        return self


class PositionOut(BaseModel):
    """Which side of the lines a KNOWN repair cost falls on.

    Reachable only when the caller supplies an expert's figure. At that point it
    is a division rather than a prediction — which is precisely why the product
    offers it as a second step instead of guessing the numerator in the first.
    """

    model_config = ConfigDict(extra="forbid")

    repair_cost_try: Decimal = Field(ge=0)
    ratio_of_value: float = Field(ge=0.0)
    crossed: list[str]
    below: list[str]
    #: Supplied by the caller, never derived here.
    cost_is_user_supplied: Literal[True] = True


class PremiumImpactOut(BaseModel):
    """What one claim payment does to a trafik sigortası step."""

    model_config = ConfigDict(extra="forbid")

    from_step: int = Field(ge=0, le=8)
    to_step: int = Field(ge=0, le=8)
    relative_increase: float = Field(
        description=(
            "to/from minus 1 on the Ek-2 multipliers. A ratio, because the "
            "base premium is unknown."
        )
    )
    recovery_years: int = Field(
        ge=0,
        description=(
            "Clean years needed to return. Five from the top step, not one: "
            "Geçici m.11(14) requires five clean years at 7 before 8 is granted."
        ),
    )
    is_ceiling: Literal[True] = Field(
        default=True,
        description=(
            "Always true. Ek-2 caps what an insurer may charge; the yönetmelik's "
            "own Madde 5 table is printed blank with 'şirketlerce serbestçe "
            "belirlenecektir'. This is a worst case, never a quote."
        ),
    )
    source: str


class CriticalPartOut(BaseModel):
    """One Ek-1 structural part, and whether a photograph could show it."""

    model_config = ConfigDict(extra="forbid")

    index: int
    name_tr: str
    visible_in_photo: bool
    ask_user: bool = False
    question_tr: str | None = None


class RegulationOut(BaseModel):
    """The rule sheet, rendered for a client.

    Served whole rather than piecemeal so a reader can see the gaps beside the
    rules. `unverified` is part of the payload, not an omission.
    """

    model_config = ConfigDict(extra="forbid")

    version: int
    jurisdiction: str
    verified_on: str
    thresholds: list[ThresholdLineOut] | None = Field(
        default=None,
        description="Present only when a vehicle value was supplied; ratios alone otherwise.",
    )
    critical_parts: list[CriticalPartOut]
    critical_parts_source: str
    critical_parts_discretionary: bool
    critical_parts_note_tr: str
    consequences: list[Citation]
    corrections: list[Citation]
    #: Named gaps travel with the rules. A reader can then see the shape of what
    #: is missing instead of assuming it was covered.
    gaps: list[GapOut]
    kasko_nationally_regulated: Literal[False] = Field(
        default=False,
        description=(
            "Always false. Kasko GŞ C.11 makes the no-claims ladder an özel şart, "
            "so no national table exists. Any kasko figure must come from the "
            "caller's own policy."
        ),
    )
    kasko_note_tr: str
    kasko_source: str


class VehicleTypeOut(BaseModel):
    """One selectable trim from the TSB list."""

    model_config = ConfigDict(extra="forbid")

    brand_code: int
    type_code: int
    brand_name: str
    type_name: str


class ValuationOut(BaseModel):
    """A value read from the TSB list, with what it does not account for.

    The caveat travels with the figure rather than living in the UI, because a
    number that leaves this response without it is a number someone will screenshot.
    """

    model_config = ConfigDict(extra="forbid")

    vehicle: VehicleTypeOut
    model_year: int
    amount_try: Decimal = Field(gt=0)
    source_label: str
    source_url: str
    revision: str
    fetched_at: str
    caveat_tr: str
    #: False always: these are list averages, not a valuation of this vehicle.
    is_individual_appraisal: Literal[False] = False


class ValueListMetaOut(BaseModel):
    """What the mirrored list covers, so a client can say why a car is absent."""

    model_config = ConfigDict(extra="forbid")

    available: bool
    revision: str | None = None
    month_label: str | None = None
    oldest_model_year: int | None = None
    newest_model_year: int | None = None
    fetched_at: str | None = None
    caveat_tr: str | None = None
    #: Present when the list could not be loaded, so the UI can explain rather
    #: than silently offering a free-text box.
    unavailable_reason_tr: str | None = None
