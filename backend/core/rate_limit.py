"""Per-client limits for public authentication endpoints in the single-worker API."""

from slowapi import Limiter
from slowapi.util import get_remote_address


# Use the socket client address; proxy headers are only interpreted by Uvicorn
# when the connecting proxy is trusted. Buckets are local to each server process.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    headers_enabled=True,
)
