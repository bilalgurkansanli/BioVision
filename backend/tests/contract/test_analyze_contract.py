"""Contract tests for POST /v1/analyze.

Both branches of the response -- specialist present and specialist absent -- are
checked against the published schema, because a client written against the
documented shape must never receive something else.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from biovision.config import Settings
from biovision.domains.catalog import DomainCatalog
from biovision.schemas.analyze import AnalyzeResponse
from biovision.schemas.enums import UNKNOWN_DOMAIN, WarningCode
from tests.conftest import Steer, make_png, mock_vlm


def _upload(seed: int = 0) -> dict[str, tuple[str, bytes, str]]:
    return {"image": ("damage.png", make_png(seed), "image/png")}


def test_response_validates_against_the_published_schema(
    client: TestClient, steer: Steer
) -> None:
    steer(forced_domain="vehicle", forced_confidence=0.93)

    response = client.post("/v1/analyze", files=_upload())

    assert response.status_code == 200
    # Round-tripping through the model is the actual assertion: extra="forbid"
    # means an undocumented field fails here.
    parsed = AnalyzeResponse.model_validate(response.json())
    assert parsed.domain == "vehicle"
    assert parsed.domain_confidence == 0.93


def test_specialist_branch_returns_measurements(client: TestClient, steer: Steer) -> None:
    steer(forced_domain="vehicle", forced_confidence=0.93)

    body = client.post("/v1/analyze", files=_upload()).json()

    assert body["specialist_model"] is not None
    assert body["findings"], "a domain with a specialist should be able to report findings"
    # Cost control: if a specialist ran, the paid fallback was never reached.
    assert body["vlm_description"] is None
    assert body["warning"] is None

    for finding in body["findings"]:
        assert finding["severity_calibrated"] is False, "severity is never calibrated"
        assert 0.0 <= finding["score"] <= 1.0
        assert 0.0 <= finding["area_ratio"] <= 1.0


def test_domain_without_specialist_admits_it(client: TestClient, steer: Steer) -> None:
    """The response this project exists to produce."""
    steer(forced_domain="building", forced_confidence=0.71)

    body = client.post("/v1/analyze", files=_upload()).json()

    assert body["domain"] == "building"
    assert body["specialist_model"] is None
    assert body["calibrated"] is False
    assert body["findings"] == []
    assert body["warning"] == WarningCode.NO_SPECIALIST.value


def test_every_domain_without_a_specialist_behaves_the_same(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    """Not just `building` -- the rule holds for every unbacked domain.

    A per-domain special case is exactly how an honesty guarantee rots.
    """
    catalog = DomainCatalog.load(settings.domains_path)
    unbacked = [spec.key for spec in catalog.specs if not spec.has_specialist]
    assert unbacked, "the test is meaningless if every domain has a specialist"

    for domain in unbacked:
        steer(forced_domain=domain, forced_confidence=0.80)
        body = client.post("/v1/analyze", files=_upload()).json()
        assert body["specialist_model"] is None, domain
        assert body["findings"] == [], domain
        assert body["calibrated"] is False, domain
        assert body["warning"] is not None, domain


def test_low_confidence_does_not_run_a_specialist(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    """Q8: a weak routing guess must not be laundered into confident findings."""
    below = settings.router_min_confidence - 0.10
    steer(forced_domain="vehicle", forced_confidence=below)

    body = client.post("/v1/analyze", files=_upload()).json()

    assert body["domain"] == UNKNOWN_DOMAIN
    assert body["specialist_model"] is None
    assert body["findings"] == []
    assert body["warning"] == WarningCode.LOW_DOMAIN_CONFIDENCE.value
    assert body["timing_ms"]["specialist"] is None, "the specialist must not have run"


def test_gate_rejection_is_422(client: TestClient, steer: Steer) -> None:
    steer(gate_pass=False)

    response = client.post("/v1/analyze", files=_upload())

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "out_of_distribution"


def test_anonymous_callers_never_reach_the_paid_vlm(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    """The mechanism that makes a public demo link safe to publish."""
    settings.vlm_enabled = True
    registry = steer(forced_domain="building", forced_confidence=0.80, with_vlm=True)

    body = client.post("/v1/analyze", files=_upload()).json()

    assert mock_vlm(registry).call_count == 0, "anonymous traffic must not spend budget"
    assert body["vlm_description"] is None
    assert body["warning"] == WarningCode.NO_SPECIALIST.value


def test_authenticated_fallback_gets_a_description(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    settings.vlm_enabled = True
    registry = steer(
        forced_domain="building", forced_confidence=0.80, with_vlm=True, authenticated=True
    )

    body = client.post("/v1/analyze", files=_upload()).json()

    assert mock_vlm(registry).call_count == 1
    assert body["vlm_description"] is not None
    # Still not a measurement, no matter how good the prose is.
    assert body["findings"] == []
    assert body["calibrated"] is False


def test_timings_are_reported_per_stage(client: TestClient, steer: Steer) -> None:
    steer(forced_domain="vehicle", forced_confidence=0.93)

    timing = client.post("/v1/analyze", files=_upload()).json()["timing_ms"]

    assert timing["gate"] is not None
    assert timing["router"] is not None
    assert timing["specialist"] is not None
    assert timing["vlm"] is None, "a stage that did not run must be null, not zero"
    assert timing["total"] >= 0


def test_identical_uploads_produce_identical_results(client: TestClient, steer: Steer) -> None:
    """Mocks are deterministic, so the suite cannot flake on hash-driven branches."""
    steer(forced_domain="vehicle", forced_confidence=0.93)

    first = client.post("/v1/analyze", files=_upload(77)).json()
    second = client.post("/v1/analyze", files=_upload(77)).json()

    del first["request_id"], second["request_id"]
    del first["timing_ms"], second["timing_ms"]
    assert first == second
