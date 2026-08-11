"""The honesty rules are enforced by the schema, so test the schema.

These validators are the last line of defence: if any future code path tries to
emit findings that no model produced, the response fails to construct rather than
reaching a client.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from biovision.schemas.analyze import AnalyzeResponse, Finding, Privacy, TimingMs
from biovision.schemas.enums import DamageType, Severity, WarningCode


def _finding() -> Finding:
    return Finding(
        type=DamageType.SCRATCH,
        score=0.81,
        bbox=(120, 340, 260, 410),
        area_ratio=0.04,
        severity=Severity.MODERATE,
    )


def _response(**overrides: Any) -> AnalyzeResponse:
    """Build a valid specialist-branch response, then apply overrides.

    Goes through ``model_validate`` rather than the constructor so a test can pass
    an undocumented field and watch ``extra="forbid"`` reject it.
    """
    payload: dict[str, Any] = {
        "request_id": uuid4(),
        "domain": "vehicle",
        "domain_confidence": 0.93,
        "specialist_model": "cardd-yolo-seg-v1",
        "calibrated": True,
        "findings": [],
        "timing_ms": TimingMs(total=100),
    }
    payload.update(overrides)
    return AnalyzeResponse.model_validate(payload)


def test_findings_without_a_specialist_are_rejected() -> None:
    """The core invariant."""
    with pytest.raises(ValidationError, match="findings must be empty"):
        _response(
            specialist_model=None,
            calibrated=False,
            findings=[_finding()],
            warning=WarningCode.NO_SPECIALIST,
        )


def test_calibrated_true_without_a_specialist_is_rejected() -> None:
    with pytest.raises(ValidationError, match="calibrated must be false"):
        _response(specialist_model=None, calibrated=True, warning=WarningCode.NO_SPECIALIST)


def test_a_specialist_free_response_must_explain_itself() -> None:
    with pytest.raises(ValidationError, match="must carry a warning"):
        _response(specialist_model=None, calibrated=False, warning=None)


def test_a_specialist_result_cannot_also_carry_vlm_text() -> None:
    """Taking both paths would mean a vehicle photo had spent VLM budget."""
    with pytest.raises(ValidationError, match="vlm_description must be null"):
        _response(vlm_description="a description")


def test_the_valid_fallback_shape_is_accepted() -> None:
    response = _response(
        domain="building",
        domain_confidence=0.71,
        specialist_model=None,
        calibrated=False,
        vlm_description="A horizontal crack is visible on the wall.",
        warning=WarningCode.NO_SPECIALIST,
    )
    assert response.findings == []
    assert response.specialist_model is None


def test_the_valid_specialist_shape_is_accepted() -> None:
    response = _response(findings=[_finding()])

    assert response.specialist_model == "cardd-yolo-seg-v1"
    assert len(response.findings) == 1
    assert response.vlm_description is None


def test_routing_confidence_calibration_is_tracked_separately() -> None:
    """A calibrated router can serve a domain that has no specialist at all.

    Reporting both facts through one flag would force a choice between calling the
    confidence untrustworthy or calling the result a measurement.
    """
    response = _response(
        domain="building",
        specialist_model=None,
        calibrated=False,
        domain_confidence_calibrated=True,
        warning=WarningCode.NO_SPECIALIST,
    )

    assert response.calibrated is False
    assert response.domain_confidence_calibrated is True


def test_severity_is_always_flagged_uncalibrated() -> None:
    assert _finding().severity_calibrated is False

    with pytest.raises(ValidationError):
        Finding.model_validate(
            {
                "type": DamageType.DENT,
                "score": 0.5,
                "bbox": (0, 0, 10, 10),
                "area_ratio": 0.01,
                "severity": Severity.MINOR,
                "severity_calibrated": True,
            }
        )


@pytest.mark.parametrize("bbox", [(260, 340, 120, 410), (0, 0, 0, 10), (-5, 0, 10, 10)])
def test_degenerate_boxes_are_rejected(bbox: tuple[int, int, int, int]) -> None:
    with pytest.raises(ValidationError):
        Finding(
            type=DamageType.CRACK,
            score=0.5,
            bbox=bbox,
            area_ratio=0.01,
            severity=Severity.MINOR,
        )


def test_a_blur_count_requires_a_named_detector() -> None:
    """Claiming redaction without naming what performed it is the failure Q5 avoids."""
    with pytest.raises(ValidationError, match="face_detector"):
        Privacy(faces_blurred=2)

    assert Privacy(faces_blurred=2, face_detector="yunet-2023mar").faces_blurred == 2


def test_undocumented_fields_are_rejected() -> None:
    """extra='forbid' is what makes the contract tests meaningful."""
    with pytest.raises(ValidationError):
        _response(surprise_field="unexpected")
