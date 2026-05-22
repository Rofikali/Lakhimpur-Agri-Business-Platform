# Stage 6 · Code · Part 4 — Farm + Petha + Notify modules

---

## MODULE 7 — FARM

### modules/farm/schemas.py
```python
import uuid
from decimal import Decimal
from datetime import date
from typing import Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class SeasonCreate(BaseModel):
    variety    : str     = Field(pattern=r"^(joha|bora_saul|kali_jeera)$")
    area_bigha : Decimal = Field(gt=Decimal("0"))
    start_date : date
    notes      : str | None = None

    @field_validator("area_bigha", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float): raise ValueError("Use string — never float")
        return Decimal(str(v))


class FarmInputCreate(BaseModel):
    input_type   : str = Field(pattern=r"^(seed|fertilizer|pesticide|labor|irrigation|transport|other)$")
    description  : str
    qty          : Decimal | None = None
    unit         : str | None = None
    unit_cost    : Decimal
    total_amount : Decimal
    date         : date

    @field_validator("qty","unit_cost","total_amount", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal | None:
        if v is None: return None
        if isinstance(v, float): raise ValueError("No float")
        return Decimal(str(v))


class HarvestRecord(BaseModel):
    dhan_qty_kg  : Decimal
    harvest_date : date
    notes        : str | None = None

    @field_validator("dhan_qty_kg", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float): raise ValueError("No float")
        return Decimal(str(v))


class MillingRecord(BaseModel):
    dhan_sent_kg        : Decimal
    chawl_received_kg   : Decimal
    husk_recovered_kg   : Decimal = Decimal("0")
    bran_recovered_kg   : Decimal = Decimal("0")
    broken_rice_kg      : Decimal = Decimal("0")
    milling_charges     : Decimal
    husk_market_price   : Decimal = Decimal("0")
    bran_market_price   : Decimal = Decimal("0")
    broken_market_price : Decimal = Decimal("0")
    milling_date        : date

    @field_validator("dhan_sent_kg","chawl_received_kg","husk_recovered_kg",
                     "bran_recovered_kg","broken_rice_kg","milling_charges",
                     "husk_market_price","bran_market_price","broken_market_price",
                     mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float): raise ValueError("No float")
        return Decimal(str(v))


class SeasonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id                     : uuid.UUID
    variety                : str
    area_bigha             : str
    status                 : str
    start_date             : date
    harvest_date           : date | None
    dhan_qty_kg            : str | None
    chawl_qty_kg           : str | None
    total_cultivation_cost : str | None
    milling_yield_percent  : str | None
    cost_per_kg_dhan       : str | None
    cost_per_kg_chawl      : str | None
    transfer_price_per_kg  : str | None

    @field_validator("area_bigha","dhan_qty_kg","chawl_qty_kg",
                     "total_cultivation_cost","milling_yield_percent",
                     "cost_per_kg_dhan","cost_per_kg_chawl","transfer_price_per_kg",
                     mode="before")
    @classmethod
    def to_str(cls, v: Any) -> str | None:
        return str(v) if v is not None else None
```

### modules/farm/repository.py
```python
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from modules.farm.models import FarmSeason, FarmInput, FarmMilling


class FarmRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_season(self, **kwargs) -> FarmSeason:
        s = FarmSeason(**kwargs)
        self.db.add(s)
        await self.db.flush()
        await self.db.refresh(s)
        return s

    async def get_season(self, season_id: uuid.UUID) -> FarmSeason | None:
        result = await self.db.execute(
            select(FarmSeason)
            .where(FarmSeason.id == season_id)
            .options(selectinload(FarmSeason.inputs), selectinload(FarmSeason.millings))
        )
        return result.scalar_one_or_none()

    async def list_seasons(self) -> list[FarmSeason]:
        result = await self.db.execute(
            select(FarmSeason).order_by(FarmSeason.start_date.desc())
        )
        return list(result.scalars().all())

    async def add_input(self, season_id: uuid.UUID, **kwargs) -> FarmInput:
        fi = FarmInput(season_id=season_id, **kwargs)
        self.db.add(fi)
        await self.db.flush()
        return fi

    async def add_milling(self, season_id: uuid.UUID, **kwargs) -> FarmMilling:
        fm = FarmMilling(season_id=season_id, **kwargs)
        self.db.add(fm)
        await self.db.flush()
        return fm

    async def save(self, obj) -> None:
        self.db.add(obj)
        await self.db.flush()
```

