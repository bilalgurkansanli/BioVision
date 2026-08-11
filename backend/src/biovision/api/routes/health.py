"""Liveness and model-load reporting."""

from __future__ import annotations

from fastapi import APIRouter, Request

from biovision import __version__
from biovision.models.registry import ModelRegistry
from biovision.schemas.health import ComponentHealth, HealthResponse

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=HealthResponse, summary="Liveness and model state")
def health(request: Request) -> HealthResponse:
    """Report per-model readiness, not just process liveness.

    A process that answers HTTP while its router failed to load is not healthy, and
    a bare ``{"status": "ok"}`` would hide exactly that. This endpoint deliberately
    returns 200 even when degraded: the load balancer needs the body to decide, and
    a non-200 would make the failure invisible to whoever is debugging it.
    """
    registry: ModelRegistry | None = getattr(request.app.state, "registry", None)

    if registry is None:
        return HealthResponse(
            status="degraded",
            version=__version__,
            model_backend="mock",
            components=[
                ComponentHealth(name="registry", ready=False, detail="models failed to load")
            ],
            domains_loaded=0,
        )

    return HealthResponse(
        status="ok" if registry.ready else "degraded",
        version=__version__,
        model_backend=registry.backend,
        components=registry.components(),
        domains_loaded=len(registry.catalog),
    )
