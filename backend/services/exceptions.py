"""Application errors independent of any HTTP framework or status codes."""

from typing import Any


class ServiceError(Exception):
    """Base class for errors a caller can translate for its own interface."""


class NotFoundError(ServiceError):
    def __init__(self, entity: str, identifier: Any) -> None:
        self.entity = entity
        self.identifier = identifier
        super().__init__(f"{entity} not found: {identifier!r}")


class ConflictError(ServiceError):
    """Duplicate business keys or a change blocked by existing references."""


class ValidationError(ServiceError):
    """Invalid input or an inconsistent combination of business fields."""
