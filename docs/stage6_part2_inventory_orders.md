# Stage 6 · Code · Part 2 — Inventory + Orders modules

---

## MODULE 3 — INVENTORY

### modules/inventory/schemas.py
```python
import uuid
from decimal import Decimal
from datetime import date
from typing import Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class StockEntryCreate(BaseModel):
    idempotency_key : uuid.UUID
    product_id      : uuid.UUID
    entry_type      : str   = Field(pattern=r"^(sale|purchase|wastage_normal|wastage_abnormal|consumption|opening_stock|closing_stock|production|capex|fixed_cost|provision)$")
    qty             : Decimal
    unit_cost       : Decimal | None = None
    total_amount    : Decimal
    source          : str | None = None
    channel         : str | None = None
    pay_mode        : str | None = None
    wastage_type    : str | None = None
    reference_id    : uuid.UUID | None = None
    reference_type  : str | None = None
    date            : date
    note            : str | None = None

    @field_validator("qty", "unit_cost", "total_amount", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal | None:
        if v is None: return None
        if isinstance(v, float): raise ValueError("Never use float for money or quantity")
        return Decimal(str(v))


class StockEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id              : uuid.UUID
    product_id      : uuid.UUID
    entry_type      : str
    qty             : str
    unit_cost       : str | None
    total_amount    : str
    price_variance  : str | None
    cost_variance   : str | None
    new_stock_qty   : str
    date            : date

    @field_validator("qty","total_amount","price_variance",
                     "cost_variance","new_stock_qty","unit_cost", mode="before")
    @classmethod
    def to_str(cls, v: Any) -> str | None:
        return str(v) if v is not None else None


class MonthlyStockCreate(BaseModel):
    product_id : uuid.UUID
    month      : str   = Field(pattern=r"^\d{4}-\d{2}$")
    stock_type : str   = Field(pattern=r"^(opening|closing)$")
    qty        : Decimal
    value      : Decimal

    @field_validator("qty","value", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float): raise ValueError("Never use float")
        return Decimal(str(v))


class CurrentStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id  : uuid.UUID
    current_qty : str
    updated_at  : Any

    @field_validator("current_qty", mode="before")
    @classmethod
    def to_str(cls, v: Any) -> str:
        return str(v)
```

### modules/inventory/repository.py
```python
import uuid
from decimal import Decimal
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from modules.inventory.models import StockEntry, InventoryStock, MonthlyStock


class InventoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Current stock ─────────────────────────────────────────────────────────

    async def get_stock(self, product_id: uuid.UUID) -> InventoryStock | None:
        result = await self.db.execute(
            select(InventoryStock).where(InventoryStock.product_id == product_id)
        )
        return result.scalar_one_or_none()

    async def get_stock_locked(self, product_id: uuid.UUID) -> InventoryStock | None:
        """SELECT FOR UPDATE — use inside atomic transaction to prevent race."""
        result = await self.db.execute(
            select(InventoryStock)
            .where(InventoryStock.product_id == product_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def update_stock(self, stock: InventoryStock) -> InventoryStock:
        self.db.add(stock)
        await self.db.flush()
        return stock

    # ── Stock entries ─────────────────────────────────────────────────────────

    async def find_entry_by_idempotency(self, key: uuid.UUID) -> StockEntry | None:
        result = await self.db.execute(
            select(StockEntry).where(StockEntry.idempotency_key == key)
        )
        return result.scalar_one_or_none()

    async def create_entry(self, **kwargs) -> StockEntry:
        entry = StockEntry(**kwargs)
        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)
        return entry

    async def list_entries(self, product_id: uuid.UUID | None,
                           entry_type: str | None,
                           start: date, end: date) -> list[StockEntry]:
        q = select(StockEntry).where(
            StockEntry.deleted_at.is_(None),
            StockEntry.date.between(start, end),
        )
        if product_id: q = q.where(StockEntry.product_id == product_id)
        if entry_type: q = q.where(StockEntry.entry_type == entry_type)
        q = q.order_by(StockEntry.date.desc(), StockEntry.created_at.desc())
        return list((await self.db.execute(q)).scalars().all())

    async def fetch_for_month(self, month: str) -> list[StockEntry]:
        """Fetch all entries for a given YYYY-MM month."""
        from datetime import date as dt
        y, m = int(month[:4]), int(month[5:7])
        last_day = [31,28+int((y%4==0 and y%100!=0)or y%400==0),
                    31,30,31,30,31,31,30,31,30,31][m-1]
        start = dt(y, m, 1)
        end   = dt(y, m, last_day)
        result = await self.db.execute(
            select(StockEntry).where(
                StockEntry.deleted_at.is_(None),
                StockEntry.date.between(start, end),
            )
        )
        return list(result.scalars().all())

    # ── Monthly stock ─────────────────────────────────────────────────────────

    async def get_monthly_stock(self, month: str) -> list[MonthlyStock]:
        result = await self.db.execute(
            select(MonthlyStock).where(MonthlyStock.month == month)
        )
        return list(result.scalars().all())

    async def upsert_monthly_stock(self, product_id: uuid.UUID, month: str,
                                   stock_type: str, qty: Decimal,
                                   value: Decimal) -> MonthlyStock:
        existing = await self.db.execute(
            select(MonthlyStock).where(
                MonthlyStock.product_id == product_id,
                MonthlyStock.month == month,
                MonthlyStock.stock_type == stock_type,
            )
        )
        ms = existing.scalar_one_or_none()
        if ms:
            ms.qty   = qty
            ms.value = value
        else:
            ms = MonthlyStock(product_id=product_id, month=month,
                              stock_type=stock_type, qty=qty, value=value)
            self.db.add(ms)
        await self.db.flush()
        return ms
```

