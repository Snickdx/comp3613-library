
import pytest
from sqlmodel import Session, select

from app.models.booking import Booking
from app.models.room import Room
from app.services import bookings


@pytest.fixture
def validation_setup(test_engine, monkeypatch):

    # Use the isolated test database.
    monkeypatch.setattr(bookings, "default_engine", test_engine)

    # Simulate an authenticated lecturer.
    monkeypatch.setattr(
        bookings,
        "get_user",
        lambda lecturer_id: {"role": "lecturer"},
    )

    # Create a room for the booking request.
    with Session(test_engine) as session:
        room = Room(name="Validation Test Room", capacity=30)
        session.add(room)
        session.commit()
        session.refresh(room)
        room_id = room.id

    # Return valid booking information.
    return {
        "room_id": room_id,
        "course_code": "COMP3613",
        "headcount": 20,
        "preferred_date": "2099-12-01",
        "start_time": "09:00",
        "end_time": "11:00",
        "resources": "Projector",
    }


# Test missing and blank course codes.
@pytest.mark.parametrize("course_code", ["", "   ", None])
def test_invalid_course_code(validation_setup, course_code):

    validation_setup["course_code"] = course_code

    result = bookings.request_booking(1, **validation_setup)

    assert result["ok"] is False
    assert result["error"] == "course code is required"


# Test invalid headcount values.
@pytest.mark.parametrize("headcount", [0, -5, 15.5, "20", True, None])
def test_invalid_headcount(validation_setup, headcount):

    validation_setup["headcount"] = headcount

    result = bookings.request_booking(1, **validation_setup)

    assert result["ok"] is False
    assert result["error"] == "headcount must be a positive integer"


# Test missing dates, invalid dates and incorrect formats.
@pytest.mark.parametrize(
    "preferred_date",
    ["", None, "2026-02-30", "01/12/2026", "2026-13-01", "2026-1-5"],
)
def test_invalid_preferred_date(validation_setup, preferred_date):

    validation_setup["preferred_date"] = preferred_date

    result = bookings.request_booking(1, **validation_setup)

    assert result["ok"] is False
    assert result["error"] == "invalid preferred date"


# Test missing and blank resources.
@pytest.mark.parametrize("resources", ["", "   ", None])
def test_invalid_resources(validation_setup, resources):

    validation_setup["resources"] = resources

    result = bookings.request_booking(1, **validation_setup)

    assert result["ok"] is False
    assert result["error"] == "resources are required"


# Verify that existing time-range validation still works.
def test_invalid_workshop_time_range(validation_setup):

    validation_setup["start_time"] = "11:00"
    validation_setup["end_time"] = "09:00"

    result = bookings.request_booking(1, **validation_setup)

    assert result["ok"] is False
    assert result["error"] == "invalid workshop time range"


# Verify that invalid requests are not saved to the database.
def test_invalid_booking_not_saved(validation_setup, test_engine):

    validation_setup["course_code"] = ""

    result = bookings.request_booking(1, **validation_setup)

    assert result["ok"] is False

    with Session(test_engine) as session:
        rows = session.exec(select(Booking)).all()
        assert len(rows) == 0


# Verify that a valid booking request is accepted by the service.
def test_valid_booking_request(validation_setup):

    result = bookings.request_booking(1, **validation_setup)

    assert result["ok"] is True
    assert result["booking"]["course_code"] == "COMP3613"
    assert result["booking"]["headcount"] == 20
    assert result["booking"]["preferred_date"] == "2099-12-01"
    assert result["booking"]["resources"] == "Projector"
