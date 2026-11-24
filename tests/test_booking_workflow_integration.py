
from datetime import datetime, timedelta

import pytest
from sqlmodel import Session

from app.models.booking import Booking
from app.models.room import Room
from app.services import bookings


@pytest.fixture
def workflow_setup(test_engine, monkeypatch):
    monkeypatch.setattr(bookings, "default_engine", test_engine)

    users = {
        1: {"role": "lecturer"},
        2: {"role": "lecturer"},
        3: {"role": "coordinator"},
        4: {"role": "admin"},
    }

    monkeypatch.setattr(
        bookings,
        "get_user",
        lambda user_id: users.get(user_id),
    )

    with Session(test_engine) as session:
        room = Room(name="Workflow Test Room", capacity=30)
        session.add(room)
        session.commit()
        session.refresh(room)

        room_id = room.id

    return {
        "engine": test_engine,
        "room_id": room_id,
    }


def create_booking(
    engine,
    room_id,
    *,
    lecturer_id=1,
    headcount=10,
    status="accepted",
    created_at=None,
    start_time="09:00",
    end_time="11:00",
):
    with Session(engine) as session:
        booking = Booking(
            lecturer_id=lecturer_id,
            room_id=room_id,
            course_code="COMP3613",
            headcount=headcount,
            preferred_date=(
                datetime.now() + timedelta(days=7)
            ).strftime("%Y-%m-%d"),
            start_time=start_time,
            end_time=end_time,
            resources="Projector",
            status=status,
            confirmation_code="CONF-WORKFLOW",
            created_at=created_at or "2026-01-01T09:00:00",
        )

        session.add(booking)
        session.commit()
        session.refresh(booking)

        return booking.model_dump()

def test_first_come_first_served_rejects_later_booking(workflow_setup):
    room_id = workflow_setup["room_id"]
    engine = workflow_setup["engine"]

    # An earlier lecturer already has an accepted booking.
    existing = create_booking(
        engine,
        room_id,
        lecturer_id=1,
        headcount=10,
    )

    # A second lecturer requests an overlapping time slot.
    result = bookings.request_booking(
        2,
        room_id=room_id,
        course_code="COMP2605",
        headcount=10,
        preferred_date=existing["preferred_date"],
        start_time="09:30",
        end_time="10:30",
        resources="Whiteboard",
    )

    assert result["ok"] is True
    assert result["booking"]["status"] == "pending"
    assert result["booking"]["confirmation_code"] is None
    assert result["verdict"]["decision"] == "reject"

    approval = bookings.coordinator_override_accept(
        3,
        result["booking"]["id"],
    )

    assert approval["ok"] is False
    assert approval["verdict"]["decision"] == "reject"

    with Session(engine) as session:
        existing_saved = session.get(Booking, existing["id"])
        conflicting = session.get(Booking, result["booking"]["id"])

        assert existing_saved.status == "accepted"
        assert conflicting.status == "pending"
        assert conflicting.confirmation_code is None

def test_booking_rejected_when_headcount_exceeds_room_capacity(workflow_setup):
    room_id = workflow_setup["room_id"]

    result = bookings.request_booking(
        1,
        room_id=room_id,
        course_code="COMP2605",
        headcount=35,
        preferred_date=(
            datetime.now() + timedelta(days=8)
        ).strftime("%Y-%m-%d"),
        start_time="13:00",
        end_time="15:00",
        resources="Projector",
    )

    assert result["ok"] is False

def test_lecturer_cannot_override_booking(workflow_setup):
    engine = workflow_setup["engine"]
    room_id = workflow_setup["room_id"]

    existing = create_booking(
        engine,
        room_id,
        lecturer_id=1,
    )

    result = bookings.coordinator_override_accept(
        1,
        existing["id"],
    )

    assert result["ok"] is False
    assert result["error"] == "coordinator/admin only"

def test_coordinator_can_override_booking(workflow_setup):
    engine = workflow_setup["engine"]
    room_id = workflow_setup["room_id"]

    existing = create_booking(
        engine,
        room_id,
        lecturer_id=1,
        headcount=10,
        created_at="2026-01-01T09:00:00",
    )

    incoming = create_booking(
        engine,
        room_id,
        lecturer_id=2,
        headcount=20,
        status="pending",
        created_at="2026-01-01T10:00:00",
        start_time="09:30",
        end_time="10:30",
    )

    result = bookings.coordinator_override_accept(
        3,
        incoming["id"],
        override_justification="Approved because the incoming cohort is larger.",
        coordinator_override=True,
    )

    assert result["ok"] is True

