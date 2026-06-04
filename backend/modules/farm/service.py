import uuid
from decimal import Decimal

from modules.farm.models import FarmSeason
from modules.farm.repository import FarmRepository
from modules.farm.schemas import FarmInputCreate, HarvestRecord, MillingRecord, SeasonCreate
from modules.inventory.schemas import StockEntryCreate
from modules.inventory.service import InventoryService
from shared.exceptions import InvalidSeasonTransitionError, SeasonNotFoundError

MARKUP = Decimal("0.12")  # 12% transfer price markup: farm → brand
DP5 = Decimal("0.00000")

VALID_TRANSITIONS = {
    "planning": ["active"],
    "active": ["harvested", "failed"],
    "harvested": ["milled", "failed"],
    "milled": ["complete", "failed"],
    "complete": [],
    "failed": [],
}


class FarmService:
    def __init__(self, repo: FarmRepository, inventory: InventoryService | None = None):
        self.repo = repo
        self.inventory = inventory

    async def create_season(self, data: SeasonCreate) -> dict:
        season = await self.repo.create_season(
            variety=data.variety,
            area_bigha=data.area_bigha,
            start_date=data.start_date,
            status="active",
            notes=data.notes,
        )
        return self._season_dict(season)

    async def list_seasons(self) -> list[dict]:
        seasons = await self.repo.list_seasons()
        return [self._season_dict(s) for s in seasons]

    async def get_season(self, season_id: uuid.UUID) -> dict:
        s = await self.repo.get_season(season_id)
        if not s:
            raise SeasonNotFoundError()
        d = self._season_dict(s)
        d["inputs"] = [
            {
                "id": str(i.id),
                "input_type": i.input_type,
                "description": i.description,
                "total_amount": self._decimal(i.total_amount),
                "date": i.date.isoformat(),
            }
            for i in (s.inputs or [])
        ]
        return d

    async def add_input(self, season_id: uuid.UUID, data: FarmInputCreate) -> dict:
        s = await self.repo.get_season(season_id)
        if not s:
            raise SeasonNotFoundError()
        status = self._status(s.status)
        if status not in ("active", "planning"):
            raise InvalidSeasonTransitionError(status, "add_input")

        fi = await self.repo.add_input(
            season_id=season_id,
            input_type=data.input_type,
            description=data.description,
            qty=data.qty,
            unit=data.unit,
            unit_cost=data.unit_cost,
            total_amount=data.total_amount,
            date=data.date,
        )

        # Recalculate total cultivation cost
        s.total_cultivation_cost = (s.total_cultivation_cost or Decimal("0")) + data.total_amount
        await self.repo.save(s)

        return {
            "id": str(fi.id),
            "input_type": fi.input_type,
            "total_amount": self._decimal(fi.total_amount),
            "season_total_cost": self._decimal(s.total_cultivation_cost),
        }

    async def record_harvest(self, season_id: uuid.UUID, data: HarvestRecord) -> dict:
        s = await self.repo.get_season(season_id)
        if not s:
            raise SeasonNotFoundError()
        status = self._status(s.status)
        if status != "active":
            raise InvalidSeasonTransitionError(status, "harvest")

        s.dhan_qty_kg = data.dhan_qty_kg
        s.harvest_date = data.harvest_date
        s.status = "harvested"

        total_cost = s.total_cultivation_cost or Decimal("0")
        s.cost_per_kg_dhan = (
            total_cost / data.dhan_qty_kg if data.dhan_qty_kg > Decimal("0") else Decimal("0")
        )
        await self.repo.save(s)
        return self._season_dict(s)

    async def record_milling(self, season_id: uuid.UUID, data: MillingRecord) -> dict:
        s = await self.repo.get_season(season_id)
        if not s:
            raise SeasonNotFoundError()
        status = self._status(s.status)
        if status != "harvested":
            raise InvalidSeasonTransitionError(status, "milling")

        # ── Milling yield ──────────────────────────────────────────────────
        yield_pct = (
            data.chawl_received_kg / data.dhan_sent_kg * 100
            if data.dhan_sent_kg > Decimal("0")
            else Decimal("0")
        )

        # ── By-product revenue credits ─────────────────────────────────────
        byproduct = (
            data.husk_recovered_kg * data.husk_market_price
            + data.bran_recovered_kg * data.bran_market_price
            + data.broken_rice_kg * data.broken_market_price
        )

        # ── True cost per kg chawl ─────────────────────────────────────────
        total_cost = (s.total_cultivation_cost or Decimal("0")) + data.milling_charges
        net_cost = total_cost - byproduct
        cost_per_chawl = (
            net_cost / data.chawl_received_kg
            if data.chawl_received_kg > Decimal("0")
            else Decimal("0")
        )
        transfer_price = cost_per_chawl * (Decimal("1") + MARKUP)

        # Update season
        s.chawl_qty_kg = data.chawl_received_kg
        s.milling_yield_percent = yield_pct
        s.cost_per_kg_chawl = cost_per_chawl
        s.transfer_price_per_kg = transfer_price
        s.status = "milled"

        await self.repo.add_milling(
            season_id=season_id,
            dhan_sent_kg=data.dhan_sent_kg,
            chawl_received_kg=data.chawl_received_kg,
            husk_recovered_kg=data.husk_recovered_kg,
            bran_recovered_kg=data.bran_recovered_kg,
            broken_rice_kg=data.broken_rice_kg,
            milling_charges=data.milling_charges,
            husk_market_price=data.husk_market_price,
            bran_market_price=data.bran_market_price,
            broken_market_price=data.broken_market_price,
            yield_percent=yield_pct,
            milling_date=data.milling_date,
        )

        # ── Transfer chawl to inventory ────────────────────────────────────
        if self.inventory:
            from modules.products.repository import ProductRepository

            prod_repo = ProductRepository(self.repo.db)
            variety_slug = {
                "joha": "joha-rice",
                "bora_saul": "bora-saul",
                "kali_jeera": "kali-jeera",
            }.get(self._status(s.variety), "")
            product = await prod_repo.get_by_slug(variety_slug)
            if product:
                await self.inventory.add_stock_entry(
                    StockEntryCreate(
                        idempotency_key=__import__("uuid").uuid4(),
                        product_id=product.id,
                        entry_type="production",
                        qty=data.chawl_received_kg,
                        unit_cost=cost_per_chawl,
                        total_amount=cost_per_chawl * data.chawl_received_kg,
                        source="own",
                        reference_id=season_id,
                        reference_type="season",
                        date=data.milling_date,
                        note=f"From farm season {s.variety} {s.start_date.year}",
                    )
                )

        await self.repo.save(s)
        return {
            **self._season_dict(s),
            "milling_yield_pct": self._decimal(yield_pct),
            "byproduct_revenue": self._decimal(byproduct),
            "inventory_added_qty": self._decimal(data.chawl_received_kg),
        }

    async def complete_season(self, season_id: uuid.UUID) -> dict:
        s = await self.repo.get_season(season_id)
        if not s:
            raise SeasonNotFoundError()
        status = self._status(s.status)
        if status != "milled":
            raise InvalidSeasonTransitionError(status, "complete")
        s.status = "complete"
        await self.repo.save(s)
        return self._season_dict(s)

    async def mark_failed(self, season_id: uuid.UUID, reason: str) -> dict:
        s = await self.repo.get_season(season_id)
        if not s:
            raise SeasonNotFoundError()
        s.status = "failed"
        s.notes = reason
        await self.repo.save(s)
        return self._season_dict(s)

    @staticmethod
    def _status(value) -> str:
        return getattr(value, "value", value)

    @staticmethod
    def _decimal(value) -> str | None:
        return str(value.quantize(DP5)) if value is not None else None

    @staticmethod
    def _season_dict(s: FarmSeason) -> dict:
        return {
            "id": str(s.id),
            "variety": FarmService._status(s.variety),
            "area_bigha": FarmService._decimal(s.area_bigha),
            "status": FarmService._status(s.status),
            "start_date": s.start_date.isoformat(),
            "harvest_date": s.harvest_date.isoformat() if s.harvest_date else None,
            "dhan_qty_kg": FarmService._decimal(s.dhan_qty_kg),
            "chawl_qty_kg": FarmService._decimal(s.chawl_qty_kg),
            "total_cultivation_cost": FarmService._decimal(s.total_cultivation_cost),
            "milling_yield_percent": FarmService._decimal(s.milling_yield_percent),
            "cost_per_kg_dhan": FarmService._decimal(s.cost_per_kg_dhan),
            "cost_per_kg_chawl": FarmService._decimal(s.cost_per_kg_chawl),
            "transfer_price_per_kg": FarmService._decimal(s.transfer_price_per_kg),
        }
