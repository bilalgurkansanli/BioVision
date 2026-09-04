"""Per-user request history and deletion.

Authorisation here is row-level security in Postgres, not a filter in this
module. There is deliberately no `user_id` comparison in any handler below: the
caller's own access token is what the database sees, and its policies scope
every read and delete. A WHERE clause is something a future refactor can drop;
an RLS policy denies the query outright.

Deletion ships in v1 rather than v2 because a retention claim without a deletion
path is marketing.

Corrections live here rather than beside `/v1/analyze` for the same three
reasons: they are about a stored analysis, they need the same sign-in, and they
are governed by the same retention window they are allowed to extend.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from biovision.api.deps import RepositoryDep, RequiredUserDep, SettingsDep
from biovision.errors import InvalidCorrectionError, NotFoundError
from biovision.schemas.corrections import CorrectionAccepted, CorrectionRequest
from biovision.schemas.enums import CorrectionKind
from biovision.schemas.errors import ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["history"])

_AUTH_RESPONSES: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Sign-in required"},
}


class HistoryItem(BaseModel):
    """One past analysis, as stored.

    A row, not a re-serialised `AnalyzeResponse`: the two can legitimately differ
    once the schema evolves, and pretending an old row is a current response
    would quietly rewrite history.
    """

    model_config = ConfigDict(extra="allow")

    id: UUID
    created_at: str
    domain: str
    domain_confidence: float
    specialist_model: str | None = None
    calibrated: bool = False
    findings: list[dict[str, Any]] = Field(default_factory=list)
    vlm_description: str | None = None
    warning: str | None = None


class RequestHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[HistoryItem]
    count: int
    retention_days: int = Field(
        description="Stored images and rows are deleted after this many days."
    )


class DeletionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted: int = Field(description="How many analyses were removed.")


@router.get(
    "/requests",
    response_model=RequestHistoryResponse,
    responses=_AUTH_RESPONSES,
    summary="The authenticated user's own request history",
)
async def list_requests(
    user: RequiredUserDep,
    repository: RepositoryDep,
    settings: SettingsDep,
    limit: int = 50,
) -> RequestHistoryResponse:
    """Return the caller's own past analyses, newest first."""
    rows = await run_in_threadpool(
        repository.list_for_user, user.id, user.access_token, min(limit, 200)
    )

    return RequestHistoryResponse(
        items=[HistoryItem.model_validate(row) for row in rows],
        count=len(rows),
        retention_days=settings.retention_days,
    )


@router.delete(
    "/requests/{analysis_id}",
    response_model=DeletionResponse,
    responses={
        **_AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "No such analysis for this caller"},
    },
    summary="Delete one of the caller's analyses",
)
async def delete_request(
    analysis_id: UUID,
    user: RequiredUserDep,
    repository: RepositoryDep,
) -> DeletionResponse:
    """Delete one analysis and its stored image.

    Another user's analysis is invisible under RLS, so a request naming one
    deletes nothing and returns 404 -- identical to a genuinely absent id. That
    is deliberate: distinguishing the two would confirm the id exists.
    """
    removed = await run_in_threadpool(
        repository.delete_one, analysis_id, user.id, user.access_token
    )

    if not removed:
        raise NotFoundError("No such analysis.")

    logger.info("deleted analysis %s on user request", analysis_id)
    return DeletionResponse(deleted=1)


