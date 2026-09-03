"""The payout branches, and the line they must not cross.

`outcome.py` refuses to estimate a repair bill and `test_claim_outcome.py` guards
that refusal. This module answers the question the refusal used to swallow --
*what will I actually be paid* -- so these tests exist to check that answering it
did not smuggle an estimate back in through a different door.

The shape is the guard. A branch carries an exact amount **or** an interval,
never both, and an open figure has to name what would close it. Those two rules
are what stop a range from quietly acquiring a midpoint.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from biovision.claims import scenario as scenario_module
from biovision.claims.outcome import (
    WriteOffLines,
    traffic_premium_impact,
    write_off_lines,
)
from biovision.claims.scenario import kasko_premium_impact, payout_scenarios
from biovision.config import BACKEND_ROOT
from biovision.domains.regulation import Regulation

REGULATION_PATH = BACKEND_ROOT / "src" / "biovision" / "domains" / "regulation.yaml"

#: A real row from the TSB list -- CAPTUR ICON 1.3 TCe EDC 130, 2020.
VALUE = Decimal("1584880")


@pytest.fixture(scope="module")
def regulation() -> Regulation:
    return Regulation.load(REGULATION_PATH)


@pytest.fixture(scope="module")
def lines(regulation: Regulation) -> WriteOffLines:
    return write_off_lines(regulation, VALUE, "TSB Kasko Değer Listesi")


# ---------------------------------------------------------------------------
# The shape that stops a range becoming an estimate
# ---------------------------------------------------------------------------


def test_no_branch_carries_both_a_point_and_a_range(
    regulation: Regulation, lines: WriteOffLines
) -> None:
    """A point beside an interval is read as the answer and the interval as noise."""
    for supplied in (None, Decimal("5000")):
        for retained in (False, True):
            for branch in payout_scenarios(
                regulation, lines, deductible=supplied, salvage_retained=retained
            ):
                has_point = branch.amount_try is not None
                has_range = branch.lower_try is not None or branch.upper_try is not None
                assert has_point != has_range, f"{branch.key} carries both"


def test_an_open_figure_always_names_what_would_close_it(
    regulation: Regulation, lines: WriteOffLines
) -> None:
    """Otherwise a reader cannot tell a system failure from an open question."""
    for branch in payout_scenarios(regulation, lines):
        if branch.amount_try is None:
            assert branch.missing_tr, f"{branch.key} is open and says nothing about why"


def test_an_unstated_deductible_is_not_treated_as_zero(
    regulation: Regulation, lines: WriteOffLines
) -> None:
    """Assuming zero would overstate every payment on a policy that has one."""
    branches = payout_scenarios(regulation, lines, deductible=None)
    total_loss = next(b for b in branches if b.key == "tam_hasar")
    assert total_loss.amount_try is None
    assert any("muafiyet" in item.lower() for item in total_loss.missing_tr)


def test_the_total_loss_branch_closes_once_the_deductible_is_known(
    regulation: Regulation, lines: WriteOffLines
) -> None:
    """This is the branch a crushed car most needs, and it needs no repair cost."""
    branches = payout_scenarios(regulation, lines, deductible=Decimal("5000"))
    total_loss = next(b for b in branches if b.key == "tam_hasar")
    assert total_loss.amount_try == Decimal("1579880.00")
    assert total_loss.missing_tr == ()


def test_keeping_the_wreck_never_produces_an_exact_figure(
    regulation: Regulation, lines: WriteOffLines
) -> None:
    """Sovtaj is set by an eksper and no published Turkish ratio exists.

    Applying a plausible percentage would be the single easiest place in this
    codebase to invent a number, which is why it is asserted rather than trusted.
    """
    branches = payout_scenarios(regulation, lines, deductible=Decimal("0"), salvage_retained=True)
    total_loss = next(b for b in branches if b.key == "tam_hasar")
    assert total_loss.amount_try is None
    assert any("sovtaj" in item.lower() for item in total_loss.missing_tr)


def test_the_repair_branch_stays_open_and_says_why(
    regulation: Regulation, lines: WriteOffLines
) -> None:
    """The invoice is the one number no photograph produces."""
    repair = next(b for b in payout_scenarios(regulation, lines) if b.key == "onarim")
    assert repair.amount_try is None
    assert repair.lower_try == Decimal("0.00")
    assert repair.upper_try == Decimal("1584880.00")
    assert any("onarım bedeli" in item for item in repair.missing_tr)


def test_no_payment_exceeds_the_vehicle_value(regulation: Regulation, lines: WriteOffLines) -> None:
    for branch in payout_scenarios(regulation, lines, deductible=Decimal("0")):
        for figure in (branch.amount_try, branch.lower_try, branch.upper_try):
            if figure is not None:
                assert figure <= VALUE


def test_the_module_has_no_cost_estimator() -> None:
    """The same guard `outcome.py` carries, restated where the risk moved.

    Adding payout branches makes an `estimate_repair_cost` feel like the natural
    next function. It is the one function this product must not have.
    """
    forbidden = ("estimate", "predict", "forecast", "guess")
    offenders = [
        name
        for name in dir(scenario_module)
        if not name.startswith("_") and any(word in name.lower() for word in forbidden)
    ]
    assert offenders == [], f"scenario.py grew a predictor: {offenders}"


# ---------------------------------------------------------------------------
# Kasko: arithmetic over someone's own policy, never a national table
# ---------------------------------------------------------------------------


def test_kasko_is_never_presented_as_nationally_regulated(regulation: Regulation) -> None:
    impact = kasko_premium_impact(regulation, current_kademe=4, claims=1)
    assert impact.nationally_regulated is False
    assert impact.sample_size == 1, "one insurer's clause is not a market rule"
    assert impact.insurer


def test_a_partial_claim_needs_a_kademe_rather_than_a_guess(regulation: Regulation) -> None:
    """The new discount comes from an özel şart nobody here has read.

    Mapping a bare percentage onto the illustrative ladder would be inventing the
    claimant's contract, so it raises instead.
    """
    with pytest.raises(ValueError, match="özel şart"):
        kasko_premium_impact(regulation, current_discount=0.60, total_loss=False)


def test_a_total_loss_empties_the_discount(regulation: Regulation) -> None:
    """The one kasko movement with a published clause behind it."""
    impact = kasko_premium_impact(regulation, current_discount=0.60, total_loss=True)
    assert impact.to_discount == 0.0
    # 1 / (1 - 0.60) - 1: the premium multiplies by 2.5, so it rises 150%.
    assert impact.relative_increase == pytest.approx(1.5)


def test_the_renewal_matrix_is_used_rather_than_a_fixed_step(regulation: Regulation) -> None:
    """Two claims cost two steps; more than two empties it from any level."""
    one = kasko_premium_impact(regulation, current_kademe=4, claims=1)
    two = kasko_premium_impact(regulation, current_kademe=4, claims=2)
    many = kasko_premium_impact(regulation, current_kademe=4, claims=5)
    assert (one.to_kademe, two.to_kademe, many.to_kademe) == (3, 2, 0)
    assert one.relative_increase < two.relative_increase < many.relative_increase


def test_exactly_one_of_the_two_kasko_inputs_is_required(regulation: Regulation) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        kasko_premium_impact(regulation)
    with pytest.raises(ValueError, match="exactly one"):
        kasko_premium_impact(regulation, current_discount=0.5, current_kademe=4)


# ---------------------------------------------------------------------------
# The full tables, swept
# ---------------------------------------------------------------------------
#
#  Written out from the Resmî Gazete table and the published clause rather than
#  imported from `regulation.yaml`, so this compares the shipped data against an
#  independent transcription instead of against itself. A YAML typo that the
#  loader accepts has to survive being typed twice to get through.

#: Tarife Uygulama Esasları Yönetmeliği Ek-2.
EK2 = {8: 0.50, 7: 0.60, 6: 0.80, 5: 0.95, 4: 1.10, 3: 1.45, 2: 1.90, 1: 2.35, 0: 3.00}

#: Anadolu Sigorta KZ649 01/2024 §2.1.1 — row: current kademe, columns:
#: clean / 1 claim / 2 claims / more than two.
RENEWAL = {
    0: [1, 0, 0, 0],
    1: [2, 0, 0, 0],
    2: [3, 1, 0, 0],
    3: [4, 2, 1, 0],
    4: [5, 3, 2, 0],
    5: [5, 4, 3, 0],
}
KASKO_DISCOUNT = {0: 0.00, 1: 0.30, 2: 0.40, 3: 0.50, 4: 0.60, 5: 0.65}


@pytest.mark.parametrize("step", sorted(EK2))
def test_every_traffic_step_moves_and_prices_as_the_table_says(
    regulation: Regulation, step: int
) -> None:
    """One property claim: one rung down, and the ratio of the two multipliers."""
    impact = traffic_premium_impact(regulation, step)
    expected_to = max(0, step - 1)

    assert impact.to_step == expected_to
    assert impact.relative_increase == pytest.approx(EK2[expected_to] / EK2[step] - 1.0, abs=1e-4)


@pytest.mark.parametrize("step", sorted(EK2))
def test_an_injury_claim_costs_two_rungs(regulation: Regulation, step: int) -> None:
    """Geçici m.11(8). Missing this understates the cost of the worst accidents."""
    assert traffic_premium_impact(regulation, step, injury=True).to_step == max(0, step - 2)


def test_the_ladder_bottoms_out_rather_than_going_negative(regulation: Regulation) -> None:
    assert traffic_premium_impact(regulation, 0).to_step == 0
    assert traffic_premium_impact(regulation, 0, injury=True).to_step == 0


def test_returning_to_the_top_step_costs_five_years_not_one(regulation: Regulation) -> None:
    """Geçici m.11(14): five clean periods at 7 before 8 is granted.

    Every other rung is one clean year, so losing the top step is far more
    expensive than "one step down" suggests.
    """
    assert traffic_premium_impact(regulation, 8).recovery_years == 5
    assert all(traffic_premium_impact(regulation, s).recovery_years == 1 for s in range(1, 8))


@pytest.mark.parametrize("kademe", sorted(RENEWAL))
@pytest.mark.parametrize("claims", [1, 2, 5])
def test_every_kasko_row_matches_the_published_clause(
    regulation: Regulation, kademe: int, claims: int
) -> None:
    """Including the ">2 claims goes to zero from any level" column."""
    impact = kasko_premium_impact(regulation, current_kademe=kademe, claims=claims)
    expected_to = RENEWAL[kademe][min(claims, 3)]

    assert impact.to_kademe == expected_to
    assert impact.relative_increase == pytest.approx(
        (1 - KASKO_DISCOUNT[expected_to]) / (1 - KASKO_DISCOUNT[kademe]) - 1, abs=1e-4
    )
