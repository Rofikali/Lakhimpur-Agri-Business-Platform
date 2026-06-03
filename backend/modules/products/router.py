import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session, optional_owner, require_owner
from modules.products.repository import ProductRepository
from modules.products.schemas import ProductCreate, ProductUpdate
from modules.products.service import ProductService

router = APIRouter(prefix="/api/products", tags=["products"])


def _svc(db: AsyncSession = Depends(get_db_session)) -> ProductService:
    return ProductService(repo=ProductRepository(db))


@router.get("/")
async def list_products(
    service: ProductService = Depends(_svc),
    owner: dict | None = Depends(optional_owner),
):
    """Owner sees all (inc inactive). Public sees active only."""
    return await service.list_products(owner=owner is not None)


@router.get("/{product_id}")
async def get_product(
    product_id: uuid.UUID,
    service: ProductService = Depends(_svc),
):
    return await service.get_product(product_id)


@router.post("/", status_code=201)
async def create_product(
    body: ProductCreate,
    owner: dict = Depends(require_owner),
    service: ProductService = Depends(_svc),
):
    return await service.create_product(body)


@router.patch("/{product_id}")
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    owner: dict = Depends(require_owner),
    service: ProductService = Depends(_svc),
):
    return await service.update_product(product_id, body)


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: uuid.UUID,
    owner: dict = Depends(require_owner),
    service: ProductService = Depends(_svc),
):
    await service.soft_delete(product_id)
