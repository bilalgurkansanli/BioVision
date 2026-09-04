"""Every response says which frame its boxes are in.

`Finding.bbox` is in pixels of the STORED image -- after EXIF rotation and after
the resize to the stored long edge. The response used to carry that fact only in
a field description, which left a client with nothing to scale by except the file
it had uploaded. That file is the pre-resize one, so the web UI drew every box at
1280/4000 = 32% of its true offset and size: near the damage rather than on it,
which reads as a model that is almost right.

So the frame is now part of the contract. These tests assert the two things a
renderer depends on: that it is always present, and that it is the frame the
boxes actually live in.
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from biovision.config import Settings
from biovision.schemas.analyze import AnalyzeResponse
from tests.conftest import Steer, make_image


def _upload(size: tuple[int, int]) -> dict[str, tuple[str, bytes, str]]:
    buffer = io.BytesIO()
    make_image(size, seed=3).save(buffer, format="PNG")
    return {"image": ("damage.png", buffer.getvalue(), "image/png")}


def test_the_frame_is_the_stored_image_not_the_upload(
    client: TestClient, steer: Steer, settings: Settings
) -> None:
    """A photograph larger than the stored long edge comes back resized.

    2000x1500 is the shape of the bug: it is bigger than the 1280 long edge, so
    the frame the client uploaded and the frame the model measured are genuinely
    different numbers, and a renderer that confuses them is wrong by their ratio.
    """
    steer(forced_domain="vehicle", forced_confidence=0.93)

    body = client.post("/v1/analyze", files=_upload((2000, 1500))).json()

    long_edge = settings.stored_long_edge
    assert body["image"]["width"] == long_edge
    assert body["image"]["height"] == long_edge * 3 // 4
    assert (body["image"]["width"], body["image"]["height"]) != (2000, 1500)


def test_a_small_photograph_is_reported_at_its_own_size(
    client: TestClient, steer: Steer
) -> None:
    """Ingestion only ever downscales, so a small image is its own frame."""
    steer(forced_domain="vehicle", forced_confidence=0.93)

    body = client.post("/v1/analyze", files=_upload((640, 480))).json()

    assert (body["image"]["width"], body["image"]["height"]) == (640, 480)


def test_every_finding_fits_inside_the_reported_frame(
    client: TestClient, steer: Steer
) -> None:
    """The frame has to be the one the boxes are in, not merely a plausible size."""
    steer(forced_domain="vehicle", forced_confidence=0.93)

    parsed = AnalyzeResponse.model_validate(
        client.post("/v1/analyze", files=_upload((1600, 1200))).json()
    )

    assert parsed.findings, "this test is meaningless without at least one box"
    for finding in parsed.findings:
        x1, y1, x2, y2 = finding.bbox
        assert 0 <= x1 < x2 <= parsed.image.width
        assert 0 <= y1 < y2 <= parsed.image.height


def test_a_response_with_no_findings_still_carries_the_frame(
    client: TestClient, steer: Steer
) -> None:
    """Absent on the empty responses would make it a field a client must guard.

    The no-specialist and unplaced shapes carry no boxes, but a client renders
    the photograph on all three paths and should not need a branch to know how.
    """
    steer(forced_domain="other", forced_confidence=0.93)
    described = client.post("/v1/analyze", files=_upload((900, 900))).json()

    steer(forced_domain="vehicle", forced_confidence=0.10)
    unplaced = client.post("/v1/analyze", files=_upload((900, 900))).json()

    assert described["findings"] == [] and unplaced["findings"] == []
    for body in (described, unplaced):
        assert body["image"] == {"width": 900, "height": 900}


def test_an_exif_rotated_upload_reports_the_rotated_frame(
    client: TestClient, steer: Steer
) -> None:
    """Orientation is applied before measurement, so the frame is the rotated one.

    A portrait phone photograph arrives as landscape pixels plus a rotation tag.
    Reporting the pre-rotation shape would transpose every box.
    """
    steer(forced_domain="vehicle", forced_confidence=0.93)

    buffer = io.BytesIO()
    image = make_image((800, 600), seed=5)
    exif = Image.Exif()
    exif[274] = 6  # rotate 90° clockwise on display
    image.save(buffer, format="JPEG", exif=exif)

    body = client.post(
        "/v1/analyze", files={"image": ("rotated.jpg", buffer.getvalue(), "image/jpeg")}
    ).json()

    assert (body["image"]["width"], body["image"]["height"]) == (600, 800)
