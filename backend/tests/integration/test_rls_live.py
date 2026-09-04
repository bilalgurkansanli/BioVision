"""Row-level security, against a real Supabase project.

`test_history_isolation.py` proves the API does not undermine RLS. **This file
proves RLS works** — that Postgres itself refuses one user's token access to
another user's rows, with no API in the path at all. The two are different
claims, and only this one justifies the README's authorisation guarantee.

Opt-in, because it needs a running database and writes real rows:

    BIOVISION_TEST_SUPABASE=1 \\
    SUPABASE_URL=... SUPABASE_ANON_KEY=... \\
    BIOVISION_TEST_USER_A_TOKEN=... BIOVISION_TEST_USER_B_TOKEN=... \\
    uv run pytest tests/integration/test_rls_live.py

**A hosted project is not required.** `scripts/rls_check.py` brings up the local
Supabase stack, applies the migrations, creates two throwaway users and runs
this file — see `docs/DEPLOY.md`. A hosted project works identically; the two
access tokens then come from two accounts in it (sign in as each and copy
`session.access_token`).

Rows created here are deleted in teardown; if a test fails mid-way the retention
job removes the remainder.

**What running it found.** The policies were correct and the migration was still
wrong: it granted nothing. Postgres checks GRANT before it checks any policy, so
every request — including a user reading their own rows — was refused with
`permission denied for table analyses`, and the policies never executed. A hosted
project's default privileges would have hidden that. The suite passing is the
only reason the README states the authorisation guarantee as demonstrated.
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
            "domain": "other",
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
            "domain": "other",
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
            "domain": "other",
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


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------
#
# The API refuses a correction against an analysis the caller cannot see, and
# `test_corrections.py` proves it does. That is the API's half. These are the
# database's half: a caller who bypasses the API entirely still cannot file a
# correction against somebody else's analysis, and cannot write one that would
# be meaningless to whoever comes to use the rows.


def _correction(analysis_id: str, user_token: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": str(uuid4()),
        "analysis_id": analysis_id,
        "user_id": _user_id(user_token),
        "kind": "missed_damage",
        "finding_index": None,
        "expected_type": "torn",
        "retain_image": False,
    }
    row.update(overrides)
    return row


def test_user_a_can_correct_their_own_analysis(
    client: httpx.Client, alices_row: str
) -> None:
    response = client.post(
        f"{URL}/rest/v1/corrections",
        json=_correction(alices_row, TOKEN_A),
        headers={**_headers(TOKEN_A), "Prefer": "return=minimal"},
    )

    assert response.status_code < 300, response.text


def test_user_b_cannot_correct_user_as_analysis(
    client: httpx.Client, alices_row: str
) -> None:
    """The insert policy re-checks ownership of the analysis, not just of the row.

    Without that clause B could file corrections against A's analyses by naming
    the id -- invisible to B under RLS, but an id is guessable and the write
    would succeed.
    """
    response = client.post(
        f"{URL}/rest/v1/corrections",
        json=_correction(alices_row, TOKEN_B),
        headers=_headers(TOKEN_B),
    )

    assert response.status_code >= 400, response.text


def test_a_correction_cannot_be_filed_in_somebody_elses_name(
    client: httpx.Client, alices_row: str
) -> None:
    """B, writing a row that claims to be A's."""
    response = client.post(
        f"{URL}/rest/v1/corrections",
        json=_correction(alices_row, TOKEN_A),  # user_id = A
        headers=_headers(TOKEN_B),  # written by B
    )

    assert response.status_code >= 400, response.text


def test_the_database_refuses_a_correction_that_contradicts_itself(
    client: httpx.Client, alices_row: str
) -> None:
    """`finding_index` on a kind that is about the whole result.

    The API rejects this with a sentence; the constraint is what makes the row
    unrepresentable even for a writer that never met the API.
    """
    response = client.post(
        f"{URL}/rest/v1/corrections",
        json=_correction(alices_row, TOKEN_A, kind="missed_damage", finding_index=0),
        headers=_headers(TOKEN_A),
    )

    assert response.status_code >= 400
    assert "finding_kinds_name_a_finding" in response.text


def test_a_correction_disappears_with_the_analysis_it_describes(
    client: httpx.Client, alices_row: str
) -> None:
    """Deleting the analysis is how consent is withdrawn, so the cascade matters.

    A correction that outlived its analysis would keep a retention flag pointing
    at a photograph the user asked to have deleted.
    """
    client.post(
        f"{URL}/rest/v1/corrections",
        json=_correction(alices_row, TOKEN_A, retain_image=True),
        headers={**_headers(TOKEN_A), "Prefer": "return=minimal"},
    ).raise_for_status()

    client.delete(
        f"{URL}/rest/v1/analyses",
        params={"id": f"eq.{alices_row}"},
        headers=_headers(TOKEN_A),
    ).raise_for_status()

    remaining = client.get(
        f"{URL}/rest/v1/corrections",
        params={"select": "id", "analysis_id": f"eq.{alices_row}"},
        headers=_headers(TOKEN_A),
    )
    assert remaining.status_code == 200
    assert remaining.json() == []
