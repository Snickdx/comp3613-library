from copy import deepcopy

import pytest

from app.services.conflict_strategy import (
    BookingData,
    ConflictResult,
    ConflictStrategy,
)


class DummyAcceptStrategy(ConflictStrategy):
    def evaluate(
        self,
        *,
        incoming: BookingData,
        existing: list[BookingData],
        coordinator_override: bool = False,
        override_justification: str | None = None,
    ) -> ConflictResult:
        return {
            "decision": "accept",
            "reason": "dummy policy accepts",
            "override_used": coordinator_override,
            "displace_ids": [booking["id"] for booking in existing],
            "override_justification": override_justification,
            "policy": "dummy",
        }


class DummyRejectStrategy(ConflictStrategy):
    def evaluate(
        self,
        *,
        incoming: BookingData,
        existing: list[BookingData],
        coordinator_override: bool = False,
        override_justification: str | None = None,
    ) -> ConflictResult:
        return {
            "decision": "reject",
            "reason": "dummy policy rejects",
            "override_used": False,
            "displace_ids": [],
            "policy": "dummy",
        }


def test_conflict_strategy_is_abstract():
    with pytest.raises(TypeError):
        ConflictStrategy()


def test_dummy_strategy_accept_contract_and_receives_override_metadata():
    incoming = {"id": 20, "headcount": 25, "status": "pending"}
    existing = [{"id": 10, "headcount": 20, "status": "accepted"}]
    incoming_before = deepcopy(incoming)
    existing_before = deepcopy(existing)

    result: ConflictResult = DummyAcceptStrategy().evaluate(
        incoming=incoming,
        existing=existing,
        coordinator_override=True,
        override_justification="larger cohort approved",
    )

    assert result["decision"] == "accept"
    assert result["reason"]
    assert result["override_used"] is True
    assert result["displace_ids"] == [10]
    assert result["override_justification"] == "larger cohort approved"
    assert result["policy"] == "dummy"
    assert incoming == incoming_before
    assert existing == existing_before


def test_dummy_strategy_reject_contract_has_no_displacement_or_override():
    result = DummyRejectStrategy().evaluate(
        incoming={"id": 20, "headcount": 10},
        existing=[{"id": 10, "headcount": 15, "status": "accepted"}],
    )

    assert result["decision"] == "reject"
    assert result["reason"]
    assert result["override_used"] is False
    assert result["displace_ids"] == []


def test_optional_metadata_may_be_omitted():
    result = DummyRejectStrategy().evaluate(
        incoming={"id": 20, "headcount": 10},
        existing=[],
    )

    assert "override_justification" not in result