### modules/farm/service.py
```python
import uuid
from decimal import Decimal
from modules.farm.repository import FarmRepository
from modules.farm.schemas import (
    SeasonCreate, FarmInputCreate, HarvestRecord, MillingRecord
)
from modules.farm.models import FarmSeason
from modules.inventory.service import InventoryService
from modules.inventory.schemas import StockEntryCreate
from shared.exceptions import SeasonNotFoundError, InvalidSeasonTransitionError
from datetime import date

MARKUP = Decimal("0.12")   # 12% transfer price markup: farm → brand

VALID_TRANSITIONS = {
    "planning" : ["active"],
    "active"   : ["harvested", "failed"],
    "harvested": ["milled",    "failed"],
    "milled"   : ["complete",  "failed"],
    "complete" : [],
    "failed"   : [],
}


class FarmService:
    def __init__(self, repo: FarmRepository, inventory: InventoryService | None = None):
        self.repo      = repo
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
        if not s: raise SeasonNotFoundError()
        d = self._season_dict(s)
        d["inputs"] = [
            {"id": str(i.id), "input_type": i.input_type,
             "description": i.description, "total_amount": str(i.total_amount),
             "date": i.date.isoformat()}
            for i in (s.inputs or [])
        ]
        return d

    async def add_input(self, season_id: uuid.UUID, data: FarmInputCreate) -> dict:
        s = await self.repo.get_season(season_id)
        if not s: raise SeasonNotFoundError()
        if s.status not in ("active", "planning"):
            raise InvalidSeasonTransitionError(s.status, "add_input")

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

        return {"id": str(fi.id), "input_type": fi.input_type,
                "total_amount": str(fi.total_amount),
                "season_total_cost": str(s.total_cultivation_cost)}

    async def record_harvest(self, season_id: uuid.UUID, data: HarvestRecord) -> dict:
        s = await self.repo.get_season(season_id)
        if not s: raise SeasonNotFoundError()
        if s.status != "active":
            raise InvalidSeasonTransitionError(s.status, "harvest")

        s.dhan_qty_kg    = data.dhan_qty_kg
        s.harvest_date   = data.harvest_date
        s.status         = "harvested"

        total_cost       = s.total_cultivation_cost or Decimal("0")
        s.cost_per_kg_dhan = (
            total_cost / data.dhan_qty_kg if data.dhan_qty_kg > Decimal("0") else Decimal("0")
        )
        await self.repo.save(s)
        return self._season_dict(s)

    async def record_milling(self, season_id: uuid.UUID, data: MillingRecord) -> dict:
        s = await self.repo.get_season(season_id)
        if not s: raise SeasonNotFoundError()
        if s.status != "harvested":
            raise InvalidSeasonTransitionError(s.status, "milling")

        # ── Milling yield ──────────────────────────────────────────────────
        yield_pct = (data.chawl_received_kg / data.dhan_sent_kg * 100
                     if data.dhan_sent_kg > Decimal("0") else Decimal("0"))

        # ── By-product revenue credits ─────────────────────────────────────
        byproduct = (data.husk_recovered_kg  * data.husk_market_price +
                     data.bran_recovered_kg  * data.bran_market_price +
                     data.broken_rice_kg     * data.broken_market_price)

        # ── True cost per kg chawl ─────────────────────────────────────────
        total_cost    = (s.total_cultivation_cost or Decimal("0")) + data.milling_charges
        net_cost      = total_cost - byproduct
        cost_per_chawl = (net_cost / data.chawl_received_kg
                          if data.chawl_received_kg > Decimal("0") else Decimal("0"))
        transfer_price = cost_per_chawl * (Decimal("1") + MARKUP)

        # Update season
        s.chawl_qty_kg           = data.chawl_received_kg
        s.milling_yield_percent  = yield_pct
        s.cost_per_kg_chawl      = cost_per_chawl
        s.transfer_price_per_kg  = transfer_price
        s.status                 = "milled"

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
            }.get(s.variety, "")
            product = await prod_repo.get_by_slug(variety_slug)
            if product:
                await self.inventory.add_stock_entry(StockEntryCreate(
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
                ))

        await self.repo.save(s)
        return {
            **self._season_dict(s),
            "milling_yield_pct":  str(yield_pct.quantize(Decimal("0.00001"))),
            "byproduct_revenue":  str(byproduct.quantize(Decimal("0.00001"))),
            "inventory_added_qty":str(data.chawl_received_kg),
        }

    async def complete_season(self, season_id: uuid.UUID) -> dict:
        s = await self.repo.get_season(season_id)
        if not s: raise SeasonNotFoundError()
        if s.status != "milled":
            raise InvalidSeasonTransitionError(s.status, "complete")
        s.status = "complete"
        await self.repo.save(s)
        return self._season_dict(s)

    async def mark_failed(self, season_id: uuid.UUID, reason: str) -> dict:
        s = await self.repo.get_season(season_id)
        if not s: raise SeasonNotFoundError()
        s.status = "failed"
        s.notes  = reason
        await self.repo.save(s)
        return self._season_dict(s)

    @staticmethod
    def _season_dict(s: FarmSeason) -> dict:
        def _s(v): return str(v) if v is not None else None
        return {
            "id": str(s.id), "variety": s.variety,
            "area_bigha": _s(s.area_bigha), "status": s.status,
            "start_date": s.start_date.isoformat(),
            "harvest_date": s.harvest_date.isoformat() if s.harvest_date else None,
            "dhan_qty_kg": _s(s.dhan_qty_kg), "chawl_qty_kg": _s(s.chawl_qty_kg),
            "total_cultivation_cost": _s(s.total_cultivation_cost),
            "milling_yield_percent": _s(s.milling_yield_percent),
            "cost_per_kg_dhan": _s(s.cost_per_kg_dhan),
            "cost_per_kg_chawl": _s(s.cost_per_kg_chawl),
            "transfer_price_per_kg": _s(s.transfer_price_per_kg),
        }
```

