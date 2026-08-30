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
from biovision.claims.outcome import WriteOffLines, write_off_lines
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
    branches = payout_scenarios(
        regulation, lines, deductible=Decimal("0"), salvage_retained=True
    )
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


def test_no_payment_exceeds_the_vehicle_value(
    regulation: Regulation, lines: WriteOffLines
) -> None:
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
