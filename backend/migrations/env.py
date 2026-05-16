# migrations / env.py
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from core.config import settings
from shared.models.base import Base

# Import ALL models so Alembic sees them
from modules.auth.models import Owner
from modules.products.models import Product
from modules.inventory.models import StockEntry, InventoryStock, MonthlyStock
from modules.orders.models import Order, OrderItem, Payment
from modules.farm.models import FarmSeason, FarmInput, FarmMilling
from modules.petha.models import PethaBatch, PethaBatchCost
from modules.finance.models import FixedCost, Asset
from modules.notify.models import Notification

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def run_migrations_offline():
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as conn:
        await conn.run_sync(
            lambda c: context.configure(
                connection=c,
                target_metadata=target_metadata,
                compare_type=True,
                render_as_batch=False,
            )
        )
        async with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