### modules/inventory/service.py
```python
import uuid
from decimal import Decimal
from datetime import date
from modules.inventory.repository import InventoryRepository
from modules.inventory.schemas import StockEntryCreate, MonthlyStockCreate
from modules.inventory.models import InventoryStock
from modules.products.repository import ProductRepository
from shared.exceptions import (
    StockInsufficientError, StockNegativeError,
    ClosingStockExceedsMaxError, ProductNotFoundError,
)
from core.redis import cache_delete, should_send_alert


class InventoryService:
    def __init__(self, repo: InventoryRepository,
                 product_repo: ProductRepository | None = None):
        self.repo         = repo
        self.product_repo = product_repo

    async def get_current_stock(self, product_id: uuid.UUID) -> InventoryStock:
        stock = await self.repo.get_stock(product_id)
        if stock is None:
            # Auto-create if missing (shouldn't happen after seed)
            stock = InventoryStock(product_id=product_id, current_qty=Decimal("0"))
            self.repo.db.add(stock)
            await self.repo.db.flush()
        return stock

    async def decrement_stock(self, product_id: uuid.UUID,
                               qty: Decimal, order_id: uuid.UUID) -> InventoryStock:
        """Called inside an atomic transaction. Uses row lock."""
        stock = await self.repo.get_stock_locked(product_id)
        if not stock:
            raise StockInsufficientError("product", Decimal("0"), qty)
        if stock.current_qty < qty:
            raise StockInsufficientError("product", stock.current_qty, qty)
        stock.current_qty -= qty
        await self.repo.update_stock(stock)
        await cache_delete(f"products:stock:{product_id}")
        return stock

    async def restore_stock(self, product_id: uuid.UUID, qty: Decimal) -> None:
        """Called when order is cancelled. Restores decremented stock."""
        stock = await self.repo.get_stock_locked(product_id)
        if stock:
            stock.current_qty += qty
            await self.repo.update_stock(stock)
            await cache_delete(f"products:stock:{product_id}")

    async def add_stock_entry(self, data: StockEntryCreate) -> dict:
        # Idempotency
        existing = await self.repo.find_entry_by_idempotency(data.idempotency_key)
        if existing:
            stock = await self.repo.get_stock(data.product_id)
            return self._entry_dict(existing, stock)

        # Load product for standard cost reference
        product = None
        if self.product_repo:
            product = await self.product_repo.get_by_id(data.product_id)
            if not product:
                raise ProductNotFoundError(str(data.product_id))

        # Calculate variances
        price_variance = None
        cost_variance  = None
        unit_cost      = data.unit_cost

        if data.entry_type == "sale" and product and data.qty > 0:
            actual_unit = data.total_amount / data.qty
            price_variance = (actual_unit - product.sell_price) * data.qty

        if data.entry_type == "purchase" and product and data.qty > 0:
            unit_cost     = data.total_amount / data.qty
            cost_variance = (unit_cost - product.true_cost) * data.qty

        # Create the entry
        entry = await self.repo.create_entry(
            idempotency_key=data.idempotency_key,
            product_id=data.product_id,
            entry_type=data.entry_type,
            qty=data.qty,
            unit_cost=unit_cost,
            total_amount=data.total_amount,
            standard_unit_cost=product.true_cost if product else None,
            price_variance=price_variance,
            cost_variance=cost_variance,
            source=data.source,
            channel=data.channel,
            pay_mode=data.pay_mode,
            reference_id=data.reference_id,
            reference_type=data.reference_type,
            date=data.date,
            note=data.note,
        )

        # Adjust live stock for purchase and production
        stock = await self.repo.get_stock(data.product_id)
        if stock and data.entry_type in ("purchase", "production"):
            stock.current_qty += data.qty
            await self.repo.update_stock(stock)
            await cache_delete(f"products:stock:{data.product_id}")

            # Check low-stock threshold alert
            if product and stock.current_qty < product.low_stock_threshold:
                if await should_send_alert("low_stock", str(data.product_id)):
                    # Notify is handled by caller or background task
                    entry.low_stock_alert = True

        return self._entry_dict(entry, stock)

    async def add_monthly_stock(self, data: MonthlyStockCreate) -> dict:
        # Validate closing stock doesn't exceed possible maximum
        if data.stock_type == "closing":
            entries = await self.repo.fetch_for_month(data.month)
            received = sum(
                (e.qty for e in entries if e.entry_type in ("purchase","production")),
                Decimal("0"),
            )
            monthly = await self.repo.get_monthly_stock(data.month)
            opening = sum(
                (m.qty for m in monthly if m.stock_type == "opening"
                 and str(m.product_id) == str(data.product_id)),
                Decimal("0"),
            )
            max_possible = opening + received
            if data.qty > max_possible:
                raise ClosingStockExceedsMaxError(data.qty, max_possible)

        ms = await self.repo.upsert_monthly_stock(
            product_id=data.product_id,
            month=data.month,
            stock_type=data.stock_type,
            qty=data.qty,
            value=data.value,
        )
        return {"product_id": ms.product_id, "month": ms.month,
                "stock_type": ms.stock_type, "qty": str(ms.qty), "value": str(ms.value)}

    def _entry_dict(self, entry, stock) -> dict:
        return {
            "id":            entry.id,
            "product_id":    entry.product_id,
            "entry_type":    entry.entry_type,
            "qty":           str(entry.qty),
            "unit_cost":     str(entry.unit_cost) if entry.unit_cost else None,
            "total_amount":  str(entry.total_amount),
            "price_variance":str(entry.price_variance) if entry.price_variance else None,
            "cost_variance": str(entry.cost_variance)  if entry.cost_variance  else None,
            "new_stock_qty": str(stock.current_qty) if stock else "0.000",
            "date":          entry.date,
        }
```

