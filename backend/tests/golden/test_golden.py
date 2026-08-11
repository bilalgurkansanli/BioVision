"""Golden-set regression tests.

The tripwire for the whole system: if a model swap, a threshold change or a prompt
edit alters any of these outputs, this fails.

Runs against the **real** backend, because that is the thing being protected. It is
therefore opt-in and skipped in CI, which has no checkpoints:

    BIOVISION_TEST_REAL_MODELS=1 uv run pytest tests/golden -v
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from biovision.config import Settings

pytestmark = pytest.mark.golden

HERE = Path(__file__).parent
IMAGES = HERE / "images"
EXPECTED = HERE / "expected"

#: Confidence values move slightly with library versions and CPU maths. A tolerance
#: this loose still catches a changed model or prompt, which shifts scores far more.
TOLERANCE = 0.05


def _cases() -> list[tuple[str, Path, Path]]:
    if not EXPECTED.is_dir():
        return []
    cases = []
    for expectation in sorted(EXPECTED.glob("*.json")):
        matches = [
            candidate
            for suffix in (".jpg", ".jpeg", ".png", ".webp", ".heic")
            if (candidate := IMAGES / f"{expectation.stem}{suffix}").is_file()
        ]
        if matches:
            cases.append((expectation.stem, matches[0], expectation))
    return cases


CASES = _cases()


if os.environ.get("BIOVISION_TEST_REAL_MODELS") != "1":
    pytest.skip(
        "set BIOVISION_TEST_REAL_MODELS=1 to run the golden set against real models",
        allow_module_level=True,
    )

if not CASES:
    # Not `pass` -- a green test over zero cases reads as coverage and is worse than
    # an explicit skip.
    pytest.skip(
        "golden set is empty; see tests/golden/README.md", allow_module_level=True
    )


@pytest.fixture(scope="module")
def client():  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    from biovision.main import create_app

    settings = Settings(model_backend="real", anon_daily_limit=10_000, _env_file=None)  # type: ignore[call-arg]
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _compare_scalar(name: str, actual: Any, expected: Any, failures: list[str]) -> None:
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if abs(float(actual) - float(expected)) > TOLERANCE:
            failures.append(f"{name}: {actual} != {expected} (tolerance {TOLERANCE})")
    elif actual != expected:
        failures.append(f"{name}: {actual!r} != {expected!r}")


@pytest.mark.parametrize(("name", "image_path", "expected_path"), CASES, ids=[c[0] for c in CASES])
def test_golden_case(name: str, image_path: Path, expected_path: Path, client) -> None:  # type: ignore[no-untyped-def]
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    response = client.post(
        "/v1/analyze",
        files={"image": (image_path.name, image_path.read_bytes(), "image/jpeg")},
    )

    if "expect_status" in expected:
        assert response.status_code == expected["expect_status"], response.text
        if "expect_error" in expected:
            assert response.json()["error"]["code"] == expected["expect_error"]
        return

    assert response.status_code == 200, response.text
    body = response.json()
    failures: list[str] = []

    for field in (
        "domain",
        "specialist_model",
        "calibrated",
        "domain_confidence_calibrated",
        "warning",
        "domain_confidence",
    ):
        if field in expected:
            _compare_scalar(field, body.get(field), expected[field], failures)

    if "findings" in expected:
        actual_types = sorted(f["type"] for f in body["findings"])
        expected_types = sorted(f["type"] for f in expected["findings"])
        if actual_types != expected_types:
            failures.append(f"findings: {actual_types} != {expected_types}")
        else:
            for index, (actual, want) in enumerate(
                zip(
                    sorted(body["findings"], key=lambda f: (f["type"], -f["score"])),
                    sorted(expected["findings"], key=lambda f: (f["type"], -f["score"])),
                    strict=True,
                )
            ):
                for field in ("score", "area_ratio"):
                    if field in want:
                        _compare_scalar(
                            f"findings[{index}].{field}", actual[field], want[field], failures
                        )

    if "privacy" in expected:
        for field in ("face_detector", "plate_detector"):
            if field in expected["privacy"]:
                _compare_scalar(
                    f"privacy.{field}",
                    body["privacy"].get(field),
                    expected["privacy"][field],
                    failures,
                )

    if "vlm_description" in expected:
        # Presence only. The content comes from a remote model that can change
        # upstream at any time, and asserting on its prose would fail CI for
        # something that is not a regression.
        has_actual = body.get("vlm_description") is not None
        has_expected = expected["vlm_description"] is not None
        if has_actual != has_expected:
            failures.append(f"vlm_description present={has_actual}, expected {has_expected}")

    assert not failures, f"{name} drifted:\n  " + "\n  ".join(failures)
