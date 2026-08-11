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


def test_domains_advertise_which_have_a_specialist(client: TestClient) -> None:
    response = client.get("/v1/domains")

    assert response.status_code == 200
    body = DomainsResponse.model_validate(response.json())

    assert body.count == len(body.domains)
    assert body.with_specialist == sum(1 for d in body.domains if d.has_specialist)

    by_key = {domain.key: domain for domain in body.domains}
    assert by_key["vehicle"].has_specialist is True
    assert by_key["vehicle"].specialist_model is not None

    for key in ("building", "phone_screen", "other"):
        assert by_key[key].has_specialist is False, key
        assert by_key[key].specialist_model is None, key
        assert by_key[key].calibrated is False, key


def test_v1_domain_list_matches_the_catalogue_file(
    client: TestClient, settings: Settings
) -> None:
    """The endpoint renders the catalogue; it does not carry its own list."""
    catalog = DomainCatalog.load(settings.domains_path)
    body = client.get("/v1/domains").json()

    assert [domain["key"] for domain in body["domains"]] == catalog.keys
