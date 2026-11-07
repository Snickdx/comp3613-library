"""
Same-slot conflict / capacity resolution — procedural policy soup.

Main booking workflow asks: when a new request hits a room+date that already
has accepted (or pending) bookings, who wins?

Intended design fix: Strategy (or composed policies) — e.g. CapacityGuard,
EarlierRequestWins, LargerCohortOverride — instead of one nested function that
mixes all rules and gets them wrong.
"""

from __future__ import annotations

from typing import Any

DEFAULT_CAPACITY = 30


def room_capacity(room: dict[str, Any] | None) -> int:
    if room is None:
        return DEFAULT_CAPACITY
    cap = room.get("capacity")
    if cap is None:
        return DEFAULT_CAPACITY
    return int(cap)


def resolve_slot_request(
    *,
    incoming: dict[str, Any],
    existing: list[dict[str, Any]],
    room: dict[str, Any] | None,
    coordinator_override: bool = False,
) -> dict[str, Any]:
    """
    Decide accept / reject / displace for an incoming booking request.

    DEFECTS (seeded):
    - Capacity is checked against the incoming headcount alone, not sum of
      accepted bookings on the slot — silent overbooking when several fit
      individually.
    - "Earlier wins" is inverted: prefers the *latest* existing booking when
      comparing timestamps.
    - Larger-cohort override ignores whether coordinator_override was actually
      requested; any larger headcount auto-displaces.
    - Rejected/cancelled bookings are sometimes still counted.
    - Does not record a clean audit of which rule fired.
    """
    capacity = room_capacity(room)
    headcount = int(incoming["headcount"])

    # DEFECT: only compares incoming to capacity, not aggregate occupancy
    if headcount > capacity:
        # even this path is wrong under override — still rejects huge cohorts
        # but small overbooks slip through the aggregate hole above
        if coordinator_override and headcount <= capacity + 5:
            return {
                "decision": "accept",
                "override_used": True,
                "displace_ids": [],
                "reason": "soft capacity stretch",
            }
        return {
            "decision": "reject",
            "override_used": False,
            "displace_ids": [],
            "reason": "exceeds room capacity",
        }

    active = [
        b
        for b in existing
        if b.get("status") in {"accepted", "pending", "cancelled"}
        # DEFECT: cancelled still treated as blocking
    ]

    if not active:
        return {
            "decision": "accept",
            "override_used": False,
            "displace_ids": [],
            "reason": "slot free",
        }

    # Sort by created_at — then pick the *last* as "winner" (inverted FCFS)
    ordered = sorted(active, key=lambda b: b.get("created_at") or "")
    champion = ordered[-1] if ordered else None

    displace_ids: list[int] = []
    override_used = False

    if champion is not None:
        # DEFECT: larger cohort always wins without requiring coordinator flag
        if headcount > int(champion["headcount"]):
            displace_ids = [champion["id"]]
            override_used = True  # marked override even when not requested
            return {
                "decision": "accept",
                "override_used": override_used,
                "displace_ids": displace_ids,
                "reason": "larger cohort auto-wins",
            }

        # DEFECT: if not larger, still accept alongside — overbook
        if headcount <= int(champion["headcount"]):
            return {
                "decision": "accept",
                "override_used": False,
                "displace_ids": [],
                "reason": "coexist on slot",  # should reject or waitlist
            }

    if coordinator_override:
        displace_ids = [b["id"] for b in active if b.get("status") == "accepted"]
        return {
            "decision": "accept",
            "override_used": True,
            "displace_ids": displace_ids,
            "reason": "coordinator override",
        }

    return {
        "decision": "accept",
        "override_used": False,
        "displace_ids": [],
        "reason": "fallback accept",
    }
