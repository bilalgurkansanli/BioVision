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
from biovision.claims.scenario import kasko_premium_impact, payout_scenarios
from biovision.claims.valuation import TsbValueList, ValueListUnavailableError
from biovision.config import Settings, get_settings
from biovision.domains.regulation import Regulation
from biovision.models.band_reliability import reliability_out
from biovision.schemas.claims import (
    AssessmentOut,
    AssessmentRequest,
    Citation,
    ConsequenceOut,
    CriticalPartOut,
    GapOut,
    KaskoImpactOut,
    OpenQuestionOut,
    PayoutScenarioOut,
    PremiumImpactOut,
    RegulationOut,
    ThresholdLineOut,
    TrafficLimitOut,
    ValuationOut,
    ValueListMetaOut,
    VehicleTypeOut,
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


def _consequences_for(regulation: Regulation, key: str) -> list[ConsequenceOut]:
    """What crossing one line does, beyond the payment.

    `both` entries appear under each line rather than once above them: a reader
    scanning the ağır hasar figure should not have to find a shared paragraph to
    learn that the record blocks payment until a document is produced.

    They are **not** folded into `below_threshold`, which is the other side of
    the same lines: "payment needs a hurda belgesi" is a consequence of crossing
    one, and listing it under staying below would invert its meaning.
    """
    scopes = {key} if key in ("below_threshold", "procedure") else {key, "both"}
    return [
        ConsequenceOut(
            key=item.key,
            text_tr=item.text_tr,
            source=item.source,
            irreversible=item.irreversible,
            line_specific=item.applies_to == key,
        )
        for item in regulation.consequences
        if item.applies_to in scopes
    ]


def _lines_out(regulation: Regulation, value: Decimal, source: str) -> WriteOffLinesOut:
    computed = write_off_lines(regulation, value, source)
    return WriteOffLinesOut(
        vehicle_value_try=computed.vehicle_value,
        value_source=computed.value_source,
        value_basis_tr=regulation.valuation.ceiling_basis_tr,
        value_basis_source=regulation.valuation.ceiling_source,
        value_reference_default_tr=regulation.valuation.reference_default_tr,
        value_reference_default_source=regulation.valuation.reference_default_source,
        lines=[
            ThresholdLineOut(
                key=line.key,  # type: ignore[arg-type]
                label_tr=line.label_tr,
                ratio=line.ratio,
                amount_try=line.amount,
                source=line.source,
                basis_tr=line.basis_tr,
                requires_expert_finding=line.requires_expert_finding,
                consequences=_consequences_for(regulation, line.key),
            )
            for line in computed.lines
        ],
        below_threshold_tr=_consequences_for(regulation, "below_threshold"),
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
            "Value on the incident date, in TRY. Not the policy date -- Kasko GŞ B.3-3.3.1.1."
        )
    ),
    value_source: str = Query(
        default="caller-supplied",
        description=(
            "Where the value came from, carried into the response so a reader can judge it."
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


@router.post(
    "/assessment",
    response_model=AssessmentOut,
    summary="Everything the claim side can say about one photographed vehicle",
)
def assessment(request: AssessmentRequest) -> AssessmentOut:
    """The whole claim picture, assembled from what the caller could supply.

    One response rather than five, because the relationships between these
    figures are the product: a payout is meaningless without the value it
    subtracts from, and a severity band is misleading without the frequency
    behind it. Assembling them here also means the honesty invariants are
    enforced once, in pydantic, instead of in every client that stitches the
    pieces together.

    Degrades field by field. Supply nothing and the rule sheet and the questions
    come back; supply the trim and the lines appear in lira; supply the muafiyet
    and the total-loss branch becomes an exact number. Nothing is ever guessed to
    fill a gap -- `open_questions` names what would close each one.

    **Still no verdict.** Which side of a line a car falls on needs the
    VAT-inclusive repair cost, which no published method produces from a
    photograph with a measured error rate against real invoices.
    """
    regulation = _load(get_settings())

    valuation: ValuationOut | None = None
    value: Decimal | None = request.vehicle_value_try
    value_source = "caller-supplied" if value is not None else "not supplied"

    if value is None and request.model_year is not None:
        assert request.brand_code is not None and request.type_code is not None
        valuation = vehicle_value(request.model_year, request.brand_code, request.type_code)
        value = valuation.amount_try
        value_source = valuation.source_label

    lines_out: WriteOffLinesOut | None = None
    payout: list[PayoutScenarioOut] = []
    if value is not None:
        lines_out = _lines_out(regulation, value, value_source)
        computed = write_off_lines(regulation, value, value_source)
        payout = [
            PayoutScenarioOut(
                key=scenario.key,
                label_tr=scenario.label_tr,
                amount_try=scenario.amount_try,
                lower_try=scenario.lower_try,
                upper_try=scenario.upper_try,
                basis_tr=scenario.basis_tr,
                source=scenario.source,
                missing_tr=list(scenario.missing_tr),
            )
            for scenario in payout_scenarios(
                regulation,
                computed,
                deductible=request.deductible_try,
                salvage_retained=request.salvage_retained,
            )
        ]

    traffic: PremiumImpactOut | None = None
    if request.traffic_step is not None:
        try:
            impact = traffic_premium_impact(
                regulation, request.traffic_step, injury=request.traffic_injury
            )
        except ValueError as error:
            raise HTTPException(422, detail=str(error)) from error
        traffic = PremiumImpactOut(
            from_step=impact.from_step,
            to_step=impact.to_step,
            relative_increase=impact.relative_increase,
            recovery_years=impact.recovery_years,
            source=impact.source,
        )

    kasko = _kasko_out(regulation, request)

    return AssessmentOut(
        valuation=valuation,
        value_source=value_source,
        write_off=lines_out,
        payout=payout,
        severity_reliability=reliability_out(request.overall_severity),
        procedure=_consequences_for(regulation, "procedure"),
        traffic_limit=_traffic_limit_out(regulation, value),
        traffic_premium=traffic,
        kasko_premium=kasko,
        # Only the ones a photograph cannot reach. Listing all eleven would bury
        # the three that are actually visible under eight that are not.
        critical_part_questions=[
            CriticalPartOut(
                index=item.index,
                name_tr=item.name_tr,
                visible_in_photo=item.visible_in_photo,
                ask_user=item.ask_user,
                question_tr=item.question_tr,
            )
            for item in regulation.critical_parts.items
            if not item.visible_in_photo
        ],
        open_questions=_open_questions(request, value),
        gaps=[
            GapOut(key=gap.key, question_tr=gap.question_tr, reason_tr=gap.reason_tr)
            for gap in regulation.unverified
        ],
    )


def _traffic_limit_out(regulation: Regulation, value: Decimal | None) -> TrafficLimitOut:
    """The counterparty's compulsory ceiling, and the gap it leaves.

    Returned even without a vehicle value, because the limit itself is worth
    knowing; `shortfall_try` is what needs the value. The subtraction assumes
    nothing about fault -- it says what the ceiling is, not who will pay.
    """
    limits = regulation.traffic_limits
    cap = Decimal(limits.property_per_vehicle_try)
    shortfall = value - cap if value is not None and value > cap else None
    return TrafficLimitOut(
        property_per_vehicle_try=cap,
        property_per_accident_try=Decimal(limits.property_per_accident_try),
        in_force_from=limits.in_force_from,
        source=limits.source,
        official_gazette=limits.official_gazette,
        applies_on_tr=f"{limits.applies_on_tr} ({limits.applies_on_source})",
        note_tr=limits.note_tr,
        shortfall_try=shortfall,
    )


def _kasko_out(regulation: Regulation, request: AssessmentRequest) -> KaskoImpactOut | None:
    """The kasko premium ratio, where the caller gave enough to compute one.

    Silent rather than approximate when they did not: the ladder is an özel şart,
    and the alternative to `None` here is presenting one insurer's clause as the
    claimant's own contract.

    **`kasko_total_loss` is asked rather than assumed, and it used to be assumed.**
    A discount without a kademe was read as "this is a total loss", because that
    is the only branch a bare percentage can answer. So a claimant who typed the
    60% printed on their policy — and said nothing about their car being written
    off — was told their premium would rise **150%**. The true figure for a repair
    on the illustrative ladder is 25%. The wrong one was six times larger, in the
    frightening direction, on a scenario nobody had described.

    Now an unanswerable combination returns `None` and `_open_questions` asks for
    the kademe, which is the same shape every other open figure in this response
    takes.
    """
    if request.kasko_kademe is None and request.kasko_current_discount is None:
        return None
    if request.kasko_kademe is None and not request.kasko_total_loss:
        # A bare percentage cannot answer a repair: where the discount lands next
        # is written in the claimant's own özel şart, which nothing here has read.
        return None
    try:
        impact = kasko_premium_impact(
            regulation,
            current_discount=request.kasko_current_discount
            if request.kasko_kademe is None
            else None,
            current_kademe=request.kasko_kademe,
            claims=request.kasko_claims_this_period,
            total_loss=request.kasko_total_loss,
        )
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from error

    return KaskoImpactOut(
        from_discount=impact.from_discount,
        to_discount=impact.to_discount,
        relative_increase=impact.relative_increase,
        basis_tr=impact.basis_tr,
        source=impact.source,
        insurer=impact.insurer,
        sample_size=impact.sample_size,
        from_kademe=impact.from_kademe,
        to_kademe=impact.to_kademe,
        disclaimer_tr=impact.disclaimer_tr,
    )


def _open_questions(request: AssessmentRequest, value: Decimal | None) -> list[OpenQuestionOut]:
    """What the claimant could answer next, and what each answer unlocks.

    The most useful thing this product does when it cannot compute something. Not
    "unknown" but "here is the one fact that would let us know" -- which turns a
    gap into a next step rather than a dead end.
    """
    questions: list[OpenQuestionOut] = []
    if value is None:
        questions.append(
            OpenQuestionOut(
                key="vehicle_value",
                question_tr="Aracınızın marka, model yılı ve tipi nedir?",
                unlocks_tr=(
                    "Ağır hasar ve tam hasar çizgileri lira cinsinden, ve tam hasar "
                    "ödemesinin tavanı."
                ),
                from_document=False,
            )
        )
    if request.deductible_try is None:
        questions.append(
            OpenQuestionOut(
                key="deductible",
                question_tr="Kasko poliçenizde muafiyet (kendi üzerinize kalan tutar) var mı?",
                unlocks_tr="Ödeme rakamlarının kesinleşmesi; muafiyet her senaryodan düşülür.",
            )
        )
    if request.traffic_step is None:
        questions.append(
            OpenQuestionOut(
                key="traffic_step",
                question_tr="Trafik sigortası basamağınız kaç? (0–8, poliçenizde yazar)",
                unlocks_tr="Bir ödeme sonrası priminizin tavan olarak ne kadar artacağı.",
            )
        )
    if request.kasko_kademe is None and request.kasko_current_discount is None:
        questions.append(
            OpenQuestionOut(
                key="kasko_discount",
                question_tr="Kasko poliçenizdeki hasarsızlık indirimi yüzde kaç?",
                unlocks_tr=(
                    "Kaskonuzun yenilemede ne kadar artacağı — kendi oranınızla "
                    "hesaplanır, piyasa ortalamasıyla değil."
                ),
            )
        )
    elif request.kasko_kademe is None and not request.kasko_total_loss:
        # The discount alone cannot answer a repair, and this is the sentence
        # that replaced silently assuming a total loss and quoting +150%.
        questions.append(
            OpenQuestionOut(
                key="kasko_kademe",
                question_tr=(
                    "Kasko poliçenizde hasarsızlık KADEMESİ de yazıyor mu? (0–5 arası bir basamak)"
                ),
                unlocks_tr=(
                    "Onarımla sonuçlanan bir hasarda priminizin ne olacağı. Yalnız "
                    "indirim oranı bunu vermez: indirimin nereye ineceğini "
                    "poliçenizin özel şartı belirler ve bu sistem onu okumadı. "
                    "Girdiğiniz oran şimdilik yalnızca tam hasar senaryosunda "
                    "kullanılabilir."
                ),
            )
        )
    questions.append(
        OpenQuestionOut(
            key="salvage_choice",
            question_tr="Tam hasar hâlinde hasarlı aracı size mi bıraksınlar?",
            unlocks_tr=(
                "Hangi ödeme senaryosunun geçerli olduğu. Araç sizde kalırsa ödeme "
                "'rayiç eksi sovtaj' olur ve sovtajı eksper belirler."
            ),
            from_document=False,
        )
    )
    return questions


# ---------------------------------------------------------------------------
# Vehicle values
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _value_list(path_str: str) -> TsbValueList:
    """Opened once per worker, read-only. The file changes monthly, not per request."""
    from pathlib import Path

    return TsbValueList(Path(path_str))


def _values() -> TsbValueList:
    """The list, or a 503 naming what to run.

    A 503 rather than a 500: nothing is broken, a monthly mirror simply has not
    been built, and the caller can still supply a value by hand.
    """
    try:
        return _value_list(str(get_settings().tsb_value_list_path))
    except ValueListUnavailableError as error:
        raise HTTPException(503, detail=str(error)) from error


@router.get(
    "/vehicle/list",
    response_model=ValueListMetaOut,
    summary="Which TSB revision is mirrored, and what it covers",
)
def value_list_meta() -> ValueListMetaOut:
    """Always 200, because "no list" is an answer the UI must render.

    The other vehicle routes 503 when the mirror is missing; this one reports it
    as data so the form can say why it is asking for a number instead of
    offering a menu.
    """
    try:
        values = _value_list(str(get_settings().tsb_value_list_path))
    except ValueListUnavailableError as error:
        return ValueListMetaOut(
            available=False,
            unavailable_reason_tr=(
                "TSB Kasko Değer Listesi bu kurulumda yüklü değil; aracınızın "
                "değerini elle girmeniz gerekiyor. (" + str(error) + ")"
            ),
        )

    meta = values.meta
    return ValueListMetaOut(
        available=True,
        revision=meta.revision,
        month_label=meta.month_label,
        oldest_model_year=meta.oldest_model_year,
        newest_model_year=meta.newest_model_year,
        fetched_at=meta.fetched_at,
        caveat_tr=meta.caveat_tr,
    )


@router.get("/vehicle/years", response_model=list[int], summary="Model years in the list")
def vehicle_years() -> list[int]:
    return _values().model_years()


@router.get("/vehicle/brands", response_model=list[str], summary="Brands for a model year")
def vehicle_brands(
    model_year: int = Query(description="Model year, as listed by /vehicle/years."),
) -> list[str]:
    """Only brands that actually have a value that year.

    Offering one with nothing behind it would let a user complete the whole menu
    and arrive at an empty answer.
    """
    values = _values()
    if not values.covers(model_year):
        raise HTTPException(
            422,
            detail=(
                f"TSB listesi {values.meta.oldest_model_year}-"
                f"{values.meta.newest_model_year} model yıllarını kapsar; {model_year} "
                "listede yer almaz."
            ),
        )
    return values.brands(model_year)


@router.get(
    "/vehicle/types", response_model=list[VehicleTypeOut], summary="Trims for a brand and year"
)
def vehicle_types(
    model_year: int = Query(),
    brand: str = Query(description="Exact brand name as returned by /vehicle/brands."),
) -> list[VehicleTypeOut]:
    return [
        VehicleTypeOut(
            brand_code=item.brand_code,
            type_code=item.type_code,
            brand_name=item.brand_name,
            type_name=item.type_name,
        )
        for item in _values().types(model_year, brand)
    ]


@router.get("/vehicle/value", response_model=ValuationOut, summary="Listed value for one trim")
def vehicle_value(
    model_year: int = Query(),
    brand_code: int = Query(),
    type_code: int = Query(),
) -> ValuationOut:
    """The listed value, or 404 -- never the nearest year.

    A trim not sold in a given model year has no row, and the adjacent year is a
    different car. Substituting one would put a confident number under a vehicle
    nobody described, and every write-off line is a ratio against that number.
    """
    values = _values()
    if not values.covers(model_year):
        raise HTTPException(
            422,
            detail=(
                f"TSB listesi yalnızca {values.meta.oldest_model_year}-"
                f"{values.meta.newest_model_year} model yıllarını kapsar. Daha eski "
                "araçlarda sigorta bedeli sigortacı ile sigortalı arasında "
                "kararlaştırılır; değeri elle girmeniz gerekir."
            ),
        )

    found = values.value_for(model_year, brand_code, type_code)
    if found is None:
        raise HTTPException(404, detail="Bu tip için bu model yılında listede değer yok.")

    return ValuationOut(
        vehicle=VehicleTypeOut(
            brand_code=found.vehicle.brand_code,
            type_code=found.vehicle.type_code,
            brand_name=found.vehicle.brand_name,
            type_name=found.vehicle.type_name,
        ),
        model_year=found.model_year,
        amount_try=found.amount_try,
        source_label=found.source_label,
        source_url=found.meta.source_url,
        revision=found.meta.revision,
        fetched_at=found.meta.fetched_at,
        caveat_tr=found.meta.caveat_tr,
    )
