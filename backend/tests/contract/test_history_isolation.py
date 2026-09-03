"""History, deletion, and the isolation between users.

**What these tests can and cannot prove.** They exercise the API's half of the
contract: that every call is issued under the caller's own token, that no handler
substitutes the service-role key, and that one user's token never produces
another user's rows *through this API*. They run against a fake repository, so
they cannot prove the RLS policies themselves are correct — that requires a real
Supabase project and lives in `test_rls_live.py`, which is skipped without one.

The distinction matters. Passing here means the API does not undermine RLS; it
does not mean RLS is doing its job.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from httpx import Response

from biovision.api.deps import CurrentUser, get_current_user, get_repository
from biovision.schemas.analyze import AnalyzeResponse
from tests.conftest import Steer, make_png

ALICE = "alice-user-id"
BOB = "bob-user-id"


class FakeRepository:
    """A repository that enforces ownership the way RLS would.

    Deliberately keyed by the **access token**, not by the `user_id` argument.
    A handler that passed the wrong token — or reached for a service-role key —
    would silently read the wrong rows here, exactly as it would in production.
    """

    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {}
        self.saved_phashes: list[str] = []
        self.saved_images: list[bytes] = []

    def save(
        self,
        response: AnalyzeResponse,
        user_id: str,
        access_token: str,
        phash: str,
        image_bytes: bytes | None = None,
    ) -> None:
        self.rows.setdefault(access_token, []).append(
            {
                "id": str(response.request_id),
                "created_at": "2026-08-11T12:00:00Z",
                "domain": response.domain,
                "domain_confidence": response.domain_confidence,
                "specialist_model": response.specialist_model,
                "calibrated": response.calibrated,
                "findings": [f.model_dump(mode="json") for f in response.findings],
                "vlm_description": response.vlm_description,
                "warning": response.warning.value if response.warning else None,
            }
        )
        self.saved_phashes.append(phash)
        if image_bytes:
            self.saved_images.append(image_bytes)

    def list_for_user(
        self, user_id: str, access_token: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        return list(self.rows.get(access_token, []))[:limit]

    def delete_one(self, analysis_id: UUID, user_id: str, access_token: str) -> bool:
        owned = self.rows.get(access_token, [])
        remaining = [row for row in owned if row["id"] != str(analysis_id)]
        if len(remaining) == len(owned):
            return False
        self.rows[access_token] = remaining
        return True

    def delete_all(self, user_id: str, access_token: str) -> int:
        count = len(self.rows.get(access_token, []))
        self.rows[access_token] = []
        return count

    def find_duplicate(self, phash: str, user_id: str, access_token: str) -> UUID | None:
        return None


@pytest.fixture
def repository(app: FastAPI) -> FakeRepository:
    fake = FakeRepository()
    app.dependency_overrides[get_repository] = lambda: fake
    return fake


def _as(user_id: str) -> dict[str, str]:
    """Headers for a user. The fake keys on the token, so it must be distinct."""
    return {"Authorization": f"Bearer token-for-{user_id}"}


def _token(user_id: str) -> str:
    return f"token-for-{user_id}"


def _resolve_user(request: Request) -> CurrentUser | None:
    """Resolve a bearer token to a user without a real Supabase secret.

    Module-level because FastAPI resolves the annotation at override time, and a
    `Request` imported inside a fixture body is unresolvable under
    `from __future__ import annotations` -- FastAPI then treats it as a query
    parameter and every request 415s.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer token-for-"):
        return None
    user_id = header.split("token-for-", 1)[1]
    return CurrentUser(id=user_id, email=None, access_token=f"token-for-{user_id}")


@pytest.fixture
def authed(app: FastAPI) -> None:
    app.dependency_overrides[get_current_user] = _resolve_user


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


def test_a_user_sees_only_their_own_history(
    client: TestClient, steer: Steer, repository: FakeRepository, authed: None
) -> None:
    """The headline authorisation claim."""
    steer(forced_domain="vehicle", forced_confidence=0.93)

    client.post(
        "/v1/analyze", files={"image": ("a.png", make_png(1), "image/png")}, headers=_as(ALICE)
    )
    client.post(
        "/v1/analyze", files={"image": ("b.png", make_png(2), "image/png")}, headers=_as(BOB)
    )

    alice = client.get("/v1/requests", headers=_as(ALICE)).json()
    bob = client.get("/v1/requests", headers=_as(BOB)).json()

    assert alice["count"] == 1
    assert bob["count"] == 1
    assert alice["items"][0]["id"] != bob["items"][0]["id"]


def test_one_user_cannot_delete_anothers_analysis(
    client: TestClient, steer: Steer, repository: FakeRepository, authed: None
) -> None:
    """404, not 403.

    Under RLS another user's row is invisible rather than forbidden, so "not
    yours" and "not there" are the same answer. Distinguishing them would confirm
    the id exists.
    """
    steer(forced_domain="vehicle", forced_confidence=0.93)
    client.post(
        "/v1/analyze", files={"image": ("a.png", make_png(3), "image/png")}, headers=_as(ALICE)
    )
    alice_id = repository.rows[_token(ALICE)][0]["id"]

    response = client.delete(f"/v1/requests/{alice_id}", headers=_as(BOB))

    assert response.status_code == 404
    assert len(repository.rows[_token(ALICE)]) == 1, "Alice's row must survive"


