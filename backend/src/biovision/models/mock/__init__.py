"""Deterministic stand-ins for every model interface.

These exist so the test suite -- and a `docker compose up` on a laptop -- can
exercise the *real* pipeline without downloading a single checkpoint. They are
deterministic functions of the image bytes, so a given input always produces the
same output and tests never flake.

They are not simulations of accuracy. Nothing measured against a mock appears in
the README.
"""

from biovision.models.mock.models import (
    MOCK_NAME_PREFIX,
    MockGate,
    MockRouter,
    MockSpecialist,
    MockVLM,
)

__all__ = [
    "MOCK_NAME_PREFIX",
    "MockGate",
    "MockRouter",
    "MockSpecialist",
    "MockVLM",
]
