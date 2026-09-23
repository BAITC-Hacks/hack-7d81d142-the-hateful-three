"""Запуск: python -m uvicorn backend.main:app --reload --no-access-log."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api import router
from backend.core.config import settings
from backend.core.logging import RequestLoggingMiddleware, configure_logging
from backend.core.security import SecurityConfigurationError
from backend.services.exceptions import ConflictError, NotFoundError, ValidationError


configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)
# Added last so even CORS preflight responses pass through request logging.
app.add_middleware(RequestLoggingMiddleware)
app.include_router(router)


@app.exception_handler(SecurityConfigurationError)
async def security_configuration_error_handler(
    request: Request, exc: SecurityConfigurationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Authentication is not configured"},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    if request.url.path in {"/auth/register", "/auth/login"}:
        # FastAPI normally echoes rejected input, including plaintext passwords.
        errors = [{key: value for key, value in error.items() if key not in {"input", "ctx"}}
                  for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(NotFoundError)
async def not_found_error_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
async def conflict_error_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


@app.exception_handler(ValidationError)
async def service_validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception",
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"method": request.method, "path": request.url.path, "status_code": 500},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Проверка доступности HTTP-сервера."""
    return {"status": "ok"}
