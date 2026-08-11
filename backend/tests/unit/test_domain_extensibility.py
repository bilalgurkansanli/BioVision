"""The architectural promise, in executable form.

BioVision claims that adding a domain is a one-line change to `domains.yaml` with
no accompanying code change. A claim that is not tested is a hope, so this module
adds a domain that does not exist anywhere in the source tree and asserts the
system picks it up end to end.

If a future refactor introduces a hard-coded domain list anywhere, these tests fail.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from biovision.api.deps import get_registry
from biovision.config import Settings
from biovision.domains.catalog import DomainCatalog, DomainCatalogError
from biovision.main import create_app
from biovision.models.registry import build_registry
from tests.conftest import build_registry_with, make_png

#: A domain that appears nowhere in `src/`. Grep for it: the only hits are in this
#: file. That is the whole point.
NEW_DOMAIN = {
    "key": "solar_panel",
    "label": "Solar panel",
    "specialist": None,
    "prompts": ["a photo of a cracked solar panel", "a photo of a damaged solar array"],
}


def _catalogue_with(entries: list[dict[str, Any]], tmp_path: Path, source: Path) -> Path:
    document = yaml.safe_load(source.read_text(encoding="utf-8"))
    document["domains"].extend(entries)
    target = tmp_path / "domains.yaml"
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return target


def _settings_for(path: Path) -> Settings:
    return Settings(
        model_backend="mock",
        domains_file=path,
        anon_daily_limit=1000,
        _env_file=None,  # type: ignore[call-arg]
    )


def test_a_new_domain_appears_in_the_api_with_no_code_change(
    tmp_path: Path, real_domains_path: Path
) -> None:
    path = _catalogue_with([NEW_DOMAIN], tmp_path, real_domains_path)

    with TestClient(create_app(_settings_for(path))) as client:
        body = client.get("/v1/domains").json()

    listed = {domain["key"]: domain for domain in body["domains"]}
    assert "solar_panel" in listed
    assert listed["solar_panel"]["label"] == "Solar panel"
    # Honest by default: a brand-new domain has no specialist and says so.
    assert listed["solar_panel"]["has_specialist"] is False
    assert listed["solar_panel"]["calibrated"] is False


def test_a_new_domain_can_be_routed_to_and_answers_honestly(
    tmp_path: Path, real_domains_path: Path
) -> None:
    """Discovery is not enough -- the new domain has to work in the pipeline."""
    path = _catalogue_with([NEW_DOMAIN], tmp_path, real_domains_path)
    settings = _settings_for(path)
    app = create_app(settings)

    registry = build_registry_with(settings, forced_domain="solar_panel", forced_confidence=0.88)
    app.dependency_overrides[get_registry] = lambda: registry

    with TestClient(app) as client:
        body = client.post(
            "/v1/analyze", files={"image": ("panel.png", make_png(), "image/png")}
        ).json()

    assert body["domain"] == "solar_panel"
    assert body["specialist_model"] is None
    assert body["findings"] == []
    assert body["warning"] == "no_specialist_model_for_domain"


def test_the_router_offers_the_new_domain_as_a_candidate(
    tmp_path: Path, real_domains_path: Path
) -> None:
    """The zero-shot prompt set is built from the file, not from a literal."""
    path = _catalogue_with([NEW_DOMAIN], tmp_path, real_domains_path)
    prompts = DomainCatalog.load(path).prompt_map()

    assert "solar_panel" in prompts
    assert prompts["solar_panel"] == NEW_DOMAIN["prompts"]


def test_a_mistyped_specialist_name_fails_loudly_at_startup(
    tmp_path: Path, real_domains_path: Path
) -> None:
    """The flip side of a one-line change: a one-character typo must not be silent.

    Without this check, `specialist: vehicle_yolo_` would simply produce a domain
    that reports "no specialist available" forever -- a wrong answer wearing the
    costume of an honest one.
    """
    broken = dict(NEW_DOMAIN, specialist="does_not_exist")
    path = _catalogue_with([broken], tmp_path, real_domains_path)

    with pytest.raises(DomainCatalogError, match="do not exist in the code"):
        build_registry(_settings_for(path))


def test_a_known_specialist_that_is_not_loaded_is_not_an_error(
    tmp_path: Path, real_domains_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Distinct from a typo, and it must stay distinct.

    A name the code defines but this backend did not load is exactly where the real
    backend sits before Phase 5. The domain then behaves as though it has no
    specialist -- which is the honest answer, and the same one every other domain
    gets. Conflating this with a typo would make the real backend unbootable.
    """
    path = _catalogue_with([], tmp_path, real_domains_path)
    settings = _settings_for(path)

    registry = build_registry(settings)
    registry.specialists.clear()  # simulate "implemented, but not loaded here"

    with caplog.at_level("WARNING"):
        from biovision.models.registry import _verify_specialists_resolve

        _verify_specialists_resolve(DomainCatalog.load(path), registry)

    assert "is not loaded" in caplog.text
    assert registry.specialist_for("vehicle") is None


def test_duplicate_keys_are_rejected(tmp_path: Path, real_domains_path: Path) -> None:
    path = _catalogue_with([NEW_DOMAIN, dict(NEW_DOMAIN)], tmp_path, real_domains_path)

    with pytest.raises(DomainCatalogError, match="duplicate"):
        DomainCatalog.load(path)


def test_a_reserved_key_is_rejected(tmp_path: Path, real_domains_path: Path) -> None:
    """`unknown` means "the router could not place this", not a domain."""
    path = _catalogue_with([dict(NEW_DOMAIN, key="unknown")], tmp_path, real_domains_path)

    with pytest.raises(DomainCatalogError, match="reserved"):
        DomainCatalog.load(path)
