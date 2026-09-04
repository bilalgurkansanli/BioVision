"""A mock result has to be recognisable as one, from the response alone.

The stand-in specialist returns a **fixed box** — the same coordinates on a
photograph of a crushed wing and on a photograph of a wall. Drawn on a real
photograph with a confidence badge, a severity band and a measured class recall
beside it, that reads as a measurement. It was one small-type model name away
from being indistinguishable from the real thing, and a reader had no reason to
parse the name.

So the prefix is a contract rather than a coincidence, and this file is what
makes it one: a client keys on `mock-` to warn its reader, and a rename here
would silently turn that warning off everywhere.

These tests deliberately do not check the *text* of any warning. They check the
one fact a warning can be derived from.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from biovision.config import Settings
from biovision.domains.catalog import DomainCatalog
from biovision.models.mock import MOCK_NAME_PREFIX
from biovision.models.registry import build_registry
from biovision.models.specialists.vehicle_yolo import SPECIALIST_NAME
from biovision.pipeline.redact import build_redactor
from tests.conftest import Steer, make_png


def test_every_model_the_mock_backend_loads_says_so_in_its_name(
    settings: Settings,
) -> None:
    """Gate, router, specialist, VLM — no exceptions, or the warning has holes."""
    registry = build_registry(settings)

    named = [registry.gate.name, registry.router.name]
    named += [model.name for model in registry.specialists.values()]
    if registry.vlm is not None:
        named.append(registry.vlm.name)

    assert named, "the mock backend loaded nothing to check"
    for name in named:
        assert name.startswith(MOCK_NAME_PREFIX), f"{name!r} does not announce itself"


def test_the_real_specialist_name_does_not_collide_with_the_prefix() -> None:
    """Otherwise the warning would fire on a genuine measurement.

    Which is the worse failure of the two: telling a user their real result is a
    placeholder teaches them to ignore the warning.
    """
    assert not SPECIALIST_NAME.startswith(MOCK_NAME_PREFIX)


def test_redaction_is_never_labelled_a_mock(settings: Settings) -> None:
    """It is real image processing under both backends, and says so.

    Redaction does not change with the model backend -- blurring a face is not
    inference -- so labelling it a stand-in would understate a privacy measure
    that genuinely ran.
    """
    redactor = build_redactor(settings.weights_path)

    for detector in (redactor.face_detector_name, redactor.plate_detector_name):
        if detector is not None:
            assert not detector.startswith(MOCK_NAME_PREFIX)


def test_the_response_carries_the_label_a_client_reads(
    client: TestClient, steer: Steer
) -> None:
    """End to end: the field a UI branches on is in the body it receives."""
    steer(forced_domain="vehicle", forced_confidence=0.93)

    body = client.post(
        "/v1/analyze", files={"image": ("d.png", make_png(4), "image/png")}
    ).json()

    assert body["specialist_model"].startswith(MOCK_NAME_PREFIX)
    assert body["findings"], "the fixed-box findings are what needed the label"


def test_health_names_the_backend_as_well(client: TestClient) -> None:
    """A second, independent signal, for an operator rather than a claimant."""
    body = client.get("/health").json()

    assert body["model_backend"] == "mock"
    assert all(
        component["name"].startswith(MOCK_NAME_PREFIX)
        for component in body["components"]
        if "specialist" in component["detail"]
    )


@pytest.mark.parametrize("catalog_domain", ["vehicle"])
def test_the_mock_specialist_answers_the_same_box_for_any_image(
    settings: Settings, catalog_domain: str
) -> None:
    """The property that makes the label necessary, asserted rather than assumed.

    If the mock ever started varying its box with the image, this test failing is
    the prompt to ask whether the warning is still the right one -- not a reason
    to delete the test.
    """
    from biovision.pipeline.ingest import prepare_image

    registry = build_registry(settings)
    catalog = DomainCatalog.load(settings.domains_path)
    assert catalog.get(catalog_domain) is not None
    specialist = registry.specialist_for(catalog_domain)
    assert specialist is not None

    redactor = build_redactor(settings.weights_path)
    boxes = {
        tuple(finding.bbox)
        for seed in (1, 2, 3)
        for finding in specialist.analyze(
            prepare_image(make_png(seed), settings=settings, redactor=redactor)
        )
    }

    assert len(boxes) == 1, f"the mock box now varies with the image: {boxes}"
