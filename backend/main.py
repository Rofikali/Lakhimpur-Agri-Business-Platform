### main.py (FastAPI bootstrap)

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# from core.middleware import CorrelationMiddleware, RequestLoggingMiddleware
from core import CorrelationMiddleware, RequestLoggingMiddleware
from core.config import settings
from modules.auth.router import router as auth_router
from modules.farm.router import router as farm_router
from modules.inventory.router import router as inventory_router
from modules.notify.router import router as notify_router
from modules.orders.router import router as orders_router
from modules.payments.router import router as payments_router
from modules.petha.router import router as petha_router
from modules.pl_engine.router import router as pl_router
from modules.products.router import router as products_router

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        environment=settings.SENTRY_ENVIRONMENT,
    )

app = FastAPI(
    title="Lakhimpur Agri-Business API",
    version="1.0.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

# Middleware (order matters — first added = outermost)
app.add_middleware(CorrelationMiddleware)  # X-Request-ID
app.add_middleware(RequestLoggingMiddleware)  # structured JSON log
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.CORS_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["X-Idempotency-Key", "Content-Type", "X-Request-ID"],
)

limiter = Limiter(
    key_func=lambda req: req.client.host, default_limits=[f"{settings.RATE_LIMIT_PER_MIN}/minute"]
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

for r in [
    auth_router,
    products_router,
    inventory_router,
    orders_router,
    payments_router,
    pl_router,
    farm_router,
    petha_router,
    notify_router,
]:
    app.include_router(r)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/ready")
async def ready():
    from core.database import check_db
    from core.redis import check_redis

    await check_db()
    await check_redis()
    return {"status": "ready"}


@app.on_event("startup")
async def startup():
    from core.database import run_migrations

    await run_migrations()  # alembic upgrade head on every boot


# from fastapi import FastAPI

# app = FastAPI(
#     title="Lakhimpur Biz API",
#     version="0.1.0",
# )


# @app.get("/")
# async def root():
#     return {"message": "API Running"}


# @app.get("/health")
# async def health():
#     return {"status": "ok"}


# # Add these to the existing main.py from Stage 5:

# from core.dependencies import register_exception_handlers
# from core.scheduler import start_scheduler
# from modules.finance.router import router as finance_router

# # Include finance router alongside others:
# app.include_router(finance_router)

# # Register custom exception handlers:
# register_exception_handlers(app)


# # Start scheduler on startup:
# @app.on_event("startup")
# async def startup():
#     from core.database import run_migrations

#     await run_migrations()
#     start_scheduler(app)
