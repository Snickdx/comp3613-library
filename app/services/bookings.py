"""Booking request / confirm / cancel flows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from app.database import engine
from app.models.booking import Booking
from app.models.room import Room
from app.services.conflicts import resolve_slot_request
from app.services.library_auth import get_user


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dict(row: Booking | Room | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return row.model_dump()


def list_rooms() -> list[dict[str, Any]]:
    with Session(engine) as session:
        rows = session.exec(select(Room).order_by(Room.id)).all()
        return [r.model_dump() for r in rows]


def list_bookings(
    *, room_id: int | None = None, date: str | None = None
) -> list[dict[str, Any]]:
    with Session(engine) as session:
        stmt = select(Booking)
        if room_id is not None:
            stmt = stmt.where(Booking.room_id == room_id)
        if date is not None:
            stmt = stmt.where(Booking.preferred_date == date)
        stmt = stmt.order_by(Booking.id)
        return [b.model_dump() for b in session.exec(stmt).all()]


def request_booking(
    lecturer_id: int,
    *,
    room_id: int,
    course_code: str,
    headcount: int,
    preferred_date: str,
    resources: str,
) -> dict[str, Any]:
    user = get_user(lecturer_id)
    if not user or user["role"] != "lecturer":
        return {"ok": False, "error": "lecturers only"}

    # DEFECT: incomplete validation — empty resources / missing course allowed
    if headcount <= 0:
        return {"ok": False, "error": "headcount must be positive"}

    with Session(engine) as session:
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

        incoming = {
            "lecturer_id": lecturer_id,
            "room_id": room_id,
            "course_code": course_code,
            "headcount": headcount,
            "preferred_date": preferred_date,
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
            return {"ok": False, "error": verdict["reason"], "verdict": verdict}

        for bid in verdict.get("displace_ids") or []:
            # DEFECT: displace marks rejected but leaves confirmation_code
            displaced = session.get(Booking, bid)
            if displaced is not None:
                displaced.status = "rejected"
                session.add(displaced)

        # DEFECT: new requests go straight to accepted (skip pending coordinator review)
        status = "accepted"
        code = f"CONF-{uuid4().hex[:8].upper()}"
        booking = Booking(
            lecturer_id=lecturer_id,
            room_id=room_id,
            course_code=course_code or "",
            headcount=headcount,
            preferred_date=preferred_date,
            resources=resources or "",
            status=status,
            override_used=1 if verdict.get("override_used") else 0,
            confirmation_code=code,
            created_at=incoming["created_at"],
        )
        session.add(booking)
        session.commit()
        session.refresh(booking)
        return {"ok": True, "booking": booking.model_dump(), "verdict": verdict}


def coordinator_override_accept(
    coordinator_id: int, booking_id: int
) -> dict[str, Any]:
    """Force-accept a booking, using the same flawed resolver for displace."""
    user = get_user(coordinator_id)
    if not user or user["role"] not in {"coordinator", "admin"}:
        return {"ok": False, "error": "coordinator/admin only"}

    with Session(engine) as session:
        booking_row = session.get(Booking, booking_id)
        if booking_row is None:
            return {"ok": False, "error": "booking not found"}
        booking = booking_row.model_dump()

        room = _dict(session.get(Room, booking["room_id"]))
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
        verdict = resolve_slot_request(
            incoming=booking,
            existing=existing,
            room=room,
            coordinator_override=True,
        )
        for bid in verdict.get("displace_ids") or []:
            displaced = session.get(Booking, bid)
            if displaced is not None:
                displaced.status = "rejected"
                session.add(displaced)
        code = booking.get("confirmation_code") or f"CONF-{uuid4().hex[:8].upper()}"
        booking_row.status = "accepted"
        booking_row.override_used = 1
        booking_row.confirmation_code = code
        session.add(booking_row)
        session.commit()
        session.refresh(booking_row)
        return {"ok": True, "booking": booking_row.model_dump(), "verdict": verdict}


def cancel_booking(actor_id: int, booking_id: int) -> dict[str, Any]:
    user = get_user(actor_id)
    if not user:
        return {"ok": False, "error": "unknown user"}
    with Session(engine) as session:
        booking = session.get(Booking, booking_id)
        if booking is None:
            return {"ok": False, "error": "booking not found"}
        if user["role"] == "lecturer" and booking.lecturer_id != actor_id:
            return {"ok": False, "error": "forbidden"}
        if user["role"] not in {"lecturer", "coordinator", "admin"}:
            return {"ok": False, "error": "forbidden"}

        # DEFECT: cancel sets status but confirmation_code remains usable
        booking.status = "cancelled"
        session.add(booking)
        session.commit()
        session.refresh(booking)
        return {"ok": True, "booking": booking.model_dump()}


def get_confirmation(code: str) -> dict[str, Any]:
    with Session(engine) as session:
        row = session.exec(
            select(Booking).where(Booking.confirmation_code == code)
        ).first()
        if row is None:
            return {"ok": False, "error": "not found"}
        # DEFECT: returns confirmation even when cancelled/rejected
        return {"ok": True, "booking": row.model_dump()}
