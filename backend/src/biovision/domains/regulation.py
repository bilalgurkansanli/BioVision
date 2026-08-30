"""Loading `regulation.yaml`.

Kept separate from the domain catalogue, the gate and the severity prompts for
the reason those are separate from each other: they change for different reasons
and on different clocks. Domains follow the product; prompts follow what people
upload; this file follows the Resmî Gazete.

**Every field is a citation-carrying fact, and the loader enforces that.** A
threshold without a `source` fails to construct, because a regulatory figure
whose article nobody can look up is exactly as useful as an invented one -- and
much more dangerous, since it looks authoritative.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from biovision.domains.catalog import DomainCatalogError


class Cited(BaseModel):
    """Base for anything that must name where it came from."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(
        min_length=3,
        description="Instrument and article, e.g. Genelge 2025/12 m.5(1)",
    )


class Threshold(Cited):
    """One write-off line, as a ratio of repair cost to vehicle value."""

    key: str
    label_tr: str
    ratio: float = Field(gt=0.0, le=2.0)
    basis_tr: str
    in_force_from: str
    #: Total loss needs an expert finding as well as the ratio -- the two are
    #: cumulative in m.4(1), and treating them as alternatives would overstate
    #: how often a vehicle is written off.
    requires_expert_finding: bool = False


class Debunked(Cited):
    """A widely repeated figure that the regulation does not contain."""

    claim_tr: str
    correction_tr: str


