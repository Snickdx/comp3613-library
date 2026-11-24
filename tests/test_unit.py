from types import SimpleNamespace
from app.services.capacity_guard import CapacityGuard

import jwt

from app.services.auth_service import AuthService
from app.utilities.security import encrypt_password, verify_password


def test_password_hash_round_trip_and_rejects_wrong_password():
    password_hash = encrypt_password("correct horse")

    assert password_hash != "correct horse"
    assert verify_password("correct horse", password_hash)
    assert not verify_password("wrong horse", password_hash)


def test_authenticate_user_returns_token_for_valid_credentials(monkeypatch):
    user = SimpleNamespace(
        id=7,
        username="alice",
        password=encrypt_password("secret"),
        role="regular_user",
    )

    class FakeUserRepository:
        def get_by_username(self, username):
            return user if username == "alice" else None

    monkeypatch.setattr(
        "app.services.auth_service.create_access_token",
        lambda data: {"sub": data["sub"], "role": data["role"]},
    )

    token = AuthService(FakeUserRepository()).authenticate_user("alice", "secret")

    assert token == {"sub": "7", "role": "regular_user"}


def test_authenticate_user_returns_none_for_invalid_credentials():
    user = SimpleNamespace(
        id=7,
        username="alice",
        password=encrypt_password("secret"),
        role="regular_user",
    )

    class FakeUserRepository:
        def get_by_username(self, username):
            return user if username == "alice" else None

    service = AuthService(FakeUserRepository())

    assert service.authenticate_user("alice", "incorrect") is None
    assert service.authenticate_user("missing", "secret") is None


def test_access_token_contains_subject_and_role():
    from app.config import get_settings
    from app.utilities.security import create_access_token

    token = create_access_token({"sub": "7", "role": "admin"})
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    assert payload["sub"] == "7"
    assert payload["role"] == "admin"
    assert "exp" in payload


#capacity guard tests

def test_capacity_guard_allows_booking_within_capacity():
    guard = CapacityGuard()

    result = guard.check(
        incoming={"headcount": 10},
        existing=[
            {"headcount": 10, "status": "accepted"}
        ],
        room={"capacity": 30},
    )

    assert result["allowed"] is True
    assert result["total"] == 20


def test_capacity_guard_rejects_booking_exceeding_capacity():
    guard = CapacityGuard()

    result = guard.check(
        incoming={"headcount": 15},
        existing=[
            {"headcount": 20, "status": "accepted"}
        ],
        room={"capacity": 30},
    )

    assert result["allowed"] is False
    assert result["total"] == 35


def test_capacity_guard_counts_multiple_existing_bookings():
    guard = CapacityGuard()

    result = guard.check(
        incoming={"headcount": 10},
        existing=[
            {"headcount": 15, "status": "accepted"},
            {"headcount": 10, "status": "pending"},
        ],
        room={"capacity": 30},
    )

    assert result["allowed"] is False
    assert result["occupied"] == 25
    assert result["total"] == 35


def test_capacity_guard_ignores_cancelled_and_rejected_bookings():
    guard = CapacityGuard()

    result = guard.check(
        incoming={"headcount": 10},
        existing=[
            {"headcount": 20, "status": "cancelled"},
            {"headcount": 15, "status": "rejected"},
            {"headcount": 10, "status": "accepted"},
        ],
        room={"capacity": 30},
    )

    assert result["allowed"] is True
    assert result["occupied"] == 10
    assert result["total"] == 20

