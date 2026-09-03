"""What the claimant is actually paid, and what the next policy costs.

Two questions this project previously answered only by refusing them. It still
refuses to estimate a repair bill -- see `outcome.py` for the measured reasons --
but refusing the bill is not the same as refusing the question, and the two had
been collapsed into one.

**The insight that separates them.** A claim has exactly two outcomes, and only
one of them needs a repair cost:

* **Tam hasar.** The payment is the vehicle's value on the incident date, less
  the deductible, less the wreck if the insured keeps it. No repair estimate
  appears anywhere in that sentence. It is arithmetic over a figure the TSB list
  already supplies, and it is the branch a claimant looking at a crushed car most
  needs.
* **Onarım.** The payment is the invoice, less the deductible. The invoice is the
  number nobody can produce from a photograph, so this branch is returned as a
  **bounded interval** with its bounds named -- not as a point estimate dressed
  up with a plus-or-minus.

Returning both, labelled, is strictly more useful than returning neither, and it
adds no estimate to the system: every closed figure below is a subtraction from a
listed value, and every open one says what would close it.

**Sovtaj is a hole and stays a hole.** Where the insured keeps the wreck, the
payment is "rayiç eksi sovtaj" and the sovtaj is set by an eksper. No published
Turkish salvage-ratio data was found (`regulation.yaml: unverified.salvage_ratio`),
so that branch returns an upper bound and names what is missing rather than
applying a plausible-looking percentage.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from biovision.claims.outcome import WriteOffLines, _money
from biovision.domains.regulation import Regulation

ScenarioKey = Literal["tam_hasar", "onarim"]


@dataclass(frozen=True)
class PayoutScenario:
    """One branch a claim can take, with as much of it closed as the facts allow.

    `amount_try` is set only where the arithmetic closes completely. Where it does
    not, `lower_try`/`upper_try` carry the interval and `missing_tr` names what
    would collapse it. A scenario never carries both a point and a range: a point
    estimate beside an interval invites the reader to treat the point as the
    answer.
    """

    key: ScenarioKey
    label_tr: str
    amount_try: Decimal | None
    lower_try: Decimal | None
    upper_try: Decimal | None
    basis_tr: str
    source: str
    #: Empty when the figure is exact. Each entry is something only a person or a
    #: document can supply -- never something the system could have estimated.
    missing_tr: tuple[str, ...]


def payout_scenarios(
    regulation: Regulation,
    lines: WriteOffLines,
    deductible: Decimal | None = None,
    salvage_retained: bool = False,
) -> tuple[PayoutScenario, ...]:
    """Both branches, in lira, for one vehicle.

    `deductible` is the policy's muafiyet. `None` means the caller did not say,
    and the figures come back without it subtracted -- stated in `missing_tr`
    rather than silently assumed to be zero, because assuming zero overstates
    every payment on a policy that has one.

    `salvage_retained` is the choice a claimant is offered at total loss: hand
    over the wreck and take the full value, or keep the wreck for less. The two
    produce genuinely different answers and the system should not pick one.
    """
    excess = _money(deductible) if deductible is not None else None
    if excess is not None and excess < 0:
        raise ValueError(f"deductible cannot be negative, got {deductible}")

    value = lines.vehicle_value
    unstated: tuple[str, ...] = () if excess is not None else ("Poliçenizdeki muafiyet tutarı",)
    after_excess = _money(value - excess) if excess is not None else value
    if after_excess < 0:
        after_excess = _money(Decimal(0))

    if salvage_retained:
        total_loss = PayoutScenario(
            key="tam_hasar",
            label_tr="Tam hasar — hasarlı araç sizde kalırsa",
            amount_try=None,
            lower_try=None,
            upper_try=after_excess,
            basis_tr=(
                "Rayiç değer eksi sovtaj (hasarlı hâlin değeri)"
                + (" eksi muafiyet" if excess is not None else "")
            ),
            source=regulation.valuation.ceiling_source,
            missing_tr=(
                *unstated,
                "Sovtaj bedeli — eksper belirler. Türkiye'de yayımlanmış bir "
                "sovtaj/rayiç oranı bulunamadığı için bu sistem tahmin etmez.",
            ),
        )
    else:
        total_loss = PayoutScenario(
            key="tam_hasar",
            label_tr="Tam hasar — hasarlı aracı sigortacı alırsa",
            amount_try=after_excess if excess is not None else None,
            lower_try=None,
            upper_try=None if excess is not None else after_excess,
            basis_tr=(
                "Aracın riziko tarihindeki rayiç değeri"
                + (" eksi muafiyet" if excess is not None else "")
            ),
            source=regulation.valuation.ceiling_source,
            missing_tr=unstated,
        )

    # The ceiling on a repair payment is the vehicle's value, not the 60% line:
    # crossing 60% produces an "ağır hasarlı" record, it does not stop the repair
    # from being paid. The heavy-damage line is reported by `write_off_lines` for
    # what it actually decides.
    repair = PayoutScenario(
        key="onarim",
        label_tr="Onarım",
        amount_try=None,
        lower_try=_money(Decimal(0)),
        upper_try=after_excess,
        basis_tr=(
            "KDV dahil onarım faturası"
            + (" eksi muafiyet" if excess is not None else "")
            + ". Bu aralık daraltılmıyor: onarım bedeli fotoğraftan çıkarılmaz."
        ),
        source=regulation.valuation.ceiling_source,
        missing_tr=(
            *unstated,
            "KDV dahil onarım bedeli — eksper veya servis raporu. Sektör "
            "verisine göre bir onarımın gerektirdiği kalemlerin %51,5'i ancak "
            "söküm sonrası görülüyor; fotoğraf oraya ulaşmaz.",
        ),
    )

    return (total_loss, repair)


# ---------------------------------------------------------------------------
# Kasko premium
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KaskoImpact:
    """What one paid claim does to a kasko premium.

    **Not a national rule and the type says so.** Kasko GŞ C.11 leaves the
    no-claims ladder to özel şartlar, so there is no table to apply. Two honest
    modes exist and both are here:

    * the claimant gives the discount printed on their own policy, and the ratio
      is arithmetic over *their* number;
    * they give a kademe, and one insurer's published clause is applied with
      `sample_size` and `insurer` attached to the answer.

    `nationally_regulated` is a field rather than a comment so that a client
    cannot render this beside the trafik figure as though the two had the same
    standing.
    """

    from_discount: float
    to_discount: float
    #: (1 - new) / (1 - old) - 1. Positive means the premium goes up.
    relative_increase: float
    basis_tr: str
    source: str
    nationally_regulated: Literal[False] = False
    insurer: str | None = None
    sample_size: int | None = None
    from_kademe: int | None = None
    to_kademe: int | None = None
    disclaimer_tr: str | None = None


def _discount_for(regulation: Regulation, kademe: int) -> float:
    for step in regulation.kasko_discount.illustrative_ladder.steps:
        if step.kademe == kademe:
            return step.discount
    raise ValueError(
        f"kademe {kademe} is not on the illustrative ladder "
        f"{[s.kademe for s in regulation.kasko_discount.illustrative_ladder.steps]}"
    )


def kasko_premium_impact(
    regulation: Regulation,
    current_discount: float | None = None,
    current_kademe: int | None = None,
    claims: int = 1,
    total_loss: bool = False,
) -> KaskoImpact:
    """The premium ratio after `claims` paid claims in one period.

    Exactly one of `current_discount` and `current_kademe` is required. The first
    is the honest path -- it uses the claimant's own policy -- but it can only be
    completed for a total loss, where the discount is documented to go to zero.
    For a partial claim the new discount is whatever their özel şart says, and
    the ladder is the only thing available to illustrate it.

    `claims` counts PAID CLAIMS in the period, matching the published matrix, and
    more than two claims empties the discount from any level.
    """
    kasko = regulation.kasko_discount
    ladder = kasko.illustrative_ladder

    if (current_discount is None) == (current_kademe is None):
        raise ValueError("supply exactly one of current_discount or current_kademe")
    if claims < 0:
        raise ValueError(f"claims cannot be negative, got {claims}")

    if current_kademe is not None:
        from_discount = _discount_for(regulation, current_kademe)
        if total_loss and kasko.total_loss_wipes_discount:
            to_kademe, to_discount = 0, 0.0
            basis = kasko.total_loss_text_tr
            source = kasko.total_loss_source
        else:
            row = ladder.renewal_matrix.get(str(current_kademe))
            if not isinstance(row, list) or len(row) < 4:
                raise ValueError(f"no renewal row for kademe {current_kademe}")
            # Columns are hasarsız / 1 / 2 / more-than-two, so anything above two
            # claims lands on the last column rather than running off the end.
            to_kademe = int(row[min(claims, 3)])
            to_discount = _discount_for(regulation, to_kademe)
            basis = ladder.disclaimer_tr
            source = ladder.document
        return KaskoImpact(
            from_discount=from_discount,
            to_discount=to_discount,
            relative_increase=round((1 - to_discount) / (1 - from_discount) - 1, 4),
            basis_tr=basis,
            source=source,
            insurer=ladder.insurer,
            sample_size=ladder.sample_size,
            from_kademe=current_kademe,
            to_kademe=to_kademe,
            disclaimer_tr=ladder.disclaimer_tr,
        )

    assert current_discount is not None
    if not 0.0 <= current_discount < 1.0:
        raise ValueError(f"discount must be in [0, 1), got {current_discount}")
    if not total_loss:
        # Deliberately refused rather than approximated. Where the claimant's own
        # discount is known but their özel şart is not, the new discount is
        # genuinely unknown, and the illustrative ladder is keyed on kademe --
        # mapping a bare percentage onto it would be inventing their policy.
        raise ValueError(
            "a partial claim needs current_kademe: the new discount is set by the "
            "policy's özel şart, and it cannot be derived from the current "
            "percentage alone"
        )

    return KaskoImpact(
        from_discount=current_discount,
        to_discount=0.0,
        relative_increase=round(1 / (1 - current_discount) - 1, 4),
        basis_tr=kasko.total_loss_text_tr,
        source=kasko.total_loss_source,
        insurer=ladder.insurer,
        sample_size=ladder.sample_size,
        disclaimer_tr=ladder.disclaimer_tr,
    )
