"""A single error envelope for every failure the API can produce."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from biovision.schemas.enums import ErrorCode


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str = Field(description="Human-readable explanation. Safe to display to a user.")
    request_id: UUID | None = Field(
        default=None, description="Correlates this failure with the server logs."
    )


class ErrorResponse(BaseModel):
    """Every non-2xx response from this API has exactly this body."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail
