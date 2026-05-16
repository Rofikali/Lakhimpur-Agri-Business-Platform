# core / dependencies.py

from fastapi import Request, HTTPException, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.redis import is_token_blocked
from core.security import decode_token, get_token_from_request

# ── Auth dependency ───────────────────────────────────────────────────────────


async def require_owner(request: Request):
    """Use on all /dashboard and owner-only routes."""
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"error": "TOKEN_MISSING", "message": "Login required"},
        )
    payload = decode_token(token)
    # Check blocklist (logged-out tokens)
    jti = payload.get("jti", "")
    if jti and await is_token_blocked(jti):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"error": "TOKEN_BLOCKLISTED", "message": "Session expired"},
        )
    return payload


# ── DB + Redis dependencies ───────────────────────────────────────────────────


async def get_db_session() -> AsyncSession:
    async for session in get_db():
        yield session


# ── Exception handler registration ───────────────────────────────────────────

from shared.exceptions import AppException
import sentry_sdk


def register_exception_handlers(app) -> None:
    @app.exception_handler(AppException)
    async def app_exc_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error_code,
                "message": exc.message,
                "field": exc.field,
                "detail": exc.detail,
                "status": exc.status_code,
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(Exception)
    async def generic_exc_handler(request: Request, exc: Exception):
        sentry_sdk.capture_exception(exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "status": 500,
                "request_id": getattr(request.state, "request_id", None),
            },
        )


# ── Service factories ─────────────────────────────────────────────────────────
# Each wires a service with its repo + inter-module deps injected.
# Add new factories here as each module is built in Stage 6.

from modules.products.repository import ProductRepository
from modules.products.service import ProductService
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.orders.repository import OrderRepository
from modules.orders.service import OrderService
from modules.payments.service import PaymentService
from modules.notify.service import NotifyService


async def get_product_service(db: AsyncSession = Depends(get_db_session)) -> ProductService:
    return ProductService(repo=ProductRepository(db))


async def get_inventory_service(db: AsyncSession = Depends(get_db_session)) -> InventoryService:
    return InventoryService(repo=InventoryRepository(db))


async def get_order_service(db: AsyncSession = Depends(get_db_session)) -> OrderService:
    return OrderService(
        repo=OrderRepository(db),
        products=ProductService(repo=ProductRepository(db)),
        inventory=InventoryService(repo=InventoryRepository(db)),
        payments=PaymentService(),
        notify=NotifyService(),
    )
