# Stage 4 LLD — Complete Final Document
## Lakhimpur Agri-Business Platform

---

## PART 1 — API CONTRACTS

### POST /api/auth/login
```json
// Request
{ "username": "admin", "password": "your_password" }

// Response 200
// Header: Set-Cookie: token=eyJhbGc...; HttpOnly; Secure; SameSite=Strict
{ "owner_id": "uuid", "username": "admin", "expires_at": "2025-05-11T10:30:00Z" }

// Error 401
{ "error": "INVALID_CREDENTIALS", "message": "Invalid credentials", "status": 401 }
```

### POST /api/orders/
```json
// Request
{
  "idempotency_key":  "uuid-client-generated",
  "customer_name":    "Ratan Das",
  "customer_phone":   "+919876543210",
  "customer_address": "Lakhimpur town",
  "fulfillment_type": "pickup",
  "channel":          "online",
  "payment_mode":     "razorpay",
  "items": [
    { "product_id": "uuid-joha-rice",     "qty": "3.000", "source": "own" },
    { "product_id": "uuid-narikal-petha", "qty": "4.000", "source": "own" }
  ]
}

// Response 201
{
  "id":                "uuid-order",
  "order_number":      "LKP-2025-0042",
  "status":            "pending",
  "channel":           "online",
  "total_amount":      "595.00000",
  "final_amount":      "595.00000",
  "razorpay_order_id": "order_xxx",
  "items": [
    { "product_name": "Joha Rice", "qty": "3.000", "unit_price": "105.00000", "total": "315.00000" },
    { "product_name": "Narikal Petha", "qty": "4.000", "unit_price": "70.00000", "total": "280.00000" }
  ],
  "created_at": "2025-05-10T10:30:45Z"
}

// Error 422 — STOCK_INSUFFICIENT
{
  "error":   "STOCK_INSUFFICIENT",
  "message": "Only 2.5kg available",
  "field":   "quantity",
  "detail":  { "available_qty": "2.500", "requested_qty": "3.000" },
  "status":  422
}
```

### POST /api/payments/webhook  (Razorpay → FastAPI)
```json
// Headers: X-Razorpay-Signature: hmac_sha256_hex_value

// Request body (sent by Razorpay)
{
  "entity": "event",
  "event":  "payment.captured",
  "payload": {
    "payment": {
      "entity": {
        "id":       "pay_xxx",
        "order_id": "order_xxx",
        "amount":   59500,
        "currency": "INR",
        "status":   "captured"
      }
    }
  }
}

// Response 200 (always fast — background tasks run after)
{ "status": "ok" }

// On HMAC failure → 400
{ "error": "WEBHOOK_SIGNATURE_INVALID", "status": 400 }

// On duplicate → 200 silently (idempotent)
{ "status": "ok", "note": "already_processed" }
```

### GET /api/pl/monthly?month=2025-05
```json
// Response 200
{
  "month":          "2025-05",
  "from_cache":     false,
  "warnings":       ["Opening stock missing for joha-rice"],

  "rev_online":     "12450.00000",
  "rev_offline":    "6200.00000",
  "rev_credit":     "1500.00000",
  "rev_total":      "18650.00000",

  "cogs_opening":   "3200.00000",
  "cogs_own_prod":  "4250.00000",
  "cogs_purchased": "1800.00000",
  "cogs_norm_loss": "420.00000",
  "cogs_consumed":  "315.00000",
  "cogs_closing":   "2100.00000",
  "cogs_total":     "7885.00000",

  "gross_profit":   "10765.00000",
  "abnormal_loss":  "350.00000",

  "opex_fixed":     "1200.00000",
  "opex_deprec":    "83.33333",
  "opex_provisions":"100.00000",
  "opex_total":     "1383.33333",

  "net_profit":     "9031.66667",
  "net_margin_pct": "48.42135",

  "cash_inflow":    "17150.00000",
  "cash_outflow":   "3000.00000",
  "net_cash_flow":  "14150.00000",
  "cash_pl_gap":    "1500.00000",

  "price_variance": "250.00000",
  "cost_variance":  "-120.00000"
}
```

### POST /api/inventory/entries
```json
// Request
{
  "idempotency_key": "uuid",
  "product_id":      "uuid",
  "entry_type":      "purchase",
  "qty":             "50.000",
  "unit_cost":       "72.00000",
  "total_amount":    "3600.00000",
  "source":          "external",
  "date":            "2025-05-10",
  "note":            "Bought from market"
}

// Response 201
{
  "id":            "uuid",
  "entry_type":    "purchase",
  "qty":           "50.000",
  "total_amount":  "3600.00000",
  "cost_variance": "350.00000",
  "new_stock_qty": "73.500",
  "date":          "2025-05-10"
}
```

