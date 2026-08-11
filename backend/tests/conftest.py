"""Shared fixtures.

Every fixture builds its own ``Settings`` and its own app. Nothing here touches
``os.environ`` or the cached settings singleton, so tests cannot leak configuration
into each other.
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from biovision.api.deps import CurrentUser, get_current_user, get_registry
from biovision.config import BACKEND_ROOT, Settings
from biovision.domains.catalog import DomainCatalog
from biovision.main import create_app
from biovision.models.base import SpecialistModel
from biovision.models.mock import MockGate, MockRouter, MockSpecialist, MockVLM
from biovision.models.registry import ModelRegistry
from biovision.models.specialists import KNOWN_SPECIALISTS

# ---------------------------------------------------------------------------
# Synthetic image bytes
# ---------------------------------------------------------------------------
# Sprint 1 validates by magic bytes and never decodes, so byte-level fixtures are
# sufficient and keep the suite dependency-free. Phase 2 introduces Pillow and
# replaces these with genuinely decodable images.


def make_png(payload: bytes = b"biovision") -> bytes:
    """A structurally valid 1x1 PNG with `payload` mixed into the pixel data.

    Varying the payload varies the SHA-256, which is what steers the deterministic
    mock models -- so a test that needs two different routing outcomes just passes
    two different payloads.
    """

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00" + payload[:3].ljust(3, b"\x00"))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def make_jpeg(payload: bytes = b"biovision") -> bytes:
    return b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF\x00" + payload.ljust(16, b"\x00") + b"\xff\xd9"


def make_animated_webp() -> bytes:
    body = b"WEBPVP8X" + b"\x00" * 8 + b"ANIM" + b"\x00" * 16
    return b"RIFF" + struct.pack("<I", len(body)) + body


def make_gif() -> bytes:
    return b"GIF89a" + b"\x00" * 32


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    """Test settings: mock backend, the real domain catalogue, VLM off."""
    return Settings(
        env="development",
        model_backend="mock",
        domains_file=Path("src/biovision/domains/domains.yaml"),
        vlm_enabled=False,
        anon_daily_limit=1000,
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # The context manager is what runs `lifespan`, and therefore what loads the
    # models. A bare TestClient(app) would leave app.state.registry unset.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def upload_png() -> dict[str, tuple[str, bytes, str]]:
    return {"image": ("damage.png", make_png(), "image/png")}


@pytest.fixture
def real_domains_path() -> Path:
    return BACKEND_ROOT / "src" / "biovision" / "domains" / "domains.yaml"


# ---------------------------------------------------------------------------
# Steering the pipeline
# ---------------------------------------------------------------------------


def build_registry_with(
    settings: Settings,
    *,
    forced_domain: str | None = None,
    forced_confidence: float | None = None,
    gate_pass: bool | None = None,
    with_vlm: bool = False,
) -> ModelRegistry:
    """A registry whose mocks are pinned to a specific branch of the pipeline.

    The production ``build_registry`` is hash-driven, which is right for a demo but
    useless for a test that needs "route this to a domain with no specialist". This
    assembles the same object with the mocks configured explicitly.
    """
    catalog = DomainCatalog.load(settings.domains_path)
    specialists: dict[str, SpecialistModel] = {}
    for spec in catalog.with_specialist():
        assert spec.specialist is not None
        # Mirrors production: only names with an implementation get a model.
        if spec.specialist not in KNOWN_SPECIALISTS:
            continue
        specialists[spec.specialist] = MockSpecialist(
            domain=spec.key, name=f"mock-{spec.specialist}-v1"
        )

    return ModelRegistry(
        backend="mock",
        catalog=catalog,
        gate=MockGate(threshold=settings.gate_threshold, forced_pass=gate_pass),
        router=MockRouter(
            domain_keys=catalog.keys,
            forced_domain=forced_domain,
            forced_confidence=forced_confidence,
        ),
        specialists=specialists,
        vlm=MockVLM() if with_vlm else None,
    )


class Steer(Protocol):
    """Signature of the :func:`steer` fixture.

    Spelled out as a Protocol so tests can be fully annotated under strict mypy
    rather than each carrying a `type: ignore`.
    """

    def __call__(
        self,
        *,
        authenticated: bool = False,
        forced_domain: str | None = None,
        forced_confidence: float | None = None,
        gate_pass: bool | None = None,
        with_vlm: bool = False,
    ) -> ModelRegistry: ...


@pytest.fixture
def steer(app: FastAPI, settings: Settings) -> Iterator[Steer]:
    """Override the app's registry -- and optionally its auth -- for one test."""

    def _steer(
        *,
        authenticated: bool = False,
        forced_domain: str | None = None,
        forced_confidence: float | None = None,
        gate_pass: bool | None = None,
        with_vlm: bool = False,
    ) -> ModelRegistry:
        registry = build_registry_with(
            settings,
            forced_domain=forced_domain,
            forced_confidence=forced_confidence,
            gate_pass=gate_pass,
            with_vlm=with_vlm,
        )
        app.dependency_overrides[get_registry] = lambda: registry
        if authenticated:
            user = CurrentUser(id="test-user", email="test@example.com")
            app.dependency_overrides[get_current_user] = lambda: user
        return registry

    yield _steer
    app.dependency_overrides.clear()


def mock_vlm(registry: ModelRegistry) -> MockVLM:
    """The registry's VLM, narrowed so `call_count` is visible to the type checker."""
    assert isinstance(registry.vlm, MockVLM), "this registry was built without a VLM"
    return registry.vlm
