"""The real zero-shot gate and router.

These need a ~600 MB checkpoint, so they are opt-in:

    BIOVISION_TEST_REAL_MODELS=1 uv run pytest tests/unit/test_clip_layers.py

CI never runs them and never downloads anything.

**Scope.** What is checked here is *mechanism*: that the softmax is well formed,
that the candidate set comes from the catalogue, that a shared encoder is genuinely
shared, that adding a domain still needs no code change. Whether the router is
*accurate* is not knowable from synthetic gradients -- that requires the annotated
evaluation set and is Phase 4's job. Nothing in this file licenses a number in the
README.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
import yaml

from biovision.config import BACKEND_ROOT, Settings
from biovision.domains.catalog import DomainCatalog
from biovision.domains.gate import GatePrompts
from biovision.pipeline.ingest import prepare_image
from biovision.pipeline.redact import Redactor
from biovision.pipeline.types import PreparedImage
from tests.conftest import make_png

pytestmark = pytest.mark.weights

REAL_MODELS_ENABLED = os.environ.get("BIOVISION_TEST_REAL_MODELS") == "1"

if not REAL_MODELS_ENABLED:
    pytest.skip(
        "set BIOVISION_TEST_REAL_MODELS=1 to run against the real CLIP checkpoint",
        allow_module_level=True,
    )

from biovision.models.clip import ClipEncoder  # noqa: E402
from biovision.models.clip_gate import ClipGate  # noqa: E402
from biovision.models.clip_router import ClipRouter  # noqa: E402


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings(model_backend="real", _env_file=None)  # type: ignore[call-arg]


@pytest.fixture(scope="module")
def encoder(settings: Settings) -> ClipEncoder:
    """Module-scoped: loading the checkpoint takes seconds, and it is immutable."""
    return ClipEncoder(
        model_name=settings.clip_model,
        pretrained=settings.clip_pretrained,
        cache_dir=settings.weights_path,
        num_threads=settings.torch_num_threads,
    )


@pytest.fixture(scope="module")
def catalog(settings: Settings) -> DomainCatalog:
    return DomainCatalog.load(settings.domains_path)


@pytest.fixture
def image(settings: Settings) -> PreparedImage:
    return prepare_image(make_png(seed=5), settings=settings, redactor=Redactor())


# ---------------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------------


def test_image_embeddings_are_unit_length(encoder: ClipEncoder, image: PreparedImage) -> None:
    embedding = encoder.encode_image(image.pixels)

    assert embedding.dtype == np.float32
    assert float(np.linalg.norm(embedding)) == pytest.approx(1.0, abs=1e-4)


def test_encoding_is_deterministic(encoder: ClipEncoder, image: PreparedImage) -> None:
    assert np.allclose(encoder.encode_image(image.pixels), encoder.encode_image(image.pixels))


def test_the_embedding_cache_returns_the_same_object(
    encoder: ClipEncoder, image: PreparedImage
) -> None:
    """The gate and router run back to back on one image; encoding it twice would
    double the most expensive operation in the request."""
    first = encoder.encode_image(image.pixels, cache_key=image.phash)
    second = encoder.encode_image(image.pixels, cache_key=image.phash)

    assert first is second, "the second call should have been served from the cache"


def test_a_different_key_recomputes(encoder: ClipEncoder, image: PreparedImage) -> None:
    first = encoder.encode_image(image.pixels, cache_key="aaaaaaaaaaaaaaaa")
    second = encoder.encode_image(image.pixels, cache_key="bbbbbbbbbbbbbbbb")

    assert first is not second
    assert np.allclose(first, second), "same pixels must still give the same embedding"


def test_omitting_the_key_always_recomputes(
    encoder: ClipEncoder, image: PreparedImage
) -> None:
    assert encoder.encode_image(image.pixels) is not encoder.encode_image(image.pixels)


def test_text_embeddings_are_unit_length(encoder: ClipEncoder) -> None:
    embeddings = encoder.encode_texts(["a photo of a car", "a photo of a wall"])

    assert embeddings.shape[0] == 2
    for row in embeddings:
        assert float(np.linalg.norm(row)) == pytest.approx(1.0, abs=1e-4)


def test_the_text_space_is_semantically_ordered(encoder: ClipEncoder) -> None:
    """A real signal that does not depend on having realistic images.

    Related phrasings must sit closer together than unrelated ones. If this fails,
    the checkpoint is wrong or the tokenizer is mismatched, and every downstream
    number would be meaningless.
    """
    damaged_car, dented_car, food = encoder.encode_texts(
        [
            "a photo of a damaged car",
            "a photo of a car with a dent in the door",
            "a photograph of food on a plate",
        ]
    )

    assert float(damaged_car @ dented_car) > float(damaged_car @ food)


def test_the_prompt_ensemble_is_a_unit_vector(encoder: ClipEncoder) -> None:
    ensemble = encoder.embed_prompt_ensemble(
        ["a photo of a damaged car", "a photo of a scratched vehicle"]
    )

    assert float(np.linalg.norm(ensemble)) == pytest.approx(1.0, abs=1e-4)


def test_the_ensemble_sits_between_its_members(encoder: ClipEncoder) -> None:
    """Averaging is the point: no single phrasing dominates the direction."""
    prompts = ["a photo of a damaged car", "a photo of a scratched vehicle"]
    members = encoder.encode_texts(prompts)
    ensemble = encoder.embed_prompt_ensemble(prompts)

    for member in members:
        assert float(ensemble @ member) > float(members[0] @ members[1])


def test_the_logit_scale_is_applied(encoder: ClipEncoder) -> None:
    """Without it a softmax over raw cosines is nearly uniform and carries no signal."""
    assert encoder.logit_scale > 10.0


def test_empty_prompt_lists_are_a_bug(encoder: ClipEncoder) -> None:
    with pytest.raises(ValueError, match="at least one prompt"):
        encoder.encode_texts([])


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def test_gate_scores_are_a_probability(
    encoder: ClipEncoder, settings: Settings, image: PreparedImage
) -> None:
    gate = ClipGate(
        encoder=encoder,
        prompts=GatePrompts.load(settings.gate_prompts_path),
        threshold=settings.gate_threshold,
    )

    decision = gate.check(image)

    assert 0.0 <= decision.score <= 1.0
    assert decision.threshold == settings.gate_threshold
    assert decision.passed == (decision.score >= decision.threshold)


def test_gate_names_the_encoder_it_used(
    encoder: ClipEncoder, settings: Settings
) -> None:
    gate = ClipGate(encoder, GatePrompts.load(settings.gate_prompts_path), 0.25)

    assert encoder.name in gate.name
    assert gate.ready is True


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def test_router_returns_a_distribution_over_every_domain(
    encoder: ClipEncoder, catalog: DomainCatalog, image: PreparedImage
) -> None:
    decision = ClipRouter(encoder, catalog).classify(image)

    assert set(decision.scores) == set(catalog.keys)
    assert sum(decision.scores.values()) == pytest.approx(1.0, abs=0.01)
    assert decision.domain in catalog.keys
    assert decision.confidence == max(decision.scores.values())


def test_an_uncalibrated_router_says_so(
    encoder: ClipEncoder, catalog: DomainCatalog, image: PreparedImage
) -> None:
    """Until Phase 4 fits a temperature, the confidence is not a probability."""
    router = ClipRouter(encoder, catalog, calibration=None)

    assert router.calibrated is False
    assert router.classify(image).calibrated is False


def test_classification_is_deterministic(
    encoder: ClipEncoder, catalog: DomainCatalog, image: PreparedImage
) -> None:
    router = ClipRouter(encoder, catalog)

    assert router.classify(image).scores == router.classify(image).scores


# ---------------------------------------------------------------------------
# The architectural promise, with a real model behind it
# ---------------------------------------------------------------------------


def test_adding_a_domain_needs_no_code_change_with_a_real_router(
    encoder: ClipEncoder, tmp_path: Path
) -> None:
    """The Sprint 1 extensibility test, re-run against real inference.

    A mock router accepting a new catalogue entry proves the plumbing. This proves
    the claim: a domain that exists nowhere in `src/` becomes a real column in a
    real softmax, purely by editing YAML.
    """
    source = BACKEND_ROOT / "src" / "biovision" / "domains" / "domains.yaml"
    document = yaml.safe_load(source.read_text(encoding="utf-8"))
    document["domains"].append(
        {
            "key": "solar_panel",
            "label": "Solar panel",
            "specialist": None,
            "prompts": [
                "a photo of a cracked solar panel",
                "a photo of a damaged solar array",
            ],
        }
    )
    path = tmp_path / "domains.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    extended = DomainCatalog.load(path)
    router = ClipRouter(encoder, extended)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    image = prepare_image(make_png(seed=6), settings=settings, redactor=Redactor())
    decision = router.classify(image)

    assert "solar_panel" in decision.scores
    assert len(decision.scores) == len(extended.keys)


# ---------------------------------------------------------------------------
# Memory: the constraint that sets the worker count
# ---------------------------------------------------------------------------


def test_the_gate_and_router_share_one_encoder(
    encoder: ClipEncoder, settings: Settings, catalog: DomainCatalog
) -> None:
    """Two encoders would double the largest allocation, per worker.

    On an 8 GB box with two workers, that is the difference between fitting and
    being OOM-killed.
    """
    gate = ClipGate(encoder, GatePrompts.load(settings.gate_prompts_path), 0.25)
    router = ClipRouter(encoder, catalog)

    assert gate.encoder is router.encoder is encoder


def test_registry_wires_the_real_backend(settings: Settings) -> None:
    from biovision.models.registry import build_registry

    registry = build_registry(settings)

    assert registry.backend == "real"
    assert registry.gate.ready and registry.router.ready
    # Phase 5 loads the specialist. Until then the vehicle domain honestly has none.
    assert registry.specialist_for("vehicle") is None