### POST /api/farm/seasons/{id}/milling
```json
// Request
{
  "dhan_sent_kg":       "1200.000",
  "chawl_received_kg":  "780.000",
  "husk_recovered_kg":  "240.000",
  "bran_recovered_kg":  "96.000",
  "broken_rice_kg":     "24.000",
  "milling_charges":    "1800.00000",
  "husk_market_price":  "2.00000",
  "bran_market_price":  "18.00000",
  "broken_market_price":"30.00000",
  "milling_date":       "2025-11-20"
}

// Response 201
{
  "milling_yield_pct":   "65.00000",
  "byproduct_revenue":   "3204.00000",
  "cost_per_kg_chawl":   "52.30769",
  "transfer_price_per_kg":"58.58462",
  "inventory_added_qty": "780.000"
}
```

### POST /api/petha/batches/ + PATCH outcome
```json
// POST request
{
  "variety":        "narikal",
  "batch_date":     "2025-05-10",
  "planned_pieces": 30,
  "shelf_life_days":7,
  "recipe_snapshot": { "petha_guri_kg": "1.5", "coconut_pcs": 3, "sugar_kg": "0.8" },
  "costs": [
    { "cost_type":"ingredient", "description":"petha guri", "qty":"1.5", "unit_cost":"60.00000", "total_amount":"90.00000" },
    { "cost_type":"ingredient", "description":"coconut",    "qty":"3",   "unit_cost":"20.00000", "total_amount":"60.00000" },
    { "cost_type":"labor",      "description":"maker 2hr",  "qty":"2",   "unit_cost":"75.00000", "total_amount":"150.00000" },
    { "cost_type":"fuel",       "description":"LPG",        "qty":"1",   "unit_cost":"25.00000", "total_amount":"25.00000" }
  ]
}

// POST Response 201
{
  "id": "uuid-batch", "variety": "narikal", "status": "in_production",
  "planned_pieces": 30, "total_batch_cost": "325.00000",
  "expiry_date": "2025-05-17", "days_to_expiry": 7
}

// PATCH /api/petha/batches/{id}/outcome
// Request: { "good_pieces": 27, "rejected_pieces": 3 }
// Response adds:
{
  "good_pieces": 27, "rejected_pieces": 3,
  "cost_per_piece": "12.03704",
  "rejection_pct":  "10.00000",
  "status":         "completed"
}
```

---

## PART 2 — REMAINING SQLALCHEMY MODELS

### inventory/models.py
```python
import enum, uuid
from decimal import Decimal
from datetime import date, datetime
from sqlalchemy import String, Enum as SAEnum, Date, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column, Mapped, relationship
from shared.models.base import Base, TimestampMixin, MONEY, QTY

class EntryType(str, enum.Enum):
    sale             = "sale"
    purchase         = "purchase"
    wastage_normal   = "wastage_normal"
    wastage_abnormal = "wastage_abnormal"
    consumption      = "consumption"
    opening_stock    = "opening_stock"
    closing_stock    = "closing_stock"
    production       = "production"
    capex            = "capex"
    fixed_cost       = "fixed_cost"
    provision        = "provision"

class StockEntry(Base, TimestampMixin):
    __tablename__ = "stock_entries"

    idempotency_key    : Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), unique=True)
    product_id         : Mapped[uuid.UUID]      = mapped_column(ForeignKey("products.id"))
    entry_type         : Mapped[str]            = mapped_column(SAEnum(EntryType))
    qty                : Mapped[Decimal]        = mapped_column(QTY)
    unit_cost          : Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    total_amount       : Mapped[Decimal]        = mapped_column(MONEY)
    standard_unit_cost : Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    price_variance     : Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    cost_variance      : Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    source             : Mapped[str | None]     = mapped_column(SAEnum("own","external","internal"), nullable=True)
    channel            : Mapped[str | None]     = mapped_column(SAEnum("online","offline"), nullable=True)
    pay_mode           : Mapped[str | None]     = mapped_column(nullable=True)
    reference_id       : Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reference_type     : Mapped[str | None]     = mapped_column(String(50), nullable=True)
    date               : Mapped[date]           = mapped_column(Date)
    note               : Mapped[str | None]     = mapped_column(Text, nullable=True)
    product = relationship("Product", back_populates="stock_entries")

class InventoryStock(Base):
    """One row per product — live stock level."""
    __tablename__ = "inventory_stock"
    id          : Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id  : Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), unique=True)
    current_qty : Mapped[Decimal]   = mapped_column(QTY, default=Decimal("0"))
    updated_at  : Mapped[datetime]  = mapped_column(default=lambda: datetime.utcnow())
    product = relationship("Product", back_populates="stock")

class MonthlyStock(Base):
    """Opening and closing stock values for COGS accuracy."""
    __tablename__ = "monthly_stock"
    __table_args__ = (UniqueConstraint("product_id", "month", "stock_type"),)
    id         : Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id : Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    month      : Mapped[str]       = mapped_column(String(7))   # "2025-05"
    stock_type : Mapped[str]       = mapped_column(SAEnum("opening","closing"))
    qty        : Mapped[Decimal]   = mapped_column(QTY)
    value      : Mapped[Decimal]   = mapped_column(MONEY)
    created_at : Mapped[datetime]  = mapped_column(default=lambda: datetime.utcnow())
```