### modules/inventory/router.py
```python
import uuid
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from modules.inventory.schemas import StockEntryCreate, MonthlyStockCreate
from modules.inventory.service import InventoryService
from modules.inventory.repository import InventoryRepository
from modules.products.repository import ProductRepository
from core.dependencies import require_owner, get_db_session

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


def _svc(db: AsyncSession = Depends(get_db_session)) -> InventoryService:
    return InventoryService(
        repo=InventoryRepository(db),
        product_repo=ProductRepository(db),
    )


@router.get("/stock")
async def get_all_stock(
    owner   : dict = Depends(require_owner),
    service : InventoryService = Depends(_svc),
):
    """Current stock level for every product."""
    from modules.products.repository import ProductRepository
    products = await ProductRepository(service.repo.db).get_all()
    result = []
    for p in products:
        stock = await service.get_current_stock(p.id)
        result.append({
            "product_id": p.id, "product_name": p.name,
            "unit": p.unit, "current_qty": str(stock.current_qty),
            "low_stock_threshold": str(p.low_stock_threshold),
            "is_low": stock.current_qty < p.low_stock_threshold,
        })
    return result


@router.post("/entries", status_code=201)
async def add_entry(
    body    : StockEntryCreate,
    owner   : dict = Depends(require_owner),
    service : InventoryService = Depends(_svc),
):
    return await service.add_stock_entry(body)


@router.get("/entries")
async def list_entries(
    product_id : uuid.UUID | None = Query(None),
    entry_type : str | None       = Query(None),
    start      : date             = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end        : date             = Query(default_factory=date.today),
    owner      : dict = Depends(require_owner),
    service    : InventoryService = Depends(_svc),
):
    entries = await service.repo.list_entries(product_id, entry_type, start, end)
    return [service._entry_dict(e, None) for e in entries]


@router.post("/monthly-stock", status_code=201)
async def set_monthly_stock(
    body    : MonthlyStockCreate,
    owner   : dict = Depends(require_owner),
    service : InventoryService = Depends(_svc),
):
    return await service.add_monthly_stock(body)


@router.get("/monthly-stock")
async def get_monthly_stock(
    month   : str  = Query(pattern=r"^\d{4}-\d{2}$"),
    owner   : dict = Depends(require_owner),
    service : InventoryService = Depends(_svc),
):
    entries = await service.repo.get_monthly_stock(month)
    return [{"product_id": e.product_id, "month": e.month,
             "stock_type": e.stock_type, "qty": str(e.qty),
             "value": str(e.value)} for e in entries]
```

