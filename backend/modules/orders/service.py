import uuid
from decimal import Decimal
from datetime import datetime, timezone
from fastapi import BackgroundTasks
from modules.orders.repository import OrderRepository
from modules.orders.schemas import OrderCreate, StatusUpdate
from modules.products.service import ProductService
from modules.payments.service import PaymentService
from modules.notify.service import NotifyService
from modules.inventory.service import InventoryService
from shared.exceptions import (
    OrderNotFoundError,
    OrderAlreadyCancelledError,
    InvalidStatusTransitionError,
    StockInsufficientError,
)

# Valid status transitions
ALLOWED_TRANSITIONS = {
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"packed", "cancelled"},
    "packed": {"out_for_delivery", "picked_up", "cancelled"},
    "out_for_delivery": {"delivered", "cancelled"},
    "delivered": {"completed"},
    "picked_up": {"completed"},
    "completed": set(),
    "cancelled": set(),
}


class OrderService:
    def __init__(
        self,
        repo: OrderRepository,
        products: ProductService,
        inventory: InventoryService,
        payments: PaymentService,
        notify: NotifyService,
    ):
        self.repo = repo
        self.products = products
        self.inventory = inventory
        self.payments = payments
        self.notify = notify

    async def create_order(self, data: OrderCreate, bg: BackgroundTasks) -> dict:
        # ── Idempotency check ──────────────────────────────────────────────────
        existing = await self.repo.find_by_idempotency_key(data.idempotency_key)
        if existing:
            return self.repo.to_dict(existing)

        # ── Validate products + stock ──────────────────────────────────────────
        items_data, total = [], Decimal("0")
        for item in data.items:
            product = await self.products.get_active(item.product_id)
            stock = await self.inventory.get_current_stock(item.product_id)
            if stock.current_qty < item.qty:
                raise StockInsufficientError(product.name, stock.current_qty, item.qty)
            line = item.qty * product.sell_price
            total += line
            items_data.append(
                {
                    "product_id": item.product_id,
                    "product_name": product.name,
                    "unit_price": product.sell_price,
                    "qty": item.qty,
                    "total": line,
                    "source": item.source,
                }
            )

        # ── Create order (status=pending, stock not yet decremented) ───────────
        order = await self.repo.create(
            idempotency_key=data.idempotency_key,
            customer_name=data.customer_name,
            customer_phone=data.customer_phone,
            customer_address=data.customer_address,
            fulfillment_type=data.fulfillment_type,
            channel=data.channel,
            total_amount=total,
            final_amount=total,
            items_data=items_data,
        )

        # ── Online → Razorpay ──────────────────────────────────────────────────
        if data.payment_mode == "razorpay":
            rzp = await self.payments.create_razorpay_order(str(order.id), total)
            order.razorpay_order_id = rzp["id"]
            await self.repo.save(order)
            # Payment record
            await self.payments.create_payment_record(
                order_id=order.id,
                mode="razorpay",
                amount=total,
                rzp_order_id=rzp["id"],
            )

        # ── Offline/cash → confirm immediately ────────────────────────────────
        else:
            await self._confirm_and_decrement(order, bg)
            credit_due = data.credit_due_date if data.payment_mode == "credit" else None
            await self.payments.create_payment_record(
                order_id=order.id,
                mode=data.payment_mode,
                amount=total,
                credit_due_date=credit_due,
                status="outstanding" if data.payment_mode == "credit" else "paid",
            )

        return self.repo.to_dict(order)

    async def confirm_from_webhook(
        self, order_id: uuid.UUID, rzp_payment_id: str, rzp_signature: str, bg: BackgroundTasks
    ) -> None:
        """Called by payments webhook after HMAC verification."""
        order = await self.repo.get(order_id)
        if not order or order.status != "pending":
            return  # Already confirmed or doesn't exist — idempotent
        await self._confirm_and_decrement(order, bg)
        await self.payments.confirm_payment(
            order_id=order_id,
            rzp_payment_id=rzp_payment_id,
            rzp_signature=rzp_signature,
        )

    async def _confirm_and_decrement(self, order, bg: BackgroundTasks) -> None:
        """Atomic: confirm order + decrement stock for all items."""
        async with self.repo.transaction():
            order.status = "confirmed"
            await self.repo.save(order)
            for item in order.items:
                await self.inventory.decrement_stock(
                    product_id=item.product_id,
                    qty=item.qty,
                    order_id=order.id,
                )
        # Notifications after commit (non-blocking)
        bg.add_task(self.notify.order_confirmed, order)
        bg.add_task(self.notify.new_order_to_owner, order)

    async def update_status(
        self, order_id: uuid.UUID, data: StatusUpdate, bg: BackgroundTasks
    ) -> dict:
        order = await self.repo.get(order_id)
        if not order:
            raise OrderNotFoundError(str(order_id))

        allowed = ALLOWED_TRANSITIONS.get(order.status, set())
        if data.status not in allowed:
            raise InvalidStatusTransitionError(order.status, data.status)

        old_status = order.status
        order.status = data.status

        if data.status == "cancelled":
            if old_status in ("confirmed", "packed"):
                # Restore stock for all items
                async with self.repo.transaction():
                    order.cancel_reason = data.cancel_reason
                    await self.repo.save(order)
                    for item in order.items:
                        await self.inventory.restore_stock(item.product_id, item.qty)
            else:
                order.cancel_reason = data.cancel_reason
                await self.repo.save(order)
        else:
            await self.repo.save(order)

        # Notify customer on key transitions
        if data.status in ("packed", "out_for_delivery", "delivered", "picked_up"):
            bg.add_task(self.notify.order_status_updated, order, data.status)

        return self.repo.to_dict(order)

    async def get_order(self, order_id: uuid.UUID) -> dict:
        order = await self.repo.get(order_id)
        if not order:
            raise OrderNotFoundError(str(order_id))
        return self.repo.to_dict(order)

    async def list_orders(
        self, status: str | None, channel: str | None, page: int, per_page: int
    ) -> list[dict]:
        orders = await self.repo.list_with_filters(status, channel, page, per_page)
        return [self.repo.to_dict(o) for o in orders]
