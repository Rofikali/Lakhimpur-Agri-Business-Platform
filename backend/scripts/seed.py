### scripts/seed.py

# Run once: python scripts/seed.py
import asyncio
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from passlib.context import CryptContext
from core.config import settings

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEFAULT_PRODUCTS = [
    {
        "name": "Joha Rice",
        "slug": "joha-rice",
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
        "category": "petha",
        "unit": "pc",
        "sell_price": "60",
        "farm_cost": "15",
        "labor_cost": "7.5",
        "packaging_cost": "3.5",
    },
]


async def seed():
    from shared.models.base import Base
    from modules.auth.models import Owner
    from modules.products.models import Product
    from modules.inventory.models import InventoryStock

    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as db:
        db.add(
            Owner(
                username=settings.OWNER_USERNAME,
                password_hash=pwd_ctx.hash("changeme123"),
            )
        )
        for p in DEFAULT_PRODUCTS:
            money_fields = (
                "sell_price",
                "farm_cost",
                "labor_cost",
                "overhead_cost",
                "packaging_cost",
                "normal_loss_percent",
            )
            product = Product(**{k: Decimal(v) if k in money_fields else v for k, v in p.items()})
            db.add(product)
            await db.flush()
            db.add(InventoryStock(product_id=product.id, current_qty=Decimal("0")))
        await db.commit()
    print("✓ Seed complete. Login: admin / changeme123  ← change on first login")


if __name__ == "__main__":
    asyncio.run(seed())
