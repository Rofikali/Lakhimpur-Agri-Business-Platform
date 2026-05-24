import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from modules.inventory.models import InventoryStock
from modules.products.models import Product

from core.redis import cache_delete
from modules.products.repository import ProductRepository
from modules.products.schemas import ProductCreate, ProductUpdate
from shared.exceptions import ProductInactiveError, ProductNotFoundError


def _calculate_true_cost(
    farm_cost: Decimal,
    labor_cost: Decimal,
    overhead_cost: Decimal,
    packaging_cost: Decimal,
    normal_loss_percent: Decimal,
) -> Decimal:
    """
    True cost per unit including normal loss absorption.
    Normal loss is absorbed: if 33% loss, 1kg chawl needs 1.49kg dhan.
    loss_absorb = farm_cost * (loss% / (1 - loss%))
    """
    ZERO = Decimal("0")
    if normal_loss_percent >= Decimal("100"):
        return Decimal("99999.99999")  # invalid — protect against div/0
    loss_pct = normal_loss_percent / Decimal("100")
    loss_absorb = farm_cost * loss_pct / (Decimal("1") - loss_pct) if loss_pct > ZERO else ZERO
    return farm_cost + loss_absorb + labor_cost + overhead_cost + packaging_cost


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")


class ProductService:
    def __init__(self, repo: ProductRepository):
        self.repo = repo

    async def list_products(self, owner: bool = False) -> list[dict]:
        products = await (self.repo.get_all() if owner else self.repo.get_all_active())
        result = []
        for p in products:
            stock = await self.repo.get_stock(p.id)
            result.append(self._to_response_dict(p, stock))
        return result

    async def get_product(self, product_id: uuid.UUID) -> dict:
        product = await self.repo.get_by_id(product_id)
        if not product:
            raise ProductNotFoundError(str(product_id))
        stock = await self.repo.get_stock(product.id)
        return self._to_response_dict(product, stock)

    async def get_active(self, product_id: uuid.UUID) -> Product:
        product = await self.repo.get_by_id(product_id)
        if not product:
            raise ProductNotFoundError(str(product_id))
        if not product.is_active:
            raise ProductInactiveError(product.name)
        return product

    async def create_product(self, data: ProductCreate) -> dict:
        true_cost = _calculate_true_cost(
            data.farm_cost,
            data.labor_cost,
            data.overhead_cost,
            data.packaging_cost,
            data.normal_loss_percent,
        )
        slug = _slugify(data.name)

        product = await self.repo.create(
            name=data.name,
            slug=slug,
            category=data.category,
            unit=data.unit,
            sell_price=data.sell_price,
            farm_cost=data.farm_cost,
            labor_cost=data.labor_cost,
            overhead_cost=data.overhead_cost,
            packaging_cost=data.packaging_cost,
            normal_loss_percent=data.normal_loss_percent,
            true_cost=true_cost,
            is_own_farm=data.is_own_farm,
            low_stock_threshold=data.low_stock_threshold,
        )
        # Create inventory_stock row
        stock = InventoryStock(product_id=product.id, current_qty=Decimal("0"))
        self.repo.db.add(stock)
        await self.repo.db.flush()

        await cache_delete("products:list:active")
        return self._to_response_dict(product, stock)

    async def update_product(self, product_id: uuid.UUID, data: ProductUpdate) -> dict:
        product = await self.repo.get_by_id(product_id)
        if not product:
            raise ProductNotFoundError(str(product_id))

        for field, val in data.model_dump(exclude_none=True).items():
            setattr(product, field, val)

        # Recalculate true_cost if any cost field changed
        product.true_cost = _calculate_true_cost(
            product.farm_cost,
            product.labor_cost,
            product.overhead_cost,
            product.packaging_cost,
            product.normal_loss_percent,
        )

        await self.repo.update(product)
        await cache_delete("products:list:active")
        await cache_delete(f"products:detail:{product.slug}")

        stock = await self.repo.get_stock(product.id)
        return self._to_response_dict(product, stock)

    async def soft_delete(self, product_id: uuid.UUID) -> None:
        product = await self.repo.get_by_id(product_id)
        if not product:
            raise ProductNotFoundError(str(product_id))
        product.deleted_at = datetime.now(UTC)
        product.is_active = False
        await self.repo.update(product)
        await cache_delete("products:list:active")

    def _to_response_dict(self, p: Product, stock: InventoryStock | None) -> dict:
        margin = p.sell_price - p.true_cost
        margin_pct = (margin / p.sell_price * 100) if p.sell_price else Decimal("0")
        return {
            "id": p.id,
            "name": p.name,
            "slug": p.slug,
            "category": p.category,
            "unit": p.unit,
            "sell_price": str(p.sell_price),
            "farm_cost": str(p.farm_cost),
            "labor_cost": str(p.labor_cost),
            "overhead_cost": str(p.overhead_cost),
            "packaging_cost": str(p.packaging_cost),
            "normal_loss_percent": str(p.normal_loss_percent),
            "true_cost": str(p.true_cost),
            "gross_margin": str(margin),
            "margin_pct": str(margin_pct.quantize(Decimal("0.00001"))),
            "is_own_farm": p.is_own_farm,
            "is_active": p.is_active,
            "low_stock_threshold": str(p.low_stock_threshold),
            "current_qty": str(stock.current_qty) if stock else "0.000",
            "image_url": p.image_url,
        }
