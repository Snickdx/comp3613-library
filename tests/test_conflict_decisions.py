import pytest
from sqlmodel import Session

from app.models.room import Room
from app.services import bookings


@pytest.fixture
def audit_setup(test_engine, monkeypatch):

    # Use the test database.
    monkeypatch.setattr(bookings, "default_engine", test_engine)

    users = {
        1: {"id": 1, "role": "lecturer"},
        2: {"id": 2, "role": "coordinator"},
        3: {"id": 3, "role": "admin"},
        4: {"id": 4, "role": "lecturer"},
    }

    monkeypatch.setattr(
        bookings, "get_user", lambda user_id: users.get(user_id)
    )

    # Create a room for the booking requests.
    with Session(test_engine) as session:
        room = Room(name="Test Room", capacity=30)
        session.add(room)
        session.commit()
        session.refresh(room)

        room_id = room.id

    return room_id


def submit_booking(room_id, lecturer_id=1, headcount=10):

    # Submit a booking using the actual booking service.
    return bookings.request_booking(
        lecturer_id,
        room_id=room_id,
        course_code="COMP3613",
        headcount=headcount,
        preferred_date="2099-12-01",
        start_time="09:00",
        end_time="11:00",
        resources="Projector",
    )


def test_submission_decision_is_recorded(audit_setup):

    # Submit a valid booking.
    result = submit_booking(audit_setup)

    assert result["ok"] is True

    booking_id = result["booking"]["id"]
    records = bookings.list_conflict_decisions(
        booking_id=booking_id
    )

    assert len(records) == 1
    assert records[0]["decision"] == "accept"
    assert records[0]["stage"] == "submission"
    assert records[0]["booking_status"] == "pending"
    assert records[0]["lecturer_id"] == 1
    assert records[0]["room_id"] == audit_setup
    assert records[0]["created_at"] is not None


def test_rejected_submission_is_recorded(audit_setup):

    # Submit a booking exceeding the room capacity.
    result = submit_booking(audit_setup, headcount=50)

    assert result["ok"] is False

    records = bookings.list_conflict_decisions()

    assert len(records) == 1
    assert records[0]["decision"] == "reject"
    assert records[0]["stage"] == "submission"
    assert records[0]["booking_status"] == "rejected"
    assert records[0]["booking_id"] is None
    assert records[0]["headcount"] == 50


def test_policy_and_reason_are_recorded(audit_setup):

    # Verify that the original resolver metadata is preserved.
    result = submit_booking(audit_setup)

    assert result["ok"] is True

    records = bookings.list_conflict_decisions(
        booking_id=result["booking"]["id"]
    )

    assert records[0]["policy"] == result["verdict"].get("policy")
    assert records[0]["reason"] == result["verdict"]["reason"]
    assert records[0]["decision"] == result["verdict"]["decision"]


def test_approval_decision_is_recorded(audit_setup):

    result = submit_booking(audit_setup)
    booking_id = result["booking"]["id"]

    # Approve the pending booking.
    approval = bookings.coordinator_override_accept(2, booking_id)

    assert approval["ok"] is True

    records = bookings.list_conflict_decisions(
        booking_id=booking_id
    )

    assert len(records) == 2

    record = records[-1]

    assert record["decision"] == "accept"
    assert record["stage"] == "approval"
    assert record["booking_status"] == "accepted"
    assert record["coordinator_id"] == 2
    assert record["override_authorized"] is False
    assert record["override_used"] is False


def test_failed_approval_is_recorded(audit_setup, monkeypatch):

    # Give the first request an earlier submission timestamp.
    monkeypatch.setattr(
        bookings, "_now", lambda: "2026-11-01T09:00:00+00:00"
    )

    first = submit_booking(audit_setup)

    assert first["ok"] is True

    monkeypatch.setattr(
        bookings, "_now", lambda: "2026-11-01T10:00:00+00:00"
    )

    second = submit_booking(audit_setup, lecturer_id=4)

    assert second["ok"] is True

    booking_id = second["booking"]["id"]

    # Attempt to approve the later request without an override.
    approval = bookings.coordinator_override_accept(2, booking_id)

    assert approval["ok"] is False

    records = bookings.list_conflict_decisions(
        booking_id=booking_id
    )

    record = records[-1]

    assert record["decision"] == "reject"
    assert record["stage"] == "approval"
    assert record["booking_status"] == "pending"
    assert record["coordinator_id"] == 2
    assert record["override_used"] is False
    assert record["reason"] == approval["verdict"]["reason"]


def test_override_justification_is_recorded(audit_setup, monkeypatch):

    # Submit the earlier booking.
    monkeypatch.setattr(
        bookings, "_now", lambda: "2026-11-01T09:00:00+00:00"
    )

    first = submit_booking(audit_setup, headcount=10)

    assert first["ok"] is True

    # Submit a later booking with a larger cohort.
    monkeypatch.setattr(
        bookings, "_now", lambda: "2026-11-01T10:00:00+00:00"
    )

    second = submit_booking(
        audit_setup, lecturer_id=4, headcount=25
    )

    assert second["ok"] is True

    booking_id = second["booking"]["id"]
    justification = "Larger cohort requires the workshop slot."

    # Approve the larger cohort using an authorized override.
    approval = bookings.coordinator_override_accept(
        2,
        booking_id,
        override_justification=justification,
        coordinator_override=True,
    )

    assert approval["ok"] is True

    records = bookings.list_conflict_decisions(
        booking_id=booking_id
    )

    record = records[-1]

    assert record["decision"] == "accept"
    assert record["stage"] == "approval"
    assert record["booking_status"] == "accepted"
    assert record["coordinator_id"] == 2
    assert record["override_authorized"] is True
    assert record["override_used"] is True
    assert record["override_justification"] == justification
    assert record["policy"] == "larger-cohort-override"


