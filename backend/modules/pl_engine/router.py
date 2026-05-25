# modules/orders/router.py  (and repeat for each of the 9 modules)
from fastapi import APIRouter, Depends, Query

router = APIRouter()
# routes added here as each module is builtfrom fastapi import APIRouter, Depends, Query
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from core.dependencies import get_db_session, require_owner
from modules.pl_engine.service import PLService

router = APIRouter(prefix="/api/pl", tags=["pl_engine"])


def _svc(db: AsyncSession = Depends(get_db_session)) -> PLService:
    return PLService(db=db)


@router.get("/monthly")
async def monthly_pl(
    month: str = Query(
        default_factory=lambda: date.today().strftime("%Y-%m"), pattern=r"^\d{4}-\d{2}$"
    ),
    owner: dict = Depends(require_owner),
    svc: PLService = Depends(_svc),
):
    """Full P&L statement for a month. Past months served from cache."""
    return await svc.get_monthly_pl(month)


@router.get("/breakeven/{product_id}")
async def breakeven(
    product_id: str,
    owner: dict = Depends(require_owner),
    svc: PLService = Depends(_svc),
):
    return await svc.get_breakeven(product_id)


@router.get("/margins")
async def product_margins(
    owner: dict = Depends(require_owner),
    svc: PLService = Depends(_svc),
):
    """All products ranked by margin — highest to lowest."""
    return await svc.get_product_margins()