def test_delete_all_touches_only_the_caller(
    client: TestClient, steer: Steer, repository: FakeRepository, authed: None
) -> None:
    steer(forced_domain="vehicle", forced_confidence=0.93)
    for seed, user in ((4, ALICE), (5, ALICE), (6, BOB)):
        client.post(
            "/v1/analyze",
            files={"image": (f"{seed}.png", make_png(seed), "image/png")},
            headers=_as(user),
        )

    response = client.delete("/v1/requests", headers=_as(ALICE))

    assert response.status_code == 200
    assert response.json()["deleted"] == 2
    assert repository.rows[_token(ALICE)] == []
    assert len(repository.rows[_token(BOB)]) == 1


# ---------------------------------------------------------------------------
# Persistence behaviour
# ---------------------------------------------------------------------------


def test_anonymous_analyses_are_not_stored(
    client: TestClient, steer: Steer, repository: FakeRepository, authed: None
) -> None:
    """Nobody could retrieve or delete them, so keeping the image would be
    collecting data with no owner and no purpose."""
    steer(forced_domain="vehicle", forced_confidence=0.93)

    client.post("/v1/analyze", files={"image": ("a.png", make_png(7), "image/png")})

    assert repository.rows == {}
    assert repository.saved_images == []


def test_the_stored_image_is_the_redacted_derivative(
    client: TestClient, steer: Steer, repository: FakeRepository, authed: None
) -> None:
    """Not the upload. The original never reaches storage."""
    steer(forced_domain="vehicle", forced_confidence=0.93)
    original = make_png(8)

    client.post(
        "/v1/analyze", files={"image": ("a.png", original, "image/png")}, headers=_as(ALICE)
    )

    stored = repository.saved_images[0]
    assert stored != original
    assert stored.startswith(b"\xff\xd8\xff"), "storage is always JPEG"


def test_the_real_perceptual_hash_is_persisted(
    client: TestClient, steer: Steer, repository: FakeRepository, authed: None
) -> None:
    """A synthetic value would silently poison duplicate detection."""
    steer(forced_domain="vehicle", forced_confidence=0.93)

    client.post(
        "/v1/analyze", files={"image": ("a.png", make_png(9), "image/png")}, headers=_as(ALICE)
    )

    phash = repository.saved_phashes[0]
    assert len(phash) == 16
    int(phash, 16)  # must be hex


def test_history_reports_the_retention_window(
    client: TestClient, repository: FakeRepository, authed: None, settings: object
) -> None:
    """A retention claim the client can display without hard-coding it."""
    body = client.get("/v1/requests", headers=_as(ALICE)).json()

    assert body["retention_days"] == 7


def test_deleting_a_nonexistent_analysis_is_404(
    client: TestClient, repository: FakeRepository, authed: None
) -> None:
    response = client.delete(f"/v1/requests/{uuid4()}", headers=_as(ALICE))

    assert response.status_code == 404


def test_every_history_endpoint_requires_sign_in(client: TestClient) -> None:
    assert client.get("/v1/requests").status_code == 401
    assert client.delete("/v1/requests").status_code == 401
    assert client.delete(f"/v1/requests/{uuid4()}").status_code == 401


# ---------------------------------------------------------------------------
# The operator exemption, through the API
# ---------------------------------------------------------------------------


def test_a_listed_account_keeps_working_past_the_daily_limit(
    steer: Steer, repository: FakeRepository
) -> None:
    """The exemption has to hold where it is actually applied.

    Parsing the setting correctly is a separate question from the dependency
    honouring it, and only this reaches the code path a request takes.
    """
    from pathlib import Path

    from biovision.config import Settings
    from biovision.main import create_app

    owner = "owner@example.com"
    settings = Settings(
        env="development",
        model_backend="mock",
        domains_file=Path("src/biovision/domains/domains.yaml"),
        vlm_enabled=False,
        user_daily_limit=2,
        unlimited_emails=owner,
        _env_file=None,  # type: ignore[call-arg]
    )
    application = create_app(settings)

    def resolve(request: Request) -> CurrentUser | None:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer as-"):
            return None
        email = header.split("as-", 1)[1]
        return CurrentUser(id=f"id-of-{email}", email=email, access_token=header)

    application.dependency_overrides[get_current_user] = resolve
    application.dependency_overrides[get_repository] = lambda: repository

    with TestClient(application) as client:
        steer(forced_domain="vehicle", forced_confidence=0.93)

        def upload(email: str, seed: int) -> int:
            # Annotated rather than returned straight through: `TestClient.post`
            # resolves to `Any` under the installed starlette/httpx pair, so the
            # status code arrived untyped and `uv run mypy` failed on it -- which
            # broke the whole check chain in README section 10, because `&&`
            # meant `pytest` never ran. Naming the real type fixes it without a
            # cast; httpx is already a declared dependency.
            response: Response = client.post(
                "/v1/analyze",
                files={"image": (f"{seed}.png", make_png(seed), "image/png")},
                headers={"Authorization": f"Bearer as-{email}"},
            )
            return response.status_code

        # A limited account is cut off on the third request.
        limited = [upload("someone@example.com", seed) for seed in (10, 11, 12)]
        assert limited[:2] == [200, 200]
        assert limited[2] == 429, "the daily limit must still apply to everyone else"

        # The listed account keeps going well past it.
        assert [upload(owner, seed) for seed in (20, 21, 22, 23, 24)] == [200] * 5

        # Case is not a way to lose the exemption.
        assert upload(owner.upper(), 25) == 200
