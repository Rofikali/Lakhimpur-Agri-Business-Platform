import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session, require_owner
from core.redis import cache_get, cache_set
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.notify.service import NotifyService
from modules.orders.repository import OrderRepository
from modules.orders.service import OrderService
from modules.payments import razorpay as rzp_client
from modules.payments.schemas import MarkPaidRequest
from modules.payments.service import PaymentService
from modules.products.repository import ProductRepository
from modules.products.service import ProductService
from shared.exceptions import WebhookSignatureInvalidError

logger = logging.getLogger("payments")
router = APIRouter(prefix="/api/payments", tags=["payments"])

WEBHOOK_IDEMPOTENCY_TTL = 7 * 24 * 3600  # 7 days


def _svc(db: AsyncSession = Depends(get_db_session)) -> PaymentService:
    return PaymentService(db=db)


def _order_svc(db: AsyncSession = Depends(get_db_session)) -> OrderService:
    return OrderService(
        repo=OrderRepository(db),
        products=ProductService(repo=ProductRepository(db)),
        inventory=InventoryService(
            repo=InventoryRepository(db), product_repo=ProductRepository(db)
        ),
        payments=PaymentService(db=db),
        notify=NotifyService(),
    )


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    bg: BackgroundTasks,
    svc: PaymentService = Depends(_svc),
    order_svc: OrderService = Depends(_order_svc),
):
    """
    Razorpay sends webhooks here.
    CRITICAL: Must return 200 quickly — BG tasks run after response.
    CRITICAL: Must be idempotent — Razorpay retries for 24 hours.
    """
    body = await request.body()
    sig = request.headers.get("X-Razorpay-Signature", "")

    # ── Step 1: Verify HMAC signature ──────────────────────────────────────
    try:
        rzp_client.verify_webhook_signature(body, sig)
    except WebhookSignatureInvalidError:
        logger.warning("Webhook HMAC failed — possible spoofing attempt")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "WEBHOOK_SIGNATURE_INVALID",
                "message": "Invalid webhook signature",
            },
        )

    payload = json.loads(body)
    event = payload.get("event", "")

    if event != "payment.captured":
        return {"status": "ok", "note": "event_ignored"}

    payment_entity = payload["payload"]["payment"]["entity"]
    rzp_payment_id = payment_entity["id"]
    rzp_order_id = payment_entity.get("order_id", "")

    # ── Step 2: Idempotency check ───────────────────────────────────────────
    idem_key = f"webhook:rzp:{rzp_payment_id}"
    if await cache_get(idem_key):
        logger.info(f"Duplicate webhook ignored: {rzp_payment_id}")
        return {"status": "ok", "note": "already_processed"}

    await cache_set(idem_key, "1", ttl=WEBHOOK_IDEMPOTENCY_TTL)

    # ── Step 3: Find our order by Razorpay order_id ─────────────────────────
    from sqlalchemy import select

    from modules.orders.models import Order

    result = await svc.db.execute(select(Order).where(Order.razorpay_order_id == rzp_order_id))
    order = result.scalar_one_or_none()
    if not order:
        logger.error(f"Webhook: no order found for rzp_order_id={rzp_order_id}")
        return {"status": "ok", "note": "order_not_found"}

    # ── Step 4: Confirm order + decrement stock (atomic) ───────────────────
    bg.add_task(
        order_svc.confirm_from_webhook,
        order.id,
        rzp_payment_id,
        sig,
        bg,
    )

    return {"status": "ok"}


@router.patch("/{order_id}/mark-paid")
async def mark_paid(
    order_id: uuid.UUID,
    body: MarkPaidRequest,
    owner: dict = Depends(require_owner),
    svc: PaymentService = Depends(_svc),
):
    """Owner marks an offline order as paid (cash/UPI/credit)."""
    return await svc.mark_paid(order_id, body.payment_mode, body.credit_due_date)


@router.get("/outstanding")
async def outstanding_credits(
    owner: dict = Depends(require_owner),
    db: AsyncSession = Depends(get_db_session),
):
    """All credit sales not yet collected."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from modules.orders.models import Payment

    result = await db.execute(
        select(Payment)
        .where(Payment.status == "outstanding")
        .options(selectinload(Payment.order))
        .order_by(Payment.credit_due_date.asc().nullslast())
    )
    payments = result.scalars().all()
    return [
        {
            "order_id": str(p.order_id),
            "order_number": p.order.order_number if p.order else "",
            "customer_name": p.order.customer_name if p.order else "",
            "customer_phone": p.order.customer_phone if p.order else "",
            "amount": str(p.amount),
            "credit_due_date": p.credit_due_date.isoformat() if p.credit_due_date else None,
        }
        for p in payments
    ]
