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

from biovision.schemas.analyze import SeverityReliabilityOut
from biovision.schemas.enums import Severity


class Citation(BaseModel):
    """A statement and the instrument it comes from.

    Inseparable on purpose: a regulatory claim without its article looks
    authoritative and cannot be checked, which is worse than no claim.
    """

    model_config = ConfigDict(extra="forbid")

    text_tr: str
    source: str = Field(min_length=3)


class ConsequenceOut(BaseModel):
    """Something that follows from a determination, and whether it can be undone.

    `irreversible` is the field that earns this type its existence. Crossing 60%
    produces six consequences, five of them procedural — and putting all six
    under the figure buried the one that matters, which is that the registration
    record ends the değer kaybı claim outright. The flag lets a client keep the
    permanent ones in front of the reader and the rest behind a disclosure.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    text_tr: str
    source: str = Field(min_length=3)
    irreversible: bool = False
    line_specific: bool = Field(
        default=False,
        description=(
            "True where this consequence IS the meaning of the line it hangs "
            "under — what happens to the vehicle's registration — rather than "
            "something shared with the other line. Line-specific and irreversible "
            "entries stay in front of the reader; the rest go behind a click."
        ),
    )


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
            "are cumulative. False for ağır hasar, which m.5(1) states as a bare "
            "60% threshold — the two rules are NOT parallel, and modelling them "
            "as though they were gives wrong answers at the boundary."
        )
    )
    consequences: list[ConsequenceOut] = Field(
        default_factory=list,
        description=(
            "What crossing THIS line does, beyond the payment. Attached per line "
            "because the most important one is not about money: at 60% the "
            "vehicle takes a 'trafikten çekilmiştir' record, and that record "
            "permanently forecloses değer kaybı. A response that reported only "
            "the lira figure would omit the irreversible part."
        ),
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
    value_reference_default_tr: str = Field(
        description=(
            "What this product has to say about its OWN denominator. Genelge "
            "2017/14 m.2 makes the eksper raporu's rayiç the reference wherever "
            "the policy names none — the TSB list this value came from is a "
            "sector service, not the regulatory default. Required rather than "
            "optional so the figure cannot travel without the sentence that "
            "bounds it."
        )
    )
    value_reference_default_source: str
    lines: list[ThresholdLineOut] = Field(min_length=2)
    corrections: list[Citation] = Field(
        description=(
            "Widely repeated figures the regulation does not contain, carried with "
            "their correction. The 70% write-off threshold is the notable one."
        )
    )
    below_threshold_tr: list[ConsequenceOut] = Field(
        default_factory=list,
        description=(
            "What holds while the vehicle stays UNDER both lines. Served beside "
            "the thresholds rather than only above them, because the protections "
            "on this side — the insurer cannot make you surrender the car, and "
            "the değer kaybı claim survives — are the ones a claimant does not "
            "know they have."
        ),
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


class AssessmentRequest(BaseModel):
    """What the caller knows, so the response can say what follows from it.

    Every field is optional and every one of them unlocks something specific. A
    request with nothing in it still returns the rule sheet and the list of
    questions; each answer supplied closes one more figure. That shape is
    deliberate — the alternative is a form that refuses to produce anything until
    a claimant has found their policy, which is not the state someone is in an
    hour after a crash.

    **None of these can be read off the photograph**, and none is guessed. The
    trim decides the value (27,906 rows separated by engine and gearbox), the
    muafiyet and the kademe are printed on a policy, and the salvage choice is a
    decision the claimant has not made yet.
    """

    model_config = ConfigDict(extra="forbid")

    vehicle_value_try: Decimal | None = Field(
        default=None, gt=0, description="Value on the incident date. Overrides the TSB lookup."
    )
    model_year: int | None = Field(default=None, ge=1900, le=2100)
    brand_code: int | None = None
    type_code: int | None = None

    overall_severity: Severity | None = Field(
        default=None,
        description=(
            "The band `/v1/analyze` returned for the photograph. Carried in so the "
            "measured frequency behind it travels with the money figures instead "
            "of sitting on a different screen."
        ),
    )

    deductible_try: Decimal | None = Field(
        default=None, ge=0, description="Muafiyet from the policy. Null means not stated."
    )
    salvage_retained: bool = Field(
        default=False,
        description=(
            "Whether the claimant keeps the wreck at total loss. The two choices "
            "produce different payments and the system does not pick one."
        ),
    )

    traffic_step: int | None = Field(default=None, ge=0, le=8)
    traffic_injury: bool = False

    kasko_kademe: int | None = Field(default=None, ge=0)
    kasko_current_discount: float | None = Field(default=None, ge=0.0, lt=1.0)
    kasko_claims_this_period: int = Field(default=1, ge=0)

    @model_validator(mode="after")
    def _a_trim_needs_all_three_parts(self) -> Self:
        parts = (self.model_year, self.brand_code, self.type_code)
        if any(part is not None for part in parts) and any(part is None for part in parts):
            raise ValueError(
                "model_year, brand_code and type_code identify one trim and must be "
                "supplied together; two of the three name a different car"
            )
        return self


class PayoutScenarioOut(BaseModel):
    """One branch a claim can take, closed as far as the facts allow.

    A scenario carries **either** an exact amount **or** an interval, never both.
    A point estimate printed beside a range gets read as the answer and the range
    as decoration, which is the failure this whole schema is arranged against.
    """

    model_config = ConfigDict(extra="forbid")

    key: Literal["tam_hasar", "onarim"]
    label_tr: str
    amount_try: Decimal | None = Field(
        default=None,
        ge=0,
        description="Exact, where every input was supplied. Null where it was not.",
    )
    lower_try: Decimal | None = Field(default=None, ge=0)
    upper_try: Decimal | None = Field(default=None, ge=0)
    basis_tr: str
    source: str
    missing_tr: list[str] = Field(
        description=(
            "What would close this figure. Every entry is something a person or a "
            "document supplies — never something the system chose not to compute."
        )
    )
    #: False always. Nothing here is a model output; the whole scenario is a
    #: subtraction from a listed value.
    is_estimate: Literal[False] = False

    @model_validator(mode="after")
    def _a_point_or_a_range_but_not_both(self) -> Self:
        if self.amount_try is not None and (
            self.lower_try is not None or self.upper_try is not None
        ):
            raise ValueError(
                "a scenario carries an exact amount or an interval, never both: "
                "a point printed beside a range is read as the answer"
            )
        if self.amount_try is None and self.upper_try is None:
            raise ValueError("a scenario with no amount must at least carry an upper bound")
        if (
            self.lower_try is not None
            and self.upper_try is not None
            and self.lower_try > self.upper_try
        ):
            raise ValueError(f"lower {self.lower_try} exceeds upper {self.upper_try}")
        if self.amount_try is None and not self.missing_tr:
            raise ValueError(
                "an open figure must name what is missing, or the reader cannot tell "
                "whether the system failed or the question is genuinely open"
            )
        return self


class KaskoImpactOut(BaseModel):
    """What one paid claim does to a kasko premium.

    Structurally distinct from `PremiumImpactOut` even though the two look alike
    on screen, because their standing is not alike. The trafik figure is a
    national table with an article number. This one is arithmetic over the
    claimant's own policy, or — failing that — over one insurer's published
    clause, and `nationally_regulated: false` is a required literal so no client
    can render them as peers.
    """

    model_config = ConfigDict(extra="forbid")

    from_discount: float = Field(ge=0.0, lt=1.0)
    to_discount: float = Field(ge=0.0, lt=1.0)
    relative_increase: float = Field(
        description="(1 − new) / (1 − old) − 1, over the claimant's own base premium."
    )
    basis_tr: str
    source: str
    nationally_regulated: Literal[False] = Field(
        default=False,
        description=(
            "Always false. Kasko GŞ C.11 makes the no-claims ladder an özel şart. "
            "Any kasko number here is either the caller's own or one named "
            "insurer's, and `sample_size` says which."
        ),
    )
    insurer: str | None = None
    sample_size: int | None = Field(
        default=None,
        description=(
            "How many insurers' clauses stand behind this. 1 means it is an "
            "illustration, not a market rule."
        ),
    )
    from_kademe: int | None = None
    to_kademe: int | None = None
    disclaimer_tr: str | None = None


class TrafficLimitOut(BaseModel):
    """The ceiling on what the OTHER party's compulsory policy can pay.

    The most under-appreciated figure in a Turkish motor claim. Trafik sigortası
    is a liability policy with a per-vehicle property cap — 400,000 TL in 2026 —
    and a claimant whose car is worth four times that will be told the other
    driver was at fault and then discover the compulsory policy stops well short.
    `shortfall_try` states that gap in lira rather than leaving them to compute it.

    Değer kaybı comes out of the same limit, which is why the note says so: a
    claimant who wins both is not adding two pots together.
    """

    model_config = ConfigDict(extra="forbid")

    property_per_vehicle_try: Decimal = Field(gt=0)
    property_per_accident_try: Decimal = Field(gt=0)
    in_force_from: str
    source: str
    official_gazette: str
    applies_on_tr: str = Field(
        description="Which year's limit governs — the accident's, not the policy's."
    )
    note_tr: str
    shortfall_try: Decimal | None = Field(
        default=None,
        ge=0,
        description=(
            "Vehicle value minus the per-vehicle limit, where the value is known "
            "and exceeds it. Null when the limit covers the vehicle, or when no "
            "value was supplied. A subtraction, not a prediction — it assumes "
            "nothing about fault."
        ),
    )


class OpenQuestionOut(BaseModel):
    """One answer the claimant could supply that would sharpen a figure.

    The product's most useful output when it cannot compute something: not "we
    don't know", but "here is the single fact that would let us know, and here is
    which number it unlocks".
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    question_tr: str
    unlocks_tr: str
    #: True where the answer is on a document rather than in the photograph.
    from_document: bool = True


