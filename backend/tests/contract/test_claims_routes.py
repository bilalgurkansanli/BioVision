"""Contract tests for /v1/claims.

These routes run no model, so there is nothing here about accuracy. What they
assert is the shape of the promise: every regulatory statement carries its
article, no response carries a verdict, and the gaps are served rather than
omitted.

The first version of `/regulation` returned 500 in the browser and passed every
test, because nothing exercised it end to end -- the response model rejected an
em-dash where a citation was required. That defect is the reason this file
exists, and `test_the_rule_sheet_renders` is the test that would have caught it.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from biovision.schemas.claims import (
    AssessmentOut,
    PremiumImpactOut,
    RegulationOut,
    WriteOffLinesOut,
)


def test_the_rule_sheet_renders(client: TestClient) -> None:
    """A whole-payload render, which is what the unit tests could not do."""
    response = client.get("/v1/claims/regulation")

    assert response.status_code == 200
    sheet = RegulationOut.model_validate(response.json())

    assert len(sheet.critical_parts) == 11
    assert sheet.consequences
    assert sheet.corrections
    assert sheet.gaps


def test_the_gaps_are_served_with_their_reasons(client: TestClient) -> None:
    """A gap has no article to cite; it has a reason.

    Serving them through the citation type forced an invented source, which is
    how the 500 arose. They now carry `reason_tr` and no source at all.
    """
    sheet = RegulationOut.model_validate(client.get("/v1/claims/regulation").json())

    keys = {gap.key for gap in sheet.gaps}
    assert "repair_cost_from_photo" in keys
    assert all(gap.reason_tr for gap in sheet.gaps)


def test_every_consequence_and_correction_cites_an_article(client: TestClient) -> None:
    sheet = RegulationOut.model_validate(client.get("/v1/claims/regulation").json())

    for item in [*sheet.consequences, *sheet.corrections]:
        assert len(item.source) >= 3, item.text_tr


def test_the_seventy_percent_myth_is_corrected_in_the_payload(client: TestClient) -> None:
    """The single most repeated false figure in this domain."""
    sheet = RegulationOut.model_validate(client.get("/v1/claims/regulation").json())

    assert any("70" in correction.text_tr for correction in sheet.corrections)
    assert any("2025/12" in correction.source for correction in sheet.corrections)


def test_write_off_lines_come_back_in_lira(client: TestClient) -> None:
    response = client.get(
        "/v1/claims/write-off-lines",
        params={"vehicle_value_try": "1584880", "value_source": "TSB 202608R4"},
    )

    assert response.status_code == 200
    lines = WriteOffLinesOut.model_validate(response.json())

    heavy = next(line for line in lines.lines if line.key == "agir_hasar")
    total = next(line for line in lines.lines if line.key == "tam_hasar")

    assert str(heavy.amount_try) == "950928.00"
    assert heavy.ratio == 0.60
    assert total.requires_expert_finding is True


def test_no_endpoint_returns_a_verdict(client: TestClient) -> None:
    """The structural promise, asserted against the wire format.

    A claimant wants to know whether their car will be written off. That needs
    the VAT-inclusive repair cost, which no photo-based method produces with any
    published accuracy -- so no field here may imply one.
    """
    body = client.get(
        "/v1/claims/write-off-lines", params={"vehicle_value_try": "1000000"}
    ).json()

    forbidden = {"verdict", "outcome", "probability", "will_be_written_off", "repair_cost_try"}
    assert not forbidden & set(body)
    assert "eksper" in body["determined_by_tr"].lower()


def test_the_premium_figure_is_a_ceiling_not_a_quote(client: TestClient) -> None:
    """Ek-2 caps what an insurer may charge; Madde 5's own table is blank."""
    response = client.get("/v1/claims/premium-impact", params={"current_step": 5})

    assert response.status_code == 200
    impact = PremiumImpactOut.model_validate(response.json())
    assert impact.is_ceiling is True


