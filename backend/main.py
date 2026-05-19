from fastapi import FastAPI

app = FastAPI(
    title="Lakhimpur Biz API",
    version="0.1.0",
)


@app.get("/")
async def root():
    return {"message": "API Running"}


@app.get("/health")
async def health():
    return {"status": "ok"}


# Add these to the existing main.py from Stage 5:

from modules.finance.router import router as finance_router
from core.scheduler import start_scheduler
from core.dependencies import register_exception_handlers

# Include finance router alongside others:
app.include_router(finance_router)

# Register custom exception handlers:
register_exception_handlers(app)


# Start scheduler on startup:
@app.on_event("startup")
async def startup():
    from core.database import run_migrations

    await run_migrations()
    start_scheduler(app)
