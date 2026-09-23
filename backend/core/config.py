"""Настройки из окружения и корневого .env (шаблон: .env.example)."""

from pathlib import Path

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
    cors_origins: list[str] = ["http://localhost:8501", "http://127.0.0.1:8501"]
    jwt_secret_key: SecretStr | None = None
    access_token_expire_minutes: int = Field(default=30, gt=0)

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 UTF-8 bytes")
        return value


settings = Settings()
