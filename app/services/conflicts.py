"""Same-slot conflict resolution using the Strategy pattern."""

from __future__ import annotations

from typing import Any

from app.services.conflict_strategy import (
    BookingData,
    ConflictResult,
    ConflictStrategy,
)
from app.services.first_come_first_served import FirstComeFirstServed
from app.services.larger_cohort_override import LargerCohortOverride

DEFAULT_CAPACITY = 30


def room_capacity(room: dict[str, Any] | None) -> int:
    if room is None:
        return DEFAULT_CAPACITY
    cap = room.get("capacity")
    if cap is None:
        return DEFAULT_CAPACITY
    return int(cap)


class CoordinatorOverrideStrategy(ConflictStrategy):
    """Apply FCFS first, then authorize larger-cohort overrides."""

    def __init__(self) -> None:
        self.fcfs = FirstComeFirstServed()
        self.larger_cohort = LargerCohortOverride()

    def evaluate(
        self,
        *,
        incoming: BookingData,
        existing: list[BookingData],
        coordinator_override: bool = False,
        override_justification: str | None = None,
    ) -> ConflictResult:
        fcfs_result = self.fcfs.evaluate(
            incoming=incoming,
            existing=existing,
            coordinator_override=coordinator_override,
            override_justification=override_justification,
        )

        if fcfs_result["decision"] == "accept":
            return fcfs_result

        if fcfs_result["reason"] not in {
            "existing booking submitted earlier",
            "existing booking has equal submission timestamp",
        }:
            return fcfs_result

        if not coordinator_override:
            return {
                "decision": "reject",
                "reason": "earlier request wins",
                "override_used": False,
                "displace_ids": [],
                "policy": "earlier-request-wins",
            }

        return self.larger_cohort.evaluate(
            incoming=incoming,
            existing=existing,
            coordinator_override=coordinator_override,
            override_justification=override_justification,
        )


# Compatibility aliases for existing callers.
EarlierRequestWinsStrategy = CoordinatorOverrideStrategy
FirstComeFirstServedStrategy = CoordinatorOverrideStrategy
EarlierRequestStrategy = CoordinatorOverrideStrategy
LargerCohortOverrideStrategy = LargerCohortOverride


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
