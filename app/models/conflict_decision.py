from typing import Optional

from sqlmodel import Field, SQLModel


class ConflictDecision(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    booking_id: Optional[int] = Field(default=None, index=True)
    lecturer_id: int = Field(index=True)
    room_id: int = Field(index=True)
    course_code: str
    headcount: int
    preferred_date: str
    start_time: str
    end_time: str
    decision: str
    policy: Optional[str] = None
    reason: str
    stage: str
    booking_status: Optional[str] = None
    coordinator_id: Optional[int] = None
    override_authorized: bool = False
    override_used: bool = False
    override_justification: Optional[str] = None
    related_booking_id: Optional[int] = None
    created_at: str