def test_losing_the_top_step_reports_five_recovery_years(client: TestClient) -> None:
    top = PremiumImpactOut.model_validate(
        client.get("/v1/claims/premium-impact", params={"current_step": 8}).json()
    )
    middle = PremiumImpactOut.model_validate(
        client.get("/v1/claims/premium-impact", params={"current_step": 5}).json()
    )

    assert top.recovery_years == 5
    assert middle.recovery_years == 1


def test_an_injury_claim_costs_two_steps(client: TestClient) -> None:
    body = client.get(
        "/v1/claims/premium-impact", params={"current_step": 6, "injury": True}
    ).json()

    assert body["to_step"] == 4


def test_a_missing_vehicle_value_is_refused_rather_than_defaulted(client: TestClient) -> None:
    """There is no sensible default for the denominator of a write-off ratio.

    Substituting an average vehicle value would produce a plausible line for a
    car nobody described.
    """
    assert client.get("/v1/claims/write-off-lines").status_code == 422


def test_a_nonsense_vehicle_value_is_refused(client: TestClient) -> None:
    for value in ("0", "-5", "abc"):
        response = client.get(
            "/v1/claims/write-off-lines", params={"vehicle_value_try": value}
        )
        assert response.status_code == 422, value


def test_the_rule_sheet_omits_thresholds_without_a_vehicle(client: TestClient) -> None:
    """Ratios are knowable without a car; lira are not."""
    without = RegulationOut.model_validate(client.get("/v1/claims/regulation").json())
    assert without.thresholds is None

    with_vehicle = RegulationOut.model_validate(
        client.get("/v1/claims/regulation", params={"vehicle_value_try": "1000000"}).json()
    )
    assert with_vehicle.thresholds is not None
    assert str(with_vehicle.thresholds[0].amount_try) == "600000.00"


def test_the_kasko_ladder_is_never_presented_as_national(client: TestClient) -> None:
    sheet = RegulationOut.model_validate(client.get("/v1/claims/regulation").json())

    assert sheet.kasko_nationally_regulated is False
    assert "özel şart" in sheet.kasko_note_tr.lower() or "C.11" in sheet.kasko_source


def test_the_critical_parts_report_what_a_photograph_cannot_show(client: TestClient) -> None:
    """Eight of eleven sit behind panels.

    Published as a field rather than as prose, because it is the argument
    against training a parts model for this question and a client should be able
    to render it.
    """
    sheet = RegulationOut.model_validate(client.get("/v1/claims/regulation").json())

    invisible = [part for part in sheet.critical_parts if not part.visible_in_photo]
    asked = [part for part in sheet.critical_parts if part.ask_user]

    assert len(invisible) >= 8
    assert len(asked) == 1
    assert asked[0].question_tr


# ---------------------------------------------------------------------------
# Vehicle values, and the envelope every error must wear
# ---------------------------------------------------------------------------


def test_the_value_list_reports_itself_when_absent(client: TestClient) -> None:
    """`/vehicle/list` answers 200 whether or not the mirror exists.

    The other vehicle routes 503 when it is missing; this one reports it as data,
    so the form can explain why it is asking for a number instead of silently
    offering a free-text box where a menu should be.
    """
    response = client.get("/v1/claims/vehicle/list")

    assert response.status_code == 200
    body = response.json()
    assert "available" in body
    if not body["available"]:
        assert body["unavailable_reason_tr"]


def test_route_errors_use_the_project_envelope(client: TestClient) -> None:
    """Every failure wears `{"error": {code, message, request_id}}`.

    FastAPI's own `{"detail": "..."}` was leaking out of the claims routes. The
    frontend client parses only the envelope, so the sentence the route wrote --
    "TSB listesi yalnızca 2012-2026 model yıllarını kapsar" -- was being replaced
    by a generic failure exactly where the user needed the specific one.
    """
    response = client.get("/v1/claims/write-off-lines", params={"vehicle_value_try": "0"})

    assert response.status_code == 422
    body = response.json()
    assert "error" in body, f"raw FastAPI shape leaked: {body}"
    assert set(body["error"]) >= {"code", "message"}
    assert "detail" not in body


