"""Where the write-off lines fall, and what follows from them.

**This module computes thresholds. It never predicts an outcome.**

The distinction is the whole design. A claimant wants to know "will my car be
written off", and that question needs the VAT-inclusive repair cost -- the one
number nobody can produce from a photograph with any published accuracy. Not
academia (the one headline figure is measured against cost labels its authors
invented, because no open price database existed), not the commercial vendors
(Tractable, Solera, CCC and Mitchell publish cycle time and automation rate, never
error), and not in principle either: 51.5% of the calibrations a repair needs only
appear after teardown, which a camera cannot reach.

So the module answers the question that *is* answerable, and it turns out to be
the more useful one:

    "The heavy-damage line for your car is 950,928 TL. Here is the rule, here is
     the article, and here is who is allowed to tell you which side you are on."

That is arithmetic plus a citation. A claimant cannot get it anywhere else, and
the figure everyone repeats -- 70% -- is wrong.

**What the caller must supply and why.** The vehicle's value cannot come from the
photograph: 27,906 rows in the TSB list, and one model year of one make carries
dozens of trims separated by engine and gearbox. No vision model reads a gearbox
off a body panel. The user picks, or there is no denominator and no lines.

Structurally: `estimate_repair_cost` does not exist in this module and must not
be added. A field that does not exist cannot leak into a screenshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from biovision.domains.regulation import Regulation

#: Money is Decimal end to end. A float threshold compared against a float cost
#: can flip a write-off decision on a representation error, and this figure is
#: the one the whole product turns on.
TWO_PLACES = Decimal("0.01")


def _money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ThresholdLine:
    """One regulatory line, in lira, for a specific vehicle."""

    key: str
    label_tr: str
    ratio: float
    amount: Decimal
    source: str
    #: True where the ratio alone does not decide it -- total loss also needs an
    #: expert finding that the vehicle is beyond repair.
    requires_expert_finding: bool
    basis_tr: str


@dataclass(frozen=True)
class WriteOffLines:
    """The computable core: where the lines fall for this vehicle.

    Deliberately carries no verdict field. There is nothing to put in it.
    """

    vehicle_value: Decimal
    value_source: str
    lines: list[ThresholdLine]
    #: Reproduced so a reader sees the false figure corrected next to the real
    #: one, rather than having to already know it was false.
    debunked: list[dict[str, str]]
    determined_by_tr: str
    determined_by_source: str

    def line(self, key: str) -> ThresholdLine:
        for entry in self.lines:
            if entry.key == key:
                return entry
        raise KeyError(f"no threshold line {key!r}")


def write_off_lines(
    regulation: Regulation, vehicle_value: Decimal, value_source: str
) -> WriteOffLines:
    """Both thresholds in lira, for one vehicle.

    `vehicle_value` is the value **on the date of the incident**, not the policy
    date -- Kasko Genel Şartları B.3-3.3.1.1. In an inflationary market the
    difference runs in the claimant's favour and most claimants believe the
    opposite, so the caller is expected to surface it.
    """
    if vehicle_value <= 0:
        raise ValueError(f"vehicle value must be positive, got {vehicle_value}")

    value = _money(vehicle_value)
    lines = [
        ThresholdLine(
            key=threshold.key,
            label_tr=threshold.label_tr,
            ratio=threshold.ratio,
            amount=_money(value * Decimal(str(threshold.ratio))),
            source=threshold.source,
            requires_expert_finding=threshold.requires_expert_finding,
            basis_tr=threshold.basis_tr,
        )
        for threshold in (regulation.write_off.heavy_damage, regulation.write_off.total_loss)
    ]

    return WriteOffLines(
        vehicle_value=value,
        value_source=value_source,
        lines=lines,
        debunked=[
            {"claim_tr": d.claim_tr, "correction_tr": d.correction_tr, "source": d.source}
            for d in regulation.write_off.debunked
        ],
        determined_by_tr=regulation.write_off.determined_by_tr,
        determined_by_source=regulation.write_off.determined_by_source,
    )


@dataclass(frozen=True)
class Position:
    """Which side of a line a KNOWN repair cost falls on.

    Only reachable once the claimant has an expert's figure. At that point this
    is a division, not a prediction -- which is exactly why the product offers it
    as a second step rather than guessing the numerator in the first.
    """

    repair_cost: Decimal
    ratio_of_value: float
    crossed: list[str]
    #: The lines it did not cross, so "below the threshold" is stated rather than
    #: inferred from an absence.
    below: list[str]


def position_for(lines: WriteOffLines, repair_cost: Decimal) -> Position:
    """Compare a known, VAT-inclusive repair cost against the lines."""
    if repair_cost < 0:
        raise ValueError(f"repair cost cannot be negative, got {repair_cost}")

    cost = _money(repair_cost)
    crossed = [line.key for line in lines.lines if cost > line.amount]
    below = [line.key for line in lines.lines if cost <= line.amount]
    ratio = float(cost / lines.vehicle_value) if lines.vehicle_value else 0.0

    return Position(repair_cost=cost, ratio_of_value=round(ratio, 4), crossed=crossed, below=below)


@dataclass(frozen=True)
class PremiumImpact:
    """What one claim does to a trafik sigortası step, as a ratio.

    Expressed against the driver's CURRENT premium rather than in lira, because
    the lira figure depends on a base premium the system does not know. A ratio
    is insurer-independent and is arguably the better output.

    Ek-2 is a **ceiling**: the regulation caps what an insurer may charge and
    leaves the actual price free (Madde 5's own table is printed blank). So this
    is the worst case, not a quote, and `is_ceiling` carries that into the
    response rather than leaving it to prose.
    """

    from_step: int
    to_step: int
    from_multiplier: float
    to_multiplier: float
    #: to/from − 1. At step 8 → 7 this is +20%, which understates the real cost:
    #: returning to 8 needs five clean years at 7. `recovery_years` says so.
    relative_increase: float
    recovery_years: int
    is_ceiling: bool
    source: str


def traffic_premium_impact(
    regulation: Regulation, current_step: int, injury: bool = False
) -> PremiumImpact:
    """Step movement and the resulting premium ratio for one claim payment.

    Per PAYMENT, not per accident: one accident producing two payments moves two
    steps (Geçici Madde 11(8)).
    """
    ladder = regulation.traffic_ladder
    movement = ladder.movement
    steps = [entry.step for entry in ladder.steps]

    if current_step not in steps:
        raise ValueError(f"step {current_step} is not on the ladder {steps}")

    drop = movement.per_injury_claim if injury else movement.per_property_claim
    target = max(min(steps), current_step + drop)

    # Climbing back is one step per clean year, except the top: Geçici Madde
    # 11(14) requires five clean years at 7 before 8 is granted. Losing the top
    # step therefore costs far more than the one-step rule suggests.
    top = max(steps)
    years = current_step - target
    if current_step == top:
        years += 4

    from_multiplier = ladder.multiplier_for(current_step)
    to_multiplier = ladder.multiplier_for(target)

    return PremiumImpact(
        from_step=current_step,
        to_step=target,
        from_multiplier=from_multiplier,
        to_multiplier=to_multiplier,
        relative_increase=round(to_multiplier / from_multiplier - 1.0, 4),
        recovery_years=years,
        is_ceiling=ladder.is_ceiling_not_price,
        source=f"{ladder.source}; {movement.source}",
    )
