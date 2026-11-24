import pytest

from app.models.booking import Booking
from app.services import bookings


class InMemorySession:
    def __init__(self, booking: Booking) -> None:
        self.booking = booking
        self.commit_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def get(self, model, booking_id):
        if model is Booking and booking_id == self.booking.id:
            return self.booking
        return None

    def add(self, row):
        pass

    def commit(self):
        self.commit_count += 1

    def refresh(self, row):
        pass


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
    monkeypatch,
    role,
    actor_id,
    owner_id,
    allowed,
):
    booking = Booking(
        id=1,
        lecturer_id=owner_id,
        room_id=1,
        course_code="COMP3613",
        headcount=20,
        preferred_date="2099-03-16",
        start_time="10:00",
        end_time="11:00",
        resources="projector",
        status="accepted",
        created_at="2026-01-01T10:00:00+00:00",
    )
    session = InMemorySession(booking)
    monkeypatch.setattr(
        bookings,
        "get_user",
        lambda user_id: {"id": user_id, "role": role},
    )
    monkeypatch.setattr(bookings, "Session", lambda engine: session)

    result = bookings.cancel_booking(actor_id, booking.id)

    if allowed:
        assert result["ok"] is True
        assert booking.status == "cancelled"
        assert session.commit_count == 1
    else:
        assert result == {"ok": False, "error": "forbidden"}
        assert booking.status == "accepted"
        assert session.commit_count == 0
