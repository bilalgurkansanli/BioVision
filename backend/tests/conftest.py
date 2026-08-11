"""Shared fixtures.

Every fixture builds its own ``Settings`` and its own app. Nothing here touches
``os.environ`` or the cached settings singleton, so tests cannot leak configuration
into each other.

Image fixtures are **genuinely decodable** -- built with Pillow at call time rather
than hand-assembled from magic bytes. Phase 2 decodes every upload, so byte-level
fakes would no longer exercise the code under test; and generating them keeps the
repository free of committed binaries.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from biovision.api.deps import CurrentUser, get_current_user, get_registry
from biovision.config import BACKEND_ROOT, Settings
from biovision.domains.catalog import DomainCatalog
from biovision.main import create_app
from biovision.models.base import SpecialistModel
from biovision.models.mock import MockGate, MockRouter, MockSpecialist, MockVLM
from biovision.models.registry import ModelRegistry
from biovision.models.specialists import KNOWN_SPECIALISTS
from biovision.pipeline.redact import Detection, Redactor

# ---------------------------------------------------------------------------
# Image fixtures
# ---------------------------------------------------------------------------

#: Comfortably above `min_image_dimension` (200) so size is never the reason a
#: fixture is rejected.
DEFAULT_SIZE = (640, 480)


def make_image(
    size: tuple[int, int] = DEFAULT_SIZE, seed: int = 0, mode: str = "RGB"
) -> Image.Image:
    """A deterministic image with real structure.

    Structure matters: flat colour compresses to almost nothing and produces a
    degenerate DCT, which would make the perceptual-hash tests meaningless. This
    draws smooth gradients plus a seed-dependent block so distinct seeds are
    genuinely distinct images rather than noise that happens to differ.
    """
    width, height = size
    xs = np.linspace(0, 255, width, dtype=np.float32)
    ys = np.linspace(0, 255, height, dtype=np.float32)
    grid_x, grid_y = np.meshgrid(xs, ys)

    red = grid_x
    green = grid_y
    blue = (grid_x + grid_y) / 2 + (seed * 37 % 90)

    pixels = np.clip(np.stack([red, green, blue], axis=-1), 0, 255).astype(np.uint8)

    # A solid rectangle whose position depends on the seed: low-frequency, so it
    # survives resizing and re-compression the way real image content does.
    block_x = (seed * 53) % max(1, width - width // 4)
    block_y = (seed * 31) % max(1, height - height // 4)
    pixels[block_y : block_y + height // 4, block_x : block_x + width // 4] = (
        20,
        200,
        120,
    )

    image = Image.fromarray(pixels, mode="RGB")
    return image if mode == "RGB" else image.convert(mode)


def encode(image: Image.Image, image_format: str = "PNG", **options: object) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=image_format, **options)
    return buffer.getvalue()


def make_png(seed: int = 0, size: tuple[int, int] = DEFAULT_SIZE) -> bytes:
    return encode(make_image(size, seed), "PNG")


def make_jpeg(seed: int = 0, size: tuple[int, int] = DEFAULT_SIZE, quality: int = 92) -> bytes:
    return encode(make_image(size, seed), "JPEG", quality=quality)


def make_webp(seed: int = 0, size: tuple[int, int] = DEFAULT_SIZE) -> bytes:
    return encode(make_image(size, seed), "WEBP")


def make_heic(seed: int = 0, size: tuple[int, int] = DEFAULT_SIZE) -> bytes:
    """A real HEIC file, via pillow-heif's encoder.

    Generated rather than committed so the iPhone path is covered without a binary
    in the repository. `pipeline.validate` registers the HEIF opener on import.
    """
    import pillow_heif

    pillow_heif.register_heif_opener()
    return encode(make_image(size, seed), "HEIF", quality=90)


def make_jpeg_with_exif(
    seed: int = 0,
    size: tuple[int, int] = DEFAULT_SIZE,
    *,
    orientation: int | None = None,
    datetime_original: str | None = None,
    make: str | None = None,
    model: str | None = None,
    gps: bool = False,
) -> bytes:
    """A JPEG carrying exactly the EXIF tags a test asks for."""
    exif = Image.Exif()

    if orientation is not None:
        exif[0x0112] = orientation
    if make is not None:
        exif[0x010F] = make
    if model is not None:
        exif[0x0110] = model
    if datetime_original is not None:
        exif.get_ifd(0x8769)[0x9003] = datetime_original
    if gps:
        # Version tag only. The pipeline records GPS *presence*, never coordinates,
        # so a populated GPS IFD is all a test needs.
        exif.get_ifd(0x8825)[0x0000] = b"\x02\x03\x00\x00"

    buffer = io.BytesIO()
    make_image(size, seed).save(buffer, format="JPEG", quality=92, exif=exif)
    return buffer.getvalue()


def make_animated_webp(frames: int = 3) -> bytes:
    buffer = io.BytesIO()
    images = [make_image((320, 320), seed) for seed in range(frames)]
    images[0].save(buffer, format="WEBP", save_all=True, append_images=images[1:], duration=100)
    return buffer.getvalue()


def make_animated_gif(frames: int = 3) -> bytes:
    buffer = io.BytesIO()
    images = [make_image((320, 320), seed).convert("P") for seed in range(frames)]
    images[0].save(buffer, format="GIF", save_all=True, append_images=images[1:], duration=100)
    return buffer.getvalue()


def make_gif() -> bytes:
    return encode(make_image((320, 320)).convert("P"), "GIF")


def make_truncated_jpeg() -> bytes:
    """A valid JPEG header followed by nothing. Only decoding catches this."""
    return make_jpeg()[:512]


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
# Redaction test doubles
# ---------------------------------------------------------------------------


class FixedDetector:
    """Returns boxes it was handed, so redaction is testable without checkpoints.

    The real detectors need downloaded weights, which CI deliberately does not have.
    What has to be tested here is the redaction *behaviour* -- that pixels are
    destroyed, that counts are reported, that the detector is named -- and that is
    independent of which model produced the boxes.
    """

    def __init__(self, name: str, boxes: list[tuple[int, int, int, int]]) -> None:
        self._name = name
        self._boxes = boxes

    @property
    def name(self) -> str:
        return self._name

    def detect(self, bgr: np.ndarray) -> list[Detection]:
        return [Detection(box=box, score=0.99) for box in self._boxes]


class ExplodingDetector:
    """Raises on every call. A crashing detector must not take the request down."""

    @property
    def name(self) -> str:
        return "exploding-detector"

    def detect(self, bgr: np.ndarray) -> list[Detection]:
        raise RuntimeError("detector exploded")


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
    redactor: Redactor | None = None,
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
        # No detectors by default: CI has no weights, so this is also what
        # production looks like before `fetch_weights.py` has been run.
        redactor=redactor or Redactor(),
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
        redactor: Redactor | None = None,
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
        redactor: Redactor | None = None,
    ) -> ModelRegistry:
        registry = build_registry_with(
            settings,
            forced_domain=forced_domain,
            forced_confidence=forced_confidence,
            gate_pass=gate_pass,
            with_vlm=with_vlm,
            redactor=redactor,
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
