# Stage 6 · Code · Part 3 — Payments + P&L Engine modules

---

## MODULE 5 — PAYMENTS

### modules/payments/razorpay.py
```python
import hashlib
import hmac
import razorpay
from decimal import Decimal
from core.config import settings
from shared.exceptions import RazorpayOrderCreateFailedError, WebhookSignatureInvalidError


def _client() -> razorpay.Client:
    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


async def create_razorpay_order(our_order_id: str, amount: Decimal) -> dict:
    """
    Create Razorpay order. Amount in paise (multiply ₹ by 100).
    Returns {"id": "order_xxx", "amount": 59500, ...}
    """
    paise = int(amount * 100)   # Razorpay uses paise, not rupees
    try:
        client = _client()
        data = client.order.create({
            "amount":   paise,
            "currency": settings.RAZORPAY_CURRENCY,
            "receipt":  our_order_id[:40],         # max 40 chars
            "notes":    {"our_order_id": our_order_id},
        })
        return data
    except Exception as e:
        raise RazorpayOrderCreateFailedError() from e


def verify_webhook_signature(payload_body: bytes, signature: str) -> None:
    """
    Verify Razorpay webhook HMAC-SHA256 signature.
    Raises WebhookSignatureInvalidError if invalid.
    """
    expected = hmac.new(
        key=settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise WebhookSignatureInvalidError()


def issue_refund(razorpay_payment_id: str, amount: Decimal) -> dict:
    """Issue full or partial refund."""
    try:
        client = _client()
        return client.payment.refund(razorpay_payment_id, {"amount": int(amount * 100)})
    except Exception as e:
        raise RazorpayOrderCreateFailedError() from e
```

### modules/payments/schemas.py
```python
import uuid
from decimal import Decimal
from datetime import date
from typing import Any
from pydantic import BaseModel, field_validator


class WebhookPayload(BaseModel):
    """Razorpay webhook body (parsed from JSON)."""
    entity  : str
    event   : str
    payload : dict


class MarkPaidRequest(BaseModel):
    payment_mode    : str           # "cash" | "upi_manual" | "credit"
    credit_due_date : date | None = None


class PaymentResponse(BaseModel):
    order_id      : uuid.UUID
    payment_mode  : str
    status        : str
    amount        : str
    paid_at       : Any | None

    @field_validator("amount", mode="before")
    @classmethod
    def to_str(cls, v: Any) -> str:
        return str(v)
```

### modules/payments/service.py
```python
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

    async def create_payment_record(self, order_id: uuid.UUID, mode: str,
                                     amount: Decimal,
                                     rzp_order_id: str | None = None,
                                     credit_due_date=None,
                                     status: str = "pending") -> Payment:
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

    async def confirm_payment(self, order_id: uuid.UUID,
                               rzp_payment_id: str,
                               rzp_signature: str) -> None:
        if not self.db:
            return
        result = await self.db.execute(
            select(Payment).where(Payment.order_id == order_id)
        )
        payment = result.scalar_one_or_none()
        if payment and payment.status == "pending":
            payment.status              = "paid"
            payment.razorpay_payment_id = rzp_payment_id
            payment.razorpay_signature  = rzp_signature
            payment.paid_at             = datetime.now(timezone.utc)
            self.db.add(payment)
            await self.db.flush()

    async def mark_paid(self, order_id: uuid.UUID, mode: str,
                        credit_due_date=None) -> dict:
        if not self.db:
            raise RuntimeError("DB required for mark_paid")
        result = await self.db.execute(
            select(Payment).where(Payment.order_id == order_id)
        )
        payment = result.scalar_one_or_none()
        if not payment:
            raise ValueError(f"No payment record for order {order_id}")
        payment.payment_mode = mode
        if mode == "credit":
            payment.status          = "outstanding"
            payment.credit_due_date = credit_due_date
        else:
            payment.status  = "paid"
            payment.paid_at = datetime.now(timezone.utc)
        self.db.add(payment)
        await self.db.flush()
        return {
            "order_id":    str(order_id),
            "payment_mode": payment.payment_mode,
            "status":       payment.status,
            "amount":       str(payment.amount),
            "paid_at":      payment.paid_at.isoformat() if payment.paid_at else None,
        }

    def issue_refund(self, razorpay_payment_id: str, amount: Decimal) -> dict:
        return rzp_client.issue_refund(razorpay_payment_id, amount)
```

