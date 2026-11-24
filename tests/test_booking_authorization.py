import pytest
from sqlmodel import Session

from app.models.booking import Booking
from app.models.room import Room
from app.services import bookings


@pytest.mark.parametrize(
    ("role", "actor_id", "owner_id", "allowed"),
    [
        ("lecturer", 10, 20, False),
        ("lecturer", 10, 10, True),
        ("coordinator", 10, 20, True),
        ("admin", 10, 20, True),
        ("regular_user", 10, 10, False),
    ],
)
def test_cancel_booking_enforces_owner_and_role(
    test_engine,
    monkeypatch,
    role,
    actor_id,
    owner_id,
    allowed,
):

    # Use the isolated test database.
    monkeypatch.setattr(bookings, "default_engine", test_engine)

    monkeypatch.setattr(
        bookings,
        "get_user",
        lambda user_id: {"id": user_id, "role": role},
    )

    # Create a room and an accepted booking.
    with Session(test_engine) as session:
        room = Room(name="Authorization Test Room", capacity=30)
        session.add(room)
        session.commit()
        session.refresh(room)

        booking = Booking(
            lecturer_id=owner_id,
            room_id=room.id,
            course_code="COMP3613",
            headcount=20,
            preferred_date="2099-03-16",
            start_time="10:00",
            end_time="11:00",
            resources="projector",
            status="accepted",
            confirmation_code="CONF-AUTH1234",
            created_at="2026-01-01T10:00:00+00:00",
        )

        session.add(booking)
        session.commit()
        session.refresh(booking)

        booking_id = booking.id

    result = bookings.cancel_booking(actor_id, booking_id)

    # Verify the result and the persisted booking state.
    with Session(test_engine) as session:
        booking = session.get(Booking, booking_id)

        if allowed:
            assert result["ok"] is True
            assert booking.status == "cancelled"
            assert booking.confirmation_code is None
        else:
            assert result == {"ok": False, "error": "forbidden"}
            assert booking.status == "accepted"
            assert booking.confirmation_code == "CONF-AUTH1234"