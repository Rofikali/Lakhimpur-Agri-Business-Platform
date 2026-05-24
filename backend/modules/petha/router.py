# modules/orders/router.py  (and repeat for each of the 9 modules)
from fastapi import APIRouter

router = APIRouter()
# routes added here as each module is built
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session, require_owner
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.petha.repository import PethaRepository
from modules.petha.schemas import BatchCreate, BatchOutcome
from modules.petha.service import PethaService
from modules.products.repository import ProductRepository

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
    include_expired: bool = Query(False),
    owner: dict = Depends(require_owner),
    svc: PethaService = Depends(_svc),
):
    return await svc.list_batches(include_expired)


@router.post("/batches", status_code=201)
async def create_batch(
    body: BatchCreate, owner: dict = Depends(require_owner), svc: PethaService = Depends(_svc)
):
    return await svc.create_batch(body)


@router.get("/batches/expiring-soon")
async def expiring_soon(
    days: int = Query(3, ge=1, le=14),
    owner: dict = Depends(require_owner),
    svc: PethaService = Depends(_svc),
):
    return await svc.get_expiring_soon(days)


@router.get("/batches/{batch_id}")
async def get_batch(
    batch_id: uuid.UUID, owner: dict = Depends(require_owner), svc: PethaService = Depends(_svc)
):
    batch = await svc.repo.get_batch(batch_id)
    if not batch:
        from shared.exceptions import BatchNotFoundError

        raise BatchNotFoundError()
    return svc._batch_dict(batch)


@router.patch("/batches/{batch_id}/outcome")
async def record_outcome(
    batch_id: uuid.UUID,
    body: BatchOutcome,
    owner: dict = Depends(require_owner),
    svc: PethaService = Depends(_svc),
):
    return await svc.record_outcome(batch_id, body)


@router.patch("/batches/{batch_id}/expire")
async def expire_batch(
    batch_id: uuid.UUID, owner: dict = Depends(require_owner), svc: PethaService = Depends(_svc)
):
    return await svc.mark_expired(batch_id)
