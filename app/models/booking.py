from typing import Optional

from sqlmodel import Field, SQLModel


class Booking(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    lecturer_id: int = Field(index=True)
    room_id: int = Field(index=True)
    course_code: str
    headcount: int
    preferred_date: str = Field(index=True)
    resources: str
    status: str
    override_used: int = 0
    confirmation_code: Optional[str] = Field(default=None, index=True)
    created_at: str