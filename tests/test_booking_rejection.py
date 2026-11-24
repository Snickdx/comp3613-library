import pytest
from sqlmodel import Session

from app.models.booking import Booking
from app.models.room import Room
from app.services import bookings


@pytest.fixture
def rejection_setup(test_engine, monkeypatch):

    # Use the test database instead of the application database.
    monkeypatch.setattr(bookings, "default_engine", test_engine)

    users = {
        1: {"id": 1, "role": "lecturer"},
        2: {"id": 2, "role": "coordinator"},
        3: {"id": 3, "role": "admin"},
    }

    monkeypatch.setattr(
        bookings, "get_user", lambda user_id: users.get(user_id)
    )

    # Create a room and a pending booking.
    with Session(test_engine) as session:
        room = Room(name="Test Room", capacity=30)
        session.add(room)
        session.commit()
        session.refresh(room)

        booking = Booking(
            lecturer_id=1,
            room_id=room.id,
            course_code="COMP3613",
            headcount=15,
            preferred_date="2099-12-01",
            start_time="09:00",
            end_time="11:00",
            resources="Projector",
            status="pending",
            confirmation_code=None,
            created_at="2026-11-01T09:00:00+00:00",
        )

        session.add(booking)
        session.commit()
        session.refresh(booking)

        return {
            "engine": test_engine,
            "booking_id": booking.id,
            "room_id": room.id,
        }


def test_coordinator_can_reject_booking(rejection_setup):

    # Verify that a coordinator can reject a pending booking.
    booking_id = rejection_setup["booking_id"]

    result = bookings.coordinator_reject(2, booking_id)

    assert result["ok"] is True
    assert result["booking"]["status"] == "rejected"
    assert result["booking"]["confirmation_code"] is None

    # Verify that the rejection is saved in the database.
    with Session(rejection_setup["engine"]) as session:
        booking = session.get(Booking, booking_id)
        assert booking.status == "rejected"


def test_admin_can_reject_booking(rejection_setup):

    # Verify that an administrator can reject a pending booking.
    result = bookings.coordinator_reject(
        3, rejection_setup["booking_id"]
    )

    assert result["ok"] is True
    assert result["booking"]["status"] == "rejected"


def test_lecturer_cannot_reject_booking(rejection_setup):

    # Verify that lecturers cannot reject bookings.
    booking_id = rejection_setup["booking_id"]

    result = bookings.coordinator_reject(1, booking_id)

    assert result["ok"] is False
    assert result["error"] == "coordinator/admin only"

    # Verify that the booking remains pending.
    with Session(rejection_setup["engine"]) as session:
        booking = session.get(Booking, booking_id)
        assert booking.status == "pending"


def test_unknown_user_cannot_reject_booking(rejection_setup):

    # Verify that an unknown user cannot reject bookings.
    result = bookings.coordinator_reject(
        999, rejection_setup["booking_id"]
    )

    assert result["ok"] is False
    assert result["error"] == "coordinator/admin only"


def test_cannot_reject_nonexistent_booking(rejection_setup):

    # Verify that rejecting a nonexistent booking fails.
    result = bookings.coordinator_reject(2, 9999)

    assert result["ok"] is False
    assert result["error"] == "booking not found"


@pytest.mark.parametrize(
    "status", ["accepted", "rejected", "cancelled"]
)
def test_cannot_reject_non_pending_booking(rejection_setup, status):

    # Change the booking to a non-pending status.
    booking_id = rejection_setup["booking_id"]

    with Session(rejection_setup["engine"]) as session:
        booking = session.get(Booking, booking_id)
        booking.status = status
        session.add(booking)
        session.commit()

    # Verify that only pending bookings can be rejected.
    result = bookings.coordinator_reject(2, booking_id)

    assert result["ok"] is False
    assert result["error"] == "booking is not pending"

    # Verify that the original status remains unchanged.
    with Session(rejection_setup["engine"]) as session:
        booking = session.get(Booking, booking_id)
        assert booking.status == status


def test_rejection_clears_confirmation_code(rejection_setup):

    # Simulate a pending booking with an invalid leftover confirmation.
    booking_id = rejection_setup["booking_id"]

    with Session(rejection_setup["engine"]) as session:
        booking = session.get(Booking, booking_id)
        booking.confirmation_code = "CONF-TEST1234"
        session.add(booking)
        session.commit()

    result = bookings.coordinator_reject(2, booking_id)

    assert result["ok"] is True
    assert result["booking"]["confirmation_code"] is None

    # Verify that the confirmation code was cleared in the database.
    with Session(rejection_setup["engine"]) as session:
        booking = session.get(Booking, booking_id)
        assert booking.confirmation_code is None

    # Verify that the old confirmation cannot be retrieved.
    confirmation = bookings.get_confirmation("CONF-TEST1234")

    assert confirmation["ok"] is False


def test_rejected_booking_cannot_be_approved(rejection_setup):

    # Reject the pending booking.
    booking_id = rejection_setup["booking_id"]

    rejection = bookings.coordinator_reject(2, booking_id)

    assert rejection["ok"] is True

    # Verify that a rejected booking cannot subsequently be approved.
    approval = bookings.coordinator_override_accept(2, booking_id)

    assert approval["ok"] is False
    assert approval["error"] == "booking is not pending"


def test_rejected_booking_releases_slot(rejection_setup):

    # Reject the existing booking.
    rejection = bookings.coordinator_reject(
        2, rejection_setup["booking_id"]
    )

    assert rejection["ok"] is True

    # Submit another booking for the same room and time.
    result = bookings.request_booking(
        1,
        room_id=rejection_setup["room_id"],
        course_code="COMP3607",
        headcount=20,
        preferred_date="2099-12-01",
        start_time="09:00",
        end_time="11:00",
        resources="Projector",
    )

    assert result["ok"] is True
    assert result["booking"]["status"] == "pending"

    # Verify that the new booking can be approved without an override.
    approval = bookings.coordinator_override_accept(
        2, result["booking"]["id"]
    )

    assert approval["ok"] is True
    assert approval["booking"]["status"] == "accepted"
    assert approval["booking"]["confirmation_code"] is not None