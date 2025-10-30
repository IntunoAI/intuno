"""User model."""

from sqlalchemy import Column, String

from .base import BaseModel


class User(BaseModel):
    """Represents a user in the system."""

    __tablename__: str = "users"

    first_name: Column[str] = Column(String, nullable=True)
    last_name: Column[str] = Column(String, nullable=True)
    phone_number: Column[str] = Column(String, nullable=True, unique=True)
    # etc, more fields can be added as needed
