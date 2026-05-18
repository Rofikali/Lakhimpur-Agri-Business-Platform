import uuid
from decimal import Decimal
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from modules.inventory.models import StockEntry, InventoryStock, MonthlyStock


class InventoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Current stock ─────────────────────────────────────────────────────────

    async def get_stock(self, product_id: uuid.UUID) -> InventoryStock | None:
        result = await self.db.execute(
            select(InventoryStock).where(InventoryStock.product_id == product_id)
        )
        return result.scalar_one_or_none()

    async def get_stock_locked(self, product_id: uuid.UUID) -> InventoryStock | None:
        """SELECT FOR UPDATE — use inside atomic transaction to prevent race."""
        result = await self.db.execute(
            select(InventoryStock).where(InventoryStock.product_id == product_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def update_stock(self, stock: InventoryStock) -> InventoryStock:
        self.db.add(stock)
        await self.db.flush()
        return stock

    # ── Stock entries ─────────────────────────────────────────────────────────

    async def find_entry_by_idempotency(self, key: uuid.UUID) -> StockEntry | None:
        result = await self.db.execute(select(StockEntry).where(StockEntry.idempotency_key == key))
        return result.scalar_one_or_none()

    async def create_entry(self, **kwargs) -> StockEntry:
        entry = StockEntry(**kwargs)
        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)
        return entry

    async def list_entries(
        self, product_id: uuid.UUID | None, entry_type: str | None, start: date, end: date
    ) -> list[StockEntry]:
        q = select(StockEntry).where(
            StockEntry.deleted_at.is_(None),
            StockEntry.date.between(start, end),
        )
        if product_id:
            q = q.where(StockEntry.product_id == product_id)
        if entry_type:
            q = q.where(StockEntry.entry_type == entry_type)
        q = q.order_by(StockEntry.date.desc(), StockEntry.created_at.desc())
        return list((await self.db.execute(q)).scalars().all())

    async def fetch_for_month(self, month: str) -> list[StockEntry]:
        """Fetch all entries for a given YYYY-MM month."""
        from datetime import date as dt

        y, m = int(month[:4]), int(month[5:7])
        last_day = [
            31,
            28 + int((y % 4 == 0 and y % 100 != 0) or y % 400 == 0),
            31,
            30,
            31,
            30,
            31,
            31,
            30,
            31,
            30,
            31,
        ][m - 1]
        start = dt(y, m, 1)
        end = dt(y, m, last_day)
        result = await self.db.execute(
            select(StockEntry).where(
                StockEntry.deleted_at.is_(None),
                StockEntry.date.between(start, end),
            )
        )
        return list(result.scalars().all())

    # ── Monthly stock ─────────────────────────────────────────────────────────

    async def get_monthly_stock(self, month: str) -> list[MonthlyStock]:
        result = await self.db.execute(select(MonthlyStock).where(MonthlyStock.month == month))
        return list(result.scalars().all())

    async def upsert_monthly_stock(
        self, product_id: uuid.UUID, month: str, stock_type: str, qty: Decimal, value: Decimal
    ) -> MonthlyStock:
        existing = await self.db.execute(
            select(MonthlyStock).where(
                MonthlyStock.product_id == product_id,
                MonthlyStock.month == month,
                MonthlyStock.stock_type == stock_type,
            )
        )
        ms = existing.scalar_one_or_none()
        if ms:
            ms.qty = qty
            ms.value = value
        else:
            ms = MonthlyStock(
                product_id=product_id, month=month, stock_type=stock_type, qty=qty, value=value
            )
            self.db.add(ms)
        await self.db.flush()
        return ms