### farm/models.py
```python
class FarmVariety(str, enum.Enum):
    joha       = "joha"
    bora_saul  = "bora_saul"
    kali_jeera = "kali_jeera"

class SeasonStatus(str, enum.Enum):
    planning  = "planning"
    active    = "active"
    harvested = "harvested"
    milled    = "milled"
    complete  = "complete"
    failed    = "failed"

class FarmSeason(Base, TimestampMixin):
    __tablename__ = "farm_seasons"
    variety                : Mapped[str]            = mapped_column(SAEnum(FarmVariety))
    area_bigha             : Mapped[Decimal]        = mapped_column(QTY)
    status                 : Mapped[str]            = mapped_column(SAEnum(SeasonStatus), default="planning")
    start_date             : Mapped[date]           = mapped_column(Date)
    harvest_date           : Mapped[date | None]    = mapped_column(Date, nullable=True)
    dhan_qty_kg            : Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    chawl_qty_kg           : Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    total_cultivation_cost : Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    milling_yield_percent  : Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    cost_per_kg_dhan       : Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    cost_per_kg_chawl      : Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    transfer_price_per_kg  : Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    notes                  : Mapped[str | None]     = mapped_column(Text, nullable=True)
    inputs   = relationship("FarmInput",   back_populates="season", cascade="all")
    millings = relationship("FarmMilling", back_populates="season")

class FarmInput(Base):
    __tablename__ = "farm_inputs"
    id           : Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id    : Mapped[uuid.UUID]      = mapped_column(ForeignKey("farm_seasons.id"))
    input_type   : Mapped[str]            = mapped_column(SAEnum("seed","fertilizer","pesticide","labor","irrigation","transport","other"))
    description  : Mapped[str]            = mapped_column(Text)
    qty          : Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    unit         : Mapped[str | None]     = mapped_column(String(20), nullable=True)
    unit_cost    : Mapped[Decimal]        = mapped_column(MONEY)
    total_amount : Mapped[Decimal]        = mapped_column(MONEY)
    date         : Mapped[date]           = mapped_column(Date)
    created_at   : Mapped[datetime]       = mapped_column(default=lambda: datetime.utcnow())
    season = relationship("FarmSeason", back_populates="inputs")

class FarmMilling(Base, TimestampMixin):
    __tablename__ = "farm_millings"
    season_id           : Mapped[uuid.UUID] = mapped_column(ForeignKey("farm_seasons.id"))
    dhan_sent_kg        : Mapped[Decimal]   = mapped_column(QTY)
    chawl_received_kg   : Mapped[Decimal]   = mapped_column(QTY)
    husk_recovered_kg   : Mapped[Decimal]   = mapped_column(QTY, default=Decimal("0"))
    bran_recovered_kg   : Mapped[Decimal]   = mapped_column(QTY, default=Decimal("0"))
    broken_rice_kg      : Mapped[Decimal]   = mapped_column(QTY, default=Decimal("0"))
    milling_charges     : Mapped[Decimal]   = mapped_column(MONEY)
    husk_market_price   : Mapped[Decimal]   = mapped_column(MONEY, default=Decimal("0"))
    bran_market_price   : Mapped[Decimal]   = mapped_column(MONEY, default=Decimal("0"))
    broken_market_price : Mapped[Decimal]   = mapped_column(MONEY, default=Decimal("0"))
    yield_percent       : Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    milling_date        : Mapped[date]      = mapped_column(Date)
    season = relationship("FarmSeason", back_populates="millings")
```

