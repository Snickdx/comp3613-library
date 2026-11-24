"""Library workshop booking scenario JSON API (OpenAPI /docs)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from app.dependencies.auth import AdminDep
from app.services import bookings
from app.services import rooms as room_service
from app.services import library_auth as auth

router = APIRouter(tags=["library"])


class LoginBody(BaseModel):
    email: str
    password: str


class BookingBody(BaseModel):
    room_id: int
    course_code: str = ""
    headcount: int
    preferred_date: str = Field(description="ISO date YYYY-MM-DD")
    start_time: str = Field(description="Workshop start time, HH:MM")
    end_time: str = Field(description="Workshop end time, HH:MM")
    resources: str = ""

class OverrideAcceptBody(BaseModel):
    override_justification: str = Field(min_length=1)


class RoomUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    capacity: StrictInt | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str:
        if value is None or not value.strip():
            raise ValueError("name must be a non-empty string")
        return value.strip()

    @field_validator("capacity")
    @classmethod
    def validate_capacity(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("capacity must be a positive integer or null")
        return value

    @model_validator(mode="after")
    def require_room_fields(self) -> RoomUpdateBody:
        if not self.model_fields_set:
            raise ValueError("at least one room field is required")
        return self


def _actor_id(x_user_id: str | None) -> int:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header required")
    try:
        return int(x_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="X-User-Id must be int") from exc


@router.post("/auth/login")
def login(body: LoginBody) -> dict[str, Any]:
    user = auth.login(body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return {"user": user}


@router.get("/rooms")
def rooms() -> dict[str, Any]:
    return {"rooms": bookings.list_rooms()}


@router.get("/admin/rooms")
def admin_rooms(current_admin: AdminDep) -> dict[str, Any]:
    return {"rooms": room_service.list_rooms()}


@router.get("/admin/rooms/{room_id}")
def admin_room(room_id: int, current_admin: AdminDep) -> dict[str, Any]:
    room = room_service.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    return {"room": room}


@router.patch("/admin/rooms/{room_id}")
def update_admin_room(
    room_id: int,
    body: RoomUpdateBody,
    current_admin: AdminDep,
) -> dict[str, Any]:
    result = room_service.update_room(
        room_id,
        body.model_dump(exclude_unset=True),
    )
    if not result.get("ok"):
        error = result.get("error", "room update failed")
        status_code = {
            "room not found": 404,
            "room name already exists": 409,
        }.get(error, 422)
        raise HTTPException(status_code=status_code, detail=error)
    return result


@router.get("/bookings")
def list_all(room_id: int | None = None, date: str | None = None) -> dict[str, Any]:
    return {"bookings": bookings.list_bookings(room_id=room_id, date=date)}


@router.post("/bookings")
def create_booking(
    body: BookingBody, x_user_id: str | None = Header(default=None)
) -> dict[str, Any]:
    result = bookings.request_booking(
        _actor_id(x_user_id),
        room_id=body.room_id,
        course_code=body.course_code,
        headcount=body.headcount,
        preferred_date=body.preferred_date,
        start_time=body.start_time,
        end_time=body.end_time,
        resources=body.resources,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/bookings/{booking_id}/override-accept")
def override_accept(
    booking_id: int,
    body: OverrideAcceptBody,
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    result = bookings.coordinator_override_accept(
        _actor_id(x_user_id),
        booking_id,
        override_justification=body.override_justification,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/bookings/{booking_id}/cancel")
def cancel(
    booking_id: int, x_user_id: str | None = Header(default=None)
) -> dict[str, Any]:
    result = bookings.cancel_booking(_actor_id(x_user_id), booking_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/confirmations/{code}")
def confirmation(code: str) -> dict[str, Any]:
    result = bookings.get_confirmation(code)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result
