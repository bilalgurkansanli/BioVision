"""Fixtures shared by the contract tests.

Here rather than imported from a sibling module: pytest injects fixtures by name,
so importing them makes ruff see a redefinition and makes a reader wonder which
copy is in play. The doubles themselves are in `tests/fakes.py`.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from biovision.api.deps import get_current_user, get_repository
from tests.fakes import FakeRepository, resolve_user


@pytest.fixture
def repository(app: FastAPI) -> FakeRepository:
    fake = FakeRepository()
    app.dependency_overrides[get_repository] = lambda: fake
    return fake


@pytest.fixture
def authed(app: FastAPI) -> None:
    """Resolve `Bearer token-for-<id>` to a user, without a real JWT secret."""
    app.dependency_overrides[get_current_user] = resolve_user
