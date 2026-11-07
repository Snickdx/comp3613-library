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


def test_rooms_listed():
    r = client.get("/api/rooms")
    assert r.status_code == 200
    assert len(r.json()["rooms"]) >= 1
