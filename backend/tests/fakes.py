"""A repository and an identity that behave the way Postgres would.

Shared by every contract test that needs a signed-in caller with rows of their
own: history, deletion, and corrections. It lives outside any one test module
because two modules importing a third's fixtures is how `authed` ends up meaning
something slightly different in each.

**The fake is keyed by the access token, not by the `user_id` argument.** That is
the whole point of it. A handler that passed the wrong token -- or reached for
the service-role key, which bypasses RLS -- would silently read the wrong rows
here, exactly as it would in production. Keying on `user_id` would make the fake
agree with a handler that had stopped honouring the caller's identity.

What this can prove is that the API does not undermine RLS. It cannot prove the
policies themselves are right; that needs a real Supabase project and lives in
`tests/integration/test_rls_live.py`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Request

from biovision.api.deps import CurrentUser
from biovision.schemas.analyze import AnalyzeResponse

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
        self.corrections: list[dict[str, Any]] = []

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

    @property
    def persists(self) -> bool:
        return True

    def find_one(self, analysis_id: UUID, access_token: str) -> dict[str, Any] | None:
        """Keyed on the token, like every other read here.

        A handler that reached for a service-role key would find another user's
        row in production and finds nothing here, which is the point.
        """
        for row in self.rows.get(access_token, []):
            if row["id"] == str(analysis_id):
                return row
        return None

    def save_correction(
        self,
        correction_id: UUID,
        analysis_id: UUID,
        user_id: str,
        access_token: str,
        payload: dict[str, Any],
    ) -> None:
        self.corrections.append(
            {"id": str(correction_id), "analysis_id": str(analysis_id), **payload}
        )


def headers_for(user_id: str) -> dict[str, str]:
    """Headers for a user. The fake keys on the token, so it must be distinct."""
    return {"Authorization": f"Bearer token-for-{user_id}"}


def token_for(user_id: str) -> str:
    return f"token-for-{user_id}"


def resolve_user(request: Request) -> CurrentUser | None:
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
