"""Supabase persistence: analysis rows and stored images.

**Every user-facing call carries the caller's own access token**, so PostgREST
runs it as that user and the row-level security policies apply. The service-role
key bypasses RLS entirely and is used only by the retention job — never on a
request path. Getting this backwards would make the RLS policies decorative.

The repository is a protocol with two implementations. `SupabaseRepository`
talks to Supabase; `NullRepository` accepts writes and discards them, which is
what runs when Supabase is not configured. A missing backend degrades
persistence, it does not break analysis: the API still answers, history is just
empty and says so.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

import httpx

from biovision.schemas.analyze import AnalyzeResponse

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10.0


@runtime_checkable
class AnalysisRepository(Protocol):
    """Persistence for completed analyses, scoped to one caller."""

    @property
    def persists(self) -> bool:
        """Whether writes actually reach a database.

        Part of the protocol rather than something a caller works out from the
        class name: the correction endpoint reports back whether anything was
        stored, and deriving that from `type(repository).__name__` would break
        silently the first time either implementation was renamed.
        """

    def save(
        self,
        response: AnalyzeResponse,
        user_id: str,
        access_token: str,
        phash: str,
        image_bytes: bytes | None = None,
    ) -> None: ...

    def list_for_user(
        self, user_id: str, access_token: str, limit: int = 50
    ) -> list[dict[str, Any]]: ...

    def delete_one(self, analysis_id: UUID, user_id: str, access_token: str) -> bool: ...

    def delete_all(self, user_id: str, access_token: str) -> int: ...

    def find_duplicate(self, phash: str, user_id: str, access_token: str) -> UUID | None: ...

    def find_one(self, analysis_id: UUID, access_token: str) -> dict[str, Any] | None: ...

    def save_correction(
        self,
        correction_id: UUID,
        analysis_id: UUID,
        user_id: str,
        access_token: str,
        payload: dict[str, Any],
    ) -> None: ...


class NullRepository:
    """Accepts everything and stores nothing.

    What runs when Supabase is not configured. History is honestly empty rather
    than fabricated, and an unconfigured backend never blocks an analysis.
    """

    @property
    def persists(self) -> bool:
        return False

    def save(
        self,
        response: AnalyzeResponse,
        user_id: str,
        access_token: str,
        phash: str,
        image_bytes: bytes | None = None,
    ) -> None:
        logger.debug("no storage backend; analysis %s not persisted", response.request_id)

    def list_for_user(
        self, user_id: str, access_token: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        return []

    def delete_one(self, analysis_id: UUID, user_id: str, access_token: str) -> bool:
        return False

    def delete_all(self, user_id: str, access_token: str) -> int:
        return 0

    def find_duplicate(self, phash: str, user_id: str, access_token: str) -> UUID | None:
        return None

    def find_one(self, analysis_id: UUID, access_token: str) -> dict[str, Any] | None:
        return None

    def save_correction(
        self,
        correction_id: UUID,
        analysis_id: UUID,
        user_id: str,
        access_token: str,
        payload: dict[str, Any],
    ) -> None:
        logger.debug("no storage backend; correction for %s not persisted", analysis_id)


class SupabaseRepository:
    """PostgREST + Storage, always under the caller's own token."""

    def __init__(self, url: str, anon_key: str, bucket: str) -> None:
        if not url or not anon_key:
            raise ValueError("SupabaseRepository needs a URL and an anon key")

        self._base = url.rstrip("/")
        self._anon_key = anon_key
        self._bucket = bucket
        self._client = httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)

    @property
    def persists(self) -> bool:
        return True

    # --- writes ---------------------------------------------------------

    def save(
        self,
        response: AnalyzeResponse,
        user_id: str,
        access_token: str,
        phash: str,
        image_bytes: bytes | None = None,
    ) -> None:
        """Persist one analysis, and its stored derivative if there is one.

        Failures are logged and swallowed. A storage outage must not turn a
        successful analysis into a 500 -- the user got their answer, and the
        record is the less important half.
        """
        storage_path: str | None = None

        if image_bytes:
            storage_path = f"{user_id}/{response.request_id}.jpg"
            try:
                self._upload(storage_path, image_bytes, access_token)
            except Exception:
                logger.exception("image upload failed for %s", response.request_id)
                storage_path = None

        try:
            self._insert_row(response, user_id, storage_path, phash, access_token)
        except Exception:
            logger.exception("row insert failed for %s", response.request_id)

    def _upload(self, path: str, payload: bytes, access_token: str) -> None:
        result = self._client.post(
            f"{self._base}/storage/v1/object/{self._bucket}/{path}",
            content=payload,
            headers={
                **self._headers(access_token),
                "content-type": "image/jpeg",
                # Re-analysing the same image should replace the object rather
                # than 409, so a retry is idempotent.
                "x-upsert": "true",
            },
        )
        result.raise_for_status()

    def _insert_row(
        self,
        response: AnalyzeResponse,
        user_id: str,
        storage_path: str | None,
        phash: str,
        access_token: str,
    ) -> None:
        integrity = response.integrity
        privacy = response.privacy

        row = {
            "id": str(response.request_id),
            "user_id": user_id,
            "domain": response.domain,
            "domain_confidence": response.domain_confidence,
            "domain_confidence_calibrated": response.domain_confidence_calibrated,
            "specialist_model": response.specialist_model,
            "calibrated": response.calibrated,
            "findings": [finding.model_dump(mode="json") for finding in response.findings],
            "vlm_description": response.vlm_description,
            "warning": response.warning.value if response.warning else None,
            "phash": phash,
            "exif_datetime": (
                integrity.exif_datetime.isoformat() if integrity.exif_datetime else None
            ),
            "exif_gps_present": integrity.exif_gps_present,
            "device": integrity.device,
            "duplicate_of": str(integrity.duplicate_of) if integrity.duplicate_of else None,
            "faces_blurred": privacy.faces_blurred,
            "plates_blurred": privacy.plates_blurred,
            "face_detector": privacy.face_detector,
            "plate_detector": privacy.plate_detector,
            "storage_path": storage_path,
            "timing_ms": response.timing_ms.model_dump(mode="json"),
        }

        result = self._client.post(
            f"{self._base}/rest/v1/analyses",
            json=row,
            headers={**self._headers(access_token), "Prefer": "return=minimal"},
        )
        result.raise_for_status()

    # --- reads ----------------------------------------------------------

    def list_for_user(
        self, user_id: str, access_token: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """The caller's own analyses, newest first.

        No `user_id` filter in the query on purpose. RLS scopes the result to the
        token's subject, and adding a redundant WHERE clause would suggest the
        filter is what provides the isolation -- inviting a future refactor to
        "simplify" it away.
        """
        result = self._client.get(
            f"{self._base}/rest/v1/analyses",
            params={"select": "*", "order": "created_at.desc", "limit": str(limit)},
            headers=self._headers(access_token),
        )
        result.raise_for_status()
        rows: list[dict[str, Any]] = result.json()
        return rows

    def find_duplicate(self, phash: str, user_id: str, access_token: str) -> UUID | None:
        """An earlier analysis of the same image, within the caller's own rows."""
        try:
            result = self._client.get(
                f"{self._base}/rest/v1/analyses",
                params={
                    "select": "id",
                    "phash": f"eq.{phash}",
                    "order": "created_at.asc",
                    "limit": "1",
                },
                headers=self._headers(access_token),
            )
            result.raise_for_status()
            rows = result.json()
        except Exception:
            # Duplicate detection is advisory. Losing it must not cost the user
            # their analysis.
            logger.exception("duplicate lookup failed for %s", phash)
            return None

        return UUID(rows[0]["id"]) if rows else None

    def find_one(self, analysis_id: UUID, access_token: str) -> dict[str, Any] | None:
        """One analysis by id, or None where the caller cannot see it.

        No `user_id` filter, and none is needed: RLS scopes the read to the
        token's subject, so another user's analysis simply does not come back.
        The caller cannot tell "no such row" from "not yours", which is the
        intended answer -- distinguishing them would confirm the id exists.
        """
        result = self._client.get(
            f"{self._base}/rest/v1/analyses",
            params={"select": "*", "id": f"eq.{analysis_id}", "limit": "1"},
            headers=self._headers(access_token),
        )
        result.raise_for_status()
        rows: list[dict[str, Any]] = result.json()
        return rows[0] if rows else None

    def save_correction(
        self,
        correction_id: UUID,
        analysis_id: UUID,
        user_id: str,
        access_token: str,
        payload: dict[str, Any],
    ) -> None:
        """Insert one correction under the caller's own token.

        The insert policy re-checks that the analysis belongs to the caller, so a
        correction cannot be filed against somebody else's row even if this
        module were handed the wrong id.
        """
        row = {
            "id": str(correction_id),
            "analysis_id": str(analysis_id),
            "user_id": user_id,
            **payload,
        }
        result = self._client.post(
            f"{self._base}/rest/v1/corrections",
            json=row,
            headers={**self._headers(access_token), "Prefer": "return=minimal"},
        )
        result.raise_for_status()

    # --- deletion -------------------------------------------------------

    def delete_one(self, analysis_id: UUID, user_id: str, access_token: str) -> bool:
        """Delete one analysis and its image. Returns whether a row was removed.

        RLS makes another user's row invisible, so a delete targeting one removes
        nothing and reports False -- indistinguishable from "no such analysis",
        which is the correct answer to give.
        """
        path = f"{user_id}/{analysis_id}.jpg"
        self._delete_objects([path], access_token)

        result = self._client.delete(
            f"{self._base}/rest/v1/analyses",
            params={"id": f"eq.{analysis_id}"},
            headers={**self._headers(access_token), "Prefer": "return=representation"},
        )
        result.raise_for_status()
        return bool(result.json())

    def delete_all(self, user_id: str, access_token: str) -> int:
        """Delete every analysis belonging to the caller. Returns the count."""
        rows = self.list_for_user(user_id, access_token, limit=10_000)
        paths = [row["storage_path"] for row in rows if row.get("storage_path")]
        if paths:
            self._delete_objects(paths, access_token)

        result = self._client.delete(
            f"{self._base}/rest/v1/analyses",
            # `id=neq.<impossible uuid>` matches every row the caller can see.
            # PostgREST refuses an unfiltered DELETE, which is a good default.
            params={"id": "neq.00000000-0000-0000-0000-000000000000"},
            headers={**self._headers(access_token), "Prefer": "return=representation"},
        )
        result.raise_for_status()
        deleted: list[dict[str, Any]] = result.json()

        logger.info("deleted %d analyses for user %s on request", len(deleted), user_id)
        return len(deleted)

    def _delete_objects(self, paths: list[str], access_token: str) -> None:
        try:
            self._client.request(
                "DELETE",
                f"{self._base}/storage/v1/object/{self._bucket}",
                json={"prefixes": paths},
                headers=self._headers(access_token),
            )
        except Exception:
            # An orphaned object is cleaned up by the retention job; a failed
            # row delete would leave the user's data visible, which matters more.
            logger.exception("object delete failed for %s", paths)

    # --- plumbing -------------------------------------------------------

    def _headers(self, access_token: str) -> dict[str, str]:
        """Anon key as the API key, the **user's** token as the identity.

        This pair is what makes RLS apply. Substituting the service-role key here
        would bypass every policy in the database.
        """
        return {
            "apikey": self._anon_key,
            "Authorization": f"Bearer {access_token}",
            "content-type": "application/json",
        }

    def close(self) -> None:
        self._client.close()


def build_repository(url: str, anon_key: str, bucket: str) -> AnalysisRepository:
    """A real repository if Supabase is configured, else the null one."""
    if not url or not anon_key:
        logger.warning("Supabase is not configured -- analyses will not be persisted")
        return NullRepository()

    try:
        return SupabaseRepository(url=url, anon_key=anon_key, bucket=bucket)
    except Exception:
        logger.exception("Supabase client failed to initialise; persistence disabled")
        return NullRepository()