class AssessmentOut(BaseModel):
    """Everything the claim side can say about one photographed vehicle.

    Assembled in one response rather than left to a client to stitch together,
    because the *relationships* between these figures are the product. A payout
    scenario is meaningless without the value it subtracts from; a severity band
    is misleading without the frequency behind it; a premium ratio invites the
    wrong comparison unless the two premium blocks arrive labelled with their
    different standing.

    What is deliberately absent: a verdict, a probability of write-off, and a
    repair cost. The first belongs to a registered eksper, the third has no
    published method measured against real invoices, and the second is the
    product of the two.
    """

    model_config = ConfigDict(extra="forbid")

    valuation: ValuationOut | None = None
    value_source: str
    write_off: WriteOffLinesOut | None = None
    payout: list[PayoutScenarioOut] = Field(default_factory=list)
    severity_reliability: SeverityReliabilityOut | None = Field(
        default=None,
        description=(
            "The measured frequency behind the band the photograph produced. The "
            "closest thing to a probability in this response, and a count rather "
            "than a model output."
        ),
    )
    procedure: list[ConsequenceOut] = Field(
        default_factory=list,
        description=(
            "How the claim runs whichever side of the lines it lands on: payment "
            "deadlines, and where an ihbar may be filed. Separated from the "
            "threshold consequences because attaching them to a line implied "
            "they followed from crossing it, and buried the one that did."
        ),
    )
    traffic_limit: TrafficLimitOut | None = None
    traffic_premium: PremiumImpactOut | None = None
    kasko_premium: KaskoImpactOut | None = None
    critical_part_questions: list[CriticalPartOut] = Field(
        default_factory=list,
        description=(
            "Ek-1 parts a photograph cannot show. Eight of the eleven sit behind "
            "panels; asking is the only route to them."
        ),
    )
    open_questions: list[OpenQuestionOut] = Field(default_factory=list)
    gaps: list[GapOut] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_verdict_may_be_added(self) -> Self:
        """The same guard `WriteOffLinesOut` carries, restated at the top level.

        `extra="forbid"` enforces it; this states the intent where the next
        person to extend this type will read it. No `verdict`, no
        `write_off_probability`, no `estimated_repair_cost`. Assembling the
        pieces into one response makes adding a conclusion feel natural, which is
        exactly why the prohibition is repeated here.
        """
        return self


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