---

## MODULE 4 — ORDERS

### modules/orders/models.py
```python
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Numeric, TIMESTAMP, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column, Mapped, relationship
from shared.models.base import Base, MONEY, QTY


class Order(Base):
    __tablename__ = "orders"

    id               : Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key  : Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    order_number     : Mapped[str]       = mapped_column(String(20), unique=True, nullable=False)
    customer_name    : Mapped[str]       = mapped_column(String(200), nullable=False)
    customer_phone   : Mapped[str]       = mapped_column(String(15),  nullable=False)
    customer_address : Mapped[str|None]  = mapped_column(Text, nullable=True)
    fulfillment_type : Mapped[str]       = mapped_column(String(20), nullable=False)
    channel          : Mapped[str]       = mapped_column(String(20), nullable=False)
    status           : Mapped[str]       = mapped_column(String(30), nullable=False, default="pending")
    total_amount     : Mapped[Decimal]   = mapped_column(MONEY, nullable=False)
    discount_amount  : Mapped[Decimal]   = mapped_column(MONEY, default=Decimal("0"))
    final_amount     : Mapped[Decimal]   = mapped_column(MONEY, nullable=False)
    cancel_reason    : Mapped[str|None]  = mapped_column(Text, nullable=True)
    razorpay_order_id: Mapped[str|None]  = mapped_column(String(100), nullable=True)
    created_at       : Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True),
                                                         default=lambda: datetime.now(timezone.utc))
    updated_at       : Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True),
                                                         default=lambda: datetime.now(timezone.utc),
                                                         onupdate=lambda: datetime.now(timezone.utc))
    deleted_at       : Mapped[datetime|None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    items   : Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all")
    payment : Mapped["Payment|None"]    = relationship("Payment", back_populates="order", uselist=False)


class OrderItem(Base):
    __tablename__ = "order_items"

    id           : Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id     : Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), nullable=False)
    product_id   : Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    product_name : Mapped[str]       = mapped_column(String(200), nullable=False)  # snapshot
    unit_price   : Mapped[Decimal]   = mapped_column(MONEY, nullable=False)        # snapshot
    qty          : Mapped[Decimal]   = mapped_column(QTY,  nullable=False)
    total        : Mapped[Decimal]   = mapped_column(MONEY, nullable=False)
    source       : Mapped[str]       = mapped_column(String(20), default="own")
    order        = relationship("Order", back_populates="items")


class Payment(Base):
    __tablename__ = "payments"

    id                  : Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id            : Mapped[uuid.UUID]     = mapped_column(ForeignKey("orders.id"), unique=True)
    payment_mode        : Mapped[str]           = mapped_column(String(30), nullable=False)
    status              : Mapped[str]           = mapped_column(String(30), default="pending")
    amount              : Mapped[Decimal]       = mapped_column(MONEY, nullable=False)
    razorpay_order_id   : Mapped[str|None]      = mapped_column(String(100), nullable=True)
    razorpay_payment_id : Mapped[str|None]      = mapped_column(String(100), unique=True, nullable=True)
    razorpay_signature  : Mapped[str|None]      = mapped_column(String(300), nullable=True)
    credit_due_date     : Mapped[datetime|None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    paid_at             : Mapped[datetime|None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    refunded_at         : Mapped[datetime|None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at          : Mapped[datetime]      = mapped_column(TIMESTAMP(timezone=True),
                                                               default=lambda: datetime.now(timezone.utc))
    updated_at          : Mapped[datetime]      = mapped_column(TIMESTAMP(timezone=True),
                                                               default=lambda: datetime.now(timezone.utc))
    order = relationship("Order", back_populates="payment")
```

