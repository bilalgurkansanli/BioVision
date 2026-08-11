"""The `/v1/domains` contract.

This endpoint is how a client discovers, at runtime, which domains have a specialist
behind them. It reads the domain catalogue -- it never carries a hard-coded list.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DomainInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="Stable identifier returned in AnalyzeResponse.domain.")
    label: str = Field(description="Human-readable name.")
    has_specialist: bool
    specialist_model: str | None = Field(
        default=None, description="Identifier of the specialist, or null."
    )
    calibrated: bool = Field(
        description="Whether analyses in this domain yield calibrated confidences."
    )


class DomainsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domains: list[DomainInfo]
    count: int
    with_specialist: int = Field(
        description="How many domains have a trained specialist. Currently 1 of 4, by design."
    )
