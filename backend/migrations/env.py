# migrations/env.py
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from core.config import settings

# Import all models so Alembic sees metadata.
from modules.auth.models import Owner  # noqa: F401
from modules.farm.models import FarmInput, FarmMilling, FarmSeason  # noqa: F401
from modules.finance.models import Asset, FixedCost  # noqa: F401
from modules.inventory.models import InventoryStock, MonthlyStock, StockEntry  # noqa: F401
from modules.notify.models import Notification  # noqa: F401
from modules.orders.models import Order, OrderItem, Payment  # noqa: F401
from modules.petha.models import PethaBatch, PethaBatchCost  # noqa: F401
from modules.products.models import Product  # noqa: F401
from shared.models.base import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
