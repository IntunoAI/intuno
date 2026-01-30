"""Expose base model only. Domain models added later."""

from agents.models.base import Base, BaseModel

__all__ = ["Base", "BaseModel"]
