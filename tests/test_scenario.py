"""Shallow scenario smoke tests — intentionally weak."""

from fastapi.testclient import TestClient

from app.main import app
from app.seed import seed


def setup_module() -> None:
    seed(reset=True)


client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["scenario"] == "library"


def test_login_coordinator():
    r = client.post(
        "/api/auth/login",
        json={"email": "coord@example.com", "password": "coord-dev"},
    )
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "coordinator"
    assert "password_hash" not in r.json()["user"]
    assert "password" not in r.json()["user"]
    assert r.json()["access_token"]
    assert r.json()["token_type"] == "bearer"


def test_booking_api_requires_bearer_token_even_with_user_id_header():
    room_id = client.get("/api/rooms").json()["rooms"][0]["id"]
    response = client.post(
        "/api/bookings",
        headers={"X-User-Id": "1"},
        json={
            "room_id": room_id,
            "course_code": "COMP3613",
            "headcount": 10,
            "preferred_date": "2099-03-16",
            "start_time": "10:00",
            "end_time": "11:00",
            "resources": "projector",
        },
    )

    assert response.status_code == 401


def test_user_id_header_cannot_impersonate_booking_owner():
    lecturer_response = client.post(
        "/api/auth/login",
        json={"email": "lecturer2@example.com", "password": "lect-dev"},
    )
    owner_response = client.post(
        "/api/auth/login",
        json={"email": "lecturer1@example.com", "password": "lect-dev"},
    )
    booking = next(
        item
        for item in client.get("/api/bookings").json()["bookings"]
        if item["confirmation_code"] == "CONF-SEED01"
    )

    response = client.post(
        f"/api/bookings/{booking['id']}/cancel",
        headers={
            "Authorization": f"Bearer {lecturer_response.json()['access_token']}",
            "X-User-Id": str(owner_response.json()["user"]["id"]),
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"


def test_rooms_listed():
    r = client.get("/api/rooms")
    assert r.status_code == 200
    assert len(r.json()["rooms"]) >= 1
