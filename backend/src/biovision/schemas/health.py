"""The `/health` contract.

`/health` reports *which models are loaded*, not merely that the process is alive.
A process that answers HTTP while its router failed to load is not healthy, and a
bare `{"status": "ok"}` would hide exactly that.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ComponentHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    ready: bool
    detail: str | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"] = Field(
        description="'degraded' when any required model failed to load."
    )
    version: str
    model_backend: Literal["mock", "real"]
    components: list[ComponentHealth]
    domains_loaded: int
