
from datetime import datetime, timedelta

import pytest
from sqlmodel import Session

from app.models.booking import Booking
from app.models.room import Room
from app.services import bookings


@pytest.fixture
def cancellation_setup(test_engine, monkeypatch):

    # Use the isolated test database.
    monkeypatch.setattr(bookings, "default_engine", test_engine)

    # Simulate an authenticated lecturer.
    monkeypatch.setattr(
        bookings,
        "get_user",
        lambda actor_id: {"role": "lecturer"},
    )

    # Create a room and a future workshop booking.
    with Session(test_engine) as session:
        room = Room(name="Cancellation Test Room", capacity=30)
        session.add(room)
        session.commit()
        session.refresh(room)

        booking = Booking(
            lecturer_id=1,
            room_id=room.id,
            course_code="COMP3613",
            headcount=15,
            preferred_date=(
                datetime.now() + timedelta(days=7)
            ).strftime("%Y-%m-%d"),
            start_time="09:00",
            end_time="11:00",
            resources="Projector",
            status="accepted",
            confirmation_code="CONF-TEST1234",
            created_at=datetime.now().isoformat(),
        )

        session.add(booking)
        session.commit()
        session.refresh(booking)

        return booking.model_dump()


# Verify that a future booking can be cancelled.
def test_cancel_booking(cancellation_setup):

    result = bookings.cancel_booking(
        1, cancellation_setup["id"]
    )

    assert result["ok"] is True
    assert result["booking"]["status"] == "cancelled"


# Verify that cancellation removes the stored confirmation code.
def test_cancellation_clears_confirmation(
    test_engine, cancellation_setup
):

    result = bookings.cancel_booking(
        1, cancellation_setup["id"]
    )

    assert result["ok"] is True
    assert result["booking"]["confirmation_code"] is None

    with Session(test_engine) as session:
        booking = session.get(
            Booking, cancellation_setup["id"]
        )
        assert booking.confirmation_code is None


# Verify that a cancelled confirmation cannot be used.
def test_cancelled_confirmation_is_invalid(cancellation_setup):

    code = cancellation_setup["confirmation_code"]

    result = bookings.cancel_booking(
        1, cancellation_setup["id"]
    )

    assert result["ok"] is True

    confirmation = bookings.get_confirmation(code)

    assert confirmation["ok"] is False


# Verify that a rejected booking cannot use its confirmation.
def test_rejected_confirmation_is_invalid(
    test_engine, cancellation_setup
):

    with Session(test_engine) as session:
        booking = session.get(
            Booking, cancellation_setup["id"]
        )
        booking.status = "rejected"
        session.add(booking)
        session.commit()

    result = bookings.get_confirmation(
        cancellation_setup["confirmation_code"]
    )

    assert result["ok"] is False


# Verify that an accepted booking has a valid confirmation.
def test_accepted_confirmation_is_valid(cancellation_setup):

    result = bookings.get_confirmation(
        cancellation_setup["confirmation_code"]
    )

    assert result["ok"] is True


# Verify that cancellation releases the reserved time slot.
def test_cancelled_booking_releases_slot(
    cancellation_setup, monkeypatch
):

    result = bookings.cancel_booking(
        1, cancellation_setup["id"]
    )

    assert result["ok"] is True

    captured = {}

    def fake_resolver(**kwargs):
        captured["existing"] = kwargs["existing"]
        return {
            "decision": "accept",
            "override_used": False,
            "displace_ids": [],
            "reason": "test",
        }

    monkeypatch.setattr(
        bookings, "resolve_slot_request", fake_resolver
    )

    result = bookings.request_booking(
        2,
        room_id=cancellation_setup["room_id"],
        course_code="COMP2605",
        headcount=10,
        preferred_date=cancellation_setup["preferred_date"],
        start_time="09:00",
        end_time="11:00",
        resources="Whiteboard",
    )

    assert result["ok"] is True
    assert captured["existing"] == []


# Verify that a workshop cannot be cancelled after it starts.
def test_cancellation_after_workshop_start(
    test_engine, cancellation_setup
):

    with Session(test_engine) as session:
        booking = session.get(
            Booking, cancellation_setup["id"]
        )
        booking.preferred_date = (
            datetime.now() - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        session.add(booking)
        session.commit()

    result = bookings.cancel_booking(
        1, cancellation_setup["id"]
    )

    assert result["ok"] is False
    assert result["error"] == "workshop has already started"

    with Session(test_engine) as session:
        booking = session.get(
            Booking, cancellation_setup["id"]
        )
        assert booking.status == "accepted"
        assert booking.confirmation_code == "CONF-TEST1234"


# Verify that a lecturer cannot cancel another lecturer's booking.
def test_unauthorized_cancellation(cancellation_setup):

    result = bookings.cancel_booking(
        2, cancellation_setup["id"]
    )

    assert result["ok"] is False
    assert result["error"] == "forbidden"