### modules/farm/router.py
```python
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from modules.farm.schemas import SeasonCreate, FarmInputCreate, HarvestRecord, MillingRecord
from modules.farm.service import FarmService
from modules.farm.repository import FarmRepository
from modules.inventory.service import InventoryService
from modules.inventory.repository import InventoryRepository
from modules.products.repository import ProductRepository
from core.dependencies import require_owner, get_db_session
from pydantic import BaseModel

router = APIRouter(prefix="/api/farm", tags=["farm"])


def _svc(db: AsyncSession = Depends(get_db_session)) -> FarmService:
    return FarmService(
        repo=FarmRepository(db),
        inventory=InventoryService(
            repo=InventoryRepository(db),
            product_repo=ProductRepository(db),
        ),
    )


@router.get("/seasons")
async def list_seasons(owner: dict = Depends(require_owner), svc: FarmService = Depends(_svc)):
    return await svc.list_seasons()

@router.post("/seasons", status_code=201)
async def create_season(body: SeasonCreate, owner: dict = Depends(require_owner),
                         svc: FarmService = Depends(_svc)):
    return await svc.create_season(body)

@router.get("/seasons/{season_id}")
async def get_season(season_id: uuid.UUID, owner: dict = Depends(require_owner),
                      svc: FarmService = Depends(_svc)):
    return await svc.get_season(season_id)

@router.post("/seasons/{season_id}/inputs", status_code=201)
async def add_input(season_id: uuid.UUID, body: FarmInputCreate,
                     owner: dict = Depends(require_owner), svc: FarmService = Depends(_svc)):
    return await svc.add_input(season_id, body)

@router.post("/seasons/{season_id}/harvest")
async def record_harvest(season_id: uuid.UUID, body: HarvestRecord,
                          owner: dict = Depends(require_owner), svc: FarmService = Depends(_svc)):
    return await svc.record_harvest(season_id, body)

@router.post("/seasons/{season_id}/milling")
async def record_milling(season_id: uuid.UUID, body: MillingRecord,
                          owner: dict = Depends(require_owner), svc: FarmService = Depends(_svc)):
    return await svc.record_milling(season_id, body)

@router.patch("/seasons/{season_id}/complete")
async def complete_season(season_id: uuid.UUID, owner: dict = Depends(require_owner),
                           svc: FarmService = Depends(_svc)):
    return await svc.complete_season(season_id)

class FailReason(BaseModel):
    reason: str

@router.patch("/seasons/{season_id}/fail")
async def fail_season(season_id: uuid.UUID, body: FailReason,
                       owner: dict = Depends(require_owner), svc: FarmService = Depends(_svc)):
    return await svc.mark_failed(season_id, body.reason)
```

---

## MODULE 8 — PETHA

### modules/petha/schemas.py
```python
import uuid
from decimal import Decimal
from datetime import date
from typing import Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class BatchCostCreate(BaseModel):
    cost_type    : str = Field(pattern=r"^(ingredient|labor|fuel|overhead)$")
    description  : str
    qty          : Decimal | None = None
    unit_cost    : Decimal
    total_amount : Decimal

    @field_validator("qty","unit_cost","total_amount", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal | None:
        if v is None: return None
        if isinstance(v, float): raise ValueError("No float")
        return Decimal(str(v))


class BatchCreate(BaseModel):
    variety         : str = Field(pattern=r"^(septa|narikal)$")
    batch_date      : date
    planned_pieces  : int = Field(ge=1)
    shelf_life_days : int = Field(default=7, ge=1, le=30)
    recipe_snapshot : dict
    costs           : list[BatchCostCreate] = Field(min_length=1)


class BatchOutcome(BaseModel):
    good_pieces     : int = Field(ge=0)
    rejected_pieces : int = Field(ge=0)


class BatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id              : uuid.UUID
    variety         : str
    status          : str
    batch_date      : date
    planned_pieces  : int
    good_pieces     : int | None
    rejected_pieces : int | None
    total_batch_cost: str
    cost_per_piece  : str | None
    expiry_date     : date
    days_to_expiry  : int
    rejection_pct   : str | None

    @field_validator("total_batch_cost","cost_per_piece","rejection_pct", mode="before")
    @classmethod
    def to_str(cls, v: Any) -> str | None:
        return str(v) if v is not None else None
```

