"""Row-level security, against a real Supabase project.

`test_history_isolation.py` proves the API does not undermine RLS. **This file
proves RLS works** — that Postgres itself refuses one user's token access to
another user's rows, with no API in the path at all. The two are different
claims, and only this one justifies the README's authorisation guarantee.

Opt-in, because it needs real credentials and writes real rows:

    BIOVISION_TEST_SUPABASE=1 \\
    SUPABASE_URL=... SUPABASE_ANON_KEY=... \\
    BIOVISION_TEST_USER_A_TOKEN=... BIOVISION_TEST_USER_B_TOKEN=... \\
    uv run pytest tests/integration/test_rls_live.py

The two access tokens come from two throwaway accounts in the project (sign in
as each and copy `session.access_token`). Rows created here are deleted in
teardown; if a test fails mid-way the retention job removes the remainder.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.integration

if os.environ.get("BIOVISION_TEST_SUPABASE") != "1":
    pytest.skip(
        "set BIOVISION_TEST_SUPABASE=1 with Supabase credentials to verify RLS",
        allow_module_level=True,
    )

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
TOKEN_A = os.environ.get("BIOVISION_TEST_USER_A_TOKEN", "")
TOKEN_B = os.environ.get("BIOVISION_TEST_USER_B_TOKEN", "")

if not all((URL, ANON_KEY, TOKEN_A, TOKEN_B)):
    pytest.skip("Supabase credentials incomplete", allow_module_level=True)


def _headers(token: str) -> dict[str, str]:
    return {
        "apikey": ANON_KEY,
        "Authorization": f"Bearer {token}",
        "content-type": "application/json",
    }


def _user_id(token: str) -> str:
    import jwt

    claims = jwt.decode(token, options={"verify_signature": False})
    return str(claims["sub"])


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    with httpx.Client(timeout=15.0) as http:
        yield http


@pytest.fixture
def alices_row(client: httpx.Client) -> Iterator[str]:
    """One analysis owned by user A, cleaned up afterwards."""
    row_id = str(uuid4())
    response = client.post(
        f"{URL}/rest/v1/analyses",
        json={
            "id": row_id,
            "user_id": _user_id(TOKEN_A),
            "domain": "building",
            "domain_confidence": 0.8,
            "specialist_model": None,
            "calibrated": False,
            "findings": [],
            "warning": "no_specialist_model_for_domain",
            "phash": "0123456789abcdef",
        },
        headers={**_headers(TOKEN_A), "Prefer": "return=minimal"},
    )
    response.raise_for_status()

    yield row_id

    client.delete(
        f"{URL}/rest/v1/analyses",
        params={"id": f"eq.{row_id}"},
        headers=_headers(TOKEN_A),
    )


# ---------------------------------------------------------------------------
# The guarantee
# ---------------------------------------------------------------------------


def test_user_b_cannot_read_user_as_row(client: httpx.Client, alices_row: str) -> None:
    """The claim the README makes, verified in the database."""
    response = client.get(
        f"{URL}/rest/v1/analyses",
        params={"select": "id", "id": f"eq.{alices_row}"},
        headers=_headers(TOKEN_B),
    )

    assert response.status_code == 200
    assert response.json() == [], "B must not see A's row"


def test_user_a_can_read_their_own_row(client: httpx.Client, alices_row: str) -> None:
    response = client.get(
        f"{URL}/rest/v1/analyses",
        params={"select": "id", "id": f"eq.{alices_row}"},
        headers=_headers(TOKEN_A),
    )

    assert [row["id"] for row in response.json()] == [alices_row]


def test_user_b_cannot_delete_user_as_row(client: httpx.Client, alices_row: str) -> None:
    """The delete is accepted and removes nothing -- the row is invisible."""
    client.delete(
        f"{URL}/rest/v1/analyses",
        params={"id": f"eq.{alices_row}"},
        headers={**_headers(TOKEN_B), "Prefer": "return=representation"},
    )

    still_there = client.get(
        f"{URL}/rest/v1/analyses",
        params={"select": "id", "id": f"eq.{alices_row}"},
        headers=_headers(TOKEN_A),
    ).json()
    assert len(still_there) == 1, "A's row must survive B's delete"


def test_user_b_cannot_insert_a_row_owned_by_user_a(client: httpx.Client) -> None:
    """The insert policy checks `auth.uid() = user_id`, so forging is refused."""
    response = client.post(
        f"{URL}/rest/v1/analyses",
        json={
            "id": str(uuid4()),
            "user_id": _user_id(TOKEN_A),  # not B's own id
            "domain": "building",
            "domain_confidence": 0.8,
            "calibrated": False,
            "findings": [],
            "warning": "no_specialist_model_for_domain",
            "phash": "ffffffffffffffff",
        },
        headers=_headers(TOKEN_B),
    )

    assert response.status_code in (401, 403), response.text


def test_an_anonymous_caller_sees_nothing(client: httpx.Client, alices_row: str) -> None:
    """The anon key alone grants no read access to anybody's analyses."""
    response = client.get(
        f"{URL}/rest/v1/analyses",
        params={"select": "id"},
        headers={"apikey": ANON_KEY, "content-type": "application/json"},
    )

    assert response.status_code in (200, 401)
    if response.status_code == 200:
        assert response.json() == []


def test_the_spend_counter_is_invisible_to_users(client: httpx.Client) -> None:
    """`vlm_spend` has RLS on and no policy, so nothing but the service role
    can touch it. It is an operational limit, not user data."""
    response = client.get(
        f"{URL}/rest/v1/vlm_spend",
        params={"select": "*"},
        headers=_headers(TOKEN_A),
    )

    assert response.status_code in (200, 401, 403)
    if response.status_code == 200:
        assert response.json() == []


# ---------------------------------------------------------------------------
# The honesty contract, enforced by the database
# ---------------------------------------------------------------------------


def test_the_database_refuses_findings_without_a_specialist(client: httpx.Client) -> None:
    """The same invariant the response schema enforces, one layer deeper.

    Even a direct write that bypasses the API cannot record a finding no model
    produced.
    """
    response = client.post(
        f"{URL}/rest/v1/analyses",
        json={
            "id": str(uuid4()),
            "user_id": _user_id(TOKEN_A),
            "domain": "building",
            "domain_confidence": 0.8,
            "specialist_model": None,
            "calibrated": False,
            "findings": [{"type": "crack", "score": 0.9}],
            "phash": "0000000000000000",
        },
        headers=_headers(TOKEN_A),
    )

    assert response.status_code >= 400
    assert "findings_require_a_specialist" in response.text
