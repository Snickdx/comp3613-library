from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlmodel import Session, select

from app.models.booking import Booking
from app.models.room import Room
from app.services import bookings


def _setup_room(test_engine, monkeypatch, *, capacity=30):
    monkeypatch.setattr(bookings, "default_engine", test_engine)
    monkeypatch.setattr(
        bookings,
        "get_user",
        lambda actor_id: (
            {"role": "coordinator"}
            if actor_id == 99
            else {"role": "lecturer"}
        ),
    )

    with Session(test_engine) as session:
        room = Room(name="Booking Workflow Room", capacity=capacity)
        session.add(room)
        session.commit()
        session.refresh(room)
        return room.id


def _request(test_engine, room_id):
    return bookings.request_booking(
        1,
        room_id=room_id,
        course_code="COMP3613",
        headcount=20,
        preferred_date="2099-12-01",
        start_time="09:00",
        end_time="11:00",
        resources="Projector",
    )


def test_new_valid_request_remains_pending_without_confirmation(
    test_engine, monkeypatch
):
    room_id = _setup_room(test_engine, monkeypatch)

    result = _request(test_engine, room_id)

    assert result["ok"] is True
    assert result["booking"]["status"] == "pending"
    assert result["booking"]["confirmation_code"] is None
    assert result["booking"]["override_used"] == 0


def test_successful_coordinator_approval_accepts_and_generates_code(
    test_engine, monkeypatch
):
    room_id = _setup_room(test_engine, monkeypatch)
    submitted = _request(test_engine, room_id)
    booking_id = submitted["booking"]["id"]

    result = bookings.coordinator_override_accept(99, booking_id)

    assert result["ok"] is True
    assert result["booking"]["status"] == "accepted"
    assert result["booking"]["confirmation_code"]
    assert result["booking"]["override_used"] == 0


def test_rejected_approval_leaves_pending_request_and_existing_booking(
    test_engine, monkeypatch
):
    room_id = _setup_room(test_engine, monkeypatch)

    with Session(test_engine) as session:
        existing = Booking(
            lecturer_id=2,
            room_id=room_id,
            course_code="COMP2605",
            headcount=15,
            preferred_date="2099-12-01",
            start_time="09:00",
            end_time="11:00",
            resources="Whiteboard",
            status="accepted",
            confirmation_code="CONF-EXISTING",
            created_at="2025-01-01T10:00:00+00:00",
        )
        session.add(existing)
        session.commit()
        session.refresh(existing)

    incoming = bookings.request_booking(
        1,
        room_id=room_id,
        course_code="COMP3613",
        headcount=10,
        preferred_date="2099-12-01",
        start_time="09:00",
        end_time="11:00",
        resources="Projector",
    )
    assert incoming["ok"] is True
    assert incoming["booking"]["status"] == "pending"

    result = bookings.coordinator_override_accept(
        99,
        incoming["booking"]["id"],
    )

    assert result["ok"] is False
    assert result["verdict"]["decision"] == "reject"

    with Session(test_engine) as session:
        rows = session.exec(select(Booking)).all()
        pending = next(row for row in rows if row.id == incoming["booking"]["id"])
        existing = next(row for row in rows if row.id != incoming["booking"]["id"])

        assert pending.status == "pending"
        assert pending.confirmation_code is None
        assert existing.status == "accepted"
        assert existing.confirmation_code == "CONF-EXISTING"