### modules/petha/repository.py
```python
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from modules.petha.models import PethaBatch, PethaBatchCost


class PethaRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_batch(self, **kwargs) -> PethaBatch:
        b = PethaBatch(**kwargs)
        self.db.add(b)
        await self.db.flush()
        return b

    async def get_batch(self, batch_id: uuid.UUID) -> PethaBatch | None:
        result = await self.db.execute(
            select(PethaBatch)
            .where(PethaBatch.id == batch_id)
            .options(selectinload(PethaBatch.cost_lines))
        )
        return result.scalar_one_or_none()

    async def list_batches(self, include_expired: bool = False) -> list[PethaBatch]:
        q = select(PethaBatch).order_by(PethaBatch.batch_date.desc())
        if not include_expired:
            q = q.where(PethaBatch.status != "expired")
        return list((await self.db.execute(q)).scalars().all())

    async def add_cost(self, batch_id: uuid.UUID, **kwargs) -> PethaBatchCost:
        c = PethaBatchCost(batch_id=batch_id, **kwargs)
        self.db.add(c)
        await self.db.flush()
        return c

    async def save(self, obj) -> None:
        self.db.add(obj)
        await self.db.flush()

    async def get_expiring_soon(self, days: int = 3) -> list[PethaBatch]:
        from datetime import date, timedelta
        target = date.today() + timedelta(days=days)
        result = await self.db.execute(
            select(PethaBatch)
            .where(PethaBatch.status == "completed",
                   PethaBatch.expiry_date <= target)
        )
        return list(result.scalars().all())
```

