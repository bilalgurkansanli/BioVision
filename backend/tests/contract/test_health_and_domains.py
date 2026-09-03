"""Contract tests for /health and /v1/domains."""

from __future__ import annotations

from fastapi.testclient import TestClient

from biovision.config import Settings
from biovision.domains.catalog import DomainCatalog
from biovision.schemas.domains import DomainsResponse
from biovision.schemas.health import HealthResponse


def test_health_reports_each_model(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    health = HealthResponse.model_validate(response.json())
    assert health.status == "ok"
    assert health.model_backend == "mock"
    assert health.domains_loaded > 0
    # The point of the endpoint: named components, not a bare "ok".
    details = [component.detail for component in health.components]
    assert "gate" in details
    assert "router" in details


def test_a_degraded_health_response_carries_503(client: TestClient) -> None:
    """The status line must agree with the body.

    Found by running the container: with the weights mount pointing at the wrong
    directory, no models loaded, and `/health` answered 200 with
    `status: degraded`. Docker's healthcheck reads the status line and nothing
    else, so it reported the container `healthy` and Caddy would have sent it
    traffic. A machine reading only the code and a human reading the JSON have
    to reach the same conclusion.
    """
    del client.app.state.registry  # type: ignore[attr-defined]  # simulate a failed load

    response = client.get("/health")

    assert response.status_code == 503
    health = HealthResponse.model_validate(response.json())
    assert health.status == "degraded"
    # Not "mock": the registry that would name the backend is what failed, and a
    # guess here made a failed real load look like a deliberate mock deployment.
    assert health.model_backend is None
    # 503 must not cost the detail -- that was the stated reason for returning 200.
    assert health.components and health.components[0].ready is False


def test_domains_advertise_which_have_a_specialist(client: TestClient) -> None:
    response = client.get("/v1/domains")

    assert response.status_code == 200
    body = DomainsResponse.model_validate(response.json())

    assert body.count == len(body.domains)
    assert body.with_specialist == sum(1 for d in body.domains if d.has_specialist)

    by_key = {domain.key: domain for domain in body.domains}
    assert by_key["vehicle"].has_specialist is True
    assert by_key["vehicle"].specialist_model is not None

    for key in ("other",):
        assert by_key[key].has_specialist is False, key
        assert by_key[key].specialist_model is None, key
        assert by_key[key].calibrated is False, key


def test_domains_and_analyze_agree_on_calibrated(
    client: TestClient, upload_png: dict[str, tuple[str, bytes, str]]
) -> None:
    """The two endpoints must not disagree about the same word.

    `/v1/domains` once derived `calibrated` from "does a specialist exist" while
    `/v1/analyze` derived it from "is the router calibrated". Both were false
    while no specialist existed, so the disagreement was invisible until the
    vehicle specialist was trained -- at which point the discovery endpoint
    advertised `calibrated: true` for a domain whose analyses returned false.

    A client that reads one and receives the other has been told two things.
    """
    listed = DomainsResponse.model_validate(client.get("/v1/domains").json())
    by_key = {domain.key: domain for domain in listed.domains}

    response = client.post("/v1/analyze", files=upload_png)
    assert response.status_code == 200
    analysed = response.json()

    if analysed["domain"] in by_key:
        assert by_key[analysed["domain"]].calibrated == analysed["calibrated"], (
            f"/v1/domains says calibrated={by_key[analysed['domain']].calibrated} "
            f"for {analysed['domain']}, /v1/analyze returned {analysed['calibrated']}"
        )


def test_v1_domain_list_matches_the_catalogue_file(client: TestClient, settings: Settings) -> None:
    """The endpoint renders the catalogue; it does not carry its own list."""
    catalog = DomainCatalog.load(settings.domains_path)
    body = client.get("/v1/domains").json()

    assert [domain["key"] for domain in body["domains"]] == catalog.keys
