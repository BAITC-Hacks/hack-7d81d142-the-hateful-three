"""Password hashing and strict, signed access-token validation."""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
import secrets
from typing import Any

import jwt
from passlib.context import CryptContext

from backend.core.config import settings


ALGORITHM = "HS256"
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__truncate_error=True)


class SecurityConfigurationError(RuntimeError):
    """Authentication cannot operate until a signing secret is configured."""


def _signing_key() -> str:
    if settings.jwt_secret_key is None:
        raise SecurityConfigurationError("JWT_SECRET_KEY is not configured")
    return settings.jwt_secret_key.get_secret_value()


def hash_password(password: str) -> str:
    if "\x00" in password or len(password.encode("utf-8")) > 72:
        raise ValueError("Password must not contain NUL or exceed 72 UTF-8 bytes")
    return password_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    if "\x00" in password or len(password.encode("utf-8")) > 72:
        return False
    try:
        return password_context.verify(password, hashed_password)
    except (ValueError, TypeError):
        return False


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """Use the same expensive password check for an unknown identity."""
    return hash_password(secrets.token_urlsafe(32))


def _valid_subject(subject: Any) -> bool:
    # Bound the value before conversion and before a PostgreSQL INTEGER lookup.
    return (
        isinstance(subject, str)
        and subject.isascii()
        and subject.isdecimal()
        and 1 <= len(subject) <= 10
        and not subject.startswith("0")
        and int(subject) <= 2_147_483_647
    )


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    """Sign an access token whose subject is the immutable database user ID."""
    if not _valid_subject(subject):
        raise ValueError("Token subject must be a positive user ID")
    now = datetime.now(timezone.utc)
    lifetime = (
        expires_delta if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    return jwt.encode(
        {"sub": subject, "iat": now, "exp": now + lifetime, "type": "access"},
        _signing_key(),
        algorithm=ALGORITHM,
    )


def verify_token(token: str) -> dict[str, Any]:
    """Validate signature, expiry, token purpose and the required claims.

    Invalid tokens raise jwt.InvalidTokenError; no unverified claims are used.
    """
    key = _signing_key()
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
        if (
            claims["type"] != "access"
            or not _valid_subject(claims["sub"])
            or type(claims["exp"]) is not int
            or type(claims["iat"]) is not int
            or claims["exp"] <= claims["iat"]
        ):
            raise jwt.InvalidTokenError("Invalid access token claims")
        return claims
    except (ValueError, TypeError, OverflowError) as exc:
        raise jwt.InvalidTokenError("Invalid access token") from exc
