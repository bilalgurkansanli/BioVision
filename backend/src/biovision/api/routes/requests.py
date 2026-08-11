"""Per-user request history.

Sprint 1 ships the contract only. The rows live in Supabase behind row-level
security, so this endpoint has no meaningful implementation until Phase 7.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from biovision.api.deps import SettingsDep
from biovision.errors import NotImplementedYetError
from biovision.schemas.analyze import AnalyzeResponse
from biovision.schemas.errors import ErrorResponse

router = APIRouter(prefix="/v1", tags=["history"])


class RequestHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AnalyzeResponse]
    count: int
    retention_days: int = Field(
        description="Stored images and rows are deleted after this many days."
    )


@router.get(
    "/requests",
    response_model=RequestHistoryResponse,
    responses={501: {"model": ErrorResponse, "description": "Implemented in Phase 7"}},
    summary="The authenticated user's own request history",
)
def list_requests(settings: SettingsDep) -> RequestHistoryResponse:
    """Return the caller's own past analyses.

    Phase 7 implements this against Supabase. Authorisation will be enforced by
    row-level security in Postgres rather than by a filter here: a WHERE clause is
    something a future refactor can drop, whereas an RLS policy denies the read
    outright.

    Until then this returns 501. An empty list would be indistinguishable from a
    user who genuinely has no history, and the project does not get to apply its
    honesty rule only to model outputs.
    """
    raise NotImplementedYetError(
        f"Request history arrives in Phase 7 with Supabase auth and RLS. "
        f"Records will be retained for {settings.retention_days} days."
    )
