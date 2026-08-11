"""The monthly VLM spend ceiling.

This is the mechanism that makes a publicly-linked demo safe to run on a student
budget. It is a **hard ceiling, not a guideline**: when the month's spend reaches
the configured limit the VLM is switched off and fallback requests return
``503 service_degraded``. The specialist path keeps returning 200 — the service
degrades, it does not fail.

**Each worker gets an equal slice of the ceiling.** The counter lives in process
memory, so two uvicorn workers would otherwise each spend the full limit and the
month would cost double. Dividing the ceiling by the worker count makes the total
correct regardless of how the counters are distributed; the cost is that one busy
worker cannot borrow an idle worker's slice. That is the right trade while the
counter is in-memory, and Phase 7 replaces it with a shared Postgres counter that
removes the need for the split entirely.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import date

from biovision.errors import ServiceDegradedError

logger = logging.getLogger(__name__)

# Claude Haiku 4.5 list prices, USD per million tokens.
# Cheap enough that the per-request cost is dominated by the image, and small
# enough that a $5 ceiling buys a genuinely usable demo -- see docs/COST.md.
HAIKU_INPUT_USD_PER_MTOK = 1.00
HAIKU_OUTPUT_USD_PER_MTOK = 5.00


@dataclass(frozen=True)
class Spend:
    """A point-in-time view of the budget, for /health and logging."""

    month: str
    spent_usd: float
    limit_usd: float
    calls: int

    @property
    def ratio(self) -> float:
        return self.spent_usd / self.limit_usd if self.limit_usd > 0 else 1.0

    @property
    def exhausted(self) -> bool:
        return self.spent_usd >= self.limit_usd


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Cost of one call at Haiku 4.5 list prices."""
    return (
        input_tokens * HAIKU_INPUT_USD_PER_MTOK
        + output_tokens * HAIKU_OUTPUT_USD_PER_MTOK
    ) / 1_000_000


class MonthlyBudget:
    """Tracks VLM spend against a per-worker slice of the monthly ceiling."""

    def __init__(
        self,
        monthly_limit_usd: float,
        workers: int = 1,
        warn_ratio: float = 0.80,
    ) -> None:
        if workers < 1:
            raise ValueError("workers must be at least 1")

        self._total_limit = monthly_limit_usd
        self._limit = monthly_limit_usd / workers
        self._warn_ratio = warn_ratio
        self._workers = workers

        # Counters are read and written from the threadpool that runs inference,
        # so the check-then-charge sequence needs a lock. Without it two
        # concurrent requests can both pass the check at 99% and both charge.
        self._lock = threading.Lock()
        self._month = _current_month()
        self._spent = 0.0
        self._calls = 0
        self._warned = False

        logger.info(
            "VLM budget: $%.2f/month across %d worker(s) = $%.2f per worker",
            monthly_limit_usd,
            workers,
            self._limit,
        )

    def snapshot(self) -> Spend:
        with self._lock:
            self._roll_over_if_needed()
            return Spend(
                month=self._month,
                spent_usd=round(self._spent, 6),
                limit_usd=self._limit,
                calls=self._calls,
            )

    def ensure_available(self) -> None:
        """Raise if the budget is exhausted.

        Called **before** the API request, so an exhausted budget costs nothing.

        Raises:
            ServiceDegradedError: mapped to 503 by ``api.errors``.
        """
        with self._lock:
            self._roll_over_if_needed()
            if self._spent >= self._limit:
                logger.warning(
                    "VLM budget exhausted for %s ($%.4f of $%.2f); fallback disabled",
                    self._month,
                    self._spent,
                    self._limit,
                )
                raise ServiceDegradedError(
                    "The monthly description budget is exhausted. Analysis for domains "
                    "with a trained model is unaffected; free-text descriptions resume "
                    "next month."
                )

    def charge(self, input_tokens: int, output_tokens: int) -> float:
        """Record the cost of a completed call and return it."""
        cost = estimate_cost_usd(input_tokens, output_tokens)

        with self._lock:
            self._roll_over_if_needed()
            self._spent += cost
            self._calls += 1
            spent, ratio = self._spent, self._spent / self._limit if self._limit else 1.0

            # Warn once per month, not once per call over the line -- otherwise the
            # log fills with the same warning and the signal is lost.
            should_warn = ratio >= self._warn_ratio and not self._warned
            if should_warn:
                self._warned = True

        if should_warn:
            logger.warning(
                "VLM budget at %.0f%% for %s ($%.4f of $%.2f per-worker slice)",
                ratio * 100,
                self._month,
                spent,
                self._limit,
            )

        logger.debug(
            "VLM call charged $%.6f (%d in / %d out); month total $%.4f",
            cost,
            input_tokens,
            output_tokens,
            spent,
        )
        return cost

    def _roll_over_if_needed(self) -> None:
        """Reset at the month boundary. Caller holds the lock."""
        month = _current_month()
        if month != self._month:
            logger.info(
                "VLM budget rolling over: %s spent $%.4f over %d call(s)",
                self._month,
                self._spent,
                self._calls,
            )
            self._month = month
            self._spent = 0.0
            self._calls = 0
            self._warned = False


def _current_month() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"
