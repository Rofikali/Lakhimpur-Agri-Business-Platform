import uuid

from modules.inventory.models import InventoryStock
from modules.products.models import Product
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class ProductRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_active(self) -> list[Product]:
        result = await self.db.execute(
            select(Product)
            .where(Product.is_active == True, Product.deleted_at.is_(None))
            .order_by(Product.category, Product.name)
        )
        return list(result.scalars().all())

    async def get_all(self) -> list[Product]:
        """Owner sees all including inactive."""
        result = await self.db.execute(
            select(Product)
            .where(Product.deleted_at.is_(None))
            .order_by(Product.category, Product.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, product_id: uuid.UUID) -> Product | None:
        result = await self.db.execute(
            select(Product).where(Product.id == product_id, Product.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Product | None:
        result = await self.db.execute(
            select(Product).where(Product.slug == slug, Product.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Product:
        product = Product(**kwargs)
        self.db.add(product)
        await self.db.flush()
        await self.db.refresh(product)
        return product

    async def update(self, product: Product) -> Product:
        self.db.add(product)
        await self.db.flush()
        await self.db.refresh(product)
        return product

    async def get_stock(self, product_id: uuid.UUID) -> InventoryStock | None:
        result = await self.db.execute(
            select(InventoryStock).where(InventoryStock.product_id == product_id)
        )
        return result.scalar_one_or_none()
