"""User credentials, account creation and safe ORM responses."""

from pydantic import ConfigDict, EmailStr, Field, SecretStr, field_validator

from backend.schemas.base import EntityResponse, Schema


class UserCredentials(Schema):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if "\x00" in password or len(password.encode("utf-8")) > 72:
            raise ValueError("Password must not contain NUL or exceed 72 UTF-8 bytes")
        return value


class UserCreate(UserCredentials):
    password: SecretStr = Field(min_length=8, max_length=72)


class UserResponse(EntityResponse):
    email: str