### petha/models.py
```python
class PethaVariety(str, enum.Enum):
    septa   = "septa"
    narikal = "narikal"

class BatchStatus(str, enum.Enum):
    in_production = "in_production"
    completed     = "completed"
    expired       = "expired"

class PethaBatch(Base, TimestampMixin):
    __tablename__ = "petha_batches"
    variety               : Mapped[str]            = mapped_column(SAEnum(PethaVariety))
    status                : Mapped[str]            = mapped_column(SAEnum(BatchStatus), default="in_production")
    batch_date            : Mapped[date]           = mapped_column(Date)
    planned_pieces        : Mapped[int]            = mapped_column(Integer)
    good_pieces           : Mapped[int | None]     = mapped_column(Integer, nullable=True)
    rejected_pieces       : Mapped[int | None]     = mapped_column(Integer, nullable=True)
    total_ingredient_cost : Mapped[Decimal]        = mapped_column(MONEY, default=Decimal("0"))
    total_labor_cost      : Mapped[Decimal]        = mapped_column(MONEY, default=Decimal("0"))
    total_overhead_cost   : Mapped[Decimal]        = mapped_column(MONEY, default=Decimal("0"))
    total_batch_cost      : Mapped[Decimal]        = mapped_column(MONEY)  # GENERATED ALWAYS
    cost_per_piece        : Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    shelf_life_days       : Mapped[int]            = mapped_column(Integer, default=7)
    expiry_date           : Mapped[date]           = mapped_column(Date)   # GENERATED ALWAYS
    recipe_snapshot       : Mapped[dict]           = mapped_column(JSONB)
    abnormal_loss_amount  : Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    notes                 : Mapped[str | None]     = mapped_column(Text, nullable=True)
    cost_lines = relationship("PethaBatchCost", back_populates="batch", cascade="all")

class PethaBatchCost(Base):
    __tablename__ = "petha_batch_costs"
    id           : Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id     : Mapped[uuid.UUID]      = mapped_column(ForeignKey("petha_batches.id"))
    cost_type    : Mapped[str]            = mapped_column(SAEnum("ingredient","labor","fuel","overhead"))
    description  : Mapped[str]           = mapped_column(Text)
    qty          : Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    unit_cost    : Mapped[Decimal]        = mapped_column(MONEY)
    total_amount : Mapped[Decimal]        = mapped_column(MONEY)
    created_at   : Mapped[datetime]       = mapped_column(default=lambda: datetime.utcnow())
    batch = relationship("PethaBatch", back_populates="cost_lines")
```

### finance/models.py + notify/models.py
```python
class FixedCost(Base, TimestampMixin):
    __tablename__ = "fixed_costs"
    name           : Mapped[str]     = mapped_column(String(200))
    category       : Mapped[str]     = mapped_column(SAEnum("stall","fuel","transport","drawing","provision","misc"))
    monthly_amount : Mapped[Decimal] = mapped_column(MONEY)
    is_active      : Mapped[bool]    = mapped_column(Boolean, default=True)

class Asset(Base, TimestampMixin):
    __tablename__ = "assets"
    name                 : Mapped[str]     = mapped_column(String(200))
    cost                 : Mapped[Decimal] = mapped_column(MONEY)
    useful_life_years    : Mapped[int]     = mapped_column(Integer)
    monthly_depreciation : Mapped[Decimal] = mapped_column(MONEY)  # GENERATED ALWAYS
    purchase_date        : Mapped[date]    = mapped_column(Date)
    is_active            : Mapped[bool]    = mapped_column(Boolean, default=True)

class Notification(Base):
    __tablename__ = "notifications"
    id             : Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_phone: Mapped[str]            = mapped_column(String(15))
    recipient_type : Mapped[str]            = mapped_column(SAEnum("owner","customer"))
    channel        : Mapped[str]            = mapped_column(SAEnum("whatsapp","sms"))
    template_name  : Mapped[str]            = mapped_column(String(100))
    message_body   : Mapped[str | None]     = mapped_column(Text, nullable=True)
    status         : Mapped[str]            = mapped_column(SAEnum("pending","sent","failed"), default="pending")
    reference_id   : Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reference_type : Mapped[str | None]     = mapped_column(String(50), nullable=True)
    sent_at        : Mapped[datetime | None]= mapped_column(nullable=True)
    error_message  : Mapped[str | None]     = mapped_column(Text, nullable=True)
    created_at     : Mapped[datetime]       = mapped_column(default=lambda: datetime.utcnow())
```

---

## PART 3 — FULL MODULE PATTERN (orders as example)

### modules/orders/router.py
```python
# HTTP interface ONLY. No business logic.
from fastapi import APIRouter, Depends, BackgroundTasks
from modules.orders.schemas import OrderCreate, OrderResponse, StatusUpdate
from modules.orders.service import OrderService
from core.dependencies import get_order_service, require_owner
import uuid

router = APIRouter(prefix="/api/orders", tags=["orders"])

@router.post("/", response_model=OrderResponse, status_code=201)
async def create_order(
    body: OrderCreate,
    background_tasks: BackgroundTasks,
    service: OrderService = Depends(get_order_service),
):
    return await service.create_order(body, background_tasks)

@router.get("/", response_model=list[OrderResponse])
async def list_orders(
    status: str | None = None,
    channel: str | None = None,
    page: int = 1,
    per_page: int = 20,
    owner = Depends(require_owner),
    service: OrderService = Depends(get_order_service),
):
    return await service.list_orders(status, channel, page, per_page)

@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: uuid.UUID, service: OrderService = Depends(get_order_service)):
    return await service.get_order(order_id)

@router.patch("/{order_id}/status", response_model=OrderResponse)
async def update_status(
    order_id: uuid.UUID,
    body: StatusUpdate,
    background_tasks: BackgroundTasks,
    owner = Depends(require_owner),
    service: OrderService = Depends(get_order_service),
):
    return await service.update_status(order_id, body, background_tasks)
```

