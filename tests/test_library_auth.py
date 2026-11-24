import jwt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.config import get_settings
from app.routers import library as library_router
from app.services import library_auth
from app.utilities.security import create_access_token


def test_api_access_token_contains_user_identity():
    token = library_auth.issue_api_access_token({"id": 7, "role": "lecturer"})
    payload = jwt.decode(
        token,
        get_settings().secret_key,
        algorithms=[get_settings().jwt_algorithm],
    )

    assert payload["sub"] == "7"
    assert payload["role"] == "lecturer"


def test_current_api_user_uses_signed_token_subject(monkeypatch):
    user = {"id": 7, "role": "lecturer"}
    monkeypatch.setattr(library_auth, "get_user", lambda user_id: user)
    token = create_access_token({"sub": "7", "role": "lecturer"})
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )

    assert library_auth.get_current_api_user(credentials) == user


@pytest.mark.parametrize(
    "credentials",
    [
        None,
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid"),
    ],
)
def test_current_api_user_rejects_missing_or_invalid_token(credentials):
    with pytest.raises(HTTPException) as exc_info:
        library_auth.get_current_api_user(credentials)

    assert exc_info.value.status_code == 401
    assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"


def test_current_api_user_rejects_deleted_user(monkeypatch):
    monkeypatch.setattr(library_auth, "get_user", lambda user_id: None)
    token = create_access_token({"sub": "7", "role": "lecturer"})
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )

    with pytest.raises(HTTPException) as exc_info:
        library_auth.get_current_api_user(credentials)

    assert exc_info.value.status_code == 401


def test_booking_route_uses_authenticated_user_not_user_id_header(monkeypatch):
    monkeypatch.setattr(
        library_router.bookings,
        "request_booking",
        lambda actor_id, **kwargs: {"ok": True, "actor_id": actor_id},
    )
    body = library_router.BookingBody(
        room_id=1,
        course_code="COMP3613",
        headcount=10,
        preferred_date="2099-03-16",
        start_time="10:00",
        end_time="11:00",
        resources="projector",
    )

    result = library_router.create_booking(
        body,
        current_user={"id": 42, "role": "lecturer"},
    )

    assert result["actor_id"] == 42


@pytest.mark.parametrize("role", ["coordinator", "admin"])
def test_non_lecturer_cannot_submit_booking_request(monkeypatch, role):
    def fail_if_called(*args, **kwargs):
        pytest.fail("booking service must not run for a non-lecturer")

    monkeypatch.setattr(
        library_router.bookings,
        "request_booking",
        fail_if_called,
    )
    body = library_router.BookingBody(
        room_id=1,
        course_code="COMP3613",
        headcount=10,
        preferred_date="2099-03-16",
        start_time="10:00",
        end_time="11:00",
        resources="projector",
    )

    with pytest.raises(HTTPException) as exc_info:
        library_router.create_booking(
            body,
            current_user={"id": 42, "role": role},
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "lecturers only"


@pytest.mark.parametrize("role", ["lecturer", "regular_user"])
def test_non_coordinator_cannot_override_booking(monkeypatch, role):
    def fail_if_called(*args, **kwargs):
        pytest.fail("override service must not run for an unauthorized role")

    monkeypatch.setattr(
        library_router.bookings,
        "coordinator_override_accept",
        fail_if_called,
    )

    with pytest.raises(HTTPException) as exc_info:
        library_router.override_accept(
            booking_id=10,
            body=library_router.OverrideAcceptBody(
                override_justification="approved by coordinator",
            ),
            current_user={"id": 42, "role": role},
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "coordinator or admin only"


@pytest.mark.parametrize("role", ["coordinator", "admin"])
def test_coordinator_and_admin_can_request_override(monkeypatch, role):
    monkeypatch.setattr(
        library_router.bookings,
        "coordinator_override_accept",
        lambda actor_id, booking_id, override_justification, *, coordinator_override: {
            "ok": True,
            "actor_id": actor_id,
            "booking_id": booking_id,
            "override_justification": override_justification,
            "coordinator_override": coordinator_override,
        },
        
    )

    result = library_router.override_accept(
        booking_id=10,
        body=library_router.OverrideAcceptBody(
            override_justification="approved by coordinator",
        ),
        current_user={"id": 42, "role": role},
    )

    assert result == {
        "ok": True,
        "actor_id": 42,
        "booking_id": 10,
        "override_justification": "approved by coordinator",
        "coordinator_override": True,
    }


def test_cancel_route_uses_authenticated_user_and_returns_forbidden(monkeypatch):
    calls = []

    def cancel(actor_id, booking_id):
        calls.append((actor_id, booking_id))
        return {"ok": False, "error": "forbidden"}

    monkeypatch.setattr(library_router.bookings, "cancel_booking", cancel)

    with pytest.raises(HTTPException) as exc_info:
        library_router.cancel(
            booking_id=10,
            current_user={"id": 42, "role": "lecturer"},
        )

    assert calls == [(42, 10)]
    assert exc_info.value.status_code == 403


def test_cancel_route_returns_booking_for_permitted_request(monkeypatch):
    monkeypatch.setattr(
        library_router.bookings,
        "cancel_booking",
        lambda actor_id, booking_id: {
            "ok": True,
            "actor_id": actor_id,
            "booking_id": booking_id,
        },
    )

    result = library_router.cancel(
        booking_id=10,
        current_user={"id": 42, "role": "lecturer"},
    )

    assert result == {"ok": True, "actor_id": 42, "booking_id": 10}


def test_booking_routes_advertise_bearer_authentication():
    app = FastAPI()
    app.include_router(library_router.router, prefix="/api")

    schema = app.openapi()

    assert schema["paths"]["/api/bookings"]["post"]["security"]
    assert schema["paths"]["/api/bookings/{booking_id}/cancel"]["post"]["security"]
