
from datetime import datetime, timedelta

import pytest
from sqlmodel import Session

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

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

# Verify that an already cancelled booking cannot be cancelled again.
def test_repeated_cancellation(cancellation_setup):

    booking_id = cancellation_setup["id"]

    first = bookings.cancel_booking(1, booking_id)
    second = bookings.cancel_booking(1, booking_id)

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["error"] == "booking cannot be cancelled"

# Verify that a rejected booking cannot be cancelled.
def test_rejected_booking_cannot_be_cancelled(
    test_engine, cancellation_setup
):

    booking_id = cancellation_setup["id"]

    with Session(test_engine) as session:
        booking = session.get(Booking, booking_id)
        booking.status = "rejected"
        booking.confirmation_code = None
        session.add(booking)
        session.commit()

    result = bookings.cancel_booking(1, booking_id)

    assert result["ok"] is False
    assert result["error"] == "booking cannot be cancelled"

    with Session(test_engine) as session:
        booking = session.get(Booking, booking_id)
        assert booking.status == "rejected"

# Verify that cancelled bookings cannot be approved or rejected.
@pytest.mark.parametrize("operation", ["approve", "reject"])
def test_cancelled_booking_cannot_be_processed(
    cancellation_setup, monkeypatch, operation
):

    monkeypatch.setattr(
        bookings,
        "get_user",
        lambda actor_id: {
            "role": "lecturer" if actor_id == 1 else "coordinator"
        },
    )

    booking_id = cancellation_setup["id"]

    cancelled = bookings.cancel_booking(1, booking_id)

    assert cancelled["ok"] is True

    if operation == "approve":
        result = bookings.coordinator_override_accept(
            2, booking_id
        )
    else:
        result = bookings.coordinator_reject(
            2, booking_id
        )

    assert result["ok"] is False
    assert result["error"] == "booking is not pending"

# Verify that concurrent approval and cancellation remain consistent.
def test_concurrent_approval_and_cancellation(
    test_engine, cancellation_setup, monkeypatch
):

    monkeypatch.setattr(
        bookings,
        "get_user",
        lambda actor_id: {
            "role": "lecturer" if actor_id == 1 else "coordinator"
        },
    )

    booking_id = cancellation_setup["id"]

    # Prepare a pending booking.
    with Session(test_engine) as session:
        booking = session.get(Booking, booking_id)
        booking.status = "pending"
        booking.confirmation_code = None
        session.add(booking)
        session.commit()

    barrier = Barrier(2, timeout=5)

    def approve():

        barrier.wait()
        return bookings.coordinator_override_accept(
            2, booking_id
        )

    def cancel():

        barrier.wait()
        return bookings.cancel_booking(1, booking_id)

    # Execute both operations concurrently.
    with ThreadPoolExecutor(max_workers=2) as executor:
        approval_future = executor.submit(approve)
        cancellation_future = executor.submit(cancel)

        approval = approval_future.result(timeout=10)
        cancellation = cancellation_future.result(timeout=10)

    assert cancellation["ok"] is True

    # Verify that the final booking state is consistent.
    with Session(test_engine) as session:
        booking = session.get(Booking, booking_id)

        assert booking.status == "cancelled"
        assert booking.confirmation_code is None

    # Any confirmation generated before cancellation must be invalid.
    if approval["ok"]:
        code = approval["booking"]["confirmation_code"]
        assert bookings.get_confirmation(code)["ok"] is False
    else:
        assert approval["error"] == "booking is not pending"

# Verify that concurrent rejection and cancellation cannot both succeed.
def test_concurrent_rejection_and_cancellation(
    test_engine, cancellation_setup, monkeypatch
):

    monkeypatch.setattr(
        bookings,
        "get_user",
        lambda actor_id: {
            "role": "lecturer" if actor_id == 1 else "coordinator"
        },
    )

    booking_id = cancellation_setup["id"]

    # Prepare a pending booking.
    with Session(test_engine) as session:
        booking = session.get(Booking, booking_id)
        booking.status = "pending"
        booking.confirmation_code = None
        session.add(booking)
        session.commit()

    barrier = Barrier(2, timeout=5)

    def reject():

        barrier.wait()
        return bookings.coordinator_reject(
            2, booking_id
        )

    def cancel():

        barrier.wait()
        return bookings.cancel_booking(1, booking_id)

    # Execute both operations concurrently.
    with ThreadPoolExecutor(max_workers=2) as executor:
        rejection_future = executor.submit(reject)
        cancellation_future = executor.submit(cancel)

        rejection = rejection_future.result(timeout=10)
        cancellation = cancellation_future.result(timeout=10)

    # Exactly one operation should succeed.
    assert rejection["ok"] != cancellation["ok"]

    with Session(test_engine) as session:
        booking = session.get(Booking, booking_id)

        if rejection["ok"]:
            assert booking.status == "rejected"
            assert cancellation["error"] == "booking cannot be cancelled"
        else:
            assert booking.status == "cancelled"
            assert rejection["error"] == "booking is not pending"

        assert booking.confirmation_code is None
