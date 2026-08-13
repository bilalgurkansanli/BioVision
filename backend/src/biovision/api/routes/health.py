"""Liveness and model-load reporting."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from biovision import __version__
from biovision.models.registry import ModelRegistry
from biovision.schemas.health import ComponentHealth, HealthResponse

router = APIRouter(tags=["ops"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness and model state",
    responses={503: {"model": HealthResponse, "description": "A required model is not loaded."}},
)
def health(request: Request, response: Response) -> HealthResponse:
    """Report per-model readiness, not just process liveness.

    **Degraded returns 503, and the full body comes with it.**

    This returned 200 when degraded until the container was first run, on the
    reasoning that a load balancer needs the body to decide and a non-200 would
    hide the detail. Running it showed both halves of that to be wrong. Docker's
    healthcheck never reads the body -- it reads the exit status of a request --
    so a degraded container with no models loaded was reported `healthy`, and
    Caddy would have routed traffic to it. Meanwhile 503 hides nothing: the body
    below is identical either way, and `curl` still prints it.

    So the status line now carries the same answer the body does. A machine that
    only reads the code, and a human who reads the JSON, reach the same
    conclusion -- which is the property that was missing.
    """
    registry: ModelRegistry | None = getattr(request.app.state, "registry", None)

    if registry is None:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="degraded",
            version=__version__,
            # The requested backend is unknown here -- the registry that would name
            # it is the thing that failed. Reporting "mock" was a guess that read as
            # a fact, and a misleading one: it made a failed real load look like a
            # deliberate mock deployment.
            model_backend=None,
            components=[
                ComponentHealth(name="registry", ready=False, detail="models failed to load")
            ],
            domains_loaded=0,
        )

    if not registry.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if registry.ready else "degraded",
        version=__version__,
        model_backend=registry.backend,
        components=registry.components(),
        domains_loaded=len(registry.catalog),
    )
