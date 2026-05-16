# from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
# from core.config import settings

# engine = create_async_engine(
#     settings.DATABASE_URL,
#     pool_size=settings.DATABASE_POOL_SIZE,
#     max_overflow=settings.DATABASE_MAX_OVERFLOW,
#     echo=settings.DEBUG,
# )

# AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


# async def get_db():
#     async with AsyncSessionLocal() as session:
#         yield session


# async def check_db():
#     async with engine.connect() as conn:
#         await conn.execute(text("SELECT 1"))


# async def run_migrations():
#     from alembic.config import Config
#     from alembic import command

#     cfg = Config("alembic.ini")
#     command.upgrade(cfg, "head")

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def close_db():
    await engine.dispose()
