"""The regulatory arithmetic, and the line it must never cross.

These are not accuracy tests. Nothing here is estimated, so there is nothing to
be accurate against -- they exist so the published thresholds and the code cannot
drift apart, and so the module cannot quietly grow the one function it must not
have.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from biovision.claims import outcome as outcome_module
from biovision.claims.outcome import (
    position_for,
    traffic_premium_impact,
    write_off_lines,
)
from biovision.config import BACKEND_ROOT
from biovision.domains.catalog import DomainCatalogError
from biovision.domains.regulation import Regulation

REGULATION_PATH = BACKEND_ROOT / "src" / "biovision" / "domains" / "regulation.yaml"


@pytest.fixture(scope="module")
def regulation() -> Regulation:
    return Regulation.load(REGULATION_PATH)


# ---------------------------------------------------------------------------
# The thresholds themselves
# ---------------------------------------------------------------------------


def test_the_heavy_damage_ratio_is_sixty_percent(regulation: Regulation) -> None:
    """The figure the whole product turns on, and the one everyone gets wrong.

    Public sources overwhelmingly repeat 70%. The only ratio in Turkish
    regulation is 60%, in force since 1 July 2025.
    """
    heavy = regulation.write_off.heavy_damage
    assert heavy.ratio == 0.60
    assert "2025/12" in heavy.source
    assert heavy.in_force_from == "2025-07-01"


def test_total_loss_needs_the_expert_finding_as_well(regulation: Regulation) -> None:
    """m.4(1) is cumulative, not alternative.

    Treating cost-exceeds-value as sufficient would declare vehicles written off
    that the regulation does not, which is the direction that costs a claimant a
    repairable car.
    """
    total = regulation.write_off.total_loss
    assert total.ratio == 1.00
    assert total.requires_expert_finding is True


def test_the_false_seventy_percent_figure_is_carried_and_corrected(
    regulation: Regulation,
) -> None:
    debunked = regulation.write_off.debunked
    assert any("70" in entry.claim_tr for entry in debunked)
    assert all(entry.source for entry in debunked)


def test_lines_are_computed_in_lira(regulation: Regulation) -> None:
    """The worked example: a 2020 Renault Captur at its TSB August 2026 value."""
    lines = write_off_lines(regulation, Decimal("1584880"), "TSB 202608R4")

    assert lines.line("agir_hasar").amount == Decimal("950928.00")
    assert lines.line("tam_hasar").amount == Decimal("1584880.00")


def test_money_is_decimal_not_float(regulation: Regulation) -> None:
    """A float threshold can flip a write-off decision on a representation error.

    0.1 + 0.2 != 0.3 is a curiosity until it decides whether someone's car is
    repairable.
    """
    lines = write_off_lines(regulation, Decimal("1000000"), "test")
    assert isinstance(lines.vehicle_value, Decimal)
    assert all(isinstance(line.amount, Decimal) for line in lines.lines)


@pytest.mark.parametrize("value", [Decimal("0"), Decimal("-1")])
def test_a_nonsense_vehicle_value_is_refused(regulation: Regulation, value: Decimal) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        write_off_lines(regulation, value, "test")


# ---------------------------------------------------------------------------
# Position: only once a real cost exists
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cost", "expected_crossed"),
    [
        (Decimal("420000"), []),
        (Decimal("950928"), []),  # exactly on the line is not "aşarsa"
        (Decimal("950929"), ["agir_hasar"]),
        (Decimal("1700000"), ["agir_hasar", "tam_hasar"]),
    ],
)
def test_position_is_a_comparison_not_a_prediction(
    regulation: Regulation, cost: Decimal, expected_crossed: list[str]
) -> None:
    """The regulation says "aşarsa" -- exceeds. Equal is not exceeded."""
    lines = write_off_lines(regulation, Decimal("1584880"), "TSB 202608R4")
    assert position_for(lines, cost).crossed == expected_crossed


# ---------------------------------------------------------------------------
# Premium
# ---------------------------------------------------------------------------


def test_step_four_is_not_neutral(regulation: Regulation) -> None:
    """The amendment of 4/4/2023 deleted the phrase that made it neutral.

    Nearly every source in circulation still describes basamak 4 as carrying no
    increase. It carries +10%.
    """
    assert regulation.traffic_ladder.multiplier_for(4) == 1.10


def test_losing_the_top_step_costs_five_years_not_one(regulation: Regulation) -> None:
    """Geçici Madde 11(14): returning to 8 needs five clean years at 7.

    The naive one-step-down reading understates the cost of the top step by
    roughly a factor of five, and it is the step most careful drivers occupy.
    """
    impact = traffic_premium_impact(regulation, current_step=8)

    assert impact.to_step == 7
    assert impact.recovery_years == 5

    ordinary = traffic_premium_impact(regulation, current_step=5)
    assert ordinary.recovery_years == 1


def test_an_injury_claim_costs_two_steps(regulation: Regulation) -> None:
    assert traffic_premium_impact(regulation, 6, injury=True).to_step == 4
    assert traffic_premium_impact(regulation, 6, injury=False).to_step == 5


def test_the_ladder_bottoms_out_rather_than_going_negative(regulation: Regulation) -> None:
    assert traffic_premium_impact(regulation, 0).to_step == 0


def test_the_premium_figure_is_labelled_a_ceiling(regulation: Regulation) -> None:
    """Ek-2 caps what may be charged; Madde 5's own table is printed blank.

    Presenting the computed figure as "your premium" would be a price claim the
    regulation explicitly declines to make.
    """
    assert traffic_premium_impact(regulation, 5).is_ceiling is True


# ---------------------------------------------------------------------------
# The line that must not be crossed
# ---------------------------------------------------------------------------


def test_the_module_has_no_cost_estimator(regulation: Regulation) -> None:
    """The structural prohibition, asserted rather than trusted to discipline.

    No photo-based repair-cost estimator publishes an accuracy figure against
    real invoices -- not in academia, not at Tractable, Solera, CCC or Mitchell.
    A field that does not exist cannot leak into a screenshot, so the absence is
    the safeguard and this test is what keeps it absent.
    """
    forbidden = [
        name
        for name in dir(outcome_module)
        if any(word in name.lower() for word in ("estimate", "predict", "forecast"))
    ]
    assert not forbidden, (
        f"{outcome_module.__name__} grew {forbidden}. This module computes "
        "thresholds from regulation; it must not estimate a repair cost."
    )


def test_write_off_lines_carries_no_verdict(regulation: Regulation) -> None:
    """There is no field for "will it be written off" because there is no answer.

    The determination belongs exclusively to a registered eksper, and the result
    object says who that is instead of guessing on their behalf.
    """
    lines = write_off_lines(regulation, Decimal("1584880"), "TSB 202608R4")

    fields = set(vars(lines))
    assert not fields & {"verdict", "outcome", "will_be_written_off", "probability"}
    assert "eksper" in lines.determined_by_tr.lower()


def test_the_kasko_ladder_cannot_be_presented_as_national(regulation: Regulation) -> None:
    """Kasko GŞ C.11 makes it an özel şart: there is no national table.

    One insurer's published clause is carried as an illustration with its sample
    size stated. The loader refuses to let that flag flip.
    """
    kasko = regulation.kasko_discount
    assert kasko.nationally_regulated is False
    assert kasko.illustrative_ladder.sample_size == 1
    assert kasko.illustrative_ladder.insurer

    raw = REGULATION_PATH.read_text(encoding="utf-8").replace(
        "nationally_regulated: false", "nationally_regulated: true"
    )
    broken = REGULATION_PATH.parent / "_broken_regulation.yaml"
    broken.write_text(raw, encoding="utf-8")
    try:
        with pytest.raises(DomainCatalogError, match="özel şart"):
            Regulation.load(broken)
    finally:
        broken.unlink()


def test_every_threshold_names_its_article(regulation: Regulation) -> None:
    """A regulatory figure without a citation is worse than none: it looks
    authoritative and cannot be checked."""
    for threshold in (regulation.write_off.heavy_damage, regulation.write_off.total_loss):
        assert "m." in threshold.source, threshold.key

    for consequence in regulation.consequences:
        assert consequence.source


def test_the_gaps_are_published_rather_than_omitted(regulation: Regulation) -> None:
    """Including the one that matters most: repair cost is not estimated."""
    keys = {gap.key for gap in regulation.unverified}
    assert "repair_cost_from_photo" in keys
    assert "salvage_ratio" in keys

    cost_gap = next(g for g in regulation.unverified if g.key == "repair_cost_from_photo")
    assert "TAHMİN EDİLMEZ" in cost_gap.reason_tr


def test_eight_of_the_eleven_critical_parts_are_invisible(regulation: Regulation) -> None:
    """The argument against training a parts model for the write-off question.

    Ek-1 is a list of structural components; most sit behind panels. A vision
    model buys at most one of them, and item 9 -- airbags -- is better asked than
    inferred.
    """
    parts = regulation.critical_parts
    assert len(parts.items) == 11
    assert len(parts.photographable) <= 3
    assert [item.index for item in parts.questions] == [9]
