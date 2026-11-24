"""Same-slot conflict resolution using the Strategy pattern."""

from __future__ import annotations

from typing import Any

from app.services.conflict_strategy import (
    BookingData,
    ConflictResult,
    ConflictStrategy,
)
from app.services.first_come_first_served import FirstComeFirstServed

DEFAULT_CAPACITY = 30


def room_capacity(room: dict[str, Any] | None) -> int:
    if room is None:
        return DEFAULT_CAPACITY
    cap = room.get("capacity")
    if cap is None:
        return DEFAULT_CAPACITY
    return int(cap)


class CoordinatorOverrideStrategy(ConflictStrategy):
    """Adds justified larger-cohort overrides to first-come-first-served."""

    def __init__(self) -> None:
        self.base_strategy = FirstComeFirstServed()

    
    def evaluate(
        self,
        *,
        incoming: BookingData,
        existing: list[BookingData],
        coordinator_override: bool = False,
        override_justification: str | None = None,
    ) -> ConflictResult:

        result = self.base_strategy.evaluate(
            incoming=incoming,
            existing=existing,
        )

        # Preserve the existing ConflictResolver response wording.
        if result.get("reason") == "existing booking submitted earlier":
            result["reason"] = "earlier request wins"

        result.setdefault("policy", "first-come-first-served")

        active = [
            booking for booking in existing
            if booking.get("status") in {"accepted", "pending"}
        ]

        if not coordinator_override or not active:
            return result

        champion = min(
            active,
            key=lambda b: str(b.get("created_at") or ""),
        )

        if int(incoming.get("headcount", 0)) <= int(
            champion.get("headcount", 0)
        ):
            return result

        if result["decision"] == "accept":
            return result

        if not override_justification or not override_justification.strip():
            return {
                "decision": "reject",
                "reason": "override justification is required",
                "override_used": False,
                "displace_ids": [],
            }

        if not isinstance(champion.get("id"), int):
            return {
                "decision": "reject",
                "reason": "existing booking has missing or invalid id",
                "override_used": False,
                "displace_ids": [],
            }

        return {
            "decision": "accept",
            "reason": "larger cohort coordinator override",
            "override_used": True,
            "displace_ids": [champion["id"]],
            "override_justification": override_justification.strip(),
        }


# Backward compatibility with existing callers.
EarlierRequestWinsStrategy = CoordinatorOverrideStrategy
EarlierRequestStrategy = CoordinatorOverrideStrategy
FirstComeFirstServedStrategy = CoordinatorOverrideStrategy

class ConflictResolver:
    """Context that applies a conflict strategy and room capacity policy."""

    def __init__(self, strategy: ConflictStrategy | None = None) -> None:
        self.strategy = strategy or CoordinatorOverrideStrategy()

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
