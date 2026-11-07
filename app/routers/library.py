"""Library workshop booking scenario JSON API (OpenAPI /docs)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.services import bookings
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
    resources: str = ""


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
        resources=body.resources,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/bookings/{booking_id}/override-accept")
def override_accept(
    booking_id: int, x_user_id: str | None = Header(default=None)
) -> dict[str, Any]:
    result = bookings.coordinator_override_accept(_actor_id(x_user_id), booking_id)
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
