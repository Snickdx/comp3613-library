"""Room configuration and capacity operations."""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.database import engine
from app.models.room import Room
from app.services.conflicts import room_capacity

default_engine = engine


def _room_data(room: Room) -> dict[str, Any]:
    data = room.model_dump()
    data["effective_capacity"] = room_capacity(data)
    return data


def list_rooms() -> list[dict[str, Any]]:
    with Session(default_engine) as session:
        rows = session.exec(select(Room).order_by(Room.id)).all()
        return [_room_data(room) for room in rows]


def get_room(room_id: int) -> dict[str, Any] | None:
    with Session(default_engine) as session:
        room = session.get(Room, room_id)
        return _room_data(room) if room is not None else None


def update_room(room_id: int, updates: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = {"name", "capacity"}
    if not updates:
        return {"ok": False, "error": "at least one room field is required"}
    if set(updates) - allowed_fields:
        return {"ok": False, "error": "unsupported room fields"}

    name = updates.get("name")
    if "name" in updates:
        if not isinstance(name, str) or not name.strip():
            return {"ok": False, "error": "name must be a non-empty string"}
        name = name.strip()

    capacity = updates.get("capacity")
    if "capacity" in updates and capacity is not None:
        if type(capacity) is not int or capacity <= 0:
            return {
                "ok": False,
                "error": "capacity must be a positive integer or null",
            }

    with Session(default_engine) as session:
        room = session.get(Room, room_id)
        if room is None:
            return {"ok": False, "error": "room not found"}

        if "name" in updates:
            duplicate = session.exec(
                select(Room).where(Room.name == name, Room.id != room_id)
            ).first()
            if duplicate is not None:
                return {"ok": False, "error": "room name already exists"}
            room.name = name

        if "capacity" in updates:
            room.capacity = capacity

        session.add(room)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return {"ok": False, "error": "room name already exists"}

        session.refresh(room)
        return {"ok": True, "room": _room_data(room)}