### modules/payments/router.py
```python
import uuid
import json
import logging
from fastapi import APIRouter, Depends, Request, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from modules.payments.schemas import MarkPaidRequest
from modules.payments.service import PaymentService
from modules.payments import razorpay as rzp_client
from modules.orders.service import OrderService
from modules.orders.repository import OrderRepository
from modules.products.service import ProductService
from modules.products.repository import ProductRepository
from modules.inventory.service import InventoryService
from modules.inventory.repository import InventoryRepository
from modules.notify.service import NotifyService
from shared.exceptions import WebhookSignatureInvalidError
from core.dependencies import require_owner, get_db_session
from core.redis import cache_get, cache_set

logger = logging.getLogger("payments")
router = APIRouter(prefix="/api/payments", tags=["payments"])

WEBHOOK_IDEMPOTENCY_TTL = 7 * 24 * 3600   # 7 days


def _svc(db: AsyncSession = Depends(get_db_session)) -> PaymentService:
    return PaymentService(db=db)


def _order_svc(db: AsyncSession = Depends(get_db_session)) -> OrderService:
    return OrderService(
        repo      = OrderRepository(db),
        products  = ProductService(repo=ProductRepository(db)),
        inventory = InventoryService(repo=InventoryRepository(db),
                                     product_repo=ProductRepository(db)),
        payments  = PaymentService(db=db),
        notify    = NotifyService(),
    )


@router.post("/webhook")
async def razorpay_webhook(
    request  : Request,
    bg       : BackgroundTasks,
    svc      : PaymentService  = Depends(_svc),
    order_svc: OrderService    = Depends(_order_svc),
):
    """
    Razorpay sends webhooks here.
    CRITICAL: Must return 200 quickly — BG tasks run after response.
    CRITICAL: Must be idempotent — Razorpay retries for 24 hours.
    """
    body = await request.body()
    sig  = request.headers.get("X-Razorpay-Signature", "")

    # ── Step 1: Verify HMAC signature ──────────────────────────────────────
    try:
        rzp_client.verify_webhook_signature(body, sig)
    except WebhookSignatureInvalidError:
        logger.warning("Webhook HMAC failed — possible spoofing attempt")
        raise HTTPException(status_code=400, detail={
            "error":   "WEBHOOK_SIGNATURE_INVALID",
            "message": "Invalid webhook signature",
        })

    payload = json.loads(body)
    event   = payload.get("event", "")

    if event != "payment.captured":
        return {"status": "ok", "note": "event_ignored"}

    payment_entity = payload["payload"]["payment"]["entity"]
    rzp_payment_id = payment_entity["id"]
    rzp_order_id   = payment_entity.get("order_id", "")

    # ── Step 2: Idempotency check ───────────────────────────────────────────
    idem_key = f"webhook:rzp:{rzp_payment_id}"
    if await cache_get(idem_key):
        logger.info(f"Duplicate webhook ignored: {rzp_payment_id}")
        return {"status": "ok", "note": "already_processed"}

    await cache_set(idem_key, "1", ttl=WEBHOOK_IDEMPOTENCY_TTL)

    # ── Step 3: Find our order by Razorpay order_id ─────────────────────────
    from sqlalchemy import select
    from modules.orders.models import Order
    result = await svc.db.execute(
        select(Order).where(Order.razorpay_order_id == rzp_order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        logger.error(f"Webhook: no order found for rzp_order_id={rzp_order_id}")
        return {"status": "ok", "note": "order_not_found"}

    # ── Step 4: Confirm order + decrement stock (atomic) ───────────────────
    bg.add_task(
        order_svc.confirm_from_webhook,
        order.id, rzp_payment_id, sig, bg,
    )

    return {"status": "ok"}


@router.patch("/{order_id}/mark-paid")
async def mark_paid(
    order_id : uuid.UUID,
    body     : MarkPaidRequest,
    owner    : dict = Depends(require_owner),
    svc      : PaymentService = Depends(_svc),
):
    """Owner marks an offline order as paid (cash/UPI/credit)."""
    return await svc.mark_paid(order_id, body.payment_mode, body.credit_due_date)


@router.get("/outstanding")
async def outstanding_credits(
    owner : dict = Depends(require_owner),
    db    : AsyncSession = Depends(get_db_session),
):
    """All credit sales not yet collected."""
    from sqlalchemy import select
    from modules.orders.models import Payment, Order
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Payment)
        .where(Payment.status == "outstanding")
        .options(selectinload(Payment.order))
        .order_by(Payment.credit_due_date.asc().nullslast())
    )
    payments = result.scalars().all()
    return [
        {
            "order_id":       str(p.order_id),
            "order_number":   p.order.order_number if p.order else "",
            "customer_name":  p.order.customer_name if p.order else "",
            "customer_phone": p.order.customer_phone if p.order else "",
            "amount":         str(p.amount),
            "credit_due_date":p.credit_due_date.isoformat() if p.credit_due_date else None,
        }
        for p in payments
    ]
```

