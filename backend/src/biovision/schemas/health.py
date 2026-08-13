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
        description=(
            "'degraded' when any required model failed to load. A degraded response "
            "is served with HTTP 503 so that health checks which only read the status "
            "line reach the same conclusion as a human reading this body."
        )
    )
    version: str
    # None when the registry failed to build: the object that would name the backend
    # is the one that did not load, and guessing a value here reads as a fact.
    model_backend: Literal["mock", "real"] | None
    components: list[ComponentHealth]
    domains_loaded: int
