from app.services.conflict_strategy import ConflictStrategy
from app.services.conflicts import (
    ConflictResolver,
    EarlierRequestWinsStrategy,
    resolve_slot_request,
)


def test_resolver_accepts_free_slot():
    result = resolve_slot_request(
        incoming={"id": 2, "headcount": 20},
        existing=[],
        room={"capacity": 30},
    )

    assert result["decision"] == "accept"
    assert result["override_used"] is False
    assert result["displace_ids"] == []


def test_resolver_rejects_when_earlier_request_wins():
    result = resolve_slot_request(
        incoming={"id": 2, "headcount": 15, "created_at": "2026-02-02"},
        existing=[
            {
                "id": 1,
                "headcount": 20,
                "status": "accepted",
                "created_at": "2026-02-01",
            }
        ],
        room={"capacity": 30},
    )

    assert result["decision"] == "reject"
    assert result["reason"] == "earlier request wins"
    assert result["override_used"] is False
    assert result["displace_ids"] == []


def test_resolver_requires_override_for_larger_cohort():
    existing = [
        {
            "id": 1,
            "headcount": 20,
            "status": "accepted",
            "created_at": "2026-02-01",
        }
    ]
    incoming = {"id": 2, "headcount": 25}

    rejected = resolve_slot_request(
        incoming=incoming,
        existing=existing,
        room={"capacity": 30},
    )
    accepted = resolve_slot_request(
        incoming=incoming,
        existing=existing,
        room={"capacity": 30},
        coordinator_override=True,
        override_justification="larger cohort approved",
    )

    assert rejected["decision"] == "reject"
    assert rejected["override_used"] is False
    assert accepted["decision"] == "accept"
    assert accepted["override_used"] is True
    assert accepted["displace_ids"] == [1]
    assert accepted["override_justification"] == "larger cohort approved"


def test_resolver_never_accepts_capacity_overbook():
    result = resolve_slot_request(
        incoming={"id": 2, "headcount": 35},
        existing=[
            {
                "id": 1,
                "headcount": 20,
                "status": "accepted",
                "created_at": "2026-02-01",
            }
        ],
        room={"capacity": 30},
        coordinator_override=True,
        override_justification="Approved larger cohort",
    )

    assert result["decision"] == "reject"
    assert result["reason"] == "room capacity exceeded"
    assert result["override_used"] is False
    assert result["displace_ids"] == []


def test_resolver_can_switch_strategy():
    class AlwaysAccept(ConflictStrategy):
        def evaluate(
            self,
            *,
            incoming,
            existing,
            coordinator_override=False,
            override_justification=None,
        ):
            return {
                "decision": "accept",
                "reason": "test strategy",
                "override_used": False,
                "displace_ids": [],
                "policy": "test",
            }

    resolver = ConflictResolver(EarlierRequestWinsStrategy())
    resolver.set_strategy(AlwaysAccept())

    result = resolver.resolve(
        incoming={"headcount": 10},
        existing=[],
        room={"capacity": 30},
    )

    assert result["decision"] == "accept"
    assert result["policy"] == "test"