"""The monthly VLM spend ceiling.

This is the code that keeps a public demo from costing more than a student can
pay, so it is tested as a hard limit rather than as a best effort.
"""

from __future__ import annotations

import pytest

from biovision.errors import ServiceDegradedError
from biovision.models.vlm.budget import (
    HAIKU_INPUT_USD_PER_MTOK,
    HAIKU_OUTPUT_USD_PER_MTOK,
    MonthlyBudget,
    estimate_cost_usd,
)

# ---------------------------------------------------------------------------
# Cost model
# ---------------------------------------------------------------------------


def test_pricing_matches_the_published_rates() -> None:
    """Pinned so the README's cost table and the code cannot drift apart."""
    assert HAIKU_INPUT_USD_PER_MTOK == 1.00
    assert HAIKU_OUTPUT_USD_PER_MTOK == 5.00


def test_cost_is_computed_per_million_tokens() -> None:
    assert estimate_cost_usd(1_000_000, 0) == pytest.approx(1.00)
    assert estimate_cost_usd(0, 1_000_000) == pytest.approx(5.00)
    assert estimate_cost_usd(1_000_000, 1_000_000) == pytest.approx(6.00)


def test_a_realistic_request_costs_fractions_of_a_cent() -> None:
    """~1640 image tokens + prompt, ~200 out. The basis for docs/COST.md."""
    cost = estimate_cost_usd(1_850, 200)

    assert 0.002 < cost < 0.004


# ---------------------------------------------------------------------------
# The ceiling
# ---------------------------------------------------------------------------


def test_spending_accumulates() -> None:
    budget = MonthlyBudget(monthly_limit_usd=1.0, workers=1)

    budget.charge(1_000_000, 0)  # $1.00... exactly the limit
    snapshot = budget.snapshot()

    assert snapshot.spent_usd == pytest.approx(1.0)
    assert snapshot.calls == 1
    assert snapshot.exhausted is True


def test_an_exhausted_budget_refuses_before_spending_anything() -> None:
    """The check runs before the API request, so exhaustion is free."""
    budget = MonthlyBudget(monthly_limit_usd=0.5, workers=1)
    budget.charge(1_000_000, 0)  # $1.00 -- over the $0.50 limit

    with pytest.raises(ServiceDegradedError, match="budget is exhausted"):
        budget.ensure_available()


def test_a_budget_with_room_permits_the_call() -> None:
    budget = MonthlyBudget(monthly_limit_usd=5.0, workers=1)
    budget.charge(100_000, 1_000)

    budget.ensure_available()  # must not raise


def test_the_ceiling_is_split_between_workers() -> None:
    """Counters are per-process, so each worker gets an equal slice.

    Without the split, two workers would each spend the full ceiling and the
    month would cost double the configured limit.
    """
    budget = MonthlyBudget(monthly_limit_usd=5.0, workers=2)

    assert budget.snapshot().limit_usd == pytest.approx(2.5)


def test_a_single_worker_gets_the_whole_ceiling() -> None:
    assert MonthlyBudget(5.0, workers=1).snapshot().limit_usd == pytest.approx(5.0)


def test_zero_workers_is_a_bug() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        MonthlyBudget(5.0, workers=0)


# ---------------------------------------------------------------------------
# Warning
# ---------------------------------------------------------------------------


def test_crossing_the_warning_threshold_logs_once(caplog: pytest.LogCaptureFixture) -> None:
    """Once per month, not once per call -- otherwise the log drowns the signal."""
    budget = MonthlyBudget(monthly_limit_usd=1.0, workers=1, warn_ratio=0.80)

    with caplog.at_level("WARNING"):
        budget.charge(850_000, 0)  # $0.85 -- 85%, crosses the threshold
        budget.charge(10_000, 0)  # still over, must not warn again

    assert caplog.text.count("VLM budget at") == 1


def test_no_warning_below_the_threshold(caplog: pytest.LogCaptureFixture) -> None:
    budget = MonthlyBudget(monthly_limit_usd=1.0, workers=1, warn_ratio=0.80)

    with caplog.at_level("WARNING"):
        budget.charge(500_000, 0)  # 50%

    assert "VLM budget at" not in caplog.text


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def test_the_snapshot_reports_the_ratio() -> None:
    budget = MonthlyBudget(monthly_limit_usd=2.0, workers=1)
    budget.charge(1_000_000, 0)  # $1.00 of $2.00

    assert budget.snapshot().ratio == pytest.approx(0.5)


def test_a_fresh_budget_is_empty() -> None:
    snapshot = MonthlyBudget(5.0, workers=1).snapshot()

    assert snapshot.spent_usd == 0.0
    assert snapshot.calls == 0
    assert snapshot.exhausted is False


def test_charge_returns_what_it_charged() -> None:
    budget = MonthlyBudget(5.0, workers=1)

    assert budget.charge(1_000_000, 0) == pytest.approx(1.00)


def test_concurrent_charges_are_all_recorded() -> None:
    """The check-then-charge sequence is locked.

    Without it, two threads can both pass the check at 99% and both charge --
    the exact failure mode a spend ceiling exists to prevent.
    """
    import threading

    budget = MonthlyBudget(monthly_limit_usd=100.0, workers=1)

    def spend() -> None:
        for _ in range(50):
            budget.charge(1_000, 0)

    threads = [threading.Thread(target=spend) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert budget.snapshot().calls == 200
    assert budget.snapshot().spent_usd == pytest.approx(estimate_cost_usd(200_000, 0))
