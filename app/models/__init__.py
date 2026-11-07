"""Database table models.

Import every table model here so ``SQLModel.metadata.create_all`` sees them.
"""

from app.models.booking import Booking
from app.models.room import Room
from app.models.user import User

__all__ = ["User", "Room", "Booking"]