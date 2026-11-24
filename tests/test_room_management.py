import json

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlmodel import Session
from starlette.requests import Request

from app.dependencies.auth import is_admin_dep
from app.main import unauthorized_redirect_handler
from app.models.room import Room
from app.models.user import User
from app.routers.library import (
    RoomUpdateBody,
    admin_room,
    admin_rooms,
    router,
    update_admin_room,
)
from app.services import rooms


def _create_room(
    engine,
    *,
    name: str = "Workshop A",
    capacity: int | None = 24,
) -> Room:
    with Session(engine) as session:
        room = Room(name=name, capacity=capacity)
        session.add(room)
        session.commit()
        session.refresh(room)
        return room


def _admin_user(role: str = "admin") -> User:
    return User(
        username=f"{role}-user",
        email=f"{role}@example.com",
        password="hashed-password",
        role=role,
    )


def test_admin_room_listing_exposes_effective_default_capacity(
    test_engine,
    monkeypatch,
):
    monkeypatch.setattr(rooms, "default_engine", test_engine)
    _create_room(test_engine, name="Default room", capacity=None)
    _create_room(test_engine, name="Custom room", capacity=18)

    listed = rooms.list_rooms()

    by_name = {room["name"]: room for room in listed}
    assert by_name["Default room"]["capacity"] is None
    assert by_name["Default room"]["effective_capacity"] == 30
    assert by_name["Custom room"]["effective_capacity"] == 18


def test_admin_can_get_and_update_room_configuration(
    test_engine,
    monkeypatch,
):
    monkeypatch.setattr(rooms, "default_engine", test_engine)
    room = _create_room(test_engine)
    admin = _admin_user()

    assert admin_rooms(admin)["rooms"][0]["id"] == room.id
    assert admin_room(room.id, admin)["room"]["name"] == "Workshop A"

    result = update_admin_room(
        room.id,
        RoomUpdateBody(name="  Workshop C  ", capacity=32),
        admin,
    )

    assert result["ok"] is True
    assert result["room"]["name"] == "Workshop C"
    assert result["room"]["capacity"] == 32
    assert result["room"]["effective_capacity"] == 32


def test_setting_capacity_to_null_restores_default_capacity(
    test_engine,
    monkeypatch,
):
    monkeypatch.setattr(rooms, "default_engine", test_engine)
    room = _create_room(test_engine, capacity=18)

    result = rooms.update_room(room.id, {"capacity": None})

    assert result["ok"] is True
    assert result["room"]["capacity"] is None
    assert result["room"]["effective_capacity"] == 30


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": None},
        {"name": "   "},
        {"capacity": 0},
        {"capacity": -2},
        {"capacity": True},
        {"capacity": 16.5},
        {"capacity": "16"},
        {"unknown": "value"},
    ],
)
def test_room_update_rejects_invalid_payloads(payload):
    with pytest.raises(ValidationError):
        RoomUpdateBody(**payload)


def test_duplicate_room_name_is_rejected_without_changing_room(
    test_engine,
    monkeypatch,
):
    monkeypatch.setattr(rooms, "default_engine", test_engine)
    room = _create_room(test_engine, name="Workshop A")
    _create_room(test_engine, name="Workshop B")

    result = rooms.update_room(room.id, {"name": "Workshop B"})

    assert result == {"ok": False, "error": "room name already exists"}
    assert rooms.get_room(room.id)["name"] == "Workshop A"


def test_unknown_room_returns_not_found(test_engine, monkeypatch):
    monkeypatch.setattr(rooms, "default_engine", test_engine)

    result = rooms.update_room(999, {"capacity": 12})

    assert result == {"ok": False, "error": "room not found"}


def test_only_administrators_pass_the_room_management_role_check():
    admin = _admin_user("admin")
    lecturer = _admin_user("lecturer")

    assert is_admin_dep(admin) is admin
    with pytest.raises(HTTPException) as exc_info:
        is_admin_dep(lecturer)

    assert exc_info.value.status_code == 403


def test_all_admin_room_routes_use_admin_dependency():
    admin_routes = [
        route
        for route in router.routes
        if route.path.startswith("/admin/rooms")
    ]

    assert len(admin_routes) == 3
    assert all(
        any(
            dependency.call is is_admin_dep
            for dependency in route.dependant.dependencies
        )
        for route in admin_routes
    )


def test_unauthenticated_api_requests_keep_json_401_response():
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/admin/rooms",
            "raw_path": b"/api/admin/rooms",
            "query_string": b"",
            "headers": [],
            "server": ("test", 80),
            "client": ("test", 123),
        }
    )

    response = unauthorized_redirect_handler(
        request,
        HTTPException(status_code=401, detail="authentication required"),
    )

    assert response.status_code == 401
    assert json.loads(response.body) == {
        "detail": "authentication required"
    }


def test_missing_room_details_return_not_found():
    with pytest.raises(HTTPException) as exc_info:
        admin_room(999, _admin_user())

    assert exc_info.value.status_code == 404