### modules/petha/service.py
```python
import uuid
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from modules.petha.repository import PethaRepository
from modules.petha.schemas import BatchCreate, BatchOutcome
from modules.petha.models import PethaBatch
from modules.inventory.service import InventoryService
from modules.inventory.schemas import StockEntryCreate
from shared.exceptions import (
    BatchNotFoundError, BatchAlreadyCompletedError, BatchExpiredError
)

DP5 = Decimal("0.00001")


class PethaService:
    def __init__(self, repo: PethaRepository, inventory: InventoryService | None = None):
        self.repo      = repo
        self.inventory = inventory

    async def create_batch(self, data: BatchCreate) -> dict:
        # Sum costs by type
        ingredient = sum((c.total_amount for c in data.costs if c.cost_type == "ingredient"), Decimal("0"))
        labor      = sum((c.total_amount for c in data.costs if c.cost_type == "labor"),      Decimal("0"))
        overhead   = sum((c.total_amount for c in data.costs
                          if c.cost_type in ("fuel","overhead")), Decimal("0"))
        total      = ingredient + labor + overhead
        expiry     = data.batch_date + timedelta(days=data.shelf_life_days)

        batch = await self.repo.create_batch(
            variety=data.variety,
            status="in_production",
            batch_date=data.batch_date,
            planned_pieces=data.planned_pieces,
            shelf_life_days=data.shelf_life_days,
            recipe_snapshot=data.recipe_snapshot,
            total_ingredient_cost=ingredient,
            total_labor_cost=labor,
            total_overhead_cost=overhead,
            total_batch_cost=total,
            expiry_date=expiry,
        )
        for c in data.costs:
            await self.repo.add_cost(
                batch_id=batch.id,
                cost_type=c.cost_type,
                description=c.description,
                qty=c.qty,
                unit_cost=c.unit_cost,
                total_amount=c.total_amount,
            )

        return self._batch_dict(batch)

    async def record_outcome(self, batch_id: uuid.UUID, data: BatchOutcome) -> dict:
        batch = await self.repo.get_batch(batch_id)
        if not batch:            raise BatchNotFoundError()
        if batch.status != "in_production":
            if batch.status == "expired": raise BatchExpiredError(str(batch.expiry_date))
            raise BatchAlreadyCompletedError()

        good = data.good_pieces
        total_cost = batch.total_batch_cost

        # Absorption costing: rejected pieces' cost absorbed by good pieces
        cost_per_piece = (total_cost / Decimal(str(good))
                          if good > 0 else Decimal("0"))
        rejection_pct  = (
            (Decimal(str(data.rejected_pieces)) / Decimal(str(batch.planned_pieces)) * 100)
            if batch.planned_pieces > 0 else Decimal("0")
        )

        batch.good_pieces     = good
        batch.rejected_pieces = data.rejected_pieces
        batch.cost_per_piece  = cost_per_piece
        batch.status          = "completed"

        # Add to inventory
        if self.inventory and good > 0:
            slug = "narikal-petha" if batch.variety == "narikal" else "septa-petha"
            from modules.products.repository import ProductRepository
            prod_repo = ProductRepository(self.repo.db)
            product   = await prod_repo.get_by_slug(slug)
            if product:
                await self.inventory.add_stock_entry(StockEntryCreate(
                    idempotency_key=__import__("uuid").uuid4(),
                    product_id=product.id,
                    entry_type="production",
                    qty=Decimal(str(good)),
                    unit_cost=cost_per_piece,
                    total_amount=cost_per_piece * Decimal(str(good)),
                    source="own",
                    reference_id=batch_id,
                    reference_type="petha_batch",
                    date=batch.batch_date,
                    note=f"{batch.variety} petha batch",
                ))

        await self.repo.save(batch)
        d = self._batch_dict(batch)
        d["rejection_pct"] = str(rejection_pct.quantize(DP5))
        return d

    async def mark_expired(self, batch_id: uuid.UUID) -> dict:
        """
        Called when shelf life passes with unsold pieces.
        Remaining inventory × cost_per_piece = abnormal loss.
        """
        batch = await self.repo.get_batch(batch_id)
        if not batch:         raise BatchNotFoundError()
        if batch.status != "completed": raise BatchAlreadyCompletedError()

        # Calculate unsold quantity from inventory
        unsold_qty = Decimal("0")
        if self.inventory and batch.cost_per_piece:
            slug = "narikal-petha" if batch.variety == "narikal" else "septa-petha"
            from modules.products.repository import ProductRepository
            prod_repo = ProductRepository(self.repo.db)
            product   = await prod_repo.get_by_slug(slug)
            if product:
                stock = await self.inventory.get_current_stock(product.id)
                unsold_qty = stock.current_qty

        abnormal_loss = (unsold_qty * batch.cost_per_piece
                         if batch.cost_per_piece else Decimal("0"))
        batch.abnormal_loss_amount = abnormal_loss
        batch.status               = "expired"
        await self.repo.save(batch)

        # Record abnormal loss as stock entry
        if self.inventory and unsold_qty > 0 and batch.cost_per_piece:
            slug = "narikal-petha" if batch.variety == "narikal" else "septa-petha"
            from modules.products.repository import ProductRepository
            product = await ProductRepository(self.repo.db).get_by_slug(slug)
            if product:
                await self.inventory.add_stock_entry(StockEntryCreate(
                    idempotency_key=__import__("uuid").uuid4(),
                    product_id=product.id,
                    entry_type="wastage_abnormal",
                    qty=unsold_qty,
                    unit_cost=batch.cost_per_piece,
                    total_amount=abnormal_loss,
                    source="own",
                    reference_id=batch_id,
                    reference_type="petha_batch",
                    date=date.today(),
                    note=f"Expired {batch.variety} petha batch",
                ))

        d = self._batch_dict(batch)
        d["abnormal_loss_amount"] = str(abnormal_loss)
        return d

    async def list_batches(self, include_expired: bool = False) -> list[dict]:
        batches = await self.repo.list_batches(include_expired)
        return [self._batch_dict(b) for b in batches]

    async def get_expiring_soon(self, days: int = 3) -> list[dict]:
        batches = await self.repo.get_expiring_soon(days)
        return [self._batch_dict(b) for b in batches]

    @staticmethod
    def _batch_dict(b: PethaBatch) -> dict:
        from datetime import date as dt
        days_left = (b.expiry_date - dt.today()).days if b.expiry_date else 0
        return {
            "id":               str(b.id),
            "variety":          b.variety,
            "status":           b.status,
            "batch_date":       b.batch_date.isoformat(),
            "planned_pieces":   b.planned_pieces,
            "good_pieces":      b.good_pieces,
            "rejected_pieces":  b.rejected_pieces,
            "total_batch_cost": str(b.total_batch_cost),
            "cost_per_piece":   str(b.cost_per_piece) if b.cost_per_piece else None,
            "expiry_date":      b.expiry_date.isoformat() if b.expiry_date else None,
            "days_to_expiry":   days_left,
        }
```

