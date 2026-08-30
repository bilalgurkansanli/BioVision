"""Claim-outcome endpoints: the rule sheet, and the lines for one vehicle.

These routes run no model. They read `regulation.yaml` and divide — which is why
they are fast, deterministic, and the only part of this system whose output does
not need a caveat about accuracy. A rule either cites its article or it is not
served.

The endpoint a claimant most wants — "will my car be written off" — does not
exist here and will not. See `claims/outcome.py` for why the numerator of that
question cannot be produced from a photograph.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query

from biovision.claims.outcome import traffic_premium_impact, write_off_lines
from biovision.config import Settings, get_settings
from biovision.domains.regulation import Regulation
from biovision.schemas.claims import (
    Citation,
    CriticalPartOut,
    GapOut,
    PremiumImpactOut,
    RegulationOut,
    ThresholdLineOut,
    WriteOffLinesOut,
)

router = APIRouter(prefix="/v1/claims", tags=["claims"])


@lru_cache(maxsize=1)
def _regulation(path_str: str) -> Regulation:
    """Parsed once. The file changes when the Resmî Gazette does, not per request."""
    from pathlib import Path

    return Regulation.load(Path(path_str))


def _load(settings: Settings) -> Regulation:
    return _regulation(str(settings.regulation_path))


def _lines_out(regulation: Regulation, value: Decimal, source: str) -> WriteOffLinesOut:
    computed = write_off_lines(regulation, value, source)
    return WriteOffLinesOut(
        vehicle_value_try=computed.vehicle_value,
        value_source=computed.value_source,
        value_basis_tr=regulation.valuation.ceiling_basis_tr,
        value_basis_source=regulation.valuation.ceiling_source,
        lines=[
            ThresholdLineOut(
                key=line.key,  # type: ignore[arg-type]
                label_tr=line.label_tr,
                ratio=line.ratio,
                amount_try=line.amount,
                source=line.source,
                basis_tr=line.basis_tr,
                requires_expert_finding=line.requires_expert_finding,
            )
            for line in computed.lines
        ],
        corrections=[
            Citation(text_tr=f"{d['claim_tr']} — {d['correction_tr']}", source=d["source"])
            for d in computed.debunked
        ],
        determined_by_tr=computed.determined_by_tr,
        determined_by_source=computed.determined_by_source,
    )


@router.get("/regulation", response_model=RegulationOut, summary="The rule sheet")
def rule_sheet(
    vehicle_value_try: str | None = Query(
        default=None,
        description=(
            "Vehicle value on the date of the incident, in TRY. Supply it and the "
            "thresholds come back in lira; omit it and only the ratios are known. "
            "It cannot be inferred from a photograph — the TSB list separates trims "
            "by engine and gearbox, which no image model reads off a body panel."
        ),
    ),
) -> RegulationOut:
    """Every rule this system applies, with the article each comes from.

    Served whole, gaps included. A reader who sees `repair_cost_from_photo` in
    `gaps` learns something the rest of the payload could not tell them: that the
    number they most want is one this system refuses to invent.
    """
    regulation = _load(get_settings())

    thresholds = None
    if vehicle_value_try is not None:
        try:
            value = Decimal(vehicle_value_try)
        except (InvalidOperation, ValueError):
            raise HTTPException(422, detail="vehicle_value_try must be a decimal number") from None
        if value <= 0:
            raise HTTPException(422, detail="vehicle_value_try must be positive")
        thresholds = _lines_out(regulation, value, "caller-supplied").lines

    return RegulationOut(
        version=regulation.version,
        jurisdiction=regulation.jurisdiction,
        verified_on=regulation.verified_on,
        thresholds=thresholds,
        critical_parts=[
            CriticalPartOut(
                index=item.index,
                name_tr=item.name_tr,
                visible_in_photo=item.visible_in_photo,
                ask_user=item.ask_user,
                question_tr=item.question_tr,
            )
            for item in regulation.critical_parts.items
        ],
        critical_parts_source=regulation.critical_parts.source,
        critical_parts_discretionary=regulation.critical_parts.discretionary,
        critical_parts_note_tr=regulation.critical_parts.discretion_note_tr,
        consequences=[
            Citation(text_tr=c.text_tr, source=c.source) for c in regulation.consequences
        ],
        corrections=[
            Citation(text_tr=f"{d.claim_tr} — {d.correction_tr}", source=d.source)
            for d in regulation.write_off.debunked
        ],
        gaps=[
            GapOut(key=g.key, question_tr=g.question_tr, reason_tr=g.reason_tr)
            for g in regulation.unverified
        ],
        kasko_note_tr=regulation.kasko_discount.note_tr,
        kasko_source=regulation.kasko_discount.source,
    )


@router.get(
    "/write-off-lines",
    response_model=WriteOffLinesOut,
    summary="Where the write-off lines fall for one vehicle",
)
def lines(
    vehicle_value_try: str = Query(
        description=(
            "Value on the incident date, in TRY. Not the policy date "
            "-- Kasko GŞ B.3-3.3.1.1."
        )
    ),
    value_source: str = Query(
        default="caller-supplied",
        description=(
            "Where the value came from, carried into the response so a reader "
            "can judge it."
        ),
    ),
) -> WriteOffLinesOut:
    """Both thresholds in lira, with their articles.

    Returns no verdict. Whether a specific vehicle crosses a line depends on the
    VAT-inclusive repair cost, which only an eksper produces.
    """
    try:
        value = Decimal(vehicle_value_try)
    except (InvalidOperation, ValueError):
        raise HTTPException(422, detail="vehicle_value_try must be a decimal number") from None
    if value <= 0:
        raise HTTPException(422, detail="vehicle_value_try must be positive")

    return _lines_out(_load(get_settings()), value, value_source)


@router.get(
    "/premium-impact",
    response_model=PremiumImpactOut,
    summary="What one claim payment does to a trafik sigortası step",
)
def premium_impact(
    current_step: int = Query(ge=0, le=8, description="Current basamak, 0–8."),
    injury: bool = Query(
        default=False,
        description="Injury or death claims move two steps rather than one (Geçici m.11(8)).",
    ),
) -> PremiumImpactOut:
    """Step movement and the resulting premium ratio.

    A ratio rather than lira, because the base premium is unknown — and a ratio
    is insurer-independent, which makes it the better output anyway.

    Per claim PAYMENT, not per accident: one accident producing two payments
    moves two steps.
    """
    regulation = _load(get_settings())
    try:
        impact = traffic_premium_impact(regulation, current_step, injury=injury)
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from error

    return PremiumImpactOut(
        from_step=impact.from_step,
        to_step=impact.to_step,
        relative_increase=impact.relative_increase,
        recovery_years=impact.recovery_years,
        source=impact.source,
    )
