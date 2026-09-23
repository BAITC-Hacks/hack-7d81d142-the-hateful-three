"""Reusable field types matching the scalar SQLAlchemy column constraints."""

from decimal import Decimal
from typing import Annotated

from pydantic import Field


Gid = Annotated[str, Field(max_length=32)]
KztAmount = Annotated[Decimal, Field(ge=0, max_digits=20, decimal_places=2)]
Score = Annotated[float, Field(ge=0, le=1)]
