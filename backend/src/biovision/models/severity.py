"""The severity heuristic.

VehiDE carries no severity ground truth -- nor did CarDD -- so there is nothing to
calibrate against and no honest way to report an accuracy for this field. Every
``Finding`` therefore carries ``severity_calibrated: false`` and no accuracy claim
anywhere in this project covers ``severity``.

**Severity used to be thresholds over the damaged-area fraction, and that was
wrong in a way worth recording.** ``area_ratio`` divides damaged pixels by the
whole image, so it measures the photographer's distance as much as the damage.
Measured on one VehiDE photograph, re-framed and nothing else changed:

===========================  ============  ==========
framing                      area_ratio    severity
===========================  ============  ==========
as shot                          0.2335    severe
cropped to 70%                   0.4763    severe
padded by 40%                    0.0996    severe
padded by 100%                   0.0077    **minor**
===========================  ============  ==========

Thirty-fold, same car, same damage. A wide shot of a wrecked car -- the ambulance
and the police in frame, which is exactly what a real claim photograph looks like
-- reported `minor`. The number was real; the word attached to it was not.

**So the band now starts from what was damaged, not from how much of the frame it
covered.** A torn-off bumper is severe whether photographed from two metres or
twenty. Area can still raise a band, because a large dent is worse than a small
one, but it can no longer lower one: framing must not be able to talk severity
down.

This is a judgement call, stated as one. The class-to-band mapping below is a
claims-handling intuition -- a missing part means a replacement, a scratch means
paint -- and nobody has measured whether an assessor agrees with it.
"""

from __future__ import annotations

from biovision.schemas.enums import DamageType, Severity

#: Damaged area >= 2% of the image -> at least moderate.
SEVERITY_MODERATE_MIN_AREA = 0.02
#: Damaged area >= 8% of the image -> severe.
SEVERITY_SEVERE_MIN_AREA = 0.08

#: The floor each damage class carries regardless of how it was framed.
#:
#: Reasoning, so it can be argued with rather than only obeyed:
#:   * a part that is missing, torn or punctured has to be replaced -- severe;
#:   * a dent, a shattered pane or a broken lamp is a repair, not a write-off
#:     of the panel -- moderate;
#:   * a scratch is paintwork -- minor, and area can still raise it.
CLASS_FLOOR: dict[DamageType, Severity] = {
    DamageType.MISSING_PART: Severity.SEVERE,
    DamageType.TORN: Severity.SEVERE,
    DamageType.PUNCTURED: Severity.SEVERE,
    DamageType.GLASS_SHATTER: Severity.MODERATE,
    DamageType.LAMP_BROKEN: Severity.MODERATE,
    DamageType.DENT: Severity.MODERATE,
    DamageType.SCRATCH: Severity.MINOR,
}

_ORDER = {Severity.MINOR: 0, Severity.MODERATE: 1, Severity.SEVERE: 2}


def severity_from_area(area_ratio: float) -> Severity:
    """The old area-only band. Kept because it is one half of the answer."""
    if not 0.0 <= area_ratio <= 1.0:
        raise ValueError(f"area_ratio must be within [0, 1], got {area_ratio}")
    if area_ratio >= SEVERITY_SEVERE_MIN_AREA:
        return Severity.SEVERE
    if area_ratio >= SEVERITY_MODERATE_MIN_AREA:
        return Severity.MODERATE
    return Severity.MINOR


def severity_for(damage_type: DamageType, area_ratio: float) -> Severity:
    """Band for one finding: the class floor, raised by area but never lowered.

    Taking the maximum rather than an average is the whole point. An average
    would let a wide shot pull `missing_part` down toward `minor`, which is the
    defect this function exists to prevent.
    """
    floor = CLASS_FLOOR.get(damage_type, Severity.MINOR)
    by_area = severity_from_area(area_ratio)
    return floor if _ORDER[floor] >= _ORDER[by_area] else by_area