### modules/orders/service.py
```python
# All business logic. No HTTP, no SQL.
from decimal import Decimal
from modules.orders.repository import OrderRepository
from modules.products.service import ProductService
from modules.payments.service import PaymentService
from modules.notify.service import NotifyService
from modules.inventory.service import InventoryService
from shared.exceptions import StockInsufficientError, OrderNotFoundError

class OrderService:
    def __init__(self, repo: OrderRepository, products: ProductService,
                 payments: PaymentService, notify: NotifyService,
                 inventory: InventoryService):
        self.repo      = repo
        self.products  = products
        self.payments  = payments
        self.notify    = notify
        self.inventory = inventory

    async def create_order(self, data, bg_tasks):
        # 1. Idempotency
        existing = await self.repo.find_by_idempotency_key(data.idempotency_key)
        if existing: return existing

        # 2. Validate products and stock
        items_validated, total = [], Decimal("0")
        for item in data.items:
            product = await self.products.get_active(item.product_id)
            stock   = await self.inventory.get_current_stock(item.product_id)
            if stock.current_qty < item.qty:
                raise StockInsufficientError(
                    product=product.name,
                    available=stock.current_qty,
                    requested=item.qty,
                )
            line_total = product.sell_price * item.qty
            total += line_total
            items_validated.append({
                **item.__dict__,
                "unit_price":   product.sell_price,
                "product_name": product.name,
                "total":        line_total,
            })

        # 3. Create order (status=pending, stock unchanged)
        order = await self.repo.create(
            idempotency_key=data.idempotency_key,
            items=items_validated,
            total=total,
            channel=data.channel,
            fulfillment_type=data.fulfillment_type,
            customer_name=data.customer_name,
            customer_phone=data.customer_phone,
        )

        # 4. Online → create Razorpay order
        if data.payment_mode == "razorpay":
            rzp = await self.payments.create_razorpay_order(order.id, total)
            order.razorpay_order_id = rzp["id"]
            await self.repo.update(order)

        # 5. Offline → confirm immediately
        elif data.payment_mode in ("cash", "upi_manual", "credit"):
            await self._confirm_order(order, bg_tasks)

        return order

    async def _confirm_order(self, order, bg_tasks):
        """Atomic: confirm + decrement stock. Called from webhook or offline."""
        async with self.repo.transaction():
            order.status = "confirmed"
            await self.repo.update(order)
            for item in order.items:
                await self.inventory.decrement_stock(
                    product_id=item.product_id,
                    qty=item.qty,
                    order_id=order.id,
                )
        # Notifications outside transaction (non-critical)
        bg_tasks.add_task(self.notify.order_confirmed, order)
        bg_tasks.add_task(self.notify.new_order_to_owner, order)
```

### modules/orders/repository.py
```python
# DB access ONLY. No business logic.
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from modules.orders.models import Order
from contextlib import asynccontextmanager
from datetime import datetime
import uuid

class OrderRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @asynccontextmanager
    async def transaction(self):
        async with self.db.begin():
            yield

    async def find_by_idempotency_key(self, key: uuid.UUID) -> Order | None:
        result = await self.db.execute(
            select(Order)
            .where(Order.idempotency_key == key)
            .options(selectinload(Order.items), selectinload(Order.payment))
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Order:
        order_number = await self._next_order_number()
        order = Order(order_number=order_number, **kwargs)
        self.db.add(order)
        await self.db.flush()
        await self.db.refresh(order)
        return order

    async def list_with_filters(self, status, channel, page, per_page) -> list[Order]:
        q = (select(Order)
             .where(Order.deleted_at.is_(None))
             .options(selectinload(Order.items), selectinload(Order.payment)))
        if status:  q = q.where(Order.status == status)
        if channel: q = q.where(Order.channel == channel)
        q = q.order_by(Order.created_at.desc()).offset((page-1)*per_page).limit(per_page)
        return (await self.db.execute(q)).scalars().all()

    async def update(self, order: Order) -> Order:
        self.db.add(order)
        await self.db.flush()
        return order

    async def _next_order_number(self) -> str:
        year = datetime.utcnow().year
        n = (await self.db.execute(
            select(func.count()).where(func.extract("year", Order.created_at) == year)
        )).scalar() + 1
        return f"LKP-{year}-{n:04d}"
```

