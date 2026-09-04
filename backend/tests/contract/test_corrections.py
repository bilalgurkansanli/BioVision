"""Filing a correction against one's own analysis.

The table exists to collect the one thing `docs/OPEN_QUESTIONS.md` has said is
missing since the first evaluation set was built: photographs from a real intake,
with somebody's judgement attached. So these tests are mostly about the ways a
row could be collected and turn out to be worthless later —

* filed against an analysis the caller cannot see;
* naming a finding that does not exist;
* disagreeing with a result that already agreed;
* claiming consent to keep a photograph that was never stored.

Each of those satisfies every check constraint in `0003_corrections.sql` and
means nothing to whoever comes to use it, which is why the API rejects them
rather than the database.

They run against the same `FakeRepository` as the history tests, keyed on the
access token, so a handler that reached for a service-role key would read the
wrong rows here exactly as it would in production.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import Steer, make_png
from tests.fakes import ALICE, BOB, FakeRepository, headers_for


def _analyse(client: TestClient, user: str, seed: int = 1) -> dict[str, Any]:
    body = client.post(
        "/v1/analyze",
        files={"image": (f"{seed}.png", make_png(seed), "image/png")},
        headers=headers_for(user),
    )
    assert body.status_code == 200
    return dict(body.json())


def _file(
    client: TestClient, user: str, analysis_id: str, **payload: Any
) -> tuple[int, dict[str, Any]]:
    response = client.post(
        f"/v1/requests/{analysis_id}/corrections",
        json=payload,
        headers=headers_for(user),
    )
    return response.status_code, dict(response.json())


@pytest.fixture
def vehicle(client: TestClient, steer: Steer) -> None:
    steer(forced_domain="vehicle", forced_confidence=0.93)


# ---------------------------------------------------------------------------
# The ordinary path
# ---------------------------------------------------------------------------


def test_a_user_can_say_a_finding_is_not_there(
    client: TestClient, repository: FakeRepository, authed: None, vehicle: None
) -> None:
    analysis = _analyse(client, ALICE)
    assert analysis["findings"], "this test needs a finding to disagree with"

    status, body = _file(
        client, ALICE, analysis["request_id"], kind="wrong_finding", finding_index=0
    )

    assert status == 201
    assert body["stored"] is True
    assert repository.corrections[0]["kind"] == "wrong_finding"
    assert repository.corrections[0]["finding_index"] == 0


def test_a_user_can_report_damage_nothing_found(
    client: TestClient, repository: FakeRepository, authed: None, vehicle: None
) -> None:
    """The case the published recall figures describe and cannot point at."""
    analysis = _analyse(client, ALICE)

    status, _ = _file(
        client,
        ALICE,
        analysis["request_id"],
        kind="missed_damage",
        expected_type="torn",
        note="arka tampon kopmuş",
    )

    assert status == 201
    stored = repository.corrections[0]
    assert stored["expected_type"] == "torn"
    assert stored["note"] == "arka tampon kopmuş"


def test_the_analysis_itself_is_never_touched(
    client: TestClient, repository: FakeRepository, authed: None, vehicle: None
) -> None:
    """A correction sits beside the record, and the record stays as the model left it.

    `analyses` has no UPDATE policy because it is what a model said at a point in
    time. That does not weaken because the edit would come from a user.
    """
    analysis = _analyse(client, ALICE)
    before = client.get("/v1/requests", headers=headers_for(ALICE)).json()["items"][0]

    _file(client, ALICE, analysis["request_id"], kind="wrong_finding", finding_index=0)

    after = client.get("/v1/requests", headers=headers_for(ALICE)).json()["items"][0]
    assert after == before


# ---------------------------------------------------------------------------
# Rows that would be worthless later
# ---------------------------------------------------------------------------


def test_another_users_analysis_is_not_correctable_and_is_not_confirmed(
    client: TestClient, repository: FakeRepository, authed: None, vehicle: None
) -> None:
    """404, not 403: distinguishing them would confirm the id exists."""
    analysis = _analyse(client, ALICE)

    status, body = _file(
        client, BOB, analysis["request_id"], kind="wrong_finding", finding_index=0
    )

    assert status == 404
    assert body["error"]["code"] == "not_found"
    assert repository.corrections == []


def test_an_index_past_the_end_names_nothing_and_is_refused(
    client: TestClient, repository: FakeRepository, authed: None, vehicle: None
) -> None:
    analysis = _analyse(client, ALICE)

    status, body = _file(
        client, ALICE, analysis["request_id"], kind="wrong_finding", finding_index=99
    )

    assert status == 422
    assert body["error"]["code"] == "invalid_correction"
    assert repository.corrections == []


def test_nothing_wrong_needs_something_to_disagree_with(
    client: TestClient, steer: Steer, repository: FakeRepository, authed: None
) -> None:
    """A `nothing_wrong` on an empty finding list agrees rather than corrects."""
    steer(forced_domain="other", forced_confidence=0.93)
    analysis = _analyse(client, ALICE)
    assert analysis["findings"] == []

    status, body = _file(client, ALICE, analysis["request_id"], kind="nothing_wrong")

    assert status == 422
    assert body["error"]["code"] == "invalid_correction"


def test_an_unknown_analysis_is_a_404(
    client: TestClient, repository: FakeRepository, authed: None, vehicle: None
) -> None:
    status, _ = _file(
        client,
        ALICE,
        "11111111-1111-1111-1111-111111111111",
        kind="nothing_wrong",
    )

    assert status == 404


def test_signing_in_is_required(client: TestClient, vehicle: None) -> None:
    """Anonymous analyses are never stored, so there is nothing to correct."""
    response = client.post(
        "/v1/requests/11111111-1111-1111-1111-111111111111/corrections",
        json={"kind": "nothing_wrong"},
    )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# The kind decides what else is required
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        # About one finding, but names none.
        {"kind": "wrong_finding"},
        {"kind": "wrong_type", "expected_type": "dent"},
        # About the whole result, but names a finding.
        {"kind": "missed_damage", "finding_index": 0},
        {"kind": "nothing_wrong", "finding_index": 0},
        # Says the class is wrong without saying the right one.
        {"kind": "wrong_type", "finding_index": 0},
        # Says the band is wrong without saying which it should be.
        {"kind": "wrong_severity", "finding_index": 0},
    ],
)
def test_a_correction_that_contradicts_itself_is_refused(
    client: TestClient,
    repository: FakeRepository,
    authed: None,
    vehicle: None,
    payload: dict[str, Any],
) -> None:
    analysis = _analyse(client, ALICE)

    status, _ = _file(client, ALICE, analysis["request_id"], **payload)

    assert status == 422
    assert repository.corrections == []


def test_an_expected_severity_is_recorded_rather_than_dropped(
    client: TestClient, repository: FakeRepository, authed: None, vehicle: None
) -> None:
    """The table has no column for it, so it rides in the note with a marker.

    Silently discarding the one field the user was asked to supply is how a form
    ends up collecting nothing.
    """
    analysis = _analyse(client, ALICE)

    status, _ = _file(
        client,
        ALICE,
        analysis["request_id"],
        kind="wrong_severity",
        finding_index=0,
        expected_severity="severe",
    )

    assert status == 201
    assert repository.corrections[0]["note"] == "[expected_severity=severe]"


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------


def test_keeping_the_photograph_is_off_unless_asked_for(
    client: TestClient, repository: FakeRepository, authed: None, vehicle: None
) -> None:
    """A correction must not quietly become a consent form."""
    analysis = _analyse(client, ALICE)

    _, body = _file(
        client, ALICE, analysis["request_id"], kind="wrong_finding", finding_index=0
    )

    assert body["image_retained"] is False
    assert body["retention_days"] == 7
    assert repository.corrections[0]["retain_image"] is False


def test_consent_is_not_echoed_back_for_an_image_that_was_never_stored(
    client: TestClient, repository: FakeRepository, authed: None, vehicle: None
) -> None:
    """The fake keeps no `storage_path`, which is the unconfigured-storage case.

    Reporting `image_retained: true` there would be a consent receipt for
    something that did not happen.
    """
    analysis = _analyse(client, ALICE)

    _, body = _file(
        client,
        ALICE,
        analysis["request_id"],
        kind="wrong_finding",
        finding_index=0,
        retain_image=True,
    )

    assert body["image_retained"] is False
    assert body["retention_days"] == 7
    assert repository.corrections[0]["retain_image"] is False


def test_a_stored_image_can_be_donated_and_the_longer_window_is_reported(
    client: TestClient, repository: FakeRepository, authed: None, vehicle: None
) -> None:
    analysis = _analyse(client, ALICE)
    # The row as Supabase would have written it, with the derivative kept.
    repository.rows[f"token-for-{ALICE}"][0]["storage_path"] = f"{ALICE}/x.jpg"

    _, body = _file(
        client,
        ALICE,
        analysis["request_id"],
        kind="missed_damage",
        retain_image=True,
    )

    assert body["image_retained"] is True
    assert body["retention_days"] == 365
    assert repository.corrections[0]["retain_image"] is True
