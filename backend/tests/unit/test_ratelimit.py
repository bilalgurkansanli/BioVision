"""Daily quota counter."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from biovision.errors import RateLimitedError
from biovision.limits.ratelimit import InMemoryRateLimiter


def test_counts_up_to_the_limit_then_refuses() -> None:
    limiter = InMemoryRateLimiter()
    today = date(2026, 8, 11)

    for expected in (1, 2, 3):
        assert limiter.check_and_increment("ip:1.2.3.4", limit=3, today=today) == expected

    with pytest.raises(RateLimitedError, match="Daily limit of 3"):
        limiter.check_and_increment("ip:1.2.3.4", limit=3, today=today)


def test_identities_are_counted_separately() -> None:
    limiter = InMemoryRateLimiter()
    today = date(2026, 8, 11)

    limiter.check_and_increment("ip:1.1.1.1", limit=1, today=today)
    # A different caller is unaffected by the first one's exhausted quota.
    assert limiter.check_and_increment("ip:2.2.2.2", limit=1, today=today) == 1


def test_the_quota_resets_the_next_day() -> None:
    limiter = InMemoryRateLimiter()
    today = date(2026, 8, 11)

    limiter.check_and_increment("ip:1.2.3.4", limit=1, today=today)
    assert limiter.check_and_increment("ip:1.2.3.4", limit=1, today=today + timedelta(days=1)) == 1


def test_yesterdays_counters_are_discarded() -> None:
    """Otherwise the dict grows by one entry per caller per day, forever."""
    limiter = InMemoryRateLimiter()
    today = date(2026, 8, 11)

    limiter.check_and_increment("ip:old", limit=5, today=today)
    limiter.check_and_increment("ip:new", limit=5, today=today + timedelta(days=1))

    assert limiter.usage("ip:old", today=today) == 0


def test_a_zero_limit_refuses_everything() -> None:
    limiter = InMemoryRateLimiter()
    with pytest.raises(RateLimitedError):
        limiter.check_and_increment("ip:1.2.3.4", limit=0)
