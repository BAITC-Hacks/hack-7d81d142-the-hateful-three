"""Readable console logging with structured HTTP request fields."""

import logging
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send


access_logger = logging.getLogger("backend.access")


def configure_logging() -> None:
    """Configure application logs once without replacing the server's handlers."""
    logger = logging.getLogger("backend")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s | "
            "method=%(method)s path=%(path)r status_code=%(status_code)s "
            "duration_ms=%(duration_ms)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            defaults={"method": "-", "path": "-", "status_code": "-", "duration_ms": "-"},
        ))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class RequestLoggingMiddleware:
    """Log completed HTTP requests, including failures and streaming responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = perf_counter()
        # Unhandled errors are converted to 500 by the outer ServerErrorMiddleware.
        status_code = 500

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            duration_ms = round((perf_counter() - started_at) * 1000, 3)
            if status_code >= 500:
                level = logging.ERROR
            elif status_code >= 400:
                level = logging.WARNING
            else:
                level = logging.INFO
            access_logger.log(
                level,
                "HTTP request completed",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