### modules/petha/router.py
```python
import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from modules.petha.schemas import BatchCreate, BatchOutcome
from modules.petha.service import PethaService
from modules.petha.repository import PethaRepository
from modules.inventory.service import InventoryService
from modules.inventory.repository import InventoryRepository
from modules.products.repository import ProductRepository
from core.dependencies import require_owner, get_db_session

router = APIRouter(prefix="/api/petha", tags=["petha"])


def _svc(db: AsyncSession = Depends(get_db_session)) -> PethaService:
    return PethaService(
        repo=PethaRepository(db),
        inventory=InventoryService(
            repo=InventoryRepository(db),
            product_repo=ProductRepository(db),
        ),
    )


@router.get("/batches")
async def list_batches(
    include_expired : bool = Query(False),
    owner           : dict = Depends(require_owner),
    svc             : PethaService = Depends(_svc),
):
    return await svc.list_batches(include_expired)


@router.post("/batches", status_code=201)
async def create_batch(body: BatchCreate, owner: dict = Depends(require_owner),
                        svc: PethaService = Depends(_svc)):
    return await svc.create_batch(body)


@router.get("/batches/expiring-soon")
async def expiring_soon(days: int = Query(3, ge=1, le=14),
                         owner: dict = Depends(require_owner),
                         svc: PethaService = Depends(_svc)):
    return await svc.get_expiring_soon(days)


@router.get("/batches/{batch_id}")
async def get_batch(batch_id: uuid.UUID, owner: dict = Depends(require_owner),
                     svc: PethaService = Depends(_svc)):
    batch = await svc.repo.get_batch(batch_id)
    if not batch:
        from shared.exceptions import BatchNotFoundError
        raise BatchNotFoundError()
    return svc._batch_dict(batch)


@router.patch("/batches/{batch_id}/outcome")
async def record_outcome(batch_id: uuid.UUID, body: BatchOutcome,
                          owner: dict = Depends(require_owner),
                          svc: PethaService = Depends(_svc)):
    return await svc.record_outcome(batch_id, body)


@router.patch("/batches/{batch_id}/expire")
async def expire_batch(batch_id: uuid.UUID, owner: dict = Depends(require_owner),
                        svc: PethaService = Depends(_svc)):
    return await svc.mark_expired(batch_id)
```

---

## MODULE 9 — NOTIFY

### modules/notify/wati.py
```python
"""WATI (WhatsApp Business API) client."""
import httpx
import logging
from core.config import settings

logger = logging.getLogger("notify.wati")


async def send_template_message(phone: str, template: str, params: list[str]) -> bool:
    """
    Send a WhatsApp template message via WATI.
    Returns True on success, False on failure.
    Failure is logged but NEVER raises — notifications are non-critical.
    """
    if not settings.WATI_ENABLED:
        logger.info(f"WATI disabled — skipping message to {phone[:7]}****")
        return True

    url = f"{settings.WATI_BASE_URL}/sendTemplateMessage"
    headers = {
        "Authorization": f"Bearer {settings.WATI_API_TOKEN}",
        "Content-Type":  "application/json",
    }
    body = {
        "whatsappNumber": phone.replace("+", "").replace("-", ""),
        "template_name":  template,
        "broadcast_name": template,
        "parameters":     [{"name": f"param{i+1}", "value": v}
                           for i, v in enumerate(params)],
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code == 200:
                logger.info(f"WhatsApp sent: {template} → {phone[:7]}****")
                return True
            else:
                logger.error(f"WATI error {resp.status_code}: {resp.text[:200]}")
                return False
    except Exception as e:
        logger.error(f"WATI exception: {e}")
        return False
```

### modules/notify/templates.py
```python
"""
WhatsApp message templates.
Template names must match approved WATI templates.
All params are positional strings {{1}}, {{2}}, ...
"""

TEMPLATES = {
    "order_confirmed": {
        "name":   "order_confirmed",
        "params": lambda order: [
            order.order_number,
            order.customer_name,
            str(order.final_amount),
            order.fulfillment_type,
        ],
    },
    "order_packed": {
        "name":   "order_packed",
        "params": lambda order: [
            order.order_number,
            order.customer_name,
        ],
    },
    "order_ready_pickup": {
        "name":   "order_ready_pickup",
        "params": lambda order: [
            order.order_number,
            order.customer_name,
        ],
    },
    "order_delivered": {
        "name":   "order_delivered",
        "params": lambda order: [
            order.order_number,
            order.customer_name,
        ],
    },
    "new_order_owner": {
        "name":   "new_order_owner",
        "params": lambda order: [
            order.order_number,
            order.customer_name,
            order.customer_phone,
            str(order.final_amount),
            order.fulfillment_type,
            order.channel,
        ],
    },
    "low_stock_alert": {
        "name":   "low_stock_alert",
        "params": lambda product_name, current_qty, threshold: [
            product_name,
            str(current_qty),
            str(threshold),
        ],
    },
    "petha_expiry_alert": {
        "name":   "petha_expiry_alert",
        "params": lambda variety, days_left, batch_date: [
            variety,
            str(days_left),
            str(batch_date),
        ],
    },
    "daily_summary": {
        "name":   "daily_summary",
        "params": lambda orders_count, revenue, net_profit: [
            str(orders_count),
            str(revenue),
            str(net_profit),
        ],
    },
}
```

