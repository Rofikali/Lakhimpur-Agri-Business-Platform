### scripts/seed.py

# Run once: python scripts/seed.py
import asyncio
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from core.config import settings
from core.security import hash_password

DEFAULT_PRODUCTS = [
    {
        "name": "Joha Rice",
        "slug": "joha-rice",
        "starter_stock": "25.000",
        "category": "rice",
        "unit": "kg",
        "sell_price": "105",
        "farm_cost": "50",
        "labor_cost": "5",
        "overhead_cost": "3",
        "packaging_cost": "7",
        "normal_loss_percent": "33",
        "is_own_farm": True,
    },
    {
        "name": "Bora Saul",
        "slug": "bora-saul",
        "starter_stock": "25.000",
        "category": "rice",
        "unit": "kg",
        "sell_price": "90",
        "farm_cost": "50",
        "labor_cost": "5",
        "overhead_cost": "3",
        "packaging_cost": "7",
        "normal_loss_percent": "33",
        "is_own_farm": True,
    },
    {
        "name": "Kali Jeera",
        "slug": "kali-jeera",
        "starter_stock": "20.000",
        "category": "rice",
        "unit": "kg",
        "sell_price": "110",
        "farm_cost": "50",
        "labor_cost": "5",
        "overhead_cost": "3",
        "packaging_cost": "7",
        "normal_loss_percent": "33",
        "is_own_farm": True,
    },
    {
        "name": "Narikal Petha",
        "slug": "narikal-petha",
        "starter_stock": "50.000",
        "category": "petha",
        "unit": "pc",
        "sell_price": "70",
        "farm_cost": "18",
        "labor_cost": "7.5",
        "packaging_cost": "4",
    },
    {
        "name": "Septa Petha",
        "slug": "septa-petha",
        "starter_stock": "50.000",
        "category": "petha",
        "unit": "pc",
        "sell_price": "60",
        "farm_cost": "15",
        "labor_cost": "7.5",
        "packaging_cost": "3.5",
    },
]


async def seed():
    from modules.auth.models import Owner
    from modules.farm.models import FarmInput, FarmMilling, FarmSeason  # noqa: F401
    from modules.finance.models import Asset, FixedCost  # noqa: F401
    from modules.inventory.models import InventoryStock, MonthlyStock, StockEntry  # noqa: F401
    from modules.notify.models import Notification  # noqa: F401
    from modules.orders.models import Order, OrderItem, Payment  # noqa: F401
    from modules.petha.models import PethaBatch, PethaBatchCost  # noqa: F401
    from modules.products.models import Product
    from shared.models.base import Base

    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as db:
        owner = (
            await db.execute(select(Owner).where(Owner.username == settings.OWNER_USERNAME))
        ).scalar_one_or_none()
        if owner is None:
            db.add(
                Owner(
                    username=settings.OWNER_USERNAME,
                    password_hash=hash_password("changeme123"),
                )
            )

        for seed_product in DEFAULT_PRODUCTS:
            p = dict(seed_product)
            starter_stock = Decimal(p.pop("starter_stock"))
            money_fields = (
                "sell_price",
                "farm_cost",
                "labor_cost",
                "overhead_cost",
                "packaging_cost",
                "normal_loss_percent",
            )
            values = {k: Decimal(v) if k in money_fields else v for k, v in p.items()}
            product = (
                await db.execute(select(Product).where(Product.slug == values["slug"]))
            ).scalar_one_or_none()

            if product is None:
                product = Product(**values)
                db.add(product)
                await db.flush()
            else:
                for key, value in values.items():
                    setattr(product, key, value)
                product.is_active = True
                product.deleted_at = None

            stock = (
                await db.execute(
                    select(InventoryStock).where(InventoryStock.product_id == product.id)
                )
            ).scalar_one_or_none()
            if stock is None:
                db.add(InventoryStock(product_id=product.id, current_qty=starter_stock))
            elif stock.current_qty <= 0:
                stock.current_qty = starter_stock

        await db.commit()
    print("✓ Seed complete. Login: admin / changeme123. Catalog has starter stock.")


if __name__ == "__main__":
    asyncio.run(seed())