@router.post(
    "/requests/{analysis_id}/corrections",
    response_model=CorrectionAccepted,
    status_code=status.HTTP_201_CREATED,
    responses={
        **_AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "No such analysis for this caller"},
        422: {"model": ErrorResponse, "description": "The correction cannot be true of it"},
    },
    summary="Record what the system got wrong about one analysis",
)
async def file_correction(
    analysis_id: UUID,
    correction: CorrectionRequest,
    user: RequiredUserDep,
    repository: RepositoryDep,
    settings: SettingsDep,
) -> CorrectionAccepted:
    """Record one disagreement, beside the analysis rather than inside it.

    **Sign-in is required, and that is a limitation rather than a preference.**
    Anonymous analyses are never stored, so there is no row to attach a
    correction to and no photograph it could be about. A correction about pixels
    nobody kept is a complaint, not a label.

    The analysis is read back first, for two things no check constraint can do:
    confirm the caller can see it -- which gives 404 rather than a PostgREST
    failure from the insert policy -- and confirm the correction could be true of
    it. Both of the checks below produce rows that satisfy every constraint and
    mean nothing to whoever comes to use them, which is the failure the whole
    table exists to avoid.
    """
    row = await run_in_threadpool(repository.find_one, analysis_id, user.access_token)
    if row is None:
        # Identical to a genuinely absent id: another user's analysis is invisible
        # under RLS, and distinguishing the two would confirm it exists.
        raise NotFoundError("No such analysis.")

    findings = row.get("findings") or []
    index = correction.finding_index
    if index is not None and index >= len(findings):
        raise InvalidCorrectionError(
            f"This analysis has {len(findings)} finding(s), so index {index} names nothing."
        )
    if correction.kind is CorrectionKind.NOTHING_WRONG and not findings:
        raise InvalidCorrectionError(
            "This analysis reported no damage, so there is nothing to disagree with."
        )

    # A row with no `storage_path` never had its image kept. Consent to retain
    # something that does not exist is not consent to anything, and echoing it
    # back as granted would be a receipt for a thing that did not happen.
    retained = correction.retain_image and row.get("storage_path") is not None

    correction_id = uuid4()
    payload: dict[str, Any] = {
        "kind": correction.kind.value,
        "finding_index": correction.finding_index,
        "expected_type": correction.expected_type.value if correction.expected_type else None,
        "note": _note_with_severity(correction),
        "retain_image": retained,
    }

    await run_in_threadpool(
        repository.save_correction,
        correction_id,
        analysis_id,
        user.id,
        user.access_token,
        payload,
    )

    logger.info(
        "correction filed analysis=%s kind=%s retained=%s stored=%s",
        analysis_id,
        correction.kind.value,
        retained,
        repository.persists,
    )
    return CorrectionAccepted(
        id=correction_id,
        stored=repository.persists,
        image_retained=retained,
        retention_days=(
            settings.donated_retention_days if retained else settings.retention_days
        ),
    )


def _note_with_severity(correction: CorrectionRequest) -> str | None:
    """Fold `expected_severity` into the note, prefixed so it can be parsed back.

    The table has no column for it, and adding one would be the wrong shape: a
    severity correction is the only kind whose expected value is a band, and
    `severity_calibrated` is false precisely because nobody has ground truth for
    the bands. Rather than a column that stays empty on four kinds out of five,
    the value rides in the note with a marker -- visible to the person reading
    these rows, and recoverable if it ever earns a column of its own.

    Written out rather than dropped: silently discarding the one field the user
    was asked to supply is how a form ends up collecting nothing.
    """
    if correction.expected_severity is None:
        return correction.note
    marker = f"[expected_severity={correction.expected_severity.value}]"
    return f"{marker} {correction.note}" if correction.note else marker


@router.delete(
    "/requests",
    response_model=DeletionResponse,
    responses=_AUTH_RESPONSES,
    status_code=status.HTTP_200_OK,
    summary="Delete every analysis belonging to the caller",
)
async def delete_all_requests(
    user: RequiredUserDep,
    repository: RepositoryDep,
) -> DeletionResponse:
    """Erase the caller's history and every image stored with it.

    The "delete all my data" path. It exists in v1 because the README's retention
    claim is only meaningful alongside a way to act on it sooner.
    """
    count = await run_in_threadpool(repository.delete_all, user.id, user.access_token)

    logger.info("deleted all %d analyses for user %s on request", count, user.id)
    return DeletionResponse(deleted=count)