def test_a_model_year_outside_the_list_explains_the_boundary(client: TestClient) -> None:
    """15 model years is a documented limit, not a lookup failure.

    Reporting "not found" would read as a data problem. The response names the
    range and tells the user what to do instead.
    """
    listing = client.get("/v1/claims/vehicle/list").json()
    if not listing["available"]:
        pytest.skip("TSB mirror not built in this environment")

    too_old = listing["oldest_model_year"] - 5
    response = client.get(
        "/v1/claims/vehicle/value",
        params={"model_year": too_old, "brand_code": 123, "type_code": 2212},
    )

    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert str(listing["oldest_model_year"]) in message
    assert "elle" in message.lower()


def test_a_missing_trim_is_not_substituted_with_a_neighbouring_year(
    client: TestClient,
) -> None:
    """The adjacent model year is a different car.

    Substituting one would put a confident number under a vehicle nobody
    described, and every write-off line is a ratio against that number.
    """
    listing = client.get("/v1/claims/vehicle/list").json()
    if not listing["available"]:
        pytest.skip("TSB mirror not built in this environment")

    response = client.get(
        "/v1/claims/vehicle/value",
        params={"model_year": 2020, "brand_code": 123, "type_code": 999999},
    )
    assert response.status_code == 404


def test_a_looked_up_value_carries_what_it_does_not_account_for(
    client: TestClient,
) -> None:
    """The caveat travels with the figure, not in the UI.

    A number that leaves this response without it is a number someone will
    screenshot: TSB values are averages, with no mileage, condition or damage
    adjustment, and the policy names the contractual reference.
    """
    listing = client.get("/v1/claims/vehicle/list").json()
    if not listing["available"]:
        pytest.skip("TSB mirror not built in this environment")

    years = client.get("/v1/claims/vehicle/years").json()
    brands = client.get("/v1/claims/vehicle/brands", params={"model_year": years[0]}).json()
    types = client.get(
        "/v1/claims/vehicle/types", params={"model_year": years[0], "brand": brands[0]}
    ).json()
    if not types:
        pytest.skip("no trims for the first brand in this revision")

    response = client.get(
        "/v1/claims/vehicle/value",
        params={
            "model_year": years[0],
            "brand_code": types[0]["brand_code"],
            "type_code": types[0]["type_code"],
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert body["is_individual_appraisal"] is False
    assert body["caveat_tr"]
    assert body["revision"] in body["source_label"]


# ---------------------------------------------------------------------------
# /v1/claims/assessment -- the whole picture, assembled
# ---------------------------------------------------------------------------
#
#  This endpoint is where the temptation lives. It has the vehicle's value, the
#  regulatory lines, the severity band and the premium ladder in one place, and
#  a verdict would fall out of them in one line of code. These tests are the
#  reason it does not.


def test_an_empty_assessment_still_answers_something(client: TestClient) -> None:
    """A claimant an hour after a crash has not found their policy yet.

    Refusing to produce anything until every field is filled would be a form,
    not a product. With nothing supplied this returns the questions and the
    gaps -- which is the honest version of "I need more from you".
    """
    response = client.post("/v1/claims/assessment", json={})

    assert response.status_code == 200
    body = AssessmentOut.model_validate(response.json())
    assert body.write_off is None
    assert body.payout == []
    assert body.open_questions, "with nothing supplied, the questions are the answer"
    assert body.gaps


def test_supplying_a_value_produces_lines_and_both_branches(client: TestClient) -> None:
    response = client.post(
        "/v1/claims/assessment",
        json={"vehicle_value_try": "1584880", "deductible_try": "0"},
    )

    assert response.status_code == 200
    body = AssessmentOut.model_validate(response.json())
    assert body.write_off is not None
    assert {line.key for line in body.write_off.lines} == {"agir_hasar", "tam_hasar"}
    assert {branch.key for branch in body.payout} == {"tam_hasar", "onarim"}


def test_the_response_never_grows_a_verdict(client: TestClient) -> None:
    """A structural check over the whole serialised payload, not one field.

    `extra="forbid"` stops a field being added to a model; this stops one being
    added anywhere in the tree under a name that would read as a prediction.
    """
    response = client.post(
        "/v1/claims/assessment",
        json={
            "vehicle_value_try": "1584880",
            "overall_severity": "severe",
            "traffic_step": 8,
            "kasko_kademe": 4,
        },
    )
    assert response.status_code == 200

    forbidden = ("verdict", "probability", "will_be", "estimated_cost", "repair_cost_try")
    flat = json.dumps(response.json()).lower()
    for word in forbidden:
        assert f'"{word}' not in flat, f"the payload grew a {word} field"


def test_the_severity_band_arrives_with_its_measured_frequency(client: TestClient) -> None:
    """The band alone is the failure this field exists to fix."""
    response = client.post(
        "/v1/claims/assessment",
        json={"vehicle_value_try": "1584880", "overall_severity": "moderate"},
    )
    body = AssessmentOut.model_validate(response.json())

    assert body.severity_reliability is not None
    # The most important cell in the table: of the photographs called moderate,
    # more were severe than were moderate.
    assert body.severity_reliability.worse_share > body.severity_reliability.correct_share


def test_the_kasko_figure_is_never_rendered_as_a_national_rule(client: TestClient) -> None:
    response = client.post(
        "/v1/claims/assessment", json={"vehicle_value_try": "500000", "kasko_kademe": 4}
    )
    body = AssessmentOut.model_validate(response.json())

    assert body.kasko_premium is not None
    assert body.kasko_premium.nationally_regulated is False
    assert body.kasko_premium.sample_size == 1


def test_the_traffic_limit_states_the_shortfall_in_lira(client: TestClient) -> None:
    """The figure a claimant is most likely to be blindsided by.

    Trafik sigortası is a liability policy with a per-vehicle property cap. Being
    told the other driver was at fault, and then discovering the compulsory cover
    stops at 400,000 TL, is a specific and avoidable surprise.
    """
    response = client.post(
        "/v1/claims/assessment", json={"vehicle_value_try": "1584880"}
    )
    body = AssessmentOut.model_validate(response.json())

    assert body.traffic_limit is not None
    assert body.traffic_limit.property_per_vehicle_try == Decimal("400000")
    assert body.traffic_limit.shortfall_try == Decimal("1184880")


def test_a_vehicle_under_the_limit_reports_no_shortfall(client: TestClient) -> None:
    """None rather than zero: "no gap" and "a gap of nothing" read differently."""
    response = client.post("/v1/claims/assessment", json={"vehicle_value_try": "250000"})
    body = AssessmentOut.model_validate(response.json())

    assert body.traffic_limit is not None
    assert body.traffic_limit.shortfall_try is None


def test_a_partial_trim_is_rejected_rather_than_guessed(client: TestClient) -> None:
    """Two of the three fields name a different car."""
    response = client.post(
        "/v1/claims/assessment", json={"model_year": 2020, "brand_code": 42}
    )
    assert response.status_code == 422


def test_the_two_write_off_rules_are_not_modelled_as_parallel(client: TestClient) -> None:
    """m.5(1) and m.4(1) have different structures, and the difference is money.

    Ağır hasar is a bare 60% threshold. Tam hasar is cumulative: the cost must
    exceed the value **and** an expert must find the vehicle beyond repair.
    Presenting them as two rows of the same rule would give wrong answers at the
    boundary — in the direction that writes off a repairable car.
    """
    body = AssessmentOut.model_validate(
        client.post("/v1/claims/assessment", json={"vehicle_value_try": "1000000"}).json()
    )
    assert body.write_off is not None
    lines = {line.key: line for line in body.write_off.lines}

    assert lines["agir_hasar"].requires_expert_finding is False
    assert lines["tam_hasar"].requires_expert_finding is True


def test_the_sixty_percent_line_carries_the_consequence_that_is_irreversible(
    client: TestClient,
) -> None:
    """The part a claimant cares about more than the payment.

    Crossing 60% puts a "trafikten çekilmiştir" record on the vehicle, and that
    record permanently forecloses the değer kaybı claim. A response that reported
    only the lira figure would omit the half that cannot be undone — so the
    consequence travels with the line rather than living in a separate endpoint.
    """
    body = AssessmentOut.model_validate(
        client.post("/v1/claims/assessment", json={"vehicle_value_try": "1000000"}).json()
    )
    assert body.write_off is not None
    heavy = next(line for line in body.write_off.lines if line.key == "agir_hasar")

    assert heavy.consequences, "the heavy-damage line lost its consequences"
    assert any("değer kaybı" in item.text_tr for item in heavy.consequences)
    assert all(item.source for item in heavy.consequences)


def test_staying_under_the_lines_is_described_too(client: TestClient) -> None:
    """The protections on the good side, which a claimant does not know they have.

    `below_threshold` entries must not pick up the `both` consequences: "payment
    needs a hurda belgesi" follows from CROSSING a line, and listing it under
    staying below would invert its meaning.
    """
    body = AssessmentOut.model_validate(
        client.post("/v1/claims/assessment", json={"vehicle_value_try": "1000000"}).json()
    )
    assert body.write_off is not None

    texts = " ".join(item.text_tr for item in body.write_off.below_threshold_tr)
    assert texts, "the below-threshold protections are not served"
    assert "terk ettiremez" in texts
    assert "hurda tescil belgesi" not in texts


def test_a_bare_kasko_discount_is_not_read_as_a_total_loss(client: TestClient) -> None:
    """The defect this test was written for, and it was on screen.

    A claimant typing the 60% printed on their policy — saying nothing about
    their car being written off — used to be told their premium would rise 150%,
    because a discount without a kademe was the only shape that could answer the
    total-loss branch and the route assumed it. The repair figure on the same
    ladder is 25%. The wrong answer was six times larger and in the frightening
    direction.
    """
    body = AssessmentOut.model_validate(
        client.post(
            "/v1/claims/assessment",
            json={"vehicle_value_try": "500000", "kasko_current_discount": 0.60},
        ).json()
    )

    assert body.kasko_premium is None, "a repair cannot be answered from a bare percentage"
    assert any(q.key == "kasko_kademe" for q in body.open_questions), (
        "refusing to answer must come with the question that would let us"
    )


def test_the_total_loss_branch_is_answered_when_it_is_actually_asked_for(
    client: TestClient,
) -> None:
    """Opt-in, and then the documented clause applies."""
    body = AssessmentOut.model_validate(
        client.post(
            "/v1/claims/assessment",
            json={
                "vehicle_value_try": "500000",
                "kasko_current_discount": 0.60,
                "kasko_total_loss": True,
            },
        ).json()
    )

    assert body.kasko_premium is not None
    assert body.kasko_premium.to_discount == 0.0
    # 1 / (1 - 0.60) - 1
    assert round(body.kasko_premium.relative_increase, 4) == 1.5


def test_a_kademe_still_answers_the_repair_branch(client: TestClient) -> None:
    """The common path must not have been broken by making total loss explicit."""
    body = AssessmentOut.model_validate(
        client.post(
            "/v1/claims/assessment",
            json={"vehicle_value_try": "500000", "kasko_kademe": 4},
        ).json()
    )

    assert body.kasko_premium is not None
    assert (body.kasko_premium.from_kademe, body.kasko_premium.to_kademe) == (4, 3)
    # (1 - 0.50) / (1 - 0.60) - 1
    assert round(body.kasko_premium.relative_increase, 4) == 0.25
