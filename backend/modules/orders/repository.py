import uuid
from decimal import Decimal
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from modules.orders.models import Order, OrderItem


class OrderRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @asynccontextmanager
    async def transaction(self):
        async with self.db.begin_nested():
            yield

    async def find_by_idempotency_key(self, key: uuid.UUID) -> Order | None:
        result = await self.db.execute(
            select(Order)
            .where(Order.idempotency_key == key)
            .options(selectinload(Order.items), selectinload(Order.payment))
        )
        return result.scalar_one_or_none()

    async def get(self, order_id: uuid.UUID) -> Order | None:
        result = await self.db.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.items), selectinload(Order.payment))
        )
        return result.scalar_one_or_none()

    async def create(self, items_data: list[dict], **kwargs) -> Order:
        number = await self._next_number()
        order = Order(order_number=number, **kwargs)
        self.db.add(order)
        await self.db.flush()  # get order.id
        for i in items_data:
            self.db.add(OrderItem(order_id=order.id, **i))
        await self.db.flush()
        await self.db.refresh(order)
        # Reload with relationships
        result = await self.db.execute(
            select(Order)
            .where(Order.id == order.id)
            .options(selectinload(Order.items), selectinload(Order.payment))
        )
        return result.scalar_one()

    async def save(self, order: Order) -> Order:
        self.db.add(order)
        await self.db.flush()
        return order

    async def list_with_filters(self, status, channel, page, per_page) -> list[Order]:
        q = (
            select(Order)
            .where(Order.deleted_at.is_(None))
            .options(selectinload(Order.items), selectinload(Order.payment))
            .order_by(Order.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        if status:
            q = q.where(Order.status == status)
        if channel:
            q = q.where(Order.channel == channel)
        return list((await self.db.execute(q)).scalars().all())

    async def _next_number(self) -> str:
        year = datetime.now(timezone.utc).year
        n = (
            await self.db.execute(
                select(func.count(Order.id)).where(func.extract("year", Order.created_at) == year)
            )
        ).scalar() + 1
        return f"LKP-{year}-{n:04d}"

    @staticmethod
    def to_dict(o: Order) -> dict:
        return {
            "id": str(o.id),
            "order_number": o.order_number,
            "status": o.status,
            "channel": o.channel,
            "fulfillment_type": o.fulfillment_type,
            "customer_name": o.customer_name,
            "customer_phone": o.customer_phone,
            "total_amount": str(o.total_amount),
            "final_amount": str(o.final_amount),
            "razorpay_order_id": o.razorpay_order_id,
            "cancel_reason": o.cancel_reason,
            "created_at": o.created_at.isoformat(),
            "items": [
                {
                    "product_id": str(i.product_id),
                    "product_name": i.product_name,
                    "unit_price": str(i.unit_price),
                    "qty": str(i.qty),
                    "total": str(i.total),
                    "source": i.source,
                }
                for i in (o.items or [])
            ],
            "payment": {
                "mode": o.payment.payment_mode,
                "status": o.payment.status,
                "amount": str(o.payment.amount),
            }
            if o.payment
            else None,
        }
