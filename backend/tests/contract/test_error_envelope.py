"""Every documented failure returns the same envelope with the documented status."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from biovision.config import Settings
from biovision.schemas.errors import ErrorResponse
from tests.conftest import Steer, make_animated_webp, make_gif, make_png


@pytest.mark.parametrize(
    ("filename", "payload", "expected_status", "expected_code"),
    [
        ("photo.gif", make_gif(), 415, "unsupported_media_type"),
        ("photo.webp", make_animated_webp(), 415, "animated_image"),
        (
            "photo.txt",
            b"this is not an image at all, not even close",
            415,
            "unsupported_media_type",
        ),
        ("empty.png", b"", 415, "unsupported_media_type"),
    ],
)
def test_rejected_uploads(
    client: TestClient,
    steer: Steer,
    filename: str,
    payload: bytes,
    expected_status: int,
    expected_code: str,
) -> None:
    steer()
    response = client.post("/v1/analyze", files={"image": (filename, payload, "image/png")})

    assert response.status_code == expected_status
    body = ErrorResponse.model_validate(response.json())
    assert body.error.code.value == expected_code
    assert body.error.message, "an error must explain itself to the user"


def test_a_lying_content_type_does_not_get_through(client: TestClient, steer: Steer) -> None:
    """Format comes from magic bytes, never from the client's claim."""
    steer()
    response = client.post(
        "/v1/analyze", files={"image": ("actually.png", make_gif(), "image/png")}
    )

    assert response.status_code == 415


def test_oversized_upload_is_413(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    steer()
    settings.max_upload_bytes = 4096
    oversized = make_png() + b"\x00" * 8192

    response = client.post("/v1/analyze", files={"image": ("big.png", oversized, "image/png")})

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_quota_exhaustion_is_429(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    steer(forced_domain="vehicle", forced_confidence=0.93)
    settings.anon_daily_limit = 2
    files = {"image": ("damage.png", make_png(), "image/png")}

    assert client.post("/v1/analyze", files=files).status_code == 200
    assert client.post("/v1/analyze", files=files).status_code == 200

    response = client.post("/v1/analyze", files=files)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


def test_missing_file_field_is_415_not_422(client: TestClient, steer: Steer) -> None:
    """422 is reserved for "the gate rejected your photograph".

    FastAPI's default for a malformed request is also 422, which would make the
    status ambiguous for a client trying to tell the two cases apart.
    """
    steer()
    response = client.post("/v1/analyze", data={"not_an_image": "x"})

    assert response.status_code == 415


def test_unimplemented_history_says_so(client: TestClient) -> None:
    response = client.get("/v1/requests")

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_implemented"