class WriteOff(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    heavy_damage: Threshold
    total_loss: Threshold
    debunked: list[Debunked] = Field(min_length=1)
    determined_by_tr: str
    determined_by_source: str

    @model_validator(mode="after")
    def _heavy_is_below_total(self) -> Self:
        if self.heavy_damage.ratio >= self.total_loss.ratio:
            raise ValueError(
                "heavy-damage ratio must sit below total-loss ratio; "
                f"got {self.heavy_damage.ratio} and {self.total_loss.ratio}"
            )
        return self


class CriticalPart(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    index: int = Field(ge=1)
    name_tr: str
    #: Whether an exterior photograph could show it. Eight of eleven cannot be,
    #: which is the argument against training a parts model for this purpose.
    visible_in_photo: bool
    ask_user: bool = False
    question_tr: str | None = None

    @model_validator(mode="after")
    def _asking_needs_a_question(self) -> Self:
        if self.ask_user and not self.question_tr:
            raise ValueError(f"part {self.index} is marked ask_user with no question_tr")
        return self


class CriticalParts(Cited):
    discretionary: bool
    discretion_note_tr: str
    items: list[CriticalPart] = Field(min_length=1)

    @property
    def photographable(self) -> list[CriticalPart]:
        return [item for item in self.items if item.visible_in_photo]

    @property
    def questions(self) -> list[CriticalPart]:
        return [item for item in self.items if item.ask_user]


class Consequence(Cited):
    key: str
    applies_to: str
    text_tr: str


class Valuation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ceiling_basis_tr: str
    ceiling_source: str
    ceiling_note_tr: str
    list_name_tr: str
    list_url: str
    max_model_years: int = Field(gt=0)
    absent_note_tr: str
    #: The correction this product most needed to make about ITSELF. Genelge
    #: 2017/14 m.2 makes the eksper raporu's rayiç the reference wherever the
    #: policy names none; the TSB list the product looks values up in is a sector
    #: service, not the regulatory default. Required rather than optional, so a
    #: future edit cannot drop the sentence and leave the figure looking official.
    reference_default_tr: str
    reference_default_source: str
    salvage_note_tr: str
    salvage_default_tr: str
    salvage_guarantee_tr: str
    salvage_source: str


class TrafficLimits(Cited):
    """The ceiling on what the OTHER party's trafik policy can pay for property.

    Was a named gap until the figures were traced: they are not in the Genel
    Şartlar and not announced by sektör duyurusu, which is why the first search
    failed. They live in an annex table of the Tarife Uygulama Esasları
    Yönetmeliği, replaced by a yönetmelik every December.

    Modelled with the previous year beside the current one because the applicable
    limit is the one in force on the **accident** date, and a claimant whose
    accident was last year needs last year's figure.
    """

    official_gazette: str
    in_force_from: str
    applies_on_tr: str
    applies_on_source: str
    property_per_vehicle_try: int = Field(gt=0)
    property_per_accident_try: int = Field(gt=0)
    previous_year: dict[str, int]
    note_tr: str

    @model_validator(mode="after")
    def _per_accident_covers_at_least_one_vehicle(self) -> Self:
        if self.property_per_accident_try < self.property_per_vehicle_try:
            raise ValueError(
                "the per-accident limit cannot be below the per-vehicle limit; "
                "one of the two columns has been read from the wrong row"
            )
        return self


class LadderStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: int = Field(ge=0)
    multiplier: float = Field(gt=0.0)
    label_tr: str
    note_tr: str | None = None
    #: Set where a court has suspended this row. Step 4 carries one: Danıştay 8.
    #: Dairesi stayed both its +10% and its status as the entry step. The product
    #: still prints the published figure -- it is the only one there is -- but a
    #: number under a stay must not be printed as settled law.
    stayed_by: str | None = None


class Asymmetry(Cited):
    text_tr: str


class Movement(Cited):
    entry_step: int
    clean_year: int
    per_property_claim: int
    per_injury_claim: int
    per_claim_basis_tr: str
    asymmetries: list[Asymmetry] = Field(min_length=1)


class TrafficLadder(Cited):
    in_force_from: str
    official_gazette: str
    #: Ek-2 caps the premium; it does not set it. Presenting a computed figure as
    #: "your premium" rather than "the most it may be" would be a price claim.
    is_ceiling_not_price: bool
    ceiling_note_tr: str
    steps: list[LadderStep] = Field(min_length=2)
    movement: Movement

    @model_validator(mode="after")
    def _steps_descend_and_multipliers_rise(self) -> Self:
        steps = [s.step for s in self.steps]
        if steps != sorted(steps, reverse=True):
            raise ValueError(f"ladder steps must run high to low, got {steps}")
        multipliers = [s.multiplier for s in self.steps]
        if multipliers != sorted(multipliers):
            # A higher step is a better step; its multiplier must be smaller.
            raise ValueError(f"multipliers must rise as steps fall, got {multipliers}")
        return self

    def multiplier_for(self, step: int) -> float:
        for entry in self.steps:
            if entry.step == step:
                return entry.multiplier
        raise KeyError(f"no ladder step {step}; valid steps are {[s.step for s in self.steps]}")


class KademeStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kademe: int = Field(ge=0)
    discount: float = Field(ge=0.0, lt=1.0)


class IllustrativeLadder(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    insurer: str
    document: str
    #: Stated so a reader cannot mistake one insurer's clause for a market rule.
    sample_size: int = Field(ge=1)
    disclaimer_tr: str
    steps: list[KademeStep] = Field(min_length=2)
    renewal_matrix: dict[str, Any]
    carve_outs: list[dict[str, str]]
    renewal_right_tr: str


class KaskoDiscount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    #: False, and the whole section is shaped around that being false. There is
    #: no SEDDK-set kasko ladder; every kasko figure must come from the user's
    #: own policy.
    nationally_regulated: bool
    source: str
    note_tr: str
    total_loss_wipes_discount: bool
    total_loss_source: str
    total_loss_text_tr: str
    illustrative_ladder: IllustrativeLadder

    @model_validator(mode="after")
    def _refuse_to_present_a_clause_as_national(self) -> Self:
        if self.nationally_regulated:
            raise ValueError(
                "kasko_discount.nationally_regulated must stay false: Kasko Genel "
                "Şartları C.11 makes the ladder an özel şart, so no national table "
                "exists to publish. Setting this true would let one insurer's "
                "clause be presented as market-wide."
            )
        return self


class Gap(BaseModel):
    """Something deliberately absent, with the reason it is absent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    question_tr: str
    reason_tr: str


class Regulation(BaseModel):
    """The whole rule sheet."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    jurisdiction: str
    verified_on: str
    write_off: WriteOff
    critical_parts: CriticalParts
    consequences: list[Consequence] = Field(min_length=1)
    valuation: Valuation
    traffic_limits: TrafficLimits
    traffic_ladder: TrafficLadder
    kasko_discount: KaskoDiscount
    #: Named gaps are part of the contract, not an oversight: a reader can see
    #: the shape of what is missing rather than assume it was covered.
    unverified: list[Gap] = Field(min_length=1)

    @classmethod
    def load(cls, path: Path) -> Regulation:
        if not path.is_file():
            raise DomainCatalogError(f"regulation data not found at {path}")
        try:
            raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as error:
            raise DomainCatalogError(
                f"regulation data at {path} is not valid YAML: {error}"
            ) from error
        try:
            return cls.model_validate(raw)
        except ValueError as error:
            raise DomainCatalogError(f"regulation data at {path} is invalid: {error}") from error
