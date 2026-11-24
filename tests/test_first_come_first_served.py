from app.services.first_come_first_served import FirstComeFirstServed


def test_accepts_booking_when_there_are_no_conflicts():
    result = FirstComeFirstServed().evaluate(
        incoming={
            "id": 20,
            "created_at": "2026-11-24T10:00:00",
        },
        existing=[],
    )

    assert result["decision"] == "accept"
    assert result["reason"] == "slot free"
    assert result["override_used"] is False
    assert result["displace_ids"] == []


def test_rejects_incoming_when_existing_request_is_earlier():
    result = FirstComeFirstServed().evaluate(
        incoming={
            "id": 20,
            "created_at": "2026-11-24T11:00:00",
        },
        existing=[
            {
                "id": 10,
                "status": "accepted",
                "created_at": "2026-11-24T10:00:00",
            }
        ],
    )

    assert result["decision"] == "reject"
    assert result["reason"] == "existing booking submitted earlier"
    assert result["override_used"] is False
    assert result["displace_ids"] == []


def test_accepts_incoming_when_it_is_earlier():
    result = FirstComeFirstServed().evaluate(
        incoming={
            "id": 20,
            "created_at": "2026-11-24T09:00:00",
        },
        existing=[
            {
                "id": 10,
                "status": "accepted",
                "created_at": "2026-11-24T10:00:00",
            },
            {
                "id": 11,
                "status": "pending",
                "created_at": "2026-11-24T10:30:00",
            },
        ],
    )

    assert result["decision"] == "accept"
    assert result["reason"] == "incoming booking submitted earlier"
    assert result["override_used"] is False
    assert result["displace_ids"] == [10, 11]


def test_ignores_cancelled_and_rejected_bookings():
    result = FirstComeFirstServed().evaluate(
        incoming={
            "id": 20,
            "created_at": "2026-11-24T11:00:00",
        },
        existing=[
            {
                "id": 10,
                "status": "cancelled",
                "created_at": "2026-11-24T09:00:00",
            },
            {
                "id": 11,
                "status": "rejected",
                "created_at": "2026-11-24T09:30:00",
            },
        ],
    )

    assert result["decision"] == "accept"
    assert result["reason"] == "slot free"
    assert result["override_used"] is False
    assert result["displace_ids"] == []


def test_multiple_conflicts_are_consistent_and_existing_wins_ties():
    strategy = FirstComeFirstServed()
    existing = [
        {
            "id": 10,
            "status": "accepted",
            "created_at": "2026-11-24T10:00:00",
        },
        {
            "id": 11,
            "status": "pending",
            "created_at": "2026-11-24T10:30:00",
        },
    ]

    later_incoming = strategy.evaluate(
        incoming={
            "id": 20,
            "created_at": "2026-11-24T11:00:00",
        },
        existing=existing,
    )
    earlier_incoming = strategy.evaluate(
        incoming={
            "id": 20,
            "created_at": "2026-11-24T09:00:00",
        },
        existing=list(reversed(existing)),
    )
    tied_incoming = strategy.evaluate(
        incoming={
            "id": 20,
            "created_at": "2026-11-24T10:00:00",
        },
        existing=existing,
    )

    assert later_incoming["decision"] == "reject"
    assert later_incoming["displace_ids"] == []
    assert earlier_incoming["decision"] == "accept"
    assert earlier_incoming["displace_ids"] == [11, 10]
    assert tied_incoming["decision"] == "reject"
    assert tied_incoming["displace_ids"] == []


def test_persisted_incoming_lower_id_wins_identical_timestamp():
    result = FirstComeFirstServed().evaluate(
        incoming={
            "id": 10,
            "status": "pending",
            "created_at": "2026-11-24T10:00:00",
        },
        existing=[
            {
                "id": 20,
                "status": "pending",
                "created_at": "2026-11-24T10:00:00",
            }
        ],
    )

    assert result["decision"] == "accept"
    assert result["reason"] == "incoming booking has lower booking ID"
    assert result["override_used"] is False
    assert result["displace_ids"] == [20]


def test_persisted_incoming_higher_id_loses_identical_timestamp():
    result = FirstComeFirstServed().evaluate(
        incoming={
            "id": 20,
            "status": "pending",
            "created_at": "2026-11-24T10:00:00",
        },
        existing=[
            {
                "id": 10,
                "status": "pending",
                "created_at": "2026-11-24T10:00:00",
            }
        ],
    )

    assert result["decision"] == "reject"
    assert result["reason"] == "existing booking has equal submission timestamp"
    assert result["override_used"] is False
    assert result["displace_ids"] == []


def test_incoming_without_id_loses_identical_timestamp():
    result = FirstComeFirstServed().evaluate(
        incoming={
            "status": "pending",
            "created_at": "2026-11-24T10:00:00",
        },
        existing=[
            {
                "id": 10,
                "status": "pending",
                "created_at": "2026-11-24T10:00:00",
            }
        ],
    )

    assert result["decision"] == "reject"
    assert result["reason"] == "existing booking has equal submission timestamp"
    assert result["override_used"] is False
    assert result["displace_ids"] == []


def test_identical_timestamps_are_consistent_regardless_of_list_order():
    strategy = FirstComeFirstServed()
    existing = [
        {
            "id": 20,
            "status": "pending",
            "created_at": "2026-11-24T10:00:00",
        },
        {
            "id": 30,
            "status": "accepted",
            "created_at": "2026-11-24T10:00:00",
        },
    ]

    lower_winner = strategy.evaluate(
        incoming={
            "id": 10,
            "status": "pending",
            "created_at": "2026-11-24T10:00:00",
        },
        existing=list(reversed(existing)),
    )
    higher_loser = strategy.evaluate(
        incoming={
            "id": 40,
            "status": "pending",
            "created_at": "2026-11-24T10:00:00",
        },
        existing=existing,
    )

    assert lower_winner["decision"] == "accept"
    assert lower_winner["displace_ids"] == [30, 20]
    assert higher_loser["decision"] == "reject"
    assert higher_loser["reason"] == "existing booking has equal submission timestamp"


def test_mixed_timestamps_ignore_later_booking_id_in_tie_break():
    result = FirstComeFirstServed().evaluate(
        incoming={
            "id": 15,
            "status": "pending",
            "created_at": "2026-11-24T10:00:00",
        },
        existing=[
            {
                "id": 5,
                "status": "pending",
                "created_at": "2026-11-24T11:00:00",
            },
            {
                "id": 20,
                "status": "pending",
                "created_at": "2026-11-24T10:00:00",
            },
        ],
    )

    assert result["decision"] == "accept"
    assert result["reason"] == "incoming booking has lower booking ID"
    assert result["displace_ids"] == [5, 20]


def test_rejects_when_booking_that_needs_displacement_has_invalid_id():
    result = FirstComeFirstServed().evaluate(
        incoming={
            "id": 20,
            "created_at": "2026-11-24T09:00:00",
        },
        existing=[
            {
                "id": None,
                "status": "accepted",
                "created_at": "2026-11-24T10:00:00",
            }
        ],
    )

    assert result["decision"] == "reject"
    assert result["reason"] == "existing booking has missing or invalid id"
    assert result["override_used"] is False
    assert result["displace_ids"] == []
