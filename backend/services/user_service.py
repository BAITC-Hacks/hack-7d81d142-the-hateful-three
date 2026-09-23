"""User account rules; the caller owns the repository's transaction."""

from pydantic import ValidationError as SchemaValidationError
from sqlalchemy.exc import IntegrityError

from backend.core.security import hash_password
from backend.models import User
from backend.repositories.user_repository import UserRepository
from backend.schemas.user import UserCreate
from backend.services.exceptions import ConflictError, NotFoundError, ValidationError


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    def get_by_id(self, user_id: int) -> User:
        user = self.repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User", user_id)
        return user

    def get_by_email(self, email: str) -> User | None:
        return self.repository.get_by_email(email.strip().lower())

    def create(self, data: UserCreate) -> User:
        try:
            data = UserCreate.model_validate(data.model_dump())
        except SchemaValidationError as exc:
            # Avoid including credentials in service errors or HTTP responses.
            raise ValidationError("Invalid user registration data") from exc
        if self.get_by_email(str(data.email)) is not None:
            raise ConflictError("Email is already registered")
        try:
            return self.repository.create({
                "email": str(data.email),
                "hashed_password": hash_password(data.password.get_secret_value()),
            })
        except IntegrityError as exc:
            # The unique constraint covers races between concurrent requests.
            raise ConflictError("Email is already registered") from exc
