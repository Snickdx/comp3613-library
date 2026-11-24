"""Booking request / confirm / cancel flows."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select
from sqlalchemy import text

from app.database import engine as default_engine
from app.models.booking import Booking
from app.models.conflict_decision import ConflictDecision
from app.models.room import Room
from app.services.capacity_guard import CapacityGuard
from app.services.conflicts import resolve_slot_request
from app.services.library_auth import get_user
from app.services.rooms import list_rooms as list_room_configurations


_approval_lock = RLock()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def _record_conflict_decision(
    session: Session,
    incoming: dict[str, Any],
    verdict: dict[str, Any],
    *,
    stage: str,
    booking_id: int | None = None,
    booking_status: str | None = None,
    coordinator_id: int | None = None,
    override_authorized: bool = False,
    override_justification: str | None = None,
    related_booking_id: int | None = None,
) -> None:

    """Create an audit record for a booking conflict decision."""

    record = ConflictDecision(
        booking_id=booking_id,
        lecturer_id=incoming["lecturer_id"],
        room_id=incoming["room_id"],
        course_code=incoming["course_code"],
        headcount=incoming["headcount"],
        preferred_date=incoming["preferred_date"],
        start_time=incoming["start_time"],
        end_time=incoming["end_time"],
        decision=verdict["decision"],
        policy=verdict.get("policy"),
        reason=verdict["reason"],
        stage=stage,
        booking_status=booking_status,
        coordinator_id=coordinator_id,
        override_authorized=override_authorized,
        override_used=verdict.get("override_used", False),
        override_justification=verdict.get(
            "override_justification", override_justification
        ),
        related_booking_id=related_booking_id,
        created_at=_now(),
    )

    # Add the audit record to the current database transaction.
    session.add(record)


def _valid_time_range(start_time: str, end_time: str) -> bool:
    """Check that times use HH:MM format and end is after start."""
    try:
        start = datetime.strptime(start_time, "%H:%M")
        end = datetime.strptime(end_time, "%H:%M")
    except (TypeError, ValueError):
        return False

    return (
        start.strftime("%H:%M") == start_time
        and end.strftime("%H:%M") == end_time
        and start < end
    )


def _times_overlap(
    existing_start: str,
    existing_end: str,
    new_start: str,
    new_end: str,
) -> bool:
    """Return True if two workshop time ranges overlap."""
    return existing_start < new_end and new_start < existing_end


def _dict(row: Booking | Room | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return row.model_dump()


def list_rooms() -> list[dict[str, Any]]:
    return list_room_configurations()

def list_bookings(
    *, room_id: int | None = None, date: str | None = None
) -> list[dict[str, Any]]:
    with Session(default_engine) as session:
        stmt = select(Booking)
        if room_id is not None:
            stmt = stmt.where(Booking.room_id == room_id)
        if date is not None:
            stmt = stmt.where(Booking.preferred_date == date)
        stmt = stmt.order_by(Booking.id)
        return [b.model_dump() for b in session.exec(stmt).all()]


def list_conflict_decisions(
    *, booking_id: int | None = None
) -> list[dict[str, Any]]:

    """Retrieve recorded conflict decisions."""

    with Session(default_engine) as session:
        stmt = select(ConflictDecision)

        # Filter the audit records by booking ID when provided.
        if booking_id is not None:
            stmt = stmt.where(
                ConflictDecision.booking_id == booking_id
            )

        stmt = stmt.order_by(ConflictDecision.id)

        return [
            record.model_dump()
            for record in session.exec(stmt).all()
        ]


def request_booking(
    lecturer_id: int,
    *,
    room_id: int,
    course_code: str,
    headcount: int,
    preferred_date: str,
    start_time: str,
    end_time: str,
    resources: str,
) -> dict[str, Any]:
    user = get_user(lecturer_id)
    if not user or user["role"] != "lecturer":
        return {"ok": False, "error": "lecturers only"}

    # DEFECT: incomplete validation — empty resources / missing course allowed (fixed)
    # Validate the required booking information.
    if not isinstance(course_code, str) or not course_code.strip():
        return {"ok": False, "error": "course code is required"}

    if type(headcount) is not int or headcount <= 0:
        return {"ok": False, "error": "headcount must be a positive integer"}

    try:
        date = datetime.strptime(preferred_date, "%Y-%m-%d")
        if date.strftime("%Y-%m-%d") != preferred_date:
            return {"ok": False, "error": "invalid preferred date"}
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid preferred date"}

    if not isinstance(resources, str) or not resources.strip():
        return {"ok": False, "error": "resources are required"}

    if not _valid_time_range(start_time, end_time):
        return {"ok": False, "error": "invalid workshop time range"}

    with Session(default_engine) as session:
        room_row = session.get(Room, room_id)
        room = _dict(room_row)
        if room is None:
            return {"ok": False, "error": "room not found"}

        existing = [
            b.model_dump()
            for b in session.exec(
                select(Booking).where(
                    Booking.room_id == room_id,
                    Booking.preferred_date == preferred_date,
                )
            ).all()
        ]

        existing = [
            booking for booking in existing
            if booking["status"] in {"accepted", "pending"}
            and _times_overlap(
                booking["start_time"],
                booking["end_time"],
                start_time,
                end_time,
            )
        ]

        incoming = {
            "lecturer_id": lecturer_id,
            "room_id": room_id,
            "course_code": course_code,
            "headcount": headcount,
            "preferred_date": preferred_date,
            "start_time": start_time,
            "end_time": end_time,
            "resources": resources,
            "created_at": _now(),
        }
        verdict = resolve_slot_request(
            incoming=incoming,
            existing=existing,
            room=room,
            coordinator_override=False,
        )

        if verdict["decision"] == "reject":
            priority_reasons = {
                "earlier request wins",
                "existing booking submitted earlier",
                "existing booking has equal submission timestamp",
            }
            if verdict["reason"] not in priority_reasons:

                # Record rejected requests that are not saved as bookings.
                _record_conflict_decision(
                    session,
                    incoming,
                    verdict,
                    stage="submission",
                    booking_status="rejected",
                )
                session.commit()

                return {
                    "ok": False,
                    "error": verdict["reason"],
                    "verdict": verdict,
                }

            capacity = CapacityGuard().check(
                incoming=incoming,
                existing=[],
                room=room,
            )
            if not capacity["allowed"]:

                # Record the original conflict evaluation.
                _record_conflict_decision(
                    session,
                    incoming,
                    verdict,
                    stage="submission",
                    booking_status="rejected",
                )

                # Record the capacity rejection.
                _record_conflict_decision(
                    session,
                    incoming,
                    {
                        "decision": "reject",
                        "reason": capacity["reason"],
                        "policy": "capacity-guard",
                        "override_used": False,
                    },
                    stage="capacity-check",
                    booking_status="rejected",
                )
                session.commit()

                return {
                    "ok": False,
                    "error": capacity["reason"],
                    "verdict": verdict,
                }

        booking = Booking(
            lecturer_id=lecturer_id,
            room_id=room_id,
            course_code=course_code or "",
            headcount=headcount,
            preferred_date=preferred_date,
            start_time=start_time,
            end_time=end_time,
            resources=resources or "",
            status="pending",
            override_used=0,
            confirmation_code=None,
            created_at=incoming["created_at"],
        )
        session.add(booking)

        # Obtain the booking ID before creating the audit record.
        session.flush()

        # Record the conflict evaluation and actual booking status.
        _record_conflict_decision(
            session,
            incoming,
            verdict,
            stage="submission",
            booking_id=booking.id,
            booking_status="pending",
        )

        session.commit()
        session.refresh(booking)
        return {"ok": True, "booking": booking.model_dump(), "verdict": verdict}


def coordinator_override_accept(
    coordinator_id: int,
    booking_id: int,
    override_justification: str | None = None,
    *,
    coordinator_override: bool = False,
) -> dict[str, Any]:
    """Re-evaluate and accept a pending booking under coordinator authorization."""
    user = get_user(coordinator_id)
    if not user or user["role"] not in {"coordinator", "admin"}:
        return {"ok": False, "error": "coordinator/admin only"}

    with _approval_lock:
        with Session(default_engine) as session:
            if session.bind.dialect.name == "sqlite":
                session.exec(text("BEGIN IMMEDIATE"))

            booking_row = session.get(Booking, booking_id)
            if booking_row is None:
                session.rollback()
                return {"ok": False, "error": "booking not found"}

            room_id = booking_row.room_id
            if session.bind.dialect.name == "postgresql":
                room_row = session.exec(
                    select(Room).where(Room.id == room_id).with_for_update()
                ).first()
            else:
                room_row = session.get(Room, room_id)

            room = _dict(room_row)

            session.refresh(booking_row)
            if booking_row.status != "pending":
                session.rollback()
                return {"ok": False, "error": "booking is not pending"}

            booking = booking_row.model_dump()
            existing = [
                b.model_dump()
                for b in session.exec(
                    select(Booking).where(
                        Booking.room_id == booking["room_id"],
                        Booking.preferred_date == booking["preferred_date"],
                        Booking.id != booking_id,
                    )
                ).all()
            ]

            existing = [
                other for other in existing
                if other["status"] in {"accepted", "pending"}
                and _times_overlap(
                    other["start_time"],
                    other["end_time"],
                    booking["start_time"],
                    booking["end_time"],
                )
            ]
            verdict = resolve_slot_request(
                incoming=booking,
                existing=existing,
                room=room,
                coordinator_override=coordinator_override,
                override_justification=override_justification,
            )

            if verdict["decision"] == "reject":

                # Record the failed approval without changing the booking.
                _record_conflict_decision(
                    session,
                    booking,
                    verdict,
                    stage="approval",
                    booking_id=booking_id,
                    booking_status="pending",
                    coordinator_id=coordinator_id,
                    override_authorized=coordinator_override,
                    override_justification=override_justification,
                )

                # Save the audit record even though approval failed.
                session.commit()

                return {"ok": False, "error": verdict["reason"], "verdict": verdict}

            for bid in verdict.get("displace_ids") or []:
                displaced = session.get(Booking, bid)
                if displaced is not None:
                    displaced.status = "rejected"
                    displaced.confirmation_code = None
                    session.add(displaced)

                    # Record the rejection of the displaced booking.
                    _record_conflict_decision(
                        session,
                        displaced.model_dump(),
                        {
                            "decision": "reject",
                            "reason": verdict["reason"],
                            "policy": verdict.get("policy"),
                            "override_used": verdict.get(
                                "override_used", False
                            ),
                        },
                        stage="displacement",
                        booking_id=bid,
                        booking_status="rejected",
                        coordinator_id=coordinator_id,
                        override_authorized=coordinator_override,
                        override_justification=verdict.get(
                            "override_justification",
                            override_justification,
                        ),
                        related_booking_id=booking_id,
                    )

            code = f"CONF-{uuid4().hex[:8].upper()}"
            booking_row.status = "accepted"
            booking_row.override_used = (
                1 if verdict.get("override_used") is True else 0
            )
            booking_row.confirmation_code = code
            session.add(booking_row)

            # Record the successful approval and override details.
            _record_conflict_decision(
                session,
                booking,
                verdict,
                stage="approval",
                booking_id=booking_id,
                booking_status="accepted",
                coordinator_id=coordinator_id,
                override_authorized=coordinator_override,
                override_justification=override_justification,
            )

            session.commit()
            session.refresh(booking_row)
            return {
                "ok": True,
                "booking": booking_row.model_dump(),
                "verdict": verdict,
            }


def coordinator_reject(
    coordinator_id: int,
    booking_id: int,
) -> dict[str, Any]:

    """Reject a pending booking under coordinator authorization."""

    # Verify that the user is authorized to reject bookings.
    user = get_user(coordinator_id)

    if not user or user["role"] not in {"coordinator", "admin"}:
        return {"ok": False, "error": "coordinator/admin only"}

    # Use the same locking mechanism as the approval process.
    with _approval_lock:
        with Session(default_engine) as session:
            if session.bind.dialect.name == "sqlite":
                session.exec(text("BEGIN IMMEDIATE"))

            booking = session.get(Booking, booking_id)

            # Check whether the booking exists.
            if booking is None:
                session.rollback()
                return {"ok": False, "error": "booking not found"}

            # Lock the room to prevent concurrent approval and rejection.
            if session.bind.dialect.name == "postgresql":
                session.exec(
                    select(Room)
                    .where(Room.id == booking.room_id)
                    .with_for_update()
                ).first()

            session.refresh(booking)

            # Only pending bookings can be rejected.
            if booking.status != "pending":
                session.rollback()
                return {"ok": False, "error": "booking is not pending"}

            # Reject the booking and invalidate its confirmation.
            booking.status = "rejected"
            booking.confirmation_code = None

            # Save the updated booking.
            session.add(booking)

            # Record the coordinator's manual rejection.
            _record_conflict_decision(
                session,
                booking.model_dump(),
                {
                    "decision": "reject",
                    "reason": "booking rejected by coordinator",
                    "policy": "manual-rejection",
                    "override_used": False,
                },
                stage="manual-rejection",
                booking_id=booking_id,
                booking_status="rejected",
                coordinator_id=coordinator_id,
            )

            session.commit()
            session.refresh(booking)

            return {"ok": True, "booking": booking.model_dump()}


def cancel_booking(actor_id: int, booking_id: int) -> dict[str, Any]:
    user = get_user(actor_id)
    if not user:
        return {"ok": False, "error": "unknown user"}

    # Use the same locking mechanism as approval and rejection.
    with _approval_lock:
        with Session(default_engine) as session:
            if session.bind.dialect.name == "sqlite":
                session.exec(text("BEGIN IMMEDIATE"))

            booking = session.get(Booking, booking_id)

            if booking is None:
                session.rollback()
                return {"ok": False, "error": "booking not found"}

            # Lock the room to prevent concurrent booking modifications.
            if session.bind.dialect.name == "postgresql":
                session.exec(
                    select(Room)
                    .where(Room.id == booking.room_id)
                    .with_for_update()
                ).first()

            session.refresh(booking)

            if user["role"] == "lecturer" and booking.lecturer_id != actor_id:
                session.rollback()
                return {"ok": False, "error": "forbidden"}

            if user["role"] not in {"lecturer", "coordinator", "admin"}:
                session.rollback()
                return {"ok": False, "error": "forbidden"}

            # Only pending and accepted bookings can be cancelled.
            if booking.status not in {"pending", "accepted"}:
                session.rollback()
                return {"ok": False, "error": "booking cannot be cancelled"}

            # DEFECT: cancel sets status but confirmation_code remains usable
            # Check whether the workshop has already started.
            workshop_start = datetime.strptime(
                f"{booking.preferred_date} {booking.start_time}",
                "%Y-%m-%d %H:%M",
            )

            if datetime.now() >= workshop_start:
                session.rollback()
                return {"ok": False, "error": "workshop has already started"}

            # Cancel the booking and invalidate its confirmation.
            booking.status = "cancelled"
            booking.confirmation_code = None
            session.add(booking)
            session.commit()
            session.refresh(booking)
            return {"ok": True, "booking": booking.model_dump()}


def get_confirmation(code: str) -> dict[str, Any]:
    with Session(default_engine) as session:
        row = session.exec(
            select(Booking).where(
                Booking.confirmation_code == code,
                Booking.status == "accepted",
            )
        ).first()
        if row is None:
            return {"ok": False, "error": "not found"}

        return {"ok": True, "booking": row.model_dump()}