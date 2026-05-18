import json
import logging
from datetime import date as dt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from modules.pl_engine.calculator import calculate, PLResult
from modules.inventory.repository import InventoryRepository
from modules.inventory.models import StockEntry
from modules.finance.models import Asset
from modules.products.models import Product
from core.redis import cache_get, cache_set

logger = logging.getLogger("pl_engine")

PL_CACHE_TTL = 24 * 3600  # 24 hours for past months


class PLService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_monthly_pl(self, month: str) -> dict:
        """
        Returns full P&L dict for the given month.
        Past months cached in Redis 24h.
        Current month always recalculated.
        """
        current_month = dt.today().strftime("%Y-%m")
        is_past = month < current_month

        cache_key = f"pl:monthly:{month}"
        if is_past:
            cached = await cache_get(cache_key)
            if cached:
                cached["from_cache"] = True
                return cached

        # Fetch all data in parallel-ish (single DB round trip per query)
        inv_repo = InventoryRepository(self.db)
        entries = await inv_repo.fetch_for_month(month)
        stk = await inv_repo.get_monthly_stock(month)
        assets = await self._get_active_assets()
        products = await self._get_products_dict()

        result = calculate(
            month=month,
            entries=entries,
            monthly_stk=stk,
            assets=assets,
            products=products,
        )

        result_dict = result.to_dict()

        if is_past and not result.warnings:
            await cache_set(cache_key, json.dumps(result_dict), ttl=PL_CACHE_TTL)

        return result_dict

    async def get_breakeven(self, product_id: str) -> dict:
        from uuid import UUID

        p_result = await self.db.execute(select(Product).where(Product.id == UUID(product_id)))
        p = p_result.scalar_one_or_none()
        if not p:
            return {"error": "product_not_found"}

        assets = await self._get_active_assets()
        from modules.finance.models import FixedCost

        fc_result = await self.db.execute(select(FixedCost).where(FixedCost.is_active == True))
        fixed_costs = fc_result.scalars().all()

        monthly_fixed = sum(
            (a.monthly_depreciation for a in assets), __import__("decimal").Decimal("0")
        ) + sum((f.monthly_amount for f in fixed_costs), __import__("decimal").Decimal("0"))

        from decimal import Decimal

        variable_cost = (p.farm_cost or Decimal("0")) + (p.labor_cost or Decimal("0"))
        cm = p.sell_price - variable_cost

        if cm <= Decimal("0"):
            be_qty = Decimal("999999")
            be_rev = Decimal("999999")
        else:
            be_qty = monthly_fixed / cm
            be_rev = be_qty * p.sell_price

        return {
            "product_id": str(p.id),
            "product_name": p.name,
            "sell_price": str(p.sell_price),
            "variable_cost": str(variable_cost),
            "contribution_margin": str(cm),
            "fixed_costs_monthly": str(monthly_fixed),
            "breakeven_qty": str(be_qty.quantize(__import__("decimal").Decimal("0.00001"))),
            "breakeven_revenue": str(be_rev.quantize(__import__("decimal").Decimal("0.00001"))),
        }

    async def get_product_margins(self) -> list[dict]:
        """Ranked product margin table."""
        result = await self.db.execute(select(Product).where(Product.deleted_at.is_(None)))
        products = result.scalars().all()
        from decimal import Decimal

        rows = []
        for p in products:
            margin = p.sell_price - p.true_cost
            pct = (margin / p.sell_price * 100) if p.sell_price else Decimal("0")
            vc = (p.farm_cost or Decimal("0")) + (p.labor_cost or Decimal("0"))
            cm = p.sell_price - vc
            rows.append(
                {
                    "product_id": str(p.id),
                    "product_name": p.name,
                    "unit": p.unit,
                    "true_cost": str(p.true_cost),
                    "sell_price": str(p.sell_price),
                    "gross_margin": str(margin),
                    "margin_pct": str(pct),
                    "contribution_margin": str(cm),
                }
            )
        return sorted(rows, key=lambda x: float(x["margin_pct"]), reverse=True)

    async def _get_active_assets(self) -> list:
        result = await self.db.execute(select(Asset).where(Asset.is_active == True))
        return result.scalars().all()

    async def _get_products_dict(self) -> dict:
        result = await self.db.execute(select(Product))
        return {str(p.id): p for p in result.scalars().all()}