### modules/notify/service.py
```python
import logging
from modules.notify import wati
from modules.notify.templates import TEMPLATES
from core.config import settings

logger = logging.getLogger("notify")


class NotifyService:
    """
    Stateless notification service.
    All methods are fire-and-forget — they never raise.
    Called as FastAPI BackgroundTasks.
    """

    async def order_confirmed(self, order) -> None:
        """Customer: Your order LKP-2025-0042 is confirmed."""
        tmpl = TEMPLATES["order_confirmed"]
        await wati.send_template_message(
            phone=order.customer_phone,
            template=tmpl["name"],
            params=tmpl["params"](order),
        )

    async def new_order_to_owner(self, order) -> None:
        """Owner: New order received."""
        if not settings.OWNER_WHATSAPP:
            return
        tmpl = TEMPLATES["new_order_owner"]
        await wati.send_template_message(
            phone=settings.OWNER_WHATSAPP,
            template=tmpl["name"],
            params=tmpl["params"](order),
        )

    async def order_status_updated(self, order, new_status: str) -> None:
        """Customer: Your order status changed."""
        template_map = {
            "packed":           "order_packed",
            "out_for_delivery": "order_packed",
            "picked_up":        "order_ready_pickup",
            "delivered":        "order_delivered",
        }
        tmpl_name = template_map.get(new_status)
        if not tmpl_name:
            return
        tmpl = TEMPLATES[tmpl_name]
        await wati.send_template_message(
            phone=order.customer_phone,
            template=tmpl["name"],
            params=tmpl["params"](order),
        )

    async def low_stock_alert(self, product_name: str,
                               current_qty, threshold) -> None:
        """Owner: Low stock warning."""
        if not settings.OWNER_WHATSAPP:
            return
        tmpl = TEMPLATES["low_stock_alert"]
        await wati.send_template_message(
            phone=settings.OWNER_WHATSAPP,
            template=tmpl["name"],
            params=tmpl["params"](product_name, current_qty, threshold),
        )

    async def petha_expiry_alert(self, variety: str,
                                  days_left: int, batch_date) -> None:
        """Owner: Petha batch expiring soon."""
        if not settings.OWNER_WHATSAPP:
            return
        tmpl = TEMPLATES["petha_expiry_alert"]
        await wati.send_template_message(
            phone=settings.OWNER_WHATSAPP,
            template=tmpl["name"],
            params=tmpl["params"](variety, days_left, batch_date),
        )

    async def daily_summary(self, orders_count: int,
                             revenue, net_profit) -> None:
        """Owner: Daily business summary."""
        if not settings.OWNER_WHATSAPP:
            return
        tmpl = TEMPLATES["daily_summary"]
        await wati.send_template_message(
            phone=settings.OWNER_WHATSAPP,
            template=tmpl["name"],
            params=tmpl["params"](orders_count, revenue, net_profit),
        )
```

### modules/notify/router.py
```python
"""
Notify module has minimal HTTP surface.
Most notifications are triggered internally via BackgroundTasks.
This router exposes a test endpoint (dev only) and a log endpoint.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from modules.notify.models import Notification
from core.dependencies import require_owner, get_db_session
from core.config import settings

router = APIRouter(prefix="/api/notify", tags=["notify"])


@router.get("/log")
async def notification_log(
    limit  : int = 50,
    owner  : dict = Depends(require_owner),
    db     : AsyncSession = Depends(get_db_session),
):
    """Recent notification history."""
    result = await db.execute(
        select(Notification)
        .order_by(desc(Notification.created_at))
        .limit(limit)
    )
    return [
        {
            "id":             str(n.id),
            "recipient_phone": n.recipient_phone[:7] + "****",  # masked
            "recipient_type":  n.recipient_type,
            "template_name":   n.template_name,
            "status":          n.status,
            "sent_at":         n.sent_at.isoformat() if n.sent_at else None,
            "error_message":   n.error_message,
        }
        for n in result.scalars().all()
    ]


@router.post("/test")
async def send_test(owner: dict = Depends(require_owner)):
    """Dev only — sends a test WhatsApp to OWNER_WHATSAPP."""
    if settings.is_production:
        return {"error": "Not available in production"}
    from modules.notify import wati
    ok = await wati.send_template_message(
        phone=settings.OWNER_WHATSAPP or "+919999999999",
        template="order_confirmed",
        params=["TEST-0001", "Test User", "100.00", "pickup"],
    )
    return {"sent": ok, "wati_enabled": settings.WATI_ENABLED}
```

