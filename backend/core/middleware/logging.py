# core / middleware / logging.py

import json
import logging
import time
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from core.config import settings

logger = logging.getLogger("api")


# Configure structured JSON logging
def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper()),
        format="%(message)s",  # raw — we format as JSON ourselves
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs every HTTP request as structured JSON:
    {"timestamp":"...","level":"INFO","event":"http_request",
     "method":"GET","path":"/api/orders","status":200,
     "duration_ms":45,"request_id":"abc123"}
    """

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        ms = round((time.perf_counter() - start) * 1000, 2)

        log = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": "WARNING" if response.status_code >= 400 else "INFO",
            "event": "http_request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": ms,
            "request_id": getattr(request.state, "request_id", None),
        }
        level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(level, json.dumps(log))
        return response
