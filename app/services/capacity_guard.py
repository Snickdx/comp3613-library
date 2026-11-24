
from typing import Any

from app.services.conflicts import room_capacity


class CapacityGuard:
    """Checks whether a room can accommodate an incoming booking."""

    def check(
        self,
        *,
        incoming: dict[str, Any],
        existing: list[dict[str, Any]],
        room: dict[str, Any] | None,
    ) -> dict[str, Any]:

        capacity = room_capacity(room)

        # Only accepted and pending bookings occupy room capacity.
        active_bookings = [
            booking
            for booking in existing
            if booking.get("status") in {"accepted", "pending"}
        ]

        # Calculate the total number of students already booked.
        occupied = sum(
            int(booking.get("headcount", 0))
            for booking in active_bookings
        )

        # Include the incoming booking.
        incoming_headcount = int(incoming.get("headcount", 0))
        total = occupied + incoming_headcount

        if total > capacity:
            return {
                "allowed": False,
                "reason": "room capacity exceeded",
                "occupied": occupied,
                "incoming": incoming_headcount,
                "total": total,
                "capacity": capacity,
            }

        return {
            "allowed": True,
            "reason": "room capacity available",
            "occupied": occupied,
            "incoming": incoming_headcount,
            "total": total,
            "capacity": capacity,
        }