---

## DAILY SUMMARY CRON (APScheduler)

### core/scheduler.py
```python
"""
APScheduler job: sends daily P&L summary to owner at 10 PM IST.
Registered in main.py on startup.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("scheduler")
_scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


def start_scheduler(app) -> None:
    """Call from main.py startup event."""
    _scheduler.add_job(
        _daily_summary_job,
        CronTrigger(hour=22, minute=0),   # 10 PM IST
        id="daily_summary",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started: daily_summary at 22:00 IST")


async def _daily_summary_job() -> None:
    from datetime import date
    from core.database import AsyncSessionLocal
    from modules.pl_engine.service import PLService
    from modules.notify.service import NotifyService
    from decimal import Decimal

    try:
        async with AsyncSessionLocal() as db:
            month   = date.today().strftime("%Y-%m")
            pl_svc  = PLService(db=db)
            pl      = await pl_svc.get_monthly_pl(month)
            revenue = pl.get("rev_total", "0")
            profit  = pl.get("net_profit", "0")

            # Count today's orders
            from sqlalchemy import select, func
            from modules.orders.models import Order
            today   = date.today()
            count_r = await db.execute(
                select(func.count(Order.id)).where(
                    func.date(Order.created_at) == today,
                    Order.status != "cancelled",
                )
            )
            orders_today = count_r.scalar() or 0

            await NotifyService().daily_summary(orders_today, revenue, profit)
            logger.info(f"Daily summary sent: {orders_today} orders, rev={revenue}")
    except Exception as e:
        logger.error(f"Daily summary job failed: {e}")
```

---

## UPDATED main.py (add scheduler + finance router)

```python
# Add these to the existing main.py from Stage 5:

from modules.finance.router import router as finance_router
from core.scheduler import start_scheduler
from core.dependencies import register_exception_handlers

# Include finance router alongside others:
app.include_router(finance_router)

# Register custom exception handlers:
register_exception_handlers(app)

# Start scheduler on startup:
@app.on_event("startup")
async def startup():
    from core.database import run_migrations
    await run_migrations()
    start_scheduler(app)
```

---

## SHARED UTILITIES

### shared/utils.py
```python
"""Shared utility functions used across modules."""
import re
from decimal import Decimal, ROUND_HALF_UP

DP2 = Decimal("0.01")
DP5 = Decimal("0.00001")


def slugify(text: str) -> str:
    """Convert product name to URL slug: 'Joha Rice' → 'joha-rice'"""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")


def rupees(value: Decimal, dp: int = 2) -> str:
    """Format Decimal as Indian rupee string: 1234.5 → '₹1,234.50'"""
    quantized = value.quantize(Decimal(f"0.{'0'*dp}"), ROUND_HALF_UP)
    return f"₹{quantized:,}"


def mask_phone(phone: str) -> str:
    """Mask phone for logs: +919876543210 → +91987****210"""
    if len(phone) >= 10:
        return phone[:-7] + "****" + phone[-3:]
    return "****"


def current_month() -> str:
    """Returns current month as 'YYYY-MM'"""
    from datetime import date
    return date.today().strftime("%Y-%m")


def month_date_range(month: str) -> tuple:
    """Returns (start_date, end_date) for a 'YYYY-MM' month string."""
    from datetime import date
    y, m = int(month[:4]), int(month[5:7])
    import calendar
    last = calendar.monthrange(y, m)[1]
    return date(y, m, 1), date(y, m, last)
```

---

## STAGE 6 COMPLETE — BUILD ORDER

```
Step 1:  Create stubs (make app boot)
Step 2:  Build auth  → make test-unit → git commit
Step 3:  Build products + inventory → test → commit
Step 4:  Build orders → test order flow → commit
Step 5:  Build payments → test webhook → commit
Step 6:  Build pl_engine → test P&L accuracy → commit
Step 7:  Build farm → test milling yield → commit
Step 8:  Build petha → test batch cost → commit
Step 9:  Build notify → test WhatsApp (WATI disabled) → commit
Step 10: Build finance router (fixed_costs, assets) → commit
Step 11: Add scheduler (daily summary) → commit
Step 12: make test-cov → must be ≥ 75% overall, ≥ 95% pl_engine

After all 12 steps:
  make up
  make migrate
  make seed
  curl http://localhost:8000/health/ready  → {"status":"ready"}
  Open http://localhost:3000/login → admin/changeme123
  ✅ Stage 6 DONE — move to Stage 7 (Testing)
```
