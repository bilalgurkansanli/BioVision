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
        forced_domain="phone_screen", forced_confidence=0.80, with_vlm=True, authenticated=True
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
    steer(forced_domain="phone_screen", forced_confidence=0.80, with_vlm=True, authenticated=True)

    client.post("/v1/analyze", files=_upload(43))
    second = client.post("/v1/analyze", files=_upload(43)).json()

    assert second["timing_ms"]["vlm"] is None


def test_different_images_each_cost_a_call(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    settings.vlm_enabled = True
    registry = steer(
        forced_domain="phone_screen", forced_confidence=0.80, with_vlm=True, authenticated=True
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
        forced_domain="phone_screen", forced_confidence=0.80, with_vlm=True, authenticated=True
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
        forced_domain="phone_screen", forced_confidence=0.80, with_vlm=True, authenticated=True
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
        forced_domain="phone_screen", forced_confidence=0.80, with_vlm=True, authenticated=True
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

    With `vlm_augments_specialist` off -- the default -- a measured domain never
    touches the VLM, so an exhausted budget must not affect it at all.
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
    steer(forced_domain="phone_screen", forced_confidence=0.80, with_vlm=True, authenticated=True)

    response = client.post("/v1/analyze", files=_upload(62))

    assert response.status_code == 200
    body = response.json()
    assert body["vlm_description"] is None
    assert body["warning"] == "no_specialist_model_for_domain"


# ---------------------------------------------------------------------------
# Describing a domain that a specialist already measured
# ---------------------------------------------------------------------------


def test_a_measured_domain_can_also_be_described(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    """Findings and a description, from the same request.

    The vehicle specialist finds ~25% of dents, so a badly damaged car can come
    back as one finding -- accurate about that finding, and easily read as light
    damage. A description sits beside the measurement for that case.
    """
    settings.vlm_enabled = True
    settings.vlm_augments_specialist = True
    registry = steer(
        forced_domain="vehicle", forced_confidence=0.93, with_vlm=True, authenticated=True
    )

    body = client.post("/v1/analyze", files=_upload(71)).json()

    assert body["specialist_model"] is not None
    assert body["findings"], "the measurement is still the primary answer"
    assert body["vlm_description"] is not None
    assert mock_vlm(registry).call_count == 1


def test_a_description_never_becomes_a_finding(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    """The invariant the whole schema exists to protect, on the new path too.

    Free text is a description. Findings come from a model that was measured. The
    augmenting description must not change the count, the classes, or the
    calibration flags of what the specialist produced.
    """
    settings.vlm_enabled = True
    registry = steer(
        forced_domain="vehicle", forced_confidence=0.93, with_vlm=True, authenticated=True
    )

    settings.vlm_augments_specialist = False
    without = client.post("/v1/analyze", files=_upload(72)).json()

    settings.vlm_augments_specialist = True
    with_text = client.post("/v1/analyze", files=_upload(72)).json()

    assert without["vlm_description"] is None
    assert with_text["vlm_description"] is not None
    assert with_text["findings"] == without["findings"]
    assert with_text["calibrated"] == without["calibrated"]
    assert mock_vlm(registry).call_count == 1


def test_anonymous_traffic_cannot_spend_on_the_measured_path_either(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    """The budget rule does not have an exception for the new path.

    Anonymous callers cannot reach the paid API. Adding a second place that calls
    it is exactly how that guarantee would have been lost.
    """
    settings.vlm_enabled = True
    settings.vlm_augments_specialist = True
    registry = steer(
        forced_domain="vehicle", forced_confidence=0.93, with_vlm=True, authenticated=False
    )

    body = client.post("/v1/analyze", files=_upload(73)).json()

    assert body["findings"], "an anonymous caller still gets the measurement"
    assert body["vlm_description"] is None
    assert mock_vlm(registry).call_count == 0
