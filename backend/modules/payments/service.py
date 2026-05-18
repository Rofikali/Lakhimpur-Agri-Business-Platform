import uuid
import logging
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from modules.orders.models import Payment, Order
from modules.payments import razorpay as rzp_client
from core.redis import cache_get, cache_set
from shared.exceptions import WebhookSignatureInvalidError

logger = logging.getLogger("payments")


class PaymentService:
    """
    Stateless — takes db session per call.
    Called from OrderService and PaymentsRouter.
    """

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    async def create_razorpay_order(self, our_order_id: str, amount: Decimal) -> dict:
        return await rzp_client.create_razorpay_order(our_order_id, amount)

    async def create_payment_record(
        self,
        order_id: uuid.UUID,
        mode: str,
        amount: Decimal,
        rzp_order_id: str | None = None,
        credit_due_date=None,
        status: str = "pending",
    ) -> Payment:
        payment = Payment(
            order_id=order_id,
            payment_mode=mode,
            status=status,
            amount=amount,
            razorpay_order_id=rzp_order_id,
            credit_due_date=credit_due_date,
        )
        if status == "paid":
            payment.paid_at = datetime.now(timezone.utc)
        self.db.add(payment)
        await self.db.flush()
        return payment

    async def confirm_payment(
        self, order_id: uuid.UUID, rzp_payment_id: str, rzp_signature: str
    ) -> None:
        if not self.db:
            return
        result = await self.db.execute(select(Payment).where(Payment.order_id == order_id))
        payment = result.scalar_one_or_none()
        if payment and payment.status == "pending":
            payment.status = "paid"
            payment.razorpay_payment_id = rzp_payment_id
            payment.razorpay_signature = rzp_signature
            payment.paid_at = datetime.now(timezone.utc)
            self.db.add(payment)
            await self.db.flush()

    async def mark_paid(self, order_id: uuid.UUID, mode: str, credit_due_date=None) -> dict:
        if not self.db:
            raise RuntimeError("DB required for mark_paid")
        result = await self.db.execute(select(Payment).where(Payment.order_id == order_id))
        payment = result.scalar_one_or_none()
        if not payment:
            raise ValueError(f"No payment record for order {order_id}")
        payment.payment_mode = mode
        if mode == "credit":
            payment.status = "outstanding"
            payment.credit_due_date = credit_due_date
        else:
            payment.status = "paid"
            payment.paid_at = datetime.now(timezone.utc)
        self.db.add(payment)
        await self.db.flush()
        return {
            "order_id": str(order_id),
            "payment_mode": payment.payment_mode,
            "status": payment.status,
            "amount": str(payment.amount),
            "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        }

    def issue_refund(self, razorpay_payment_id: str, amount: Decimal) -> dict:
        return rzp_client.issue_refund(razorpay_payment_id, amount)
