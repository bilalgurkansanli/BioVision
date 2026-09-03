"""Daily request quotas.

.. warning::
   This implementation keeps its counters **in process memory**. With two uvicorn
   workers the effective limit is therefore up to 2x the configured value, and every
   restart resets the counts.

   That is acceptable for the demo tier and unacceptable for the real budget
   guarantee. Phase 7 moves the counters into Postgres, where they are shared across
   workers and survive restarts. The interface below is the one Phase 7 implements,
   so nothing outside this module changes.

The quota that actually protects the wallet is the global monthly VLM budget
(Phase 6), which is a separate mechanism: anonymous callers never reach the VLM at
all, so they cannot spend money regardless of how this limiter behaves.
"""

from __future__ import annotations

from datetime import date

from biovision.errors import RateLimitedError


class InMemoryRateLimiter:
    """A per-identity, per-day counter."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, date], int] = {}

    def check_and_increment(self, identity: str, limit: int, today: date | None = None) -> int:
        """Record one request for ``identity`` and return the new count.

        ``today`` is injectable so tests can cross a day boundary without waiting
        for one.

        Raises:
            RateLimitedError: When the identity is already at its limit.
        """
        if limit <= 0:
            raise RateLimitedError("Request quota is disabled for this caller.")

        day = today or date.today()
        key = (identity, day)
        used = self._counts.get(key, 0)

        if used >= limit:
            raise RateLimitedError(
                f"Daily limit of {limit} requests reached. Quota resets at midnight UTC."
            )

        self._counts[key] = used + 1
        self._prune(day)
        return used + 1

    def usage(self, identity: str, today: date | None = None) -> int:
        return self._counts.get((identity, today or date.today()), 0)

    def _prune(self, today: date) -> None:
        """Drop counters from previous days so the dict cannot grow without bound."""
        stale = [key for key in self._counts if key[1] != today]
        for key in stale:
            del self._counts[key]
