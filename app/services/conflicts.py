"""Same-slot conflict resolution using the Strategy pattern."""

from __future__ import annotations

from typing import Any

from app.services.conflict_strategy import (
    BookingData,
    ConflictResult,
    ConflictStrategy,
)

DEFAULT_CAPACITY = 30


def room_capacity(room: dict[str, Any] | None) -> int:
    if room is None:
        return DEFAULT_CAPACITY
    cap = room.get("capacity")
    if cap is None:
        return DEFAULT_CAPACITY
    return int(cap)


class EarlierRequestWinsStrategy(ConflictStrategy):
    """Prefer the earliest active request in a shared room/date slot."""

    def evaluate(
        self,
        *,
        incoming: BookingData,
        existing: list[BookingData],
        coordinator_override: bool = False,
        override_justification: str | None = None,
    ) -> ConflictResult:
        active = [
            booking
            for booking in existing
            if booking.get("status") in {"accepted", "pending"}
        ]

        if not active:
            return {
                "decision": "accept",
                "reason": "slot free",
                "override_used": False,
                "displace_ids": [],
                "policy": "earlier-request-wins",
            }

        ordered = sorted(
            active,
            key=lambda booking: str(booking.get("created_at") or ""),
        )
        champion = ordered[0]
        incoming_headcount = int(incoming.get("headcount", 0))
        champion_headcount = int(champion.get("headcount", 0))

        if (
            coordinator_override
            and incoming_headcount > champion_headcount
        ):
            result: ConflictResult = {
                "decision": "accept",
                "reason": "larger cohort coordinator override",
                "override_used": True,
                "displace_ids": [int(champion["id"])],
                "policy": "earlier-request-wins",
            }
            if override_justification is not None:
                result["override_justification"] = override_justification
            return result

        if incoming_headcount > champion_headcount:
            return {
                "decision": "reject",
                "reason": "larger cohort requires coordinator override",
                "override_used": False,
                "displace_ids": [],
                "policy": "earlier-request-wins",
            }

        return {
            "decision": "reject",
            "reason": "earlier request wins",
            "override_used": False,
            "displace_ids": [],
            "policy": "earlier-request-wins",
        }


# A descriptive alias for diagrams and callers that prefer the FCFS term.
FirstComeFirstServedStrategy = EarlierRequestWinsStrategy
EarlierRequestStrategy = EarlierRequestWinsStrategy


class ConflictResolver:
    """Context that applies a conflict strategy and room capacity policy."""

    def __init__(self, strategy: ConflictStrategy | None = None) -> None:
        self.strategy = strategy or EarlierRequestWinsStrategy()

    def set_strategy(self, strategy: ConflictStrategy) -> None:
        if not isinstance(strategy, ConflictStrategy):
            raise TypeError("strategy must implement ConflictStrategy")
        self.strategy = strategy

    def change_strategy(self, strategy: ConflictStrategy) -> None:
        self.set_strategy(strategy)

    def resolve(
        self,
        *,
        incoming: BookingData,
        existing: list[BookingData],
        room: BookingData | None = None,
        coordinator_override: bool = False,
        override_justification: str | None = None,
    ) -> ConflictResult:
        from app.services.capacity_guard import CapacityGuard

        result = self.strategy.evaluate(
            incoming=incoming,
            existing=existing,
            coordinator_override=coordinator_override,
            override_justification=override_justification,
        )

        if result["decision"] == "reject":
            return result

        displace_ids = set(result.get("displace_ids") or [])
        remaining = [
            booking
            for booking in existing
            if booking.get("id") not in displace_ids
        ]
        capacity = CapacityGuard().check(
            incoming=incoming,
            existing=remaining,
            room=room,
        )
        if not capacity["allowed"]:
            return {
                "decision": "reject",
                "reason": "room capacity exceeded",
                "override_used": False,
                "displace_ids": [],
                "policy": result.get("policy"),
            }

        return result

    evaluate = resolve
    resolve_slot_request = resolve


_default_resolver = ConflictResolver()


def resolve_slot_request(
    *,
    incoming: dict[str, Any],
    existing: list[dict[str, Any]],
    room: dict[str, Any] | None,
    coordinator_override: bool = False,
    override_justification: str | None = None,
) -> dict[str, Any]:
    """Compatibility entry point for the existing booking service."""
    return _default_resolver.resolve(
        incoming=incoming,
        existing=existing,
        room=room,
        coordinator_override=coordinator_override,
        override_justification=override_justification,
    )
