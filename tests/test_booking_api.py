import pytest
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.routers import library as library_router


# Verify that coordinators and administrators can approve bookings.
@pytest.mark.parametrize("role", ["coordinator", "admin"])
def test_authorized_user_can_approve(monkeypatch, role):

    monkeypatch.setattr(
        library_router.bookings,
        "coordinator_override_accept",
        lambda actor_id, booking_id, *, coordinator_override: {
            "ok": True,
            "actor_id": actor_id,
            "booking_id": booking_id,
            "coordinator_override": coordinator_override,
        },
    )

    result = library_router.approve(
        booking_id=10,
        current_user={"id": 42, "role": role},
    )

    assert result == {
        "ok": True,
        "actor_id": 42,
        "booking_id": 10,
        "coordinator_override": False,
    }


# Verify that lecturers cannot approve bookings.
def test_lecturer_cannot_approve():

    with pytest.raises(HTTPException) as exc:
        library_router.approve(
            booking_id=10,
            current_user={"id": 1, "role": "lecturer"},
        )

    assert exc.value.status_code == 403


# Verify that coordinators and administrators can reject bookings.
@pytest.mark.parametrize("role", ["coordinator", "admin"])
def test_authorized_user_can_reject(monkeypatch, role):

    monkeypatch.setattr(
        library_router.bookings,
        "coordinator_reject",
        lambda actor_id, booking_id: {
            "ok": True,
            "actor_id": actor_id,
            "booking_id": booking_id,
        },
    )

    result = library_router.reject(
        booking_id=10,
        current_user={"id": 42, "role": role},
    )

    assert result == {
        "ok": True,
        "actor_id": 42,
        "booking_id": 10,
    }


# Verify that lecturers cannot reject bookings.
def test_lecturer_cannot_reject():

    with pytest.raises(HTTPException) as exc:
        library_router.reject(
            booking_id=10,
            current_user={"id": 1, "role": "lecturer"},
        )

    assert exc.value.status_code == 403


# Verify that approving a nonexistent booking returns 404.
def test_approve_nonexistent_booking(monkeypatch):

    monkeypatch.setattr(
        library_router.bookings,
        "coordinator_override_accept",
        lambda *args, **kwargs: {
            "ok": False,
            "error": "booking not found",
        },
    )

    with pytest.raises(HTTPException) as exc:
        library_router.approve(
            booking_id=999,
            current_user={"id": 42, "role": "coordinator"},
        )

    assert exc.value.status_code == 404


# Verify that rejecting a nonexistent booking returns 404.
def test_reject_nonexistent_booking(monkeypatch):

    monkeypatch.setattr(
        library_router.bookings,
        "coordinator_reject",
        lambda *args, **kwargs: {
            "ok": False,
            "error": "booking not found",
        },
    )

    with pytest.raises(HTTPException) as exc:
        library_router.reject(
            booking_id=999,
            current_user={"id": 42, "role": "coordinator"},
        )

    assert exc.value.status_code == 404


# Verify that non-pending bookings cannot be approved or rejected.
@pytest.mark.parametrize("operation", ["approve", "reject"])
def test_non_pending_booking_cannot_be_processed(
    monkeypatch, operation
):

    service = (
        "coordinator_override_accept"
        if operation == "approve"
        else "coordinator_reject"
    )

    monkeypatch.setattr(
        library_router.bookings,
        service,
        lambda *args, **kwargs: {
            "ok": False,
            "error": "booking is not pending",
        },
    )

    endpoint = getattr(library_router, operation)

    with pytest.raises(HTTPException) as exc:
        endpoint(
            booking_id=10,
            current_user={"id": 42, "role": "coordinator"},
        )

    assert exc.value.status_code == 400


# Verify that invalid headcount types cannot be converted to integers.
@pytest.mark.parametrize(
    "headcount", ["25", 25.0, 25.5, True, False, None]
)
def test_invalid_headcount_type(headcount):

    with pytest.raises(ValidationError):
        library_router.BookingBody(
            room_id=1,
            course_code="COMP3613",
            headcount=headcount,
            preferred_date="2099-12-01",
            start_time="09:00",
            end_time="11:00",
            resources="Projector",
        )


# Verify that a valid integer headcount is accepted.
def test_valid_integer_headcount():

    body = library_router.BookingBody(
        room_id=1,
        course_code="COMP3613",
        headcount=25,
        preferred_date="2099-12-01",
        start_time="09:00",
        end_time="11:00",
        resources="Projector",
    )

    assert body.headcount == 25
    assert type(body.headcount) is int

# Create an isolated API application for endpoint testing.
@pytest.fixture
def api_client():

    app = FastAPI()
    app.include_router(library_router.router, prefix="/api")

    with TestClient(app) as client:
        yield client


# Verify that approval and rejection require authentication.
@pytest.mark.parametrize("operation", ["approve", "reject"])
def test_booking_endpoint_requires_authentication(api_client, operation):

    response = api_client.post(
        f"/api/bookings/10/{operation}"
    )

    assert response.status_code == 401


# Verify that lecturers cannot access coordinator endpoints.
@pytest.mark.parametrize("operation", ["approve", "reject"])
def test_lecturer_endpoint_access_denied(api_client, operation):

    api_client.app.dependency_overrides[
        library_router.auth.get_current_api_user
    ] = lambda: {"id": 1, "role": "lecturer"}

    response = api_client.post(
        f"/api/bookings/10/{operation}"
    )

    assert response.status_code == 403


# Verify that the normal approval endpoint is accessible.
def test_approval_http_endpoint(api_client, monkeypatch):

    api_client.app.dependency_overrides[
        library_router.auth.get_current_api_user
    ] = lambda: {"id": 42, "role": "coordinator"}

    monkeypatch.setattr(
        library_router.bookings,
        "coordinator_override_accept",
        lambda actor_id, booking_id, *, coordinator_override: {
            "ok": True,
            "booking_id": booking_id,
            "coordinator_override": coordinator_override,
        },
    )

    response = api_client.post("/api/bookings/10/approve")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["booking_id"] == 10
    assert response.json()["coordinator_override"] is False


# Verify that the rejection endpoint is accessible.
def test_rejection_http_endpoint(api_client, monkeypatch):

    api_client.app.dependency_overrides[
        library_router.auth.get_current_api_user
    ] = lambda: {"id": 42, "role": "coordinator"}

    monkeypatch.setattr(
        library_router.bookings,
        "coordinator_reject",
        lambda actor_id, booking_id: {
            "ok": True,
            "booking_id": booking_id,
        },
    )

    response = api_client.post("/api/bookings/10/reject")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["booking_id"] == 10