---

## MODULE 6 — P&L ENGINE

### modules/pl_engine/schemas.py
```python
from pydantic import BaseModel
from typing import Any


class PLResponse(BaseModel):
    month          : str
    from_cache     : bool
    warnings       : list[str]

    rev_online     : str
    rev_offline    : str
    rev_credit     : str
    rev_total      : str

    cogs_opening   : str
    cogs_own_prod  : str
    cogs_purchased : str
    cogs_norm_loss : str
    cogs_consumed  : str
    cogs_closing   : str
    cogs_total     : str

    gross_profit   : str
    abnormal_loss  : str

    opex_fixed     : str
    opex_deprec    : str
    opex_provisions: str
    opex_total     : str

    net_profit     : str
    net_margin_pct : str

    cash_inflow    : str
    cash_outflow   : str
    net_cash_flow  : str
    cash_pl_gap    : str

    price_variance : str
    cost_variance  : str


class BreakevenResponse(BaseModel):
    product_id         : str
    product_name       : str
    sell_price         : str
    variable_cost      : str
    contribution_margin: str
    fixed_costs_monthly: str
    breakeven_qty      : str
    breakeven_revenue  : str
```

### modules/pl_engine/calculator.py
```python
"""
P&L Calculator — pure function, no DB.
All arithmetic: Python Decimal — never float.
Called by PLService after data is fetched.
"""
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from typing import Any


DP5  = Decimal("0.00001")
ZERO = Decimal("0.00000")


@dataclass
class PLResult:
    month          : str
    from_cache     : bool = False
    warnings       : list[str] = field(default_factory=list)

    rev_online     : Decimal = ZERO
    rev_offline    : Decimal = ZERO
    rev_credit     : Decimal = ZERO
    rev_total      : Decimal = ZERO

    cogs_opening   : Decimal = ZERO
    cogs_own_prod  : Decimal = ZERO
    cogs_purchased : Decimal = ZERO
    cogs_norm_loss : Decimal = ZERO
    cogs_consumed  : Decimal = ZERO
    cogs_closing   : Decimal = ZERO
    cogs_total     : Decimal = ZERO

    gross_profit   : Decimal = ZERO
    abnormal_loss  : Decimal = ZERO

    opex_fixed     : Decimal = ZERO
    opex_deprec    : Decimal = ZERO
    opex_provisions: Decimal = ZERO
    opex_total     : Decimal = ZERO

    net_profit     : Decimal = ZERO
    net_margin_pct : Decimal = ZERO

    cash_inflow    : Decimal = ZERO
    cash_outflow   : Decimal = ZERO
    net_cash_flow  : Decimal = ZERO
    cash_pl_gap    : Decimal = ZERO

    price_variance : Decimal = ZERO
    cost_variance  : Decimal = ZERO

    def to_dict(self) -> dict:
        def s(v): return str(v.quantize(DP5, ROUND_HALF_UP))
        return {
            "month": self.month, "from_cache": self.from_cache,
            "warnings": self.warnings,
            "rev_online": s(self.rev_online), "rev_offline": s(self.rev_offline),
            "rev_credit": s(self.rev_credit), "rev_total": s(self.rev_total),
            "cogs_opening": s(self.cogs_opening), "cogs_own_prod": s(self.cogs_own_prod),
            "cogs_purchased": s(self.cogs_purchased), "cogs_norm_loss": s(self.cogs_norm_loss),
            "cogs_consumed": s(self.cogs_consumed), "cogs_closing": s(self.cogs_closing),
            "cogs_total": s(self.cogs_total),
            "gross_profit": s(self.gross_profit), "abnormal_loss": s(self.abnormal_loss),
            "opex_fixed": s(self.opex_fixed), "opex_deprec": s(self.opex_deprec),
            "opex_provisions": s(self.opex_provisions), "opex_total": s(self.opex_total),
            "net_profit": s(self.net_profit), "net_margin_pct": s(self.net_margin_pct),
            "cash_inflow": s(self.cash_inflow), "cash_outflow": s(self.cash_outflow),
            "net_cash_flow": s(self.net_cash_flow), "cash_pl_gap": s(self.cash_pl_gap),
            "price_variance": s(self.price_variance), "cost_variance": s(self.cost_variance),
        }


def calculate(
    month       : str,
    entries     : list,        # StockEntry rows
    monthly_stk : list,        # MonthlyStock rows
    assets      : list,        # Asset rows
    products    : dict,        # {product_id: Product}
    from_cache  : bool = False,
) -> PLResult:
    r = PLResult(month=month, from_cache=from_cache)

    def _sum(rows, key="total_amount") -> Decimal:
        return sum((getattr(e, key) or ZERO for e in rows), ZERO)

    # ── Revenue ────────────────────────────────────────────────────────────
    sales   = [e for e in entries if e.entry_type == "sale"]
    online  = [e for e in sales if e.channel == "online"]
    offline = [e for e in sales if e.channel == "offline"]
    credit  = [e for e in sales if e.pay_mode == "credit"]
    cash_s  = [e for e in sales if e.pay_mode != "credit"]

    r.rev_online  = _sum(online)
    r.rev_offline = _sum(offline)
    r.rev_credit  = _sum(credit)
    r.rev_total   = r.rev_online + r.rev_offline

    # Price variance
    r.price_variance = sum(
        (e.price_variance or ZERO for e in sales if e.price_variance is not None), ZERO
    )

    # ── COGS ───────────────────────────────────────────────────────────────
    # Opening stock
    r.cogs_opening = sum(
        (ms.value for ms in monthly_stk if ms.stock_type == "opening"), ZERO
    )
    if not any(ms.stock_type == "opening" for ms in monthly_stk):
        r.warnings.append("Opening stock missing — COGS and net profit are inaccurate")

    # Own production cost: own-source sales × product.farm_cost
    own_sales = [e for e in sales if e.source == "own"]
    for e in own_sales:
        p = products.get(str(e.product_id))
        if p:
            r.cogs_own_prod += (p.farm_cost or ZERO) * (e.qty or ZERO)

    # External purchases
    purchases     = [e for e in entries if e.entry_type == "purchase"]
    r.cogs_purchased = _sum(purchases)

    # Cost variance
    r.cost_variance = sum(
        (e.cost_variance or ZERO for e in purchases if e.cost_variance is not None), ZERO
    )

    # Normal loss absorbed
    r.cogs_norm_loss = _sum([e for e in entries if e.entry_type == "wastage_normal"])

    # Own consumption at market value
    r.cogs_consumed = _sum([e for e in entries if e.entry_type == "consumption"])

    # Closing stock
    r.cogs_closing = sum(
        (ms.value for ms in monthly_stk if ms.stock_type == "closing"), ZERO
    )

    r.cogs_total = (r.cogs_opening + r.cogs_own_prod + r.cogs_purchased
                    + r.cogs_norm_loss + r.cogs_consumed - r.cogs_closing)

    r.gross_profit = r.rev_total - r.cogs_total

    # ── Abnormal loss ──────────────────────────────────────────────────────
    r.abnormal_loss = _sum([e for e in entries if e.entry_type == "wastage_abnormal"])

    # ── Operating expenses ─────────────────────────────────────────────────
    r.opex_fixed     = _sum([e for e in entries if e.entry_type == "fixed_cost"])
    r.opex_provisions= _sum([e for e in entries if e.entry_type == "provision"])
    r.opex_deprec    = sum((a.monthly_depreciation for a in assets), ZERO)
    r.opex_total     = r.opex_fixed + r.opex_provisions + r.opex_deprec

    # ── Net profit ─────────────────────────────────────────────────────────
    r.net_profit = r.gross_profit - r.abnormal_loss - r.opex_total
    if r.rev_total > ZERO:
        r.net_margin_pct = r.net_profit / r.rev_total * Decimal("100")

    # ── Cash flow ──────────────────────────────────────────────────────────
    r.cash_inflow  = _sum(cash_s)
    r.cash_outflow = (_sum(purchases) +
                      _sum([e for e in entries if e.entry_type == "fixed_cost"]))
    capex_out      = _sum([e for e in entries if e.entry_type == "capex"])
    r.net_cash_flow= r.cash_inflow - r.cash_outflow - capex_out
    r.cash_pl_gap  = r.rev_credit  # credit sales counted in P&L but not cash

    return r
```

