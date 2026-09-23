"""JSON authentication requests and responses without password disclosure."""

from typing import Literal

from pydantic import BaseModel

from backend.schemas.user import UserCreate, UserCredentials, UserResponse


class LoginRequest(UserCredentials):
    pass


class RegisterRequest(UserCreate):
    pass


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class RegistrationResponse(UserResponse, TokenResponse):
    """Preserve account fields and also authenticate the newly registered user."""
