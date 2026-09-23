"""Public registration/login and the authenticated user profile."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from backend.api.dependencies import CurrentUser, credentials_exception, get_auth_service
from backend.core.security import create_access_token
from backend.schemas.auth import LoginRequest, RegisterRequest, RegistrationResponse, TokenResponse
from backend.schemas.user import UserResponse
from backend.services.auth_service import AuthService


router = APIRouter(prefix="/auth", tags=["auth"])
AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


@router.post("/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, service: AuthServiceDependency) -> RegistrationResponse:
    user = service.register(data)
    return RegistrationResponse(
        **UserResponse.model_validate(user).model_dump(),
        access_token=create_access_token(str(user.id)),
    )


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, service: AuthServiceDependency) -> TokenResponse:
    user = service.authenticate(str(data.email), data.password.get_secret_value())
    if user is None:
        raise credentials_exception()
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser):
    return user
