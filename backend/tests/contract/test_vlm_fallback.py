"""The fallback path end to end: caching, budget, and degradation.

These are the acceptance criteria for Phase 6. Each one is a claim the README
makes about how the money is controlled.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from biovision.config import Settings
from tests.conftest import Steer, make_png, mock_vlm


def _upload(seed: int = 0) -> dict[str, tuple[str, bytes, str]]:
    return {"image": ("damage.png", make_png(seed), "image/png")}


# ---------------------------------------------------------------------------
# The cache
# ---------------------------------------------------------------------------


def test_the_same_image_reaches_the_paid_api_once(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    """The headline cost claim, asserted against a call counter."""
    settings.vlm_enabled = True
    registry = steer(
        forced_domain="building", forced_confidence=0.80, with_vlm=True, authenticated=True
    )

    first = client.post("/v1/analyze", files=_upload(42)).json()
    second = client.post("/v1/analyze", files=_upload(42)).json()

    assert mock_vlm(registry).call_count == 1, "the second request should have hit the cache"
    assert first["vlm_description"] == second["vlm_description"]
    assert second["vlm_description"] is not None


def test_a_cache_hit_skips_the_vlm_timing_stage(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    """A stage that did not run is null, so the p95 is not diluted by cache hits."""
    settings.vlm_enabled = True
    steer(forced_domain="building", forced_confidence=0.80, with_vlm=True, authenticated=True)

    client.post("/v1/analyze", files=_upload(43))
    second = client.post("/v1/analyze", files=_upload(43)).json()

    assert second["timing_ms"]["vlm"] is None


def test_different_images_each_cost_a_call(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    settings.vlm_enabled = True
    registry = steer(
        forced_domain="building", forced_confidence=0.80, with_vlm=True, authenticated=True
    )

    client.post("/v1/analyze", files=_upload(1))
    client.post("/v1/analyze", files=_upload(2))

    assert mock_vlm(registry).call_count == 2


def test_a_recompressed_copy_still_hits_the_cache(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    """The key is the *perceptual* hash, so a re-encode is the same photograph."""
    import io

    from tests.conftest import make_image

    settings.vlm_enabled = True
    registry = steer(
        forced_domain="building", forced_confidence=0.80, with_vlm=True, authenticated=True
    )

    source = make_image(seed=77)
    payloads = []
    for quality in (95, 60):
        buffer = io.BytesIO()
        source.save(buffer, format="JPEG", quality=quality)
        payloads.append(buffer.getvalue())

    for payload in payloads:
        client.post("/v1/analyze", files={"image": ("a.jpg", payload, "image/jpeg")})

    assert mock_vlm(registry).call_count == 1


def test_the_two_languages_are_cached_separately(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    """Serving a Turkish description to an English request would be a bug."""
    settings.vlm_enabled = True
    registry = steer(
        forced_domain="building", forced_confidence=0.80, with_vlm=True, authenticated=True
    )

    turkish = client.post(
        "/v1/analyze", files=_upload(55), headers={"Accept-Language": "tr"}
    ).json()
    english = client.post(
        "/v1/analyze", files=_upload(55), headers={"Accept-Language": "en"}
    ).json()

    assert mock_vlm(registry).call_count == 2
    assert turkish["vlm_description"] != english["vlm_description"]


# ---------------------------------------------------------------------------
# Degradation
# ---------------------------------------------------------------------------


def test_an_exhausted_budget_returns_503(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    from biovision.errors import ServiceDegradedError

    settings.vlm_enabled = True
    registry = steer(
        forced_domain="building", forced_confidence=0.80, with_vlm=True, authenticated=True
    )

    def exhausted(image: object, language: str) -> str:
        raise ServiceDegradedError("The monthly description budget is exhausted.")

    mock_vlm(registry).describe = exhausted  # type: ignore[method-assign]

    response = client.post("/v1/analyze", files=_upload(60))

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_degraded"


def test_the_specialist_path_survives_an_exhausted_budget(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    """The whole point of a ceiling that degrades rather than fails.

    Vehicle photographs never touch the VLM, so an exhausted budget must not
    affect them at all.
    """
    from biovision.errors import ServiceDegradedError

    settings.vlm_enabled = True
    registry = steer(
        forced_domain="vehicle", forced_confidence=0.93, with_vlm=True, authenticated=True
    )

    def exhausted(image: object, language: str) -> str:
        raise ServiceDegradedError("exhausted")

    mock_vlm(registry).describe = exhausted  # type: ignore[method-assign]

    response = client.post("/v1/analyze", files=_upload(61))

    assert response.status_code == 200
    assert response.json()["specialist_model"] is not None
    assert mock_vlm(registry).call_count == 0, "the specialist path must not touch the VLM"


def test_a_disabled_vlm_returns_200_not_503(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    """Distinct from an exhausted budget.

    Nothing has broken -- the caller simply cannot reach the fallback -- so the
    honest answer is a 200 that explains there is no specialist.
    """
    settings.vlm_enabled = False
    steer(forced_domain="building", forced_confidence=0.80, with_vlm=True, authenticated=True)

    response = client.post("/v1/analyze", files=_upload(62))

    assert response.status_code == 200
    body = response.json()
    assert body["vlm_description"] is None
    assert body["warning"] == "no_specialist_model_for_domain"
