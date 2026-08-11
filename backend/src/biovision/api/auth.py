"""Supabase JWT verification.

Supabase issues HS256 tokens signed with the project's JWT secret, so verifying
one is local: no round trip to Supabase on every request, which would put a
network hop and a third-party outage into the auth path.

Anonymous access is a first-class state, not a failure. `/v1/analyze` serves
unauthenticated callers so an executive opening the demo link is not met with a
sign-in wall — they simply cannot reach the paid fallback or their own history.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from biovision.errors import BioVisionError
from biovision.schemas.enums import ErrorCode

logger = logging.getLogger(__name__)

#: Supabase signs project JWTs with this algorithm. Pinned rather than read from
#: the token: accepting the header's `alg` is how `alg: none` and
#: HS256-verified-with-a-public-key attacks work.
ALGORITHM = "HS256"

#: Supabase sets `aud: "authenticated"` on user tokens. Anon-key tokens carry
#: `aud: "anon"` and must not authenticate anyone.
EXPECTED_AUDIENCE = "authenticated"


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None = None


class InvalidTokenError(BioVisionError):
    """A token was supplied and is not usable.

    Distinct from no token at all, which is anonymous access and not an error.
    A bad token is reported rather than silently downgraded — a client whose
    session expired should be told, not quietly served the anonymous experience.
    """

    code = ErrorCode.UNAUTHENTICATED
    status_code = 401


def verify_token(token: str, jwt_secret: str) -> AuthenticatedUser:
    """Verify a Supabase access token and return its subject.

    Raises:
        InvalidTokenError: expired, malformed, wrongly signed, or wrong audience.
    """
    if not jwt_secret:
        # Refusing is the safe direction: without a secret nothing can be
        # verified, and treating every token as valid would be catastrophic.
        logger.error("SUPABASE_JWT_SECRET is not configured; refusing to accept tokens")
        raise InvalidTokenError("Authentication is not configured on this server.")

    import jwt

    try:
        claims = jwt.decode(
            token,
            jwt_secret,
            algorithms=[ALGORITHM],
            audience=EXPECTED_AUDIENCE,
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("Your session has expired. Sign in again.") from exc
    except jwt.InvalidAudienceError as exc:
        raise InvalidTokenError("This token is not a user access token.") from exc
    except jwt.InvalidTokenError as exc:
        logger.info("rejected token: %s", exc)
        raise InvalidTokenError("Invalid authentication token.") from exc

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise InvalidTokenError("Token is missing a subject.")

    email = claims.get("email")
    return AuthenticatedUser(id=subject, email=email if isinstance(email, str) else None)


def extract_bearer(header_value: str | None) -> str | None:
    """Pull the token out of an ``Authorization: Bearer <token>`` header."""
    if not header_value:
        return None

    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()
