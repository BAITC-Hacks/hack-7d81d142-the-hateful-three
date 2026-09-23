"""Shared ORM configuration and server-managed response fields.

Partial updates must be serialized with model_dump(exclude_unset=True) to
distinguish omitted fields from explicitly supplied null values.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EntityResponse(Schema):
    id: int
    created_at: datetime
    updated_at: datetime
