from datetime import datetime, timezone
from typing import Any

from app.services.conflict_strategy import (
    BookingData,
    ConflictResult,
    ConflictStrategy,
)


class FirstComeFirstServed(ConflictStrategy):
    """Resolve conflicts by giving priority to the earliest submission."""

    def evaluate(
        self,
        *,
        incoming: BookingData,
        existing: list[BookingData],
        coordinator_override: bool = False,
        override_justification: str | None = None,
    ) -> ConflictResult:
        incoming_id = incoming.get("id")
        active_existing = [
            booking
            for booking in existing
            if booking.get("status") in {"accepted", "pending"}
            and not self._is_incoming_booking(incoming, booking, incoming_id)
        ]

        if not active_existing:
            return {
                "decision": "accept",
                "reason": "slot free",
                "override_used": False,
                "displace_ids": [],
            }

        incoming_created_at = self._parse_timestamp(incoming.get("created_at"))
        if incoming_created_at is None:
            return {
                "decision": "reject",
                "reason": "incoming booking has missing or invalid created_at",
                "override_used": False,
                "displace_ids": [],
            }

        existing_timestamps: list[datetime] = []
        for booking in active_existing:
            created_at = self._parse_timestamp(booking.get("created_at"))
            if created_at is None:
                return {
                    "decision": "reject",
                    "reason": "existing booking has missing or invalid created_at",
                    "override_used": False,
                    "displace_ids": [],
                }
            existing_timestamps.append(created_at)

        earliest_existing = min(existing_timestamps)

        if incoming_created_at <= earliest_existing:
            if incoming_created_at == earliest_existing:
                earliest_bookings = [
                    booking
                    for booking, created_at in zip(active_existing, existing_timestamps)
                    if created_at == earliest_existing
                ]
                if any(
                    not isinstance(booking.get("id"), int)
                    or isinstance(booking.get("id"), bool)
                    for booking in earliest_bookings
                ):
                    return {
                        "decision": "reject",
                        "reason": "existing booking has missing or invalid id",
                        "override_used": False,
                        "displace_ids": [],
                    }

                incoming_id = incoming.get("id")
                if (
                    isinstance(incoming_id, int)
                    and not isinstance(incoming_id, bool)
                    and incoming_id < min(
                        booking["id"] for booking in earliest_bookings
                    )
                ):
                    if any(
                        not isinstance(booking.get("id"), int)
                        or isinstance(booking.get("id"), bool)
                        for booking in active_existing
                    ):
                        return {
                            "decision": "reject",
                            "reason": "existing booking has missing or invalid id",
                            "override_used": False,
                            "displace_ids": [],
                        }

                    return {
                        "decision": "accept",
                        "reason": "incoming booking has lower booking ID",
                        "override_used": False,
                        "displace_ids": [
                            booking["id"] for booking in active_existing
                        ],
                    }

                return {
                    "decision": "reject",
                    "reason": "existing booking has equal submission timestamp",
                    "override_used": False,
                    "displace_ids": [],
                }

            if any(
                not isinstance(booking.get("id"), int)
                or isinstance(booking.get("id"), bool)
                for booking in active_existing
            ):
                return {
                    "decision": "reject",
                    "reason": "existing booking has missing or invalid id",
                    "override_used": False,
                    "displace_ids": [],
                }

            displace_ids = [booking["id"] for booking in active_existing]
            return {
                "decision": "accept",
                "reason": "incoming booking submitted earlier",
                "override_used": False,
                "displace_ids": displace_ids,
            }

        return {
            "decision": "reject",
            "reason": "existing booking submitted earlier",
            "override_used": False,
            "displace_ids": [],
        }

    @staticmethod
    def _is_incoming_booking(
        incoming: BookingData,
        booking: BookingData,
        incoming_id: Any,
    ) -> bool:
        booking_id = booking.get("id")
        if incoming_id is not None and booking_id is not None:
            return incoming_id == booking_id
        return booking == incoming

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None

        timestamp = value.strip()
        if timestamp.endswith(("Z", "z")):
            timestamp = f"{timestamp[:-1]}+00:00"

        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)

        return parsed
