"""Library workshop booking scenario JSON API (OpenAPI /docs)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
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
    start_time: str = Field(description="Workshop start time, HH:MM")
    end_time: str = Field(description="Workshop end time, HH:MM")
    resources: str = ""


def _raise_service_error(result: dict[str, Any]) -> None:
    error = result.get("error", "booking request failed")
    status_code = {
        "forbidden": 403,
        "coordinator/admin only": 403,
        "lecturers only": 403,
        "unknown user": 401,
        "booking not found": 404,
        "room not found": 404,
    }.get(error, 400)
    raise HTTPException(status_code=status_code, detail=error)


@router.post("/auth/login")
def login(body: LoginBody) -> dict[str, Any]:
    user = auth.login(body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return {
        "user": user,
        "access_token": auth.issue_api_access_token(user),
        "token_type": "bearer",
    }


@router.get("/rooms")
def rooms() -> dict[str, Any]:
    return {"rooms": bookings.list_rooms()}


@router.get("/bookings")
def list_all(room_id: int | None = None, date: str | None = None) -> dict[str, Any]:
    return {"bookings": bookings.list_bookings(room_id=room_id, date=date)}


@router.post("/bookings")
def create_booking(
    body: BookingBody,
    current_user: dict[str, Any] = Depends(auth.get_current_api_user),
) -> dict[str, Any]:
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="lecturers only")

    result = bookings.request_booking(
        int(current_user["id"]),
        room_id=body.room_id,
        course_code=body.course_code,
        headcount=body.headcount,
        preferred_date=body.preferred_date,
        start_time=body.start_time,
        end_time=body.end_time,
        resources=body.resources,
    )
    if not result.get("ok"):
        _raise_service_error(result)
    return result


@router.post("/bookings/{booking_id}/override-accept")
def override_accept(
    booking_id: int,
    body: OverrideAcceptBody,
   
    current_user: dict[str, Any] = Depends(auth.get_current_api_user),,
) -> dict[str, Any]:
    if current_user["role"] not in {"coordinator", "admin"}:
        raise HTTPException(
            status_code=403,
            detail="coordinator or admin only",
        )

    result = bookings.coordinator_override_accept(
        
        int(current_user["id"]),
        booking_id
    ,
        override_justification=body.override_justification,
        coordinator_override=True,
    )
    if not result.get("ok"):
        _raise_service_error(result)
    return result


@router.post("/bookings/{booking_id}/cancel")
def cancel(
    booking_id: int,
    current_user: dict[str, Any] = Depends(auth.get_current_api_user),
) -> dict[str, Any]:
    result = bookings.cancel_booking(int(current_user["id"]), booking_id)
    if not result.get("ok"):
        _raise_service_error(result)
    return result


@router.get("/confirmations/{code}")
def confirmation(code: str) -> dict[str, Any]:
    result = bookings.get_confirmation(code)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result
