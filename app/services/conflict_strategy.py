"""Contract for same-slot booking conflict-resolution strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal, TypedDict


BookingData = dict[str, Any]
ConflictDecision = Literal["accept", "reject"]


class _RequiredConflictResult(TypedDict):
    """Required fields shared with the existing conflict resolver result."""

    decision: ConflictDecision
    reason: str
    override_used: bool
    displace_ids: list[int]


class ConflictResult(_RequiredConflictResult, total=False):
    """
    Evaluation result returned by a conflict-resolution strategy.

    `override_justification` and `policy` are optional audit metadata.
    """

    override_justification: str | None
    policy: str | None


class ConflictStrategy(ABC):
    """Abstract interface for evaluating booking conflicts."""

    @abstractmethod
    def evaluate(
        self,
        *,
        incoming: BookingData,
        existing: list[BookingData],
        coordinator_override: bool = False,
        override_justification: str | None = None,
    ) -> ConflictResult:
        """
        Evaluate an incoming booking against relevant existing conflicts.

        Args:
            incoming: The proposed booking dictionary.
            existing: Relevant conflicting booking dictionaries supplied by the
                calling service. This collection excludes cancelled and
                rejected bookings and excludes the incoming booking itself.
            coordinator_override: An explicitly requested and trusted
                coordinator override. This must not be inferred from an
                untrusted role or client input.
            override_justification: Optional trusted audit text describing why
                an authorized override was requested.

        Returns:
            A result containing `decision`, `reason`, `override_used`, and
            `displace_ids`. Optional metadata may include
            `override_justification` and `policy`.

        Responsibilities:
            Implementations evaluate conflict policy only. They must not
            validate room capacity, perform database queries or conflict
            detection, modify bookings, write to the database, approve a
            booking, or generate a confirmation code.

            An accepted strategy decision is not final coordinator approval or
            confirmation of a booking. A rejected result must use
            `override_used=False` and an empty `displace_ids` list.
        """
