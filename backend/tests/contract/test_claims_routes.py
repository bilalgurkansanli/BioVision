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

from fastapi.testclient import TestClient

from biovision.schemas.claims import PremiumImpactOut, RegulationOut, WriteOffLinesOut


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