### modules/orders/service.py
```python
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
    OrderNotFoundError, OrderAlreadyCancelledError, InvalidStatusTransitionError,
    StockInsufficientError,
)

# Valid status transitions
ALLOWED_TRANSITIONS = {
    "pending"         : {"confirmed", "cancelled"},
    "confirmed"       : {"packed",    "cancelled"},
    "packed"          : {"out_for_delivery", "picked_up", "cancelled"},
    "out_for_delivery": {"delivered", "cancelled"},
    "delivered"       : {"completed"},
    "picked_up"       : {"completed"},
    "completed"       : set(),
    "cancelled"       : set(),
}


class OrderService:
    def __init__(self, repo: OrderRepository, products: ProductService,
                 inventory: InventoryService, payments: PaymentService,
                 notify: NotifyService):
        self.repo      = repo
        self.products  = products
        self.inventory = inventory
        self.payments  = payments
        self.notify    = notify

    async def create_order(self, data: OrderCreate, bg: BackgroundTasks) -> dict:
        # ── Idempotency check ──────────────────────────────────────────────────
        existing = await self.repo.find_by_idempotency_key(data.idempotency_key)
        if existing:
            return self.repo.to_dict(existing)

        # ── Validate products + stock ──────────────────────────────────────────
        items_data, total = [], Decimal("0")
        for item in data.items:
            product = await self.products.get_active(item.product_id)
            stock   = await self.inventory.get_current_stock(item.product_id)
            if stock.current_qty < item.qty:
                raise StockInsufficientError(product.name, stock.current_qty, item.qty)
            line = item.qty * product.sell_price
            total += line
            items_data.append({
                "product_id":   item.product_id,
                "product_name": product.name,
                "unit_price":   product.sell_price,
                "qty":          item.qty,
                "total":        line,
                "source":       item.source,
            })

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
                order_id=order.id, mode="razorpay",
                amount=total, rzp_order_id=rzp["id"],
            )

        # ── Offline/cash → confirm immediately ────────────────────────────────
        else:
            await self._confirm_and_decrement(order, bg)
            credit_due = data.credit_due_date if data.payment_mode == "credit" else None
            await self.payments.create_payment_record(
                order_id=order.id, mode=data.payment_mode,
                amount=total, credit_due_date=credit_due,
                status="outstanding" if data.payment_mode == "credit" else "paid",
            )

        return self.repo.to_dict(order)

    async def confirm_from_webhook(self, order_id: uuid.UUID,
                                   rzp_payment_id: str,
                                   rzp_signature: str,
                                   bg: BackgroundTasks) -> None:
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

    async def update_status(self, order_id: uuid.UUID,
                            data: StatusUpdate, bg: BackgroundTasks) -> dict:
        order = await self.repo.get(order_id)
        if not order:
            raise OrderNotFoundError(str(order_id))

        allowed = ALLOWED_TRANSITIONS.get(order.status, set())
        if data.status not in allowed:
            raise InvalidStatusTransitionError(order.status, data.status)

        old_status  = order.status
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

    async def list_orders(self, status: str | None, channel: str | None,
                          page: int, per_page: int) -> list[dict]:
        orders = await self.repo.list_with_filters(status, channel, page, per_page)
        return [self.repo.to_dict(o) for o in orders]
```

