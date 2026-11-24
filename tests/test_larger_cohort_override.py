from app.services.larger_cohort_override import LargerCohortOverride


def test_authorized_larger_cohort_override_succeeds():
    result = LargerCohortOverride().evaluate(
        incoming={"id": 20, "headcount": 30, "status": "pending"},
        existing=[
            {"id": 10, "headcount": 20, "status": "accepted"},
        ],
        coordinator_override=True,
        override_justification="larger seminar approved",
    )

    assert result["decision"] == "accept"
    assert result["reason"] == "larger cohort coordinator override"
    assert result["override_used"] is True
    assert result["displace_ids"] == [10]
    assert result["override_justification"] == "larger seminar approved"


def test_override_requires_coordinator_authorization():
    result = LargerCohortOverride().evaluate(
        incoming={"id": 20, "headcount": 30},
        existing=[
            {"id": 10, "headcount": 20, "status": "accepted"},
        ],
        override_justification="larger seminar approved",
    )

    assert result["decision"] == "reject"
    assert result["reason"] == "larger cohort requires coordinator override"
    assert result["override_used"] is False
    assert result["displace_ids"] == []


def test_override_requires_missing_or_blank_justification():
    existing = [
        {"id": 10, "headcount": 20, "status": "accepted"},
    ]

    missing = LargerCohortOverride().evaluate(
        incoming={"id": 20, "headcount": 30},
        existing=existing,
        coordinator_override=True,
    )
    blank = LargerCohortOverride().evaluate(
        incoming={"id": 20, "headcount": 30},
        existing=existing,
        coordinator_override=True,
        override_justification="   ",
    )

    assert missing["decision"] == "reject"
    assert missing["reason"] == "coordinator override requires justification"
    assert blank["decision"] == "reject"
    assert blank["reason"] == "coordinator override requires justification"
    assert missing["override_used"] is False
    assert missing["displace_ids"] == []
    assert blank["override_used"] is False
    assert blank["displace_ids"] == []


def test_rejects_equal_or_smaller_incoming_cohort():
    existing = [
        {"id": 10, "headcount": 25, "status": "accepted"},
    ]

    equal = LargerCohortOverride().evaluate(
        incoming={"id": 20, "headcount": 25},
        existing=existing,
        coordinator_override=True,
        override_justification="approved",
    )
    smaller = LargerCohortOverride().evaluate(
        incoming={"id": 20, "headcount": 20},
        existing=existing,
        coordinator_override=True,
        override_justification="approved",
    )

    assert equal["decision"] == "reject"
    assert equal["override_used"] is False
    assert smaller["decision"] == "reject"
    assert smaller["override_used"] is False
    assert equal["displace_ids"] == []
    assert smaller["displace_ids"] == []


def test_ignores_cancelled_rejected_and_incoming_bookings():
    result = LargerCohortOverride().evaluate(
        incoming={"id": 20, "headcount": 30, "status": "pending"},
        existing=[
            {"id": 20, "headcount": 30, "status": "pending"},
            {"id": 11, "headcount": 20, "status": "cancelled"},
            {"id": 12, "headcount": 25, "status": "rejected"},
        ],
        coordinator_override=True,
        override_justification="approved",
    )

    assert result["decision"] == "accept"
    assert result["reason"] == "slot free"
    assert result["override_used"] is False
    assert result["displace_ids"] == []


def test_returns_all_displacement_ids_for_multiple_conflicts():
    result = LargerCohortOverride().evaluate(
        incoming={"id": 20, "headcount": 40},
        existing=[
            {"id": 10, "headcount": 20, "status": "accepted"},
            {"id": 12, "headcount": 30, "status": "pending"},
            {"id": 11, "headcount": 25, "status": "cancelled"},
        ],
        coordinator_override=True,
        override_justification="large public lecture",
    )

    assert result["decision"] == "accept"
    assert result["override_used"] is True
    assert result["displace_ids"] == [10, 12]


def test_rejects_when_displaced_booking_has_invalid_id():
    result = LargerCohortOverride().evaluate(
        incoming={"id": 20, "headcount": 40},
        existing=[
            {"id": None, "headcount": 30, "status": "accepted"},
        ],
        coordinator_override=True,
        override_justification="approved",
    )

    assert result["decision"] == "reject"
    assert result["reason"] == "existing booking has missing or invalid id"
    assert result["override_used"] is False
    assert result["displace_ids"] == []
