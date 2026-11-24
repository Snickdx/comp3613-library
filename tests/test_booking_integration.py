
from sqlmodel import Session

from app.models.booking import Booking
from app.models.room import Room
from app.services import bookings


def test_overlapping_booking_is_detected(test_engine, monkeypatch):
    # Use the isolated test database.
    monkeypatch.setattr(bookings, "default_engine", test_engine)

    # Simulate an authenticated lecturer.
    monkeypatch.setattr(
        bookings,
        "get_user",
        lambda lecturer_id: {"role": "lecturer"},
    )

    # Create a room and an existing booking.
    with Session(test_engine) as session:
        room = Room(name="Integration Test Room", capacity=30)
        session.add(room)
        session.commit()
        session.refresh(room)

        existing_booking = Booking(
            lecturer_id=1,
            room_id=room.id,
            course_code="COMP3613",
            headcount=15,
            preferred_date="2026-12-01",
            start_time="09:00",
            end_time="11:00",
            resources="Projector",
            status="accepted",
            created_at="2026-11-24T10:00:00",
        )
        session.add(existing_booking)
        session.commit()
        session.refresh(existing_booking)

        existing_booking_id = existing_booking.id
        room_id = room.id

    # Capture the bookings passed to the conflict resolver.
    captured = {}

    def fake_resolver(**kwargs):
        captured["existing"] = kwargs["existing"]
        return {
            "decision": "accept",
            "override_used": False,
            "displace_ids": [],
            "reason": "test",
        }

    monkeypatch.setattr(bookings, "resolve_slot_request", fake_resolver)

    # Request a booking that overlaps the existing booking.
    result = bookings.request_booking(
        2,
        room_id=room_id,
        course_code="COMP2605",
        headcount=10,
        preferred_date="2026-12-01",
        start_time="10:00",
        end_time="12:00",
        resources="Whiteboard",
    )

    assert result["ok"] is True
    assert len(captured["existing"]) == 1
    assert captured["existing"][0]["id"] == existing_booking_id


def test_non_overlapping_booking_is_not_a_conflict(test_engine, monkeypatch):
    monkeypatch.setattr(bookings, "default_engine", test_engine)
    monkeypatch.setattr(
        bookings,
        "get_user",
        lambda lecturer_id: {"role": "lecturer"},
    )

    with Session(test_engine) as session:
        room = Room(name="Non-Overlap Test Room", capacity=30)
        session.add(room)
        session.commit()
        session.refresh(room)

        session.add(
            Booking(
                lecturer_id=1,
                room_id=room.id,
                course_code="COMP3613",
                headcount=15,
                preferred_date="2026-12-01",
                start_time="09:00",
                end_time="11:00",
                resources="Projector",
                status="accepted",
                created_at="2026-11-24T10:00:00",
            )
        )
        session.commit()

        room_id = room.id

    captured = {}

    def fake_resolver(**kwargs):
        captured["existing"] = kwargs["existing"]
        return {
            "decision": "accept",
            "override_used": False,
            "displace_ids": [],
            "reason": "test",
        }

    monkeypatch.setattr(bookings, "resolve_slot_request", fake_resolver)

    result = bookings.request_booking(
        2,
        room_id=room_id,
        course_code="COMP2605",
        headcount=10,
        preferred_date="2026-12-01",
        start_time="11:00",
        end_time="12:00",
        resources="Whiteboard",
    )

    assert result["ok"] is True
    assert captured["existing"] == []


def test_same_time_in_different_rooms_is_not_a_conflict(test_engine, monkeypatch):
    monkeypatch.setattr(bookings, "default_engine", test_engine)
    monkeypatch.setattr(
        bookings,
        "get_user",
        lambda lecturer_id: {"role": "lecturer"},
    )

    with Session(test_engine) as session:
        room1 = Room(name="Room A", capacity=30)
        room2 = Room(name="Room B", capacity=30)
        session.add_all([room1, room2])
        session.commit()
        session.refresh(room1)
        session.refresh(room2)

        session.add(
            Booking(
                lecturer_id=1,
                room_id=room1.id,
                course_code="COMP3613",
                headcount=15,
                preferred_date="2026-12-01",
                start_time="09:00",
                end_time="11:00",
                resources="Projector",
                status="accepted",
                created_at="2026-11-24T10:00:00",
            )
        )
        session.commit()

        room2_id = room2.id

    captured = {}

    def fake_resolver(**kwargs):
        captured["existing"] = kwargs["existing"]
        return {
            "decision": "accept",
            "override_used": False,
            "displace_ids": [],
            "reason": "test",
        }

    monkeypatch.setattr(bookings, "resolve_slot_request", fake_resolver)

    result = bookings.request_booking(
        2,
        room_id=room2_id,
        course_code="COMP2605",
        headcount=10,
        preferred_date="2026-12-01",
        start_time="10:00",
        end_time="12:00",
        resources="Whiteboard",
    )

    assert result["ok"] is True
    assert captured["existing"] == []


def test_same_time_on_different_dates_is_not_a_conflict(test_engine, monkeypatch):
    monkeypatch.setattr(bookings, "default_engine", test_engine)
    monkeypatch.setattr(
        bookings,
        "get_user",
        lambda lecturer_id: {"role": "lecturer"},
    )

    with Session(test_engine) as session:
        room = Room(name="Different Date Test Room", capacity=30)
        session.add(room)
        session.commit()
        session.refresh(room)

        session.add(
            Booking(
                lecturer_id=1,
                room_id=room.id,
                course_code="COMP3613",
                headcount=15,
                preferred_date="2026-12-01",
                start_time="09:00",
                end_time="11:00",
                resources="Projector",
                status="accepted",
                created_at="2026-11-24T10:00:00",
            )
        )
        session.commit()

        room_id = room.id

    captured = {}

    def fake_resolver(**kwargs):
        captured["existing"] = kwargs["existing"]
        return {
            "decision": "accept",
            "override_used": False,
            "displace_ids": [],
            "reason": "test",
        }

    monkeypatch.setattr(bookings, "resolve_slot_request", fake_resolver)

    result = bookings.request_booking(
        2,
        room_id=room_id,
        course_code="COMP2605",
        headcount=10,
        preferred_date="2026-12-02",
        start_time="09:00",
        end_time="11:00",
        resources="Whiteboard",
    )

    assert result["ok"] is True
    assert captured["existing"] == []
