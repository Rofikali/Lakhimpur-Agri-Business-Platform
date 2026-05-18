import uuid
from decimal import Decimal
from datetime import date
from modules.inventory.repository import InventoryRepository
from modules.inventory.schemas import StockEntryCreate, MonthlyStockCreate
from modules.inventory.models import InventoryStock
from modules.products.repository import ProductRepository
from shared.exceptions import (
    StockInsufficientError,
    StockNegativeError,
    ClosingStockExceedsMaxError,
    ProductNotFoundError,
)
from core.redis import cache_delete, should_send_alert


class InventoryService:
    def __init__(self, repo: InventoryRepository, product_repo: ProductRepository | None = None):
        self.repo = repo
        self.product_repo = product_repo

    async def get_current_stock(self, product_id: uuid.UUID) -> InventoryStock:
        stock = await self.repo.get_stock(product_id)
        if stock is None:
            # Auto-create if missing (shouldn't happen after seed)
            stock = InventoryStock(product_id=product_id, current_qty=Decimal("0"))
            self.repo.db.add(stock)
            await self.repo.db.flush()
        return stock

    async def decrement_stock(
        self, product_id: uuid.UUID, qty: Decimal, order_id: uuid.UUID
    ) -> InventoryStock:
        """Called inside an atomic transaction. Uses row lock."""
        stock = await self.repo.get_stock_locked(product_id)
        if not stock:
            raise StockInsufficientError("product", Decimal("0"), qty)
        if stock.current_qty < qty:
            raise StockInsufficientError("product", stock.current_qty, qty)
        stock.current_qty -= qty
        await self.repo.update_stock(stock)
        await cache_delete(f"products:stock:{product_id}")
        return stock

    async def restore_stock(self, product_id: uuid.UUID, qty: Decimal) -> None:
        """Called when order is cancelled. Restores decremented stock."""
        stock = await self.repo.get_stock_locked(product_id)
        if stock:
            stock.current_qty += qty
            await self.repo.update_stock(stock)
            await cache_delete(f"products:stock:{product_id}")

    async def add_stock_entry(self, data: StockEntryCreate) -> dict:
        # Idempotency
        existing = await self.repo.find_entry_by_idempotency(data.idempotency_key)
        if existing:
            stock = await self.repo.get_stock(data.product_id)
            return self._entry_dict(existing, stock)

        # Load product for standard cost reference
        product = None
        if self.product_repo:
            product = await self.product_repo.get_by_id(data.product_id)
            if not product:
                raise ProductNotFoundError(str(data.product_id))

        # Calculate variances
        price_variance = None
        cost_variance = None
        unit_cost = data.unit_cost

        if data.entry_type == "sale" and product and data.qty > 0:
            actual_unit = data.total_amount / data.qty
            price_variance = (actual_unit - product.sell_price) * data.qty

        if data.entry_type == "purchase" and product and data.qty > 0:
            unit_cost = data.total_amount / data.qty
            cost_variance = (unit_cost - product.true_cost) * data.qty

        # Create the entry
        entry = await self.repo.create_entry(
            idempotency_key=data.idempotency_key,
            product_id=data.product_id,
            entry_type=data.entry_type,
            qty=data.qty,
            unit_cost=unit_cost,
            total_amount=data.total_amount,
            standard_unit_cost=product.true_cost if product else None,
            price_variance=price_variance,
            cost_variance=cost_variance,
            source=data.source,
            channel=data.channel,
            pay_mode=data.pay_mode,
            reference_id=data.reference_id,
            reference_type=data.reference_type,
            date=data.date,
            note=data.note,
        )

        # Adjust live stock for purchase and production
        stock = await self.repo.get_stock(data.product_id)
        if stock and data.entry_type in ("purchase", "production"):
            stock.current_qty += data.qty
            await self.repo.update_stock(stock)
            await cache_delete(f"products:stock:{data.product_id}")

            # Check low-stock threshold alert
            if product and stock.current_qty < product.low_stock_threshold:
                if await should_send_alert("low_stock", str(data.product_id)):
                    # Notify is handled by caller or background task
                    entry.low_stock_alert = True

        return self._entry_dict(entry, stock)

    async def add_monthly_stock(self, data: MonthlyStockCreate) -> dict:
        # Validate closing stock doesn't exceed possible maximum
        if data.stock_type == "closing":
            entries = await self.repo.fetch_for_month(data.month)
            received = sum(
                (e.qty for e in entries if e.entry_type in ("purchase", "production")),
                Decimal("0"),
            )
            monthly = await self.repo.get_monthly_stock(data.month)
            opening = sum(
                (
                    m.qty
                    for m in monthly
                    if m.stock_type == "opening" and str(m.product_id) == str(data.product_id)
                ),
                Decimal("0"),
            )
            max_possible = opening + received
            if data.qty > max_possible:
                raise ClosingStockExceedsMaxError(data.qty, max_possible)

        ms = await self.repo.upsert_monthly_stock(
            product_id=data.product_id,
            month=data.month,
            stock_type=data.stock_type,
            qty=data.qty,
            value=data.value,
        )
        return {
            "product_id": ms.product_id,
            "month": ms.month,
            "stock_type": ms.stock_type,
            "qty": str(ms.qty),
            "value": str(ms.value),
        }

    def _entry_dict(self, entry, stock) -> dict:
        return {
            "id": entry.id,
            "product_id": entry.product_id,
            "entry_type": entry.entry_type,
            "qty": str(entry.qty),
            "unit_cost": str(entry.unit_cost) if entry.unit_cost else None,
            "total_amount": str(entry.total_amount),
            "price_variance": str(entry.price_variance) if entry.price_variance else None,
            "cost_variance": str(entry.cost_variance) if entry.cost_variance else None,
            "new_stock_qty": str(stock.current_qty) if stock else "0.000",
            "date": entry.date,
        }