### modules/pl_engine/service.py
```python
import json
import logging
from datetime import date as dt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from modules.pl_engine.calculator import calculate, PLResult
from modules.inventory.repository import InventoryRepository
from modules.inventory.models import StockEntry
from modules.finance.models import Asset
from modules.products.models import Product
from core.redis import cache_get, cache_set

logger = logging.getLogger("pl_engine")

PL_CACHE_TTL = 24 * 3600   # 24 hours for past months


class PLService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_monthly_pl(self, month: str) -> dict:
        """
        Returns full P&L dict for the given month.
        Past months cached in Redis 24h.
        Current month always recalculated.
        """
        current_month = dt.today().strftime("%Y-%m")
        is_past       = month < current_month

        cache_key = f"pl:monthly:{month}"
        if is_past:
            cached = await cache_get(cache_key)
            if cached:
                cached["from_cache"] = True
                return cached

        # Fetch all data in parallel-ish (single DB round trip per query)
        inv_repo = InventoryRepository(self.db)
        entries  = await inv_repo.fetch_for_month(month)
        stk      = await inv_repo.get_monthly_stock(month)
        assets   = await self._get_active_assets()
        products = await self._get_products_dict()

        result = calculate(
            month=month,
            entries=entries,
            monthly_stk=stk,
            assets=assets,
            products=products,
        )

        result_dict = result.to_dict()

        if is_past and not result.warnings:
            await cache_set(cache_key, json.dumps(result_dict), ttl=PL_CACHE_TTL)

        return result_dict

    async def get_breakeven(self, product_id: str) -> dict:
        from uuid import UUID
        p_result = await self.db.execute(
            select(Product).where(Product.id == UUID(product_id))
        )
        p = p_result.scalar_one_or_none()
        if not p:
            return {"error": "product_not_found"}

        assets       = await self._get_active_assets()
        from modules.finance.models import FixedCost
        fc_result = await self.db.execute(select(FixedCost).where(FixedCost.is_active == True))
        fixed_costs  = fc_result.scalars().all()

        monthly_fixed = (
            sum((a.monthly_depreciation for a in assets), __import__("decimal").Decimal("0"))
            + sum((f.monthly_amount for f in fixed_costs), __import__("decimal").Decimal("0"))
        )

        from decimal import Decimal
        variable_cost = (p.farm_cost or Decimal("0")) + (p.labor_cost or Decimal("0"))
        cm = p.sell_price - variable_cost

        if cm <= Decimal("0"):
            be_qty = Decimal("999999")
            be_rev = Decimal("999999")
        else:
            be_qty = monthly_fixed / cm
            be_rev = be_qty * p.sell_price

        return {
            "product_id":          str(p.id),
            "product_name":        p.name,
            "sell_price":          str(p.sell_price),
            "variable_cost":       str(variable_cost),
            "contribution_margin": str(cm),
            "fixed_costs_monthly": str(monthly_fixed),
            "breakeven_qty":       str(be_qty.quantize(__import__("decimal").Decimal("0.00001"))),
            "breakeven_revenue":   str(be_rev.quantize(__import__("decimal").Decimal("0.00001"))),
        }

    async def get_product_margins(self) -> list[dict]:
        """Ranked product margin table."""
        result  = await self.db.execute(select(Product).where(Product.deleted_at.is_(None)))
        products = result.scalars().all()
        from decimal import Decimal
        rows = []
        for p in products:
            margin = p.sell_price - p.true_cost
            pct    = (margin / p.sell_price * 100) if p.sell_price else Decimal("0")
            vc     = (p.farm_cost or Decimal("0")) + (p.labor_cost or Decimal("0"))
            cm     = p.sell_price - vc
            rows.append({
                "product_id":          str(p.id),
                "product_name":        p.name,
                "unit":                p.unit,
                "true_cost":           str(p.true_cost),
                "sell_price":          str(p.sell_price),
                "gross_margin":        str(margin),
                "margin_pct":          str(pct),
                "contribution_margin": str(cm),
            })
        return sorted(rows, key=lambda x: float(x["margin_pct"]), reverse=True)

    async def _get_active_assets(self) -> list:
        result = await self.db.execute(select(Asset).where(Asset.is_active == True))
        return result.scalars().all()

    async def _get_products_dict(self) -> dict:
        result = await self.db.execute(select(Product))
        return {str(p.id): p for p in result.scalars().all()}
```

