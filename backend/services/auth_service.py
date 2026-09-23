"""Credential registration and verification within the request transaction."""

from backend.core.security import dummy_password_hash, verify_password
from backend.models.user import User
from backend.repositories.user_repository import UserRepository
from backend.schemas.auth import RegisterRequest
from backend.services.user_service import UserService


class AuthService:
    def __init__(self, repository: UserRepository) -> None:
        self.users = UserService(repository)

    def register(self, data: RegisterRequest) -> User:
        return self.users.create(data)

    def authenticate(self, email: str, password: str) -> User | None:
        user = self.users.get_by_email(email)
        stored_hash = user.hashed_password if user is not None else dummy_password_hash()
        valid = verify_password(password, stored_hash)
        return user if valid else None
