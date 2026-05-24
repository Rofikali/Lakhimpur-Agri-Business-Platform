import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session, require_owner
from modules.farm.repository import FarmRepository
from modules.farm.schemas import FarmInputCreate, HarvestRecord, MillingRecord, SeasonCreate
from modules.farm.service import FarmService
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.products.repository import ProductRepository

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
async def create_season(
    body: SeasonCreate, owner: dict = Depends(require_owner), svc: FarmService = Depends(_svc)
):
    return await svc.create_season(body)


@router.get("/seasons/{season_id}")
async def get_season(
    season_id: uuid.UUID, owner: dict = Depends(require_owner), svc: FarmService = Depends(_svc)
):
    return await svc.get_season(season_id)


@router.post("/seasons/{season_id}/inputs", status_code=201)
async def add_input(
    season_id: uuid.UUID,
    body: FarmInputCreate,
    owner: dict = Depends(require_owner),
    svc: FarmService = Depends(_svc),
):
    return await svc.add_input(season_id, body)


@router.post("/seasons/{season_id}/harvest")
async def record_harvest(
    season_id: uuid.UUID,
    body: HarvestRecord,
    owner: dict = Depends(require_owner),
    svc: FarmService = Depends(_svc),
):
    return await svc.record_harvest(season_id, body)


@router.post("/seasons/{season_id}/milling")
async def record_milling(
    season_id: uuid.UUID,
    body: MillingRecord,
    owner: dict = Depends(require_owner),
    svc: FarmService = Depends(_svc),
):
    return await svc.record_milling(season_id, body)


@router.patch("/seasons/{season_id}/complete")
async def complete_season(
    season_id: uuid.UUID, owner: dict = Depends(require_owner), svc: FarmService = Depends(_svc)
):
    return await svc.complete_season(season_id)


class FailReason(BaseModel):
    reason: str


@router.patch("/seasons/{season_id}/fail")
async def fail_season(
    season_id: uuid.UUID,
    body: FailReason,
    owner: dict = Depends(require_owner),
    svc: FarmService = Depends(_svc),
):
    return await svc.mark_failed(season_id, body.reason)