### modules/orders/schemas.py
```python
from pydantic import BaseModel, field_validator, Field, ConfigDict
from decimal import Decimal
from datetime import datetime
import uuid

class OrderItemCreate(BaseModel):
    product_id : uuid.UUID
    qty        : Decimal = Field(gt=0)
    source     : str = "own"

    @field_validator("qty", mode="before")
    @classmethod
    def no_float(cls, v):
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
    items            : list[OrderItemCreate] = Field(min_length=1, max_length=20)

class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_name : str
    unit_price   : str
    qty          : str
    total        : str

    @field_validator("unit_price","qty","total", mode="before")
    @classmethod
    def to_str(cls, v): return str(v)

class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id                : uuid.UUID
    order_number      : str
    status            : str
    channel           : str
    fulfillment_type  : str
    customer_name     : str
    customer_phone    : str
    total_amount      : str
    final_amount      : str
    razorpay_order_id : str | None
    items             : list[OrderItemResponse]
    created_at        : datetime

    @field_validator("total_amount","final_amount", mode="before")
    @classmethod
    def to_str(cls, v): return str(v)

class StatusUpdate(BaseModel):
    status        : str
    cancel_reason : str | None = None
```

---

## PART 4 — CORE CONFIG FILES

### core/config.py
```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT           : str   = "local"
    DEBUG                 : bool  = False
    LOG_LEVEL             : str   = "INFO"

    DATABASE_URL          : str
    DATABASE_POOL_SIZE    : int   = 5
    DATABASE_MAX_OVERFLOW : int   = 10

    REDIS_URL             : str
    REDIS_PREFIX          : str   = "local"

    JWT_PRIVATE_KEY       : str
    JWT_PUBLIC_KEY        : str
    JWT_ALGORITHM         : str   = "RS256"
    JWT_EXPIRY_HOURS      : int   = 24
    JWT_REFRESH_DAYS      : int   = 7

    OWNER_USERNAME        : str   = "admin"

    RAZORPAY_KEY_ID       : str
    RAZORPAY_KEY_SECRET   : str
    RAZORPAY_WEBHOOK_SECRET: str
    RAZORPAY_CURRENCY     : str   = "INR"

    WATI_ENABLED          : bool  = False
    WATI_API_TOKEN        : str   = ""
    WATI_BASE_URL         : str   = ""
    OWNER_WHATSAPP        : str   = ""

    SENTRY_DSN            : str   = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0
    SENTRY_ENVIRONMENT    : str   = "local"

    CORS_ORIGIN           : str   = "http://localhost:3000"
    API_BASE_URL          : str   = "http://localhost:8000"

    R2_ENABLED            : bool  = False
    R2_ACCOUNT_ID         : str   = ""
    R2_ACCESS_KEY_ID      : str   = ""
    R2_SECRET_ACCESS_KEY  : str   = ""
    R2_BUCKET_NAME        : str   = "lakhimpur-dev"
    R2_PUBLIC_URL         : str   = ""

    RATE_LIMIT_PER_MIN    : int   = 100
    RATE_LIMIT_LOGIN_PER_MIN: int = 5

    @field_validator("JWT_PRIVATE_KEY","JWT_PUBLIC_KEY")
    @classmethod
    def format_pem(cls, v): return v.replace(r"\n", "\n")

    @property
    def is_production(self): return self.ENVIRONMENT == "production"

@lru_cache
def get_settings() -> Settings: return Settings()

settings = get_settings()
```

### main.py (FastAPI bootstrap)
```python
import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from core.config import settings
from core.middleware import CorrelationMiddleware, RequestLoggingMiddleware
from modules.auth.router      import router as auth_router
from modules.products.router  import router as products_router
from modules.inventory.router import router as inventory_router
from modules.orders.router    import router as orders_router
from modules.payments.router  import router as payments_router
from modules.pl_engine.router import router as pl_router
from modules.farm.router      import router as farm_router
from modules.petha.router     import router as petha_router
from modules.notify.router    import router as notify_router

if settings.SENTRY_DSN:
    sentry_sdk.init(dsn=settings.SENTRY_DSN,
                    traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
                    environment=settings.SENTRY_ENVIRONMENT)

app = FastAPI(
    title="Lakhimpur Agri-Business API",
    version="1.0.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

# Middleware (order matters — first added = outermost)
app.add_middleware(CorrelationMiddleware)      # X-Request-ID
app.add_middleware(RequestLoggingMiddleware)   # structured JSON log
app.add_middleware(CORSMiddleware,
    allow_origins=[settings.CORS_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET","POST","PATCH","DELETE"],
    allow_headers=["X-Idempotency-Key","Content-Type","X-Request-ID"],
)

limiter = Limiter(key_func=lambda req: req.client.host,
                  default_limits=[f"{settings.RATE_LIMIT_PER_MIN}/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

for r in [auth_router, products_router, inventory_router, orders_router,
          payments_router, pl_router, farm_router, petha_router, notify_router]:
    app.include_router(r)

@app.get("/health")
async def health(): return {"status": "ok"}

@app.get("/health/ready")
async def ready():
    from core.database import check_db; from core.redis import check_redis
    await check_db(); await check_redis()
    return {"status": "ready"}

@app.on_event("startup")
async def startup():
    from core.database import run_migrations
    await run_migrations()   # alembic upgrade head on every boot
```

