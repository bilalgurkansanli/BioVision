"""FastAPI application entry point.

Model loading happens once, in ``lifespan``, and never inside a request handler.

    +---------------------------------------------------------------+
    |  MEMORY: each uvicorn worker loads its OWN copy of every model. |
    |  On the 8 GB production box, TWO workers is the ceiling.        |
    |  Four workers exhausts RAM and takes the machine down.          |
    +---------------------------------------------------------------+

This constraint is repeated at every place workers are configured:
`infra/docker-compose.prod.yml` and the Dockerfile CMD.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from biovision import __version__
from biovision.api.errors import register_error_handlers
from biovision.api.routes import analyze, claims, domains, health, requests
from biovision.config import Settings, get_settings
from biovision.limits.ratelimit import InMemoryRateLimiter
from biovision.logging import configure_logging
from biovision.models.registry import build_registry
from biovision.storage.supabase import build_repository

logger = logging.getLogger(__name__)

DESCRIPTION = """
Damage analysis that reports what it cannot do.

An uploaded photograph passes a **gate** (is this a damage photo at all?), then a
**router** (which domain?), and then either a **domain specialist** -- if one has
been trained -- or an honest fallback that returns no findings and says why.

Confidence values are either calibrated and marked `calibrated: true`, or not
calibrated and marked `false`. There is no third state.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Set by create_app. Tests build an app with their own Settings, so nothing here
    # may reach for the cached process-wide singleton.
    settings: Settings = app.state.configured_settings
    configure_logging(level=settings.log_level, json_output=settings.env == "production")

    logger.info("starting BioVision %s (env=%s)", __version__, settings.env)

    app.state.rate_limiter = InMemoryRateLimiter()
    app.state.repository = build_repository(
        url=settings.supabase_url,
        anon_key=settings.supabase_anon_key,
        bucket=settings.supabase_storage_bucket,
    )
    app.state.registry = None

    try:
        app.state.registry = build_registry(settings)
        logger.info("models loaded, backend=%s", settings.model_backend)
    except Exception:
        # Startup continues so /health can report *why* the service is unusable.
        # Exiting here would leave an operator with a restart loop and no diagnosis.
        logger.exception("model loading failed -- /health will report degraded")

    yield

    logger.info("shutting down")
    app.state.registry = None


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    ``settings`` is injectable so tests can construct an app against a temporary
    domains file or a different model backend without touching the environment.
    """
    resolved = settings or get_settings()

    app = FastAPI(
        title="BioVision",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    # The single runtime source of settings. `get_settings_dep` reads it back off
    # app.state rather than calling the cached singleton, which is what lets a test
    # point one app at a temporary domains.yaml while another uses the real one.
    app.state.configured_settings = resolved

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origin_list,
        # No cookies are used -- the browser sends a bearer token it holds itself.
        # Credentials mode would additionally forbid a wildcard origin, which is a
        # guard we do not need because the origin list is explicit either way.
        allow_credentials=False,
        # DELETE was missing until an audit sent a real preflight. Every deletion
        # endpoint answered 400 from the browser, which meant the one thing a user
        # is entitled to do with their own data -- remove it -- could not be done
        # from the UI at all. The history page's delete button had never worked.
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept-Language"],
    )

    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(domains.router)
    app.include_router(analyze.router)
    app.include_router(requests.router)
    app.include_router(claims.router)

    return app


app = create_app()
