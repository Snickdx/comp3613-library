
from app.services.bookings import _valid_time_range, _times_overlap


def test_valid_time_range():
    assert _valid_time_range("09:00", "10:00")


def test_invalid_time_range():
    assert not _valid_time_range("14:00", "13:00")
    assert not _valid_time_range("10:00", "10:00")
    assert not _valid_time_range("9:00", "10:00")


def test_overlapping_times():
    assert _times_overlap("09:00", "11:00", "10:00", "12:00")


def test_time_ranges_inside_each_other():
    assert _times_overlap("09:00", "12:00", "10:00", "11:00")


def test_non_overlapping_times():
    assert not _times_overlap("09:00", "10:00", "11:00", "12:00")


def test_back_to_back_times():
    assert not _times_overlap("09:00", "10:00", "10:00", "11:00")