### modules/pl_engine/router.py
```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from modules.pl_engine.service import PLService
from core.dependencies import require_owner, get_db_session
from datetime import date

router = APIRouter(prefix="/api/pl", tags=["pl_engine"])


def _svc(db: AsyncSession = Depends(get_db_session)) -> PLService:
    return PLService(db=db)


@router.get("/monthly")
async def monthly_pl(
    month   : str  = Query(default_factory=lambda: date.today().strftime("%Y-%m"),
                           pattern=r"^\d{4}-\d{2}$"),
    owner   : dict = Depends(require_owner),
    svc     : PLService = Depends(_svc),
):
    """Full P&L statement for a month. Past months served from cache."""
    return await svc.get_monthly_pl(month)


@router.get("/breakeven/{product_id}")
async def breakeven(
    product_id : str,
    owner      : dict = Depends(require_owner),
    svc        : PLService = Depends(_svc),
):
    return await svc.get_breakeven(product_id)


@router.get("/margins")
async def product_margins(
    owner : dict = Depends(require_owner),
    svc   : PLService = Depends(_svc),
):
    """All products ranked by margin — highest to lowest."""
    return await svc.get_product_margins()
```

### modules/finance/models.py
```python
import uuid
from decimal import Decimal
from datetime import datetime, date, timezone
from sqlalchemy import String, Boolean, Integer, TIMESTAMP, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column, Mapped
from shared.models.base import Base, MONEY


class FixedCost(Base):
    __tablename__ = "fixed_costs"

    id             : Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name           : Mapped[str]       = mapped_column(String(200), nullable=False)
    category       : Mapped[str]       = mapped_column(String(50),  nullable=False)
    monthly_amount : Mapped[Decimal]   = mapped_column(MONEY, nullable=False)
    is_active      : Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at     : Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True),
                                                       default=lambda: datetime.now(timezone.utc))
    updated_at     : Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True),
                                                       default=lambda: datetime.now(timezone.utc))
    deleted_at     : Mapped[datetime|None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class Asset(Base):
    __tablename__ = "assets"

    id                   : Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name                 : Mapped[str]       = mapped_column(String(200), nullable=False)
    cost                 : Mapped[Decimal]   = mapped_column(MONEY, nullable=False)
    useful_life_years    : Mapped[int]       = mapped_column(Integer, nullable=False)
    monthly_depreciation : Mapped[Decimal]   = mapped_column(MONEY, nullable=False)
    purchase_date        : Mapped[date]      = mapped_column(Date, nullable=False)
    is_active            : Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at           : Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True),
                                                             default=lambda: datetime.now(timezone.utc))
    deleted_at           : Mapped[datetime|None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
```

