from typing import Any

from app.services.conflict_strategy import (
    BookingData,
    ConflictResult,
    ConflictStrategy,
)


class LargerCohortOverride(ConflictStrategy):
    """Allow an authorized coordinator to prefer a larger conflicting cohort."""

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
                "policy": "larger-cohort-override",
            }

        incoming_headcount = self._headcount(incoming)
        if incoming_headcount is None:
            return {
                "decision": "reject",
                "reason": "incoming booking has missing or invalid headcount",
                "override_used": False,
                "displace_ids": [],
                "policy": "larger-cohort-override",
            }

        existing_headcounts: list[int] = []
        for booking in active_existing:
            headcount = self._headcount(booking)
            if headcount is None:
                return {
                    "decision": "reject",
                    "reason": "existing booking has missing or invalid headcount",
                    "override_used": False,
                    "displace_ids": [],
                    "policy": "larger-cohort-override",
                }
            existing_headcounts.append(headcount)

        if not coordinator_override:
            return {
                "decision": "reject",
                "reason": "larger cohort requires coordinator override",
                "override_used": False,
                "displace_ids": [],
                "policy": "larger-cohort-override",
            }

        if (
            not isinstance(override_justification, str)
            or not override_justification.strip()
        ):
            return {
                "decision": "reject",
                "reason": "coordinator override requires justification",
                "override_used": False,
                "displace_ids": [],
                "policy": "larger-cohort-override",
            }

        if incoming_headcount <= max(existing_headcounts):
            return {
                "decision": "reject",
                "reason": "incoming cohort must be larger than every conflicting cohort",
                "override_used": False,
                "displace_ids": [],
                "policy": "larger-cohort-override",
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
                "policy": "larger-cohort-override",
            }

        result: ConflictResult = {
            "decision": "accept",
            "reason": "larger cohort coordinator override",
            "override_used": True,
            "displace_ids": [booking["id"] for booking in active_existing],
            "override_justification": override_justification.strip(),
            "policy": "larger-cohort-override",
        }
        return result

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
    def _headcount(booking: BookingData) -> int | None:
        value = booking.get("headcount")
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            return None
        return value