### nuxt.config.ts
```typescript
export default defineNuxtConfig({
  devtools: { enabled: process.env.NUXT_PUBLIC_ENVIRONMENT !== "production" },

  modules: [
    "@pinia/nuxt",
    "@nuxt/image",
    "nuxt-security",
    "@sentry/nuxt/module",
  ],

  runtimeConfig: {
    apiBase: process.env.NUXT_API_BASE,
    public: {
      apiBase:     process.env.NUXT_PUBLIC_API_BASE,
      razorpayKey: process.env.NUXT_RAZORPAY_KEY_ID,
      siteUrl:     process.env.NUXT_PUBLIC_SITE_URL,
      environment: process.env.NUXT_PUBLIC_ENVIRONMENT,
    },
  },

  routeRules: {
    "/dashboard/**": { ssr: true, middleware: ["auth"] },
    "/shop":              { ssr: true, cache: { maxAge: 300 } },
    "/shop/products":     { ssr: true, cache: { maxAge: 300 } },
    "/shop/products/**":  { ssr: true, cache: { maxAge: 600 } },
    "/shop/cart":         { ssr: false },
    "/shop/checkout":     { ssr: false },
  },

  security: {
    headers: {
      contentSecurityPolicy: {
        "script-src": ["'self'", "https://checkout.razorpay.com"],
        "connect-src": ["'self'", process.env.NUXT_PUBLIC_API_BASE!],
      },
    },
  },

  css: ["~/assets/css/main.css"],
  typescript: { strict: true },
  nitro: { compressPublicAssets: true },
})
```

### scripts/seed.py
```python
# Run once: python scripts/seed.py
import asyncio
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from passlib.context import CryptContext
from core.config import settings

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEFAULT_PRODUCTS = [
    {"name":"Joha Rice",     "slug":"joha-rice",     "category":"rice",  "unit":"kg",
     "sell_price":"105","farm_cost":"50","labor_cost":"5","overhead_cost":"3",
     "packaging_cost":"7","normal_loss_percent":"33","is_own_farm":True},
    {"name":"Bora Saul",     "slug":"bora-saul",     "category":"rice",  "unit":"kg",
     "sell_price":"90", "farm_cost":"50","labor_cost":"5","overhead_cost":"3",
     "packaging_cost":"7","normal_loss_percent":"33","is_own_farm":True},
    {"name":"Kali Jeera",    "slug":"kali-jeera",    "category":"rice",  "unit":"kg",
     "sell_price":"110","farm_cost":"50","labor_cost":"5","overhead_cost":"3",
     "packaging_cost":"7","normal_loss_percent":"33","is_own_farm":True},
    {"name":"Narikal Petha", "slug":"narikal-petha", "category":"petha", "unit":"pc",
     "sell_price":"70", "farm_cost":"18","labor_cost":"7.5","packaging_cost":"4"},
    {"name":"Septa Petha",   "slug":"septa-petha",   "category":"petha", "unit":"pc",
     "sell_price":"60", "farm_cost":"15","labor_cost":"7.5","packaging_cost":"3.5"},
]

async def seed():
    from shared.models.base import Base
    from modules.auth.models import Owner
    from modules.products.models import Product
    from modules.inventory.models import InventoryStock
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as db:
        db.add(Owner(
            username=settings.OWNER_USERNAME,
            password_hash=pwd_ctx.hash("changeme123"),
        ))
        for p in DEFAULT_PRODUCTS:
            money_fields = ("sell_price","farm_cost","labor_cost","overhead_cost",
                            "packaging_cost","normal_loss_percent")
            product = Product(**{
                k: Decimal(v) if k in money_fields else v
                for k, v in p.items()
            })
            db.add(product)
            await db.flush()
            db.add(InventoryStock(product_id=product.id, current_qty=Decimal("0")))
        await db.commit()
    print("✓ Seed complete. Login: admin / changeme123  ← change on first login")

if __name__ == "__main__":
    asyncio.run(seed())
```

