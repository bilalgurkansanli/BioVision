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


# ---------------------------------------------------------------------------
# X-Forwarded-For, and why the rightmost entry is the only safe one
# ---------------------------------------------------------------------------


from typing import ClassVar  # noqa: E402


def test_a_forged_forwarded_header_cannot_mint_a_new_identity() -> None:
    """The audit finding, as a test.

    `X-Forwarded-For` is appended to by each proxy, so a client that sends one
    arrives as `<what they sent>, <what our proxy saw>`. Reading the leftmost
    entry -- the obvious reading -- lets a caller pick their own rate-limit key
    and issue unlimited requests against CPU inference by varying it per call.

    Only the rightmost entry was written by our own proxy.
    """
    from starlette.datastructures import Headers

    from biovision.api.deps import client_identity

    class FakeRequest:
        def __init__(self, forwarded: str) -> None:
            self.headers = Headers({"x-forwarded-for": forwarded})
            self.client = None

    # What our proxy appends is always last, whatever the client prefixed.
    for forged in (
        "8.8.8.8, 203.0.113.9",
        "1.2.3.4, 5.6.7.8, 203.0.113.9",
        "not-an-ip, 203.0.113.9",
        "  , 203.0.113.9",
    ):
        identity = client_identity(FakeRequest(forged))  # type: ignore[arg-type]
        assert identity == "ip:203.0.113.9", f"{forged!r} escaped the real identity"

    # And a single entry is what Caddy writes when it overwrites the header,
    # which is how infra/Caddyfile is configured.
    assert client_identity(FakeRequest("203.0.113.9")) == "ip:203.0.113.9"  # type: ignore[arg-type]


def test_a_direct_connection_falls_back_to_the_socket_address() -> None:
    from biovision.api.deps import client_identity

    class FakeClient:
        host = "198.51.100.7"

    class FakeRequest:
        headers: ClassVar[dict[str, str]] = {}
        client = FakeClient()

    assert client_identity(FakeRequest()) == "ip:198.51.100.7"  # type: ignore[arg-type]
