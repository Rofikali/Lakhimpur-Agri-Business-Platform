import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session, require_owner
from modules.inventory.repository import InventoryRepository
from modules.inventory.schemas import MonthlyStockCreate, StockEntryCreate
from modules.inventory.service import InventoryService
from modules.products.repository import ProductRepository

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


def _svc(db: AsyncSession = Depends(get_db_session)) -> InventoryService:
    return InventoryService(
        repo=InventoryRepository(db),
        product_repo=ProductRepository(db),
    )


@router.get("/stock")
async def get_all_stock(
    owner: dict = Depends(require_owner),
    service: InventoryService = Depends(_svc),
):
    """Current stock level for every product."""
    from modules.products.repository import ProductRepository

    products = await ProductRepository(service.repo.db).get_all()
    result = []
    for p in products:
        stock = await service.get_current_stock(p.id)
        result.append(
            {
                "product_id": p.id,
                "product_name": p.name,
                "unit": p.unit,
                "current_qty": str(stock.current_qty),
                "low_stock_threshold": str(p.low_stock_threshold),
                "is_low": stock.current_qty < p.low_stock_threshold,
            }
        )
    return result


@router.post("/entries", status_code=201)
async def add_entry(
    body: StockEntryCreate,
    owner: dict = Depends(require_owner),
    service: InventoryService = Depends(_svc),
):
    return await service.add_stock_entry(body)


@router.get("/entries")
async def list_entries(
    product_id: uuid.UUID | None = Query(None),
    entry_type: str | None = Query(None),
    start: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end: date = Query(default_factory=date.today),
    owner: dict = Depends(require_owner),
    service: InventoryService = Depends(_svc),
):
    entries = await service.repo.list_entries(product_id, entry_type, start, end)
    return [service._entry_dict(e, None) for e in entries]


@router.post("/monthly-stock", status_code=201)
async def set_monthly_stock(
    body: MonthlyStockCreate,
    owner: dict = Depends(require_owner),
    service: InventoryService = Depends(_svc),
):
    return await service.add_monthly_stock(body)


@router.get("/monthly-stock")
async def get_monthly_stock(
    month: str = Query(pattern=r"^\d{4}-\d{2}$"),
    owner: dict = Depends(require_owner),
    service: InventoryService = Depends(_svc),
):
    entries = await service.repo.get_monthly_stock(month)
    return [
        {
            "product_id": e.product_id,
            "month": e.month,
            "stock_type": e.stock_type,
            "qty": str(e.qty),
            "value": str(e.value),
        }
        for e in entries
    ]
