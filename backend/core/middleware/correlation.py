# ore / middleware / correlation.py

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class CorrelationMiddleware(BaseHTTPMiddleware):
    """
    Attaches a unique request_id to every request.
    Returned in X-Request-ID response header.
    Owner can share this ID when reporting a bug.
    All log lines for that request include it.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response



