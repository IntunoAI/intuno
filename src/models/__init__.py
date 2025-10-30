"""Expose all models for easy importing."""
from src.models.base import BaseModel
from src.models.user import User

__all__ = ["BaseModel", "User"]
