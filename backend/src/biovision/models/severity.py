"""The severity heuristic.

Thresholds over the damaged-area fraction. These are a judgement call, not a fitted
model: VehiDE carries no severity ground truth -- nor did CarDD -- so there is
nothing to calibrate against and no honest way to report an accuracy for this field.

Consequences, applied consistently:

* the thresholds live here, in one place, and are reproduced in the README;
* every ``Finding`` carries ``severity_calibrated: false``;
* no accuracy claim anywhere in this project covers ``severity``.
"""

from __future__ import annotations

from biovision.schemas.enums import Severity

#: Damaged area >= 2% of the image -> moderate.
SEVERITY_MODERATE_MIN_AREA = 0.02
#: Damaged area >= 8% of the image -> severe.
SEVERITY_SEVERE_MIN_AREA = 0.08


def severity_for(area_ratio: float) -> Severity:
    """Map a damaged-area fraction in [0, 1] to a coarse severity band."""
    if not 0.0 <= area_ratio <= 1.0:
        raise ValueError(f"area_ratio must be within [0, 1], got {area_ratio}")
    if area_ratio >= SEVERITY_SEVERE_MIN_AREA:
        return Severity.SEVERE
    if area_ratio >= SEVERITY_MODERATE_MIN_AREA:
        return Severity.MODERATE
    return Severity.MINOR
