import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session, require_owner
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.notify.service import NotifyService
from modules.orders.repository import OrderRepository
from modules.orders.schemas import OrderCreate, StatusUpdate
from modules.orders.service import OrderService
from modules.payments.service import PaymentService
from modules.products.repository import ProductRepository
from modules.products.service import ProductService

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _svc(db: AsyncSession = Depends(get_db_session)) -> OrderService:
    return OrderService(
        repo=OrderRepository(db),
        products=ProductService(repo=ProductRepository(db)),
        inventory=InventoryService(
            repo=InventoryRepository(db), product_repo=ProductRepository(db)
        ),
        payments=PaymentService(db),
        notify=NotifyService(),
    )


@router.post("/", status_code=201)
async def create_order(
    body: OrderCreate,
    bg: BackgroundTasks,
    svc: OrderService = Depends(_svc),
):
    """Public — online customer or owner creating manual offline order."""
    return await svc.create_order(body, bg)


@router.get("/")
async def list_orders(
    status: str | None = Query(None),
    channel: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    owner: dict = Depends(require_owner),
    svc: OrderService = Depends(_svc),
):
    return await svc.list_orders(status, channel, page, per_page)


@router.get("/{order_id}")
async def get_order(
    order_id: uuid.UUID,
    svc: OrderService = Depends(_svc),
):
    """Public — customer can track their order by UUID."""
    return await svc.get_order(order_id)


@router.patch("/{order_id}/status")
async def update_status(
    order_id: uuid.UUID,
    body: StatusUpdate,
    bg: BackgroundTasks,
    owner: dict = Depends(require_owner),
    svc: OrderService = Depends(_svc),
):
    return await svc.update_status(order_id, body, bg)
