"""Shared request dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request

from biovision.api.auth import InvalidTokenError, extract_bearer, verify_token
from biovision.config import Settings
from biovision.errors import ServiceDegradedError
from biovision.limits.ratelimit import InMemoryRateLimiter
from biovision.models.registry import ModelRegistry
from biovision.storage.supabase import AnalysisRepository


@dataclass(frozen=True)
class CurrentUser:
    """An authenticated caller.

    Carries the raw access token as well as the identity: every Supabase call
    made on this caller's behalf is issued under their token so row-level
    security applies. Reaching for the service-role key instead would bypass
    every policy in the database.
    """

    id: str
    email: str | None = None
    access_token: str = ""


def get_settings_dep(request: Request) -> Settings:
    """The settings this app was built with.

    Read off ``app.state`` rather than from the cached singleton so that two apps in
    one test process can hold different configuration.
    """
    settings: Settings = request.app.state.configured_settings
    return settings


def get_registry(request: Request) -> ModelRegistry:
    """The process-wide model registry, loaded once in ``lifespan``.

    A missing registry means startup failed to load the models. 503 is the truthful
    answer: the process is up but cannot serve.
    """
    registry: ModelRegistry | None = getattr(request.app.state, "registry", None)
    if registry is None:
        raise ServiceDegradedError("Models are not loaded. The service is starting or unhealthy.")
    return registry


def get_rate_limiter(request: Request) -> InMemoryRateLimiter:
    limiter: InMemoryRateLimiter = request.app.state.rate_limiter
    return limiter


def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser | None:
    """Authenticated caller, or ``None`` for anonymous demo traffic.

    No token is anonymous access, which is a supported state: the demo link works
    without a sign-in wall. An *invalid* token is different and raises 401 -- a
    client whose session expired should be told, not quietly downgraded to the
    anonymous experience and left wondering where their history went.
    """
    token = extract_bearer(authorization)
    if token is None:
        return None

    settings: Settings = request.app.state.configured_settings
    verified = verify_token(token, settings.supabase_jwt_secret)
    return CurrentUser(id=verified.id, email=verified.email, access_token=token)


def get_repository(request: Request) -> AnalysisRepository:
    """The persistence backend, built once in ``lifespan``."""
    repository: AnalysisRepository = request.app.state.repository
    return repository


def require_user(user: Annotated[CurrentUser | None, Depends(get_current_user)]) -> CurrentUser:
    """A caller who must be signed in.

    Used by the history and deletion endpoints, where there is no meaningful
    anonymous answer -- an anonymous caller has no history to show or erase.
    """
    if user is None:
        raise InvalidTokenError("Sign in to access your own analyses.")
    return user


def client_identity(request: Request) -> str:
    """A stable key for rate limiting.

    Caddy terminates TLS and forwards the real client address in
    ``X-Forwarded-For``. The leftmost entry is used, and it is trusted **only**
    because the proxy is ours and is the sole ingress; the header is trivially
    forged if anything else can reach the app directly.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


def enforce_rate_limit(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    limiter: Annotated[InMemoryRateLimiter, Depends(get_rate_limiter)],
    user: Annotated[CurrentUser | None, Depends(get_current_user)],
) -> None:
    if user is None:
        limiter.check_and_increment(client_identity(request), settings.anon_daily_limit)
    else:
        limiter.check_and_increment(f"user:{user.id}", settings.user_daily_limit)


def resolve_language(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    accept_language: Annotated[str | None, Header()] = None,
) -> str:
    """Pick the VLM description language from ``Accept-Language``.

    Deliberately crude: only ``tr`` and ``en`` are supported, so full RFC 4647
    negotiation would be machinery without a purpose. Note that Phase 6 must
    include the resolved language in the pHash cache key -- otherwise a cached
    Turkish description gets served to a request that asked for English.
    """
    if not accept_language:
        return settings.default_language

    for part in accept_language.split(","):
        tag = part.split(";")[0].strip().lower()
        if tag.startswith("tr"):
            return "tr"
        if tag.startswith("en"):
            return "en"
    return settings.default_language


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
RepositoryDep = Annotated[AnalysisRepository, Depends(get_repository)]
RequiredUserDep = Annotated[CurrentUser, Depends(require_user)]
RegistryDep = Annotated[ModelRegistry, Depends(get_registry)]
UserDep = Annotated[CurrentUser | None, Depends(get_current_user)]
LanguageDep = Annotated[str, Depends(resolve_language)]