---

## PART 5 — COMPLETE ERROR CATALOG

| Error Code | HTTP | Module | When | Frontend action |
|---|---|---|---|---|
| INVALID_CREDENTIALS | 401 | auth | Wrong username or password | "Invalid credentials" — never say which |
| TOKEN_EXPIRED | 401 | auth | JWT past expiry | Auto-refresh → if fails → /login |
| TOKEN_INVALID | 401 | auth | Malformed or tampered JWT | Clear cookie → /login |
| TOKEN_BLOCKLISTED | 401 | auth | Logged-out token reused | Clear cookie → /login |
| FORBIDDEN | 403 | auth | Customer on owner route | 403 page |
| PRODUCT_NOT_FOUND | 404 | products | Unknown product_id/slug | "Product not found" |
| PRODUCT_INACTIVE | 422 | products | Ordering inactive product | Remove from cart |
| STOCK_INSUFFICIENT | 422 | inventory | Order qty > current stock | Show available qty |
| STOCK_NEGATIVE | 422 | inventory | Entry would make stock negative | Block + show current qty |
| CLOSING_STOCK_EXCEEDS_MAX | 422 | inventory | Closing > opening + received | Show max allowed |
| ORDER_NOT_FOUND | 404 | orders | Unknown order_id | 404 page |
| ORDER_DUPLICATE | 200 | orders | Idempotency key reused | Return existing order |
| ORDER_INVALID_STATUS_TRANSITION | 422 | orders | e.g. confirmed → pending | Show allowed next states |
| ORDER_ALREADY_CANCELLED | 422 | orders | Double cancel | "Already cancelled" |
| PAYMENT_ALREADY_PROCESSED | 200 | payments | Duplicate webhook | Silent 200 |
| WEBHOOK_SIGNATURE_INVALID | 400 | payments | HMAC check fails | N/A (server-server) |
| RAZORPAY_ORDER_CREATE_FAILED | 503 | payments | API error after retries | "Payment unavailable" |
| SEASON_NOT_FOUND | 404 | farm | Unknown season_id | 404 |
| INVALID_SEASON_TRANSITION | 422 | farm | Mill before harvest | Show required step |
| BATCH_NOT_FOUND | 404 | petha | Unknown batch_id | 404 |
| BATCH_ALREADY_COMPLETED | 422 | petha | Record outcome twice | Show existing outcome |
| BATCH_EXPIRED | 422 | petha | Action on expired batch | Show expiry date |
| FLOAT_MONEY_REJECTED | 422 | all | Float sent for money field | Developer error — use string |
| VALIDATION_ERROR | 422 | all | Pydantic schema violation | Field-level error display |
| RATE_LIMIT_EXCEEDED | 429 | all | Over request limit | "Too many requests, wait 1 min" |
| INTERNAL_SERVER_ERROR | 500 | all | Unhandled exception | Generic error + request_id |
| SERVICE_UNAVAILABLE | 503 | all | DB or Redis unreachable | "System maintenance" |

### Standard error response shape (every error, always)
```json
{
  "error":      "STOCK_INSUFFICIENT",
  "message":    "Only 3.5kg available",
  "field":      "quantity",
  "detail":     { "available_qty": "3.500", "requested_qty": "5.000" },
  "status":     422,
  "request_id": "abc123-xyz789"
}
```

---

## STAGE 4 LLD — COMPLETE CHECKLIST

- [x] ERD — 14 tables, all FK relationships
- [x] All table column definitions, types, constraints, indexes
- [x] SQLAlchemy models — all 14 tables
- [x] Pydantic schemas — create, response, all modules
- [x] Algorithms — P&L engine, batch cost, milling yield, working capital
- [x] Sequence diagrams — order, auth, P&L, stock update
- [x] State machines — order, farm season, petha batch, payment
- [x] Module interaction + dependency graph
- [x] Observability — metrics, tracing, health, alerting, daily report
- [x] Security — STRIDE, OWASP Top 10, JWT RS256, secrets, input validation
- [x] Logging — structured JSON, levels, correlation ID, retention
- [x] Frontend LLD — pages, stores, composables, components, patterns
- [x] .env files — local, staging, production, example
- [x] Testing — setup, unit tests, integration tests, coverage targets
- [x] Cache design — key naming, TTL table, invalidation strategy
- [x] API contracts — full request/response JSON for every endpoint
- [x] Remaining SQLAlchemy models — inventory, farm, petha, finance, notify
- [x] Full module pattern — router, service, repository, schemas (orders example)
- [x] Core config — config.py, main.py, nuxt.config.ts, seed script
- [x] Error catalog — 27 error codes, standard response shape

## Stage 4 LLD is DONE. Ready for Stage 5 — Dev Environment Setup.
