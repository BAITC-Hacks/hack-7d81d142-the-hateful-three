"""Настройки из окружения и корневого .env (шаблон: .env.example)."""

from pathlib import Path

from limits import parse_many
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: str = "MoneyGraph AI"
    database_url: str = "postgresql+psycopg://postgres@localhost:5432/moneygraph"
    cors_origins: list[str] = [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:8501", "http://127.0.0.1:8501",
    ]
    jwt_secret_key: SecretStr | None = None
    access_token_expire_minutes: int = Field(default=30, gt=0)
    login_rate_limit: str = "10/minute"
    register_rate_limit: str = "5/minute"

    @field_validator("login_rate_limit", "register_rate_limit")
    @classmethod
    def validate_rate_limit(cls, value: str) -> str:
        limits = parse_many(value)
        if not limits or any(limit.amount <= 0 for limit in limits):
            raise ValueError("Rate limits must have a positive count and time window")
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 UTF-8 bytes")
        return value


settings = Settings()
