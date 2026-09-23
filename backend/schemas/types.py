"""Reusable field types matching the scalar SQLAlchemy column constraints."""

from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, Field


def require_numeric_evidence(value: str) -> str:
    if not value.strip() or not any(character.isdecimal() for character in value):
        raise ValueError("evidence must contain a nonblank explanation with a numeric value")
    return value


Gid = Annotated[str, Field(max_length=32)]
KztAmount = Annotated[Decimal, Field(ge=0, max_digits=20, decimal_places=2)]
Score = Annotated[float, Field(ge=0, le=1)]
Evidence = Annotated[str, Field(min_length=1, max_length=200), AfterValidator(require_numeric_evidence)]