### modules/finance/router.py
```python
import uuid
from decimal import Decimal
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field, field_validator
from typing import Any
from modules.finance.models import FixedCost, Asset
from core.dependencies import require_owner, get_db_session

router = APIRouter(prefix="/api/finance", tags=["finance"])


class FixedCostCreate(BaseModel):
    name           : str
    category       : str
    monthly_amount : Decimal

    @field_validator("monthly_amount", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float): raise ValueError("No float")
        return Decimal(str(v))


class AssetCreate(BaseModel):
    name              : str
    cost              : Decimal
    useful_life_years : int = Field(ge=1)
    purchase_date     : date

    @field_validator("cost", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float): raise ValueError("No float")
        return Decimal(str(v))


@router.get("/fixed-costs")
async def list_fixed_costs(owner: dict = Depends(require_owner),
                            db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(FixedCost).where(FixedCost.deleted_at.is_(None)))
    return [{"id": str(f.id), "name": f.name, "category": f.category,
             "monthly_amount": str(f.monthly_amount), "is_active": f.is_active}
            for f in result.scalars().all()]


@router.post("/fixed-costs", status_code=201)
async def create_fixed_cost(body: FixedCostCreate, owner: dict = Depends(require_owner),
                             db: AsyncSession = Depends(get_db_session)):
    fc = FixedCost(name=body.name, category=body.category, monthly_amount=body.monthly_amount)
    db.add(fc)
    await db.flush()
    return {"id": str(fc.id), "name": fc.name, "monthly_amount": str(fc.monthly_amount)}


@router.get("/assets")
async def list_assets(owner: dict = Depends(require_owner),
                       db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(Asset).where(Asset.deleted_at.is_(None)))
    assets = result.scalars().all()
    total_depreciation = sum((a.monthly_depreciation for a in assets), Decimal("0"))
    return {
        "assets": [{"id": str(a.id), "name": a.name, "cost": str(a.cost),
                    "useful_life_years": a.useful_life_years,
                    "monthly_depreciation": str(a.monthly_depreciation),
                    "purchase_date": a.purchase_date.isoformat(),
                    "is_active": a.is_active}
                   for a in assets],
        "total_monthly_depreciation": str(total_depreciation),
    }


@router.post("/assets", status_code=201)
async def create_asset(body: AssetCreate, owner: dict = Depends(require_owner),
                        db: AsyncSession = Depends(get_db_session)):
    depreciation = body.cost / Decimal(str(body.useful_life_years * 12))
    asset = Asset(name=body.name, cost=body.cost,
                  useful_life_years=body.useful_life_years,
                  monthly_depreciation=depreciation,
                  purchase_date=body.purchase_date)
    db.add(asset)
    await db.flush()
    return {"id": str(asset.id), "name": asset.name,
            "monthly_depreciation": str(asset.monthly_depreciation)}
```