### modules/orders/repository.py
```python
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
        order  = Order(order_number=number, **kwargs)
        self.db.add(order)
        await self.db.flush()  # get order.id
        for i in items_data:
            self.db.add(OrderItem(order_id=order.id, **i))
        await self.db.flush()
        await self.db.refresh(order)
        # Reload with relationships
        result = await self.db.execute(
            select(Order).where(Order.id == order.id)
            .options(selectinload(Order.items), selectinload(Order.payment))
        )
        return result.scalar_one()

    async def save(self, order: Order) -> Order:
        self.db.add(order)
        await self.db.flush()
        return order

    async def list_with_filters(self, status, channel, page, per_page) -> list[Order]:
        q = (select(Order)
             .where(Order.deleted_at.is_(None))
             .options(selectinload(Order.items), selectinload(Order.payment))
             .order_by(Order.created_at.desc())
             .offset((page - 1) * per_page).limit(per_page))
        if status:  q = q.where(Order.status  == status)
        if channel: q = q.where(Order.channel == channel)
        return list((await self.db.execute(q)).scalars().all())

    async def _next_number(self) -> str:
        year = datetime.now(timezone.utc).year
        n = (await self.db.execute(
            select(func.count(Order.id))
            .where(func.extract("year", Order.created_at) == year)
        )).scalar() + 1
        return f"LKP-{year}-{n:04d}"

    @staticmethod
    def to_dict(o: Order) -> dict:
        return {
            "id":                 str(o.id),
            "order_number":       o.order_number,
            "status":             o.status,
            "channel":            o.channel,
            "fulfillment_type":   o.fulfillment_type,
            "customer_name":      o.customer_name,
            "customer_phone":     o.customer_phone,
            "total_amount":       str(o.total_amount),
            "final_amount":       str(o.final_amount),
            "razorpay_order_id":  o.razorpay_order_id,
            "cancel_reason":      o.cancel_reason,
            "created_at":         o.created_at.isoformat(),
            "items": [
                {
                    "product_id":   str(i.product_id),
                    "product_name": i.product_name,
                    "unit_price":   str(i.unit_price),
                    "qty":          str(i.qty),
                    "total":        str(i.total),
                    "source":       i.source,
                }
                for i in (o.items or [])
            ],
            "payment": {
                "mode":   o.payment.payment_mode,
                "status": o.payment.status,
                "amount": str(o.payment.amount),
            } if o.payment else None,
        }
```

### modules/orders/router.py
```python
import uuid
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from modules.orders.schemas import OrderCreate, StatusUpdate
from modules.orders.service import OrderService
from modules.orders.repository import OrderRepository
from modules.products.service import ProductService
from modules.products.repository import ProductRepository
from modules.inventory.service import InventoryService
from modules.inventory.repository import InventoryRepository
from modules.payments.service import PaymentService
from modules.notify.service import NotifyService
from core.dependencies import require_owner, get_db_session

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _svc(db: AsyncSession = Depends(get_db_session)) -> OrderService:
    return OrderService(
        repo      = OrderRepository(db),
        products  = ProductService(repo=ProductRepository(db)),
        inventory = InventoryService(repo=InventoryRepository(db),
                                     product_repo=ProductRepository(db)),
        payments  = PaymentService(),
        notify    = NotifyService(),
    )


@router.post("/", status_code=201)
async def create_order(
    body : OrderCreate,
    bg   : BackgroundTasks,
    svc  : OrderService = Depends(_svc),
):
    """Public — online customer or owner creating manual offline order."""
    return await svc.create_order(body, bg)


@router.get("/")
async def list_orders(
    status   : str | None = Query(None),
    channel  : str | None = Query(None),
    page     : int        = Query(1, ge=1),
    per_page : int        = Query(20, le=100),
    owner    : dict = Depends(require_owner),
    svc      : OrderService = Depends(_svc),
):
    return await svc.list_orders(status, channel, page, per_page)


@router.get("/{order_id}")
async def get_order(
    order_id : uuid.UUID,
    svc      : OrderService = Depends(_svc),
):
    """Public — customer can track their order by UUID."""
    return await svc.get_order(order_id)


@router.patch("/{order_id}/status")
async def update_status(
    order_id : uuid.UUID,
    body     : StatusUpdate,
    bg       : BackgroundTasks,
    owner    : dict = Depends(require_owner),
    svc      : OrderService = Depends(_svc),
):
    return await svc.update_status(order_id, body, bg)
```

### modules/orders/schemas.py
```python
import uuid
from decimal import Decimal
from datetime import date
from typing import Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class OrderItemCreate(BaseModel):
    product_id : uuid.UUID
    qty        : Decimal = Field(gt=Decimal("0"))
    source     : str = "own"

    @field_validator("qty", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float): raise ValueError("Use string for qty — never float")
        return Decimal(str(v))


class OrderCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    idempotency_key  : uuid.UUID
    customer_name    : str  = Field(min_length=2, max_length=100)
    customer_phone   : str  = Field(pattern=r"^\+?91[6-9]\d{9}$")
    customer_address : str | None = None
    fulfillment_type : str  = Field(pattern=r"^(pickup|delivery)$")
    channel          : str  = Field(pattern=r"^(online|offline)$")
    payment_mode     : str  = Field(pattern=r"^(razorpay|cash|upi_manual|credit)$")
    credit_due_date  : date | None = None
    items            : list[OrderItemCreate] = Field(min_length=1, max_length=20)


class StatusUpdate(BaseModel):
    status        : str
    cancel_reason : str | None = None
```