def test_authorised_larger_cohort_override_passes_justification(
    test_engine, monkeypatch
):
    room_id = _setup_room(test_engine, monkeypatch)

    with Session(test_engine) as session:
        existing = Booking(
            lecturer_id=2,
            room_id=room_id,
            course_code="COMP2605",
            headcount=10,
            preferred_date="2099-12-01",
            start_time="09:00",
            end_time="11:00",
            resources="Whiteboard",
            status="accepted",
            confirmation_code="CONF-EXISTING",
            created_at="2025-01-01T10:00:00+00:00",
        )
        session.add(existing)
        session.commit()
        session.refresh(existing)

    incoming = bookings.request_booking(
        1,
        room_id=room_id,
        course_code="COMP3613",
        headcount=20,
        preferred_date="2099-12-01",
        start_time="09:00",
        end_time="11:00",
        resources="Projector",
    )
    assert incoming["ok"] is True

    result = bookings.coordinator_override_accept(
        99,
        incoming["booking"]["id"],
        "larger cohort approved",
        coordinator_override=True,
    )

    assert result["ok"] is True
    assert result["booking"]["status"] == "accepted"
    assert result["booking"]["override_used"] == 1
    assert result["verdict"]["override_used"] is True
    assert result["verdict"]["override_justification"] == "larger cohort approved"

    with Session(test_engine) as session:
        displaced = session.get(Booking, existing.id)
        assert displaced.status == "rejected"
        assert displaced.confirmation_code is None


def test_capacity_violation_cannot_be_saved_or_approved(
    test_engine, monkeypatch
):
    room_id = _setup_room(test_engine, monkeypatch, capacity=30)

    incoming = bookings.request_booking(
        1,
        room_id=room_id,
        course_code="COMP3613",
        headcount=35,
        preferred_date="2099-12-01",
        start_time="09:00",
        end_time="11:00",
        resources="Projector",
    )

    assert incoming["ok"] is False
    assert incoming["error"] == "room capacity exceeded"

    with Session(test_engine) as session:
        assert session.exec(select(Booking)).all() == []


def test_capacity_change_after_submission_rejects_approval(
    test_engine, monkeypatch
):
    room_id = _setup_room(test_engine, monkeypatch, capacity=30)
    submitted = _request(test_engine, room_id)

    with Session(test_engine) as session:
        room = session.get(Room, room_id)
        room.capacity = 10
        session.add(room)
        session.commit()

    result = bookings.coordinator_override_accept(
        99,
        submitted["booking"]["id"],
    )

    assert result["ok"] is False
    assert result["error"] == "room capacity exceeded"

    with Session(test_engine) as session:
        booking = session.get(Booking, submitted["booking"]["id"])
        assert booking.status == "pending"
        assert booking.confirmation_code is None


def test_concurrent_conflicting_approvals_leave_one_accepted(
    test_engine, monkeypatch
):
    room_id = _setup_room(test_engine, monkeypatch, capacity=30)

    with Session(test_engine) as session:
        earlier = Booking(
            lecturer_id=1,
            room_id=room_id,
            course_code="COMP2605",
            headcount=10,
            preferred_date="2099-12-01",
            start_time="09:00",
            end_time="11:00",
            resources="Whiteboard",
            status="pending",
            created_at="2025-01-01T10:00:00+00:00",
        )
        later = Booking(
            lecturer_id=2,
            room_id=room_id,
            course_code="COMP3613",
            headcount=20,
            preferred_date="2099-12-01",
            start_time="09:00",
            end_time="11:00",
            resources="Projector",
            status="pending",
            created_at="2026-01-01T10:00:00+00:00",
        )
        session.add_all([earlier, later])
        session.commit()
        session.refresh(earlier)
        session.refresh(later)
        earlier_id = earlier.id
        later_id = later.id

    barrier = Barrier(2)

    def approve_earlier():
        barrier.wait()
        return bookings.coordinator_override_accept(99, earlier_id)

    def approve_later_with_override():
        barrier.wait()
        return bookings.coordinator_override_accept(
            99,
            later_id,
            "larger cohort approved",
            coordinator_override=True,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        earlier_future = executor.submit(approve_earlier)
        later_future = executor.submit(approve_later_with_override)
        results = [earlier_future.result(), later_future.result()]

    successful = [result for result in results if result["ok"]]
    assert len(successful) == 1

    with Session(test_engine) as session:
        rows = session.exec(
            select(Booking).where(
                Booking.id.in_([earlier_id, later_id])
            )
        ).all()

        accepted = [booking for booking in rows if booking.status == "accepted"]
        unsuccessful = [
            booking for booking in rows if booking.status != "accepted"
        ]

        assert len(accepted) == 1
        assert accepted[0].confirmation_code
        assert len(unsuccessful) == 1
        assert unsuccessful[0].confirmation_code is None
