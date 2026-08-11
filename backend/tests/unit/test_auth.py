"""Supabase JWT verification.

The whole authorisation model rests on this: if a forged token authenticates,
row-level security is scoping queries to an attacker-chosen identity.
"""

from __future__ import annotations

import time

import jwt
import pytest

from biovision.api.auth import (
    ALGORITHM,
    EXPECTED_AUDIENCE,
    InvalidTokenError,
    extract_bearer,
    verify_token,
)

SECRET = "test-secret-not-a-real-one"
OTHER_SECRET = "a-different-secret"


def make_token(
    secret: str = SECRET,
    subject: str = "user-123",
    audience: str = EXPECTED_AUDIENCE,
    expires_in: int = 3600,
    algorithm: str = ALGORITHM,
    **extra: object,
) -> str:
    claims: dict[str, object] = {
        "sub": subject,
        "aud": audience,
        "exp": int(time.time()) + expires_in,
        "iat": int(time.time()),
        **extra,
    }
    return jwt.encode(claims, secret, algorithm=algorithm)


# ---------------------------------------------------------------------------
# Accepting a valid token
# ---------------------------------------------------------------------------


def test_a_valid_token_yields_its_subject() -> None:
    user = verify_token(make_token(email="alice@example.com"), SECRET)

    assert user.id == "user-123"
    assert user.email == "alice@example.com"


def test_a_token_without_an_email_is_still_valid() -> None:
    """Not every Supabase provider supplies one."""
    assert verify_token(make_token(), SECRET).email is None


# ---------------------------------------------------------------------------
# Rejecting everything else
# ---------------------------------------------------------------------------


def test_a_token_signed_with_another_secret_is_rejected() -> None:
    """The forged-token case. Everything else is downstream of this."""
    with pytest.raises(InvalidTokenError):
        verify_token(make_token(secret=OTHER_SECRET), SECRET)


def test_an_expired_token_is_rejected() -> None:
    with pytest.raises(InvalidTokenError, match="expired"):
        verify_token(make_token(expires_in=-60), SECRET)


def test_an_anon_key_token_cannot_authenticate_a_user() -> None:
    """Supabase's anon key is itself a JWT, signed with the same secret.

    Without the audience check it would verify cleanly and authenticate whatever
    subject it carries -- turning a public key into an authentication bypass.
    """
    with pytest.raises(InvalidTokenError, match="not a user access token"):
        verify_token(make_token(audience="anon"), SECRET)


def test_a_token_without_an_expiry_is_rejected() -> None:
    """A token that never expires cannot be revoked by waiting."""
    token = jwt.encode({"sub": "user-123", "aud": EXPECTED_AUDIENCE}, SECRET, algorithm=ALGORITHM)

    with pytest.raises(InvalidTokenError):
        verify_token(token, SECRET)


def test_a_token_without_a_subject_is_rejected() -> None:
    token = jwt.encode(
        {"aud": EXPECTED_AUDIENCE, "exp": int(time.time()) + 3600}, SECRET, algorithm=ALGORITHM
    )

    with pytest.raises(InvalidTokenError):
        verify_token(token, SECRET)


def test_an_unsigned_token_is_rejected() -> None:
    """`alg: none` is the classic JWT bypass; the algorithm is pinned, not read."""
    token = jwt.encode(
        {"sub": "attacker", "aud": EXPECTED_AUDIENCE, "exp": int(time.time()) + 3600},
        key="",
        algorithm="none",
    )

    with pytest.raises(InvalidTokenError):
        verify_token(token, SECRET)


def test_garbage_is_rejected() -> None:
    with pytest.raises(InvalidTokenError):
        verify_token("not-a-jwt-at-all", SECRET)


def test_an_unconfigured_server_refuses_every_token() -> None:
    """Fail closed. Treating tokens as valid with no secret would be catastrophic."""
    with pytest.raises(InvalidTokenError, match="not configured"):
        verify_token(make_token(), "")


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Bearer abc.def.ghi", "abc.def.ghi"),
        ("bearer abc.def.ghi", "abc.def.ghi"),  # scheme is case-insensitive
        ("Bearer   spaced  ", "spaced"),
        (None, None),
        ("", None),
        ("abc.def.ghi", None),  # no scheme
        ("Basic dXNlcjpwYXNz", None),  # wrong scheme
        ("Bearer", None),  # no token
        ("Bearer   ", None),
    ],
)
def test_bearer_extraction(header: str | None, expected: str | None) -> None:
    assert extract_bearer(header) == expected