def test_admin_can_override_booking(workflow_setup):
    engine = workflow_setup["engine"]
    room_id = workflow_setup["room_id"]

    incoming = create_booking(
        engine,
        room_id,
        lecturer_id=2,
        headcount=20,
        status="pending",
        created_at="2026-01-01T10:00:00",
        start_time="09:30",
        end_time="10:30",
    )

    result = bookings.coordinator_override_accept(
        4,
        incoming["id"],
    )

    assert result["ok"] is True
    assert result["booking"]["status"] == "accepted"

def test_override_rejects_nonexistent_booking(workflow_setup):
    result = bookings.coordinator_override_accept(3, 9999)

    assert result["ok"] is False
    assert result["error"] == "booking not found"   

def test_lecturer_cannot_override_another_lecturers_booking(workflow_setup):
    engine = workflow_setup["engine"]
    room_id = workflow_setup["room_id"]

    existing = create_booking(
        engine,
        room_id,
        lecturer_id=2,
    )

    result = bookings.coordinator_override_accept(
        1,
        existing["id"],
    )

    assert result["ok"] is False
    assert result["error"] == "coordinator/admin only"

def test_accepted_booking_has_confirmation_code(workflow_setup):
    engine = workflow_setup["engine"]
    room_id = workflow_setup["room_id"]

    booking = create_booking(
        engine,
        room_id,
        status="accepted",
    )

    with Session(engine) as session:
        saved = session.get(Booking, booking["id"])

    assert saved.status == "accepted"
    assert saved.confirmation_code is not None

def test_lecturer_can_cancel_own_booking(workflow_setup):
    engine = workflow_setup["engine"]
    room_id = workflow_setup["room_id"]

    booking = create_booking(
        engine,
        room_id,
        lecturer_id=1,
    )

    result = bookings.cancel_booking(1, booking["id"])

    assert result["ok"] is True
    assert result["booking"]["status"] == "cancelled"

def test_lecturer_cannot_cancel_another_lecturers_booking(workflow_setup):
    engine = workflow_setup["engine"]
    room_id = workflow_setup["room_id"]

    booking = create_booking(
        engine,
        room_id,
        lecturer_id=2,
    )

    result = bookings.cancel_booking(1, booking["id"])

    assert result["ok"] is False
    assert result["error"] == "forbidden"


def test_non_overlapping_booking_is_allowed(workflow_setup):
    existing = create_booking(
        workflow_setup["engine"],
        workflow_setup["room_id"],
        lecturer_id=1,
        start_time="09:00",
        end_time="11:00",
    )

    result = bookings.request_booking(
        lecturer_id=2,
        room_id=workflow_setup["room_id"],
        course_code="COMP3613",
        headcount=10,
        preferred_date=existing["preferred_date"],
        start_time="11:00",
        end_time="13:00",
        resources="Projector",
    )

    assert result["ok"] is True


def test_booking_outside_room_capacity_is_rejected(workflow_setup):
    result = bookings.request_booking(
        lecturer_id=1,
        room_id=workflow_setup["room_id"],
        course_code="COMP3613",
        headcount=31,
        preferred_date=(
            datetime.now() + timedelta(days=7)
        ).strftime("%Y-%m-%d"),
        start_time="13:00",
        end_time="15:00",
        resources="Projector",
    )

    assert result["ok"] is False






def test_coordinator_override_cannot_exceed_room_capacity(workflow_setup):
    booking = create_booking(
        workflow_setup["engine"],
        workflow_setup["room_id"],
        lecturer_id=2,
        headcount=35,
        status="pending",
    )

    result = bookings.coordinator_override_accept(
        3,
        booking["id"],
    )

    assert result["ok"] is False


def test_overlapping_booking_is_rejected(workflow_setup):
    existing = create_booking(
        workflow_setup["engine"],
        workflow_setup["room_id"],
        lecturer_id=1,
        start_time="09:00",
        end_time="11:00",
    )

    result = bookings.request_booking(
        lecturer_id=2,
        room_id=workflow_setup["room_id"],
        course_code="COMP3613",
        headcount=10,
        preferred_date=existing["preferred_date"],
        start_time="10:00",
        end_time="12:00",
        resources="Projector",
    )

    assert result["ok"] is True
    assert result["booking"]["status"] == "pending"
    assert result["booking"]["confirmation_code"] is None
    assert result["verdict"]["decision"] == "reject"

    approval = bookings.coordinator_override_accept(
        3,
        result["booking"]["id"],
    )

    assert approval["ok"] is False
    assert approval["verdict"]["decision"] == "reject"

    with Session(workflow_setup["engine"]) as session:
        existing_saved = session.get(Booking, existing["id"])
        conflicting = session.get(Booking, result["booking"]["id"])

        assert existing_saved.status == "accepted"
        assert conflicting.status == "pending"
        assert conflicting.confirmation_code is None

