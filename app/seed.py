"""Seed demo users, rooms, and a sample booking for the library scenario."""

from __future__ import annotations

from sqlmodel import Session, select

from app.database import drop_all, ensure_db_and_tables, engine
from app.models.booking import Booking
from app.models.room import Room
from app.models.user import User
from app.utilities.security import encrypt_password

USERS = [
    # username, email, password, role, display_name
    ("coord", "coord@example.com", "coord-dev", "coordinator", "Library Coordinator"),
    ("admin", "admin@example.com", "admin-dev", "admin", "Library Admin"),
    ("lecturer1", "lecturer1@example.com", "lect-dev", "lecturer", "Dr. Alice"),
    ("lecturer2", "lecturer2@example.com", "lect-dev", "lecturer", "Dr. Bob"),
]

ROOMS = [
    ("Workshop A", 30),
    ("Workshop B", None),  # uses default capacity 30
    ("Seminar Pod", 12),
]


def seed(*, reset: bool = False) -> None:
    import app.models  # noqa: F401

    if reset:
        try:
            drop_all()
        except Exception:
            pass
    ensure_db_and_tables()

    with Session(engine) as session:
        existing = session.exec(select(User)).first()
        if existing and not reset:
            return

        for username, email, password, role, display_name in USERS:
            session.add(
                User(
                    username=username,
                    email=email,
                    password=encrypt_password(password),
                    role=role,
                    display_name=display_name,
                )
            )
        for name, capacity in ROOMS:
            session.add(Room(name=name, capacity=capacity))
        session.commit()

        lect1 = session.exec(
            select(User).where(User.email == "lecturer1@example.com")
        ).one()
        room_a = session.exec(select(Room).where(Room.name == "Workshop A")).one()

        session.add(
            Booking(
                lecturer_id=lect1.id,
                room_id=room_a.id,
                course_code="COMP3613",
                headcount=20,
                preferred_date="2099-03-15",
                resources="databases intro",
                status="accepted",
                override_used=0,
                confirmation_code="CONF-SEED01",
                created_at="2099-01-01T10:00:00+00:00",
            )
        )
        session.commit()


if __name__ == "__main__":
    seed(reset=True)
    print("Seeded library scenario data")