def test_displaced_booking_decision_is_recorded(
    audit_setup, monkeypatch
):

    # Submit the earlier booking.
    monkeypatch.setattr(
        bookings, "_now", lambda: "2026-11-01T09:00:00+00:00"
    )

    first = submit_booking(audit_setup, headcount=10)

    assert first["ok"] is True

    # Submit a larger conflicting booking.
    monkeypatch.setattr(
        bookings, "_now", lambda: "2026-11-01T10:00:00+00:00"
    )

    second = submit_booking(
        audit_setup, lecturer_id=4, headcount=25
    )

    assert second["ok"] is True

    first_id = first["booking"]["id"]
    second_id = second["booking"]["id"]

    justification = "Larger cohort requires priority."

    approval = bookings.coordinator_override_accept(
        2,
        second_id,
        override_justification=justification,
        coordinator_override=True,
    )

    assert approval["ok"] is True

    # Retrieve the audit history of the displaced booking.
    records = bookings.list_conflict_decisions(
        booking_id=first_id
    )

    record = records[-1]

    assert record["decision"] == "reject"
    assert record["stage"] == "displacement"
    assert record["booking_status"] == "rejected"
    assert record["related_booking_id"] == second_id
    assert record["coordinator_id"] == 2
    assert record["override_used"] is True
    assert record["override_justification"] == justification


def test_manual_rejection_is_recorded(audit_setup):

    result = submit_booking(audit_setup)
    booking_id = result["booking"]["id"]

    rejection = bookings.coordinator_reject(2, booking_id)

    assert rejection["ok"] is True

    records = bookings.list_conflict_decisions(
        booking_id=booking_id
    )

    assert len(records) == 2

    record = records[-1]

    assert record["decision"] == "reject"
    assert record["stage"] == "manual-rejection"
    assert record["booking_status"] == "rejected"
    assert record["coordinator_id"] == 2
    assert record["policy"] == "manual-rejection"
    assert record["override_used"] is False


def test_unauthorized_override_is_not_recorded(audit_setup):

    result = submit_booking(audit_setup)
    booking_id = result["booking"]["id"]

    # Attempt an override using a lecturer account.
    approval = bookings.coordinator_override_accept(
        1,
        booking_id,
        override_justification="Unauthorized override.",
        coordinator_override=True,
    )

    assert approval["ok"] is False

    records = bookings.list_conflict_decisions(
        booking_id=booking_id
    )

    # Only the original submission decision should exist.
    assert len(records) == 1
    assert records[0]["stage"] == "submission"
    assert records[0]["override_authorized"] is False


def test_audit_records_can_be_filtered_by_booking(audit_setup):

    first = submit_booking(audit_setup)
    second = submit_booking(audit_setup, lecturer_id=4)

    assert first["ok"] is True
    assert second["ok"] is True

    first_id = first["booking"]["id"]
    second_id = second["booking"]["id"]

    all_records = bookings.list_conflict_decisions()

    first_records = bookings.list_conflict_decisions(
        booking_id=first_id
    )

    second_records = bookings.list_conflict_decisions(
        booking_id=second_id
    )

    assert len(all_records) == 2
    assert len(first_records) == 1
    assert len(second_records) == 1
    assert first_records[0]["booking_id"] == first_id
    assert second_records[0]["booking_id"] == second_id


def test_audit_history_is_preserved(audit_setup):

    result = submit_booking(audit_setup)
    booking_id = result["booking"]["id"]

    original_records = bookings.list_conflict_decisions(
        booking_id=booking_id
    )

    approval = bookings.coordinator_override_accept(2, booking_id)

    assert approval["ok"] is True

    updated_records = bookings.list_conflict_decisions(
        booking_id=booking_id
    )

    # Verify that approval does not overwrite the submission record.
    assert len(updated_records) == 2
    assert updated_records[0] == original_records[0]
    assert updated_records[1]["stage"] == "approval"
    assert updated_records[0]["id"] != updated_records[1]["id"]


def test_failed_override_is_recorded(audit_setup, monkeypatch):

    monkeypatch.setattr(
        bookings, "_now", lambda: "2026-11-01T09:00:00+00:00"
    )

    first = submit_booking(audit_setup, headcount=10)

    assert first["ok"] is True

    monkeypatch.setattr(
        bookings, "_now", lambda: "2026-11-01T10:00:00+00:00"
    )

    second = submit_booking(
        audit_setup, lecturer_id=4, headcount=25
    )

    assert second["ok"] is True

    booking_id = second["booking"]["id"]

    # Attempt an authorized override without justification.
    approval = bookings.coordinator_override_accept(
        2,
        booking_id,
        coordinator_override=True,
    )

    assert approval["ok"] is False

    records = bookings.list_conflict_decisions(
        booking_id=booking_id
    )

    record = records[-1]

    assert record["decision"] == "reject"
    assert record["stage"] == "approval"
    assert record["booking_status"] == "pending"
    assert record["override_authorized"] is True
    assert record["override_used"] is False
    assert record["override_justification"] is None