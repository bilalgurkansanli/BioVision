"""Per-user request history and deletion.

Authorisation here is row-level security in Postgres, not a filter in this
module. There is deliberately no `user_id` comparison in any handler below: the
caller's own access token is what the database sees, and its policies scope
every read and delete. A WHERE clause is something a future refactor can drop;
an RLS policy denies the query outright.

Deletion ships in v1 rather than v2 because a retention claim without a deletion
path is marketing.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from biovision.api.deps import RepositoryDep, RequiredUserDep, SettingsDep
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
        from biovision.errors import NotFoundError

        raise NotFoundError("No such analysis.")

    logger.info("deleted analysis %s on user request", analysis_id)
    return DeletionResponse(deleted=1)


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
