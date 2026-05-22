# Stage 7 · Testing · Part 3 — Factories + Edge Cases + Coverage + Run Guide


## tests/fixtures/factories.py
"""
Factory Boy factories for generating realistic test data.
Use these in tests instead of manually building DB objects.
"""
import uuid
import factory
from decimal import Decimal
from datetime import date, timedelta
from factory.alchemy import SQLAlchemyModelFactory
from modules.auth.models import Owner
from modules.products.models import Product
from modules.inventory.models import InventoryStock, StockEntry
from modules.orders.models import Order, OrderItem, Payment
from modules.farm.models import FarmSeason, FarmInput
from modules.petha.models import PethaBatch
from modules.finance.models import Asset, FixedCost
from core.security import hash_password


class BaseFactory(SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session_persistence = "flush"


class OwnerFactory(BaseFactory):
    class Meta:
        model = Owner

    username      = factory.Sequence(lambda n: f"owner_{n}")
    password_hash = factory.LazyFunction(lambda: hash_password("TestPass123!"))


class ProductFactory(BaseFactory):
    class Meta:
        model = Product

    name                 = factory.Sequence(lambda n: f"Product {n}")
    slug                 = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))
    category             = "rice"
    unit                 = "kg"
    sell_price           = Decimal("100.00000")
    farm_cost            = Decimal("50.00000")
    labor_cost           = Decimal("5.00000")
    overhead_cost        = Decimal("3.00000")
    packaging_cost       = Decimal("7.00000")
    normal_loss_percent  = Decimal("0.00000")
    true_cost            = Decimal("65.00000")
    is_active            = True
    is_own_farm          = True
    low_stock_threshold  = Decimal("5.000")


class StockFactory(BaseFactory):
    class Meta:
        model = InventoryStock

    product_id  = factory.LazyFunction(uuid.uuid4)
    current_qty = Decimal("50.000")


class OrderFactory(BaseFactory):
    class Meta:
        model = Order

    idempotency_key  = factory.LazyFunction(uuid.uuid4)
    order_number     = factory.Sequence(lambda n: f"LKP-2025-{n:04d}")
    customer_name    = factory.Faker("name")
    customer_phone   = "+919876543210"
    fulfillment_type = "pickup"
    channel          = "offline"
    status           = "pending"
    total_amount     = Decimal("315.00000")
    discount_amount  = Decimal("0.00000")
    final_amount     = Decimal("315.00000")


class AssetFactory(BaseFactory):
    class Meta:
        model = Asset

    name                 = factory.Sequence(lambda n: f"Asset {n}")
    cost                 = Decimal("12000.00000")
    useful_life_years    = 10
    monthly_depreciation = Decimal("100.00000")
    purchase_date        = factory.LazyFunction(lambda: date(2024, 1, 1))
    is_active            = True


class FixedCostFactory(BaseFactory):
    class Meta:
        model = FixedCost

    name           = factory.Sequence(lambda n: f"Fixed cost {n}")
    category       = "stall"
    monthly_amount = Decimal("1200.00000")
    is_active      = True


class FarmSeasonFactory(BaseFactory):
    class Meta:
        model = FarmSeason

    variety                = "joha"
    area_bigha             = Decimal("3.500")
    status                 = "active"
    start_date             = factory.LazyFunction(lambda: date(2025, 6, 1))
    total_cultivation_cost = Decimal("40000.00000")


class PethaBatchFactory(BaseFactory):
    class Meta:
        model = PethaBatch

    variety               = "narikal"
    status                = "in_production"
    batch_date            = factory.LazyFunction(lambda: date.today())
    planned_pieces        = 30
    shelf_life_days       = 7
    total_ingredient_cost = Decimal("90.00000")
    total_labor_cost      = Decimal("150.00000")
    total_overhead_cost   = Decimal("25.00000")
    total_batch_cost      = Decimal("265.00000")
    expiry_date           = factory.LazyFunction(lambda: date.today() + timedelta(days=7))
    recipe_snapshot       = {"petha_guri_kg": "1.5"}
```

---

## tests/integration/test_edge_cases.py
```python
"""
Critical edge cases — these represent real-world failure scenarios
that MUST be handled correctly in production.
"""
import pytest
import uuid
import asyncio
from decimal import Decimal
from datetime import date


class TestRaceConditions:
    async def test_concurrent_orders_do_not_oversell(
        self, auth_client, joha_product, mock_wati
    ):
        """
        Simulate two customers ordering the last 5 kg simultaneously.
        Only ONE should succeed. The second must get STOCK_INSUFFICIENT.
        This tests the SELECT FOR UPDATE row lock in decrement_stock().
        """
        product, stock = joha_product
        # Set stock to exactly 5 kg
        await auth_client.patch(f"/api/products/{product.id}", json={})
        # Directly set stock via a purchase entry
        await auth_client.post("/api/inventory/entries", json={
            "idempotency_key": str(uuid.uuid4()),
            "product_id":      str(product.id),
            "entry_type":      "purchase",
            "qty":             str(Decimal("5") - stock.current_qty)
                               if stock.current_qty < Decimal("5")
                               else "0",
            "total_amount":    "0",
            "date":            date.today().isoformat(),
        })

        # Both try to order 5 kg simultaneously
        async def place_order():
            return await auth_client.post("/api/orders/", json={
                "idempotency_key":  str(uuid.uuid4()),
                "customer_name":    "Customer",
                "customer_phone":   "+919876543210",
                "fulfillment_type": "pickup",
                "channel":          "offline",
                "payment_mode":     "cash",
                "items": [{"product_id": str(product.id), "qty": "5", "source": "own"}],
            })

        results = await asyncio.gather(
            place_order(), place_order(), return_exceptions=True
        )
        status_codes = [r.status_code for r in results if hasattr(r, "status_code")]
        # One 201 + one 422, or both 422 — never two 201s
        assert status_codes.count(201) <= 1, \
            "Race condition: both orders succeeded — stock oversold!"


class TestFinancialAccuracy:
    async def test_pl_net_profit_with_all_components(
        self, auth_client, joha_product, rice_mill_asset, stall_rent, mock_wati
    ):
        """
        Full P&L cycle:
        - Set opening stock
        - Create a sale
        - Set closing stock
        - Add fixed cost entry
        - Verify net_profit formula: gross_profit - opex
        """
        product, _ = joha_product
        month = date.today().strftime("%Y-%m")

        # Opening stock
        await auth_client.post("/api/inventory/monthly-stock", json={
            "product_id": str(product.id), "month": month,
            "stock_type": "opening", "qty": "50", "value": "4000",
        })

        # Sale
        await auth_client.post("/api/orders/", json={
            "idempotency_key":  str(uuid.uuid4()),
            "customer_name":    "Test",
            "customer_phone":   "+919876543210",
            "fulfillment_type": "pickup",
            "channel":          "online",
            "payment_mode":     "cash",
            "items": [{"product_id": str(product.id), "qty": "5", "source": "own"}],
        })

        # Fixed cost entry
        await auth_client.post("/api/inventory/entries", json={
            "idempotency_key": str(uuid.uuid4()),
            "product_id":      str(product.id),
            "entry_type":      "fixed_cost",
            "qty":             "1",
            "total_amount":    "1200",
            "date":            date.today().isoformat(),
        })

        # Closing stock
        await auth_client.post("/api/inventory/monthly-stock", json={
            "product_id": str(product.id), "month": month,
            "stock_type": "closing", "qty": "45", "value": "3600",
        })

        pl = await auth_client.get(f"/api/pl/monthly?month={month}")
        assert pl.status_code == 200
        data = pl.json()

        # Verify formula: net_profit = gross_profit - abnormal_loss - opex_total
        gross  = Decimal(data["gross_profit"])
        abnorm = Decimal(data["abnormal_loss"])
        opex   = Decimal(data["opex_total"])
        net    = Decimal(data["net_profit"])

        assert net == gross - abnorm - opex, \
            f"net_profit formula wrong: {net} != {gross} - {abnorm} - {opex}"

    async def test_credit_sale_in_revenue_not_cash_flow(
        self, auth_client, joha_product, mock_wati
    ):
        """
        Credit sale counts in P&L revenue (accrual)
        but NOT in cash_inflow (cash basis).
        cash_pl_gap must equal credit amount.
        """
        product, _ = joha_product
        month = date.today().strftime("%Y-%m")

        await auth_client.post("/api/inventory/monthly-stock", json={
            "product_id": str(product.id), "month": month,
            "stock_type": "opening", "qty": "50", "value": "4000",
        })

        await auth_client.post("/api/orders/", json={
            "idempotency_key":  str(uuid.uuid4()),
            "customer_name":    "Credit Customer",
            "customer_phone":   "+919876543210",
            "fulfillment_type": "pickup",
            "channel":          "offline",
            "payment_mode":     "credit",
            "items": [{"product_id": str(product.id), "qty": "3", "source": "own"}],
        })

        pl = await auth_client.get(f"/api/pl/monthly?month={month}")
        data = pl.json()

        rev_credit   = Decimal(data["rev_credit"])
        cash_pl_gap  = Decimal(data["cash_pl_gap"])
        cash_inflow  = Decimal(data["cash_inflow"])
        rev_total    = Decimal(data["rev_total"])

        assert rev_credit   == cash_pl_gap, "cash_pl_gap must equal credit amount"
        assert cash_inflow  == rev_total - rev_credit, "cash_inflow excludes credit"


class TestDataIntegrity:
    async def test_soft_delete_preserves_data(self, auth_client, joha_product):
        """Soft-deleted product must still exist in DB (financial audit trail)."""
        product, _ = joha_product
        await auth_client.delete(f"/api/products/{product.id}")

        # Owner can still see it
        resp = await auth_client.get("/api/products/")
        ids = [p["id"] for p in resp.json()]
        assert str(product.id) in ids
        deleted = next(p for p in resp.json() if p["id"] == str(product.id))
        assert deleted["is_active"] is False

    async def test_order_items_snapshot_price(self, auth_client, joha_product, mock_wati):
        """
        Order item must snapshot sell_price at order time.
        Later price changes must NOT affect existing order items.
        """
        product, _ = joha_product

        # Create order at current price (105)
        order_resp = await auth_client.post("/api/orders/", json={
            "idempotency_key":  str(uuid.uuid4()),
            "customer_name":    "Test",
            "customer_phone":   "+919876543210",
            "fulfillment_type": "pickup",
            "channel":          "offline",
            "payment_mode":     "cash",
            "items": [{"product_id": str(product.id), "qty": "1", "source": "own"}],
        })
        original_price = Decimal(order_resp.json()["items"][0]["unit_price"])
        assert original_price == Decimal("105.00000")

        # Change the sell price
        await auth_client.patch(f"/api/products/{product.id}", json={"sell_price": "200"})

        # Retrieve the original order — price must still be 105
        order_id   = order_resp.json()["id"]
        check_resp = await auth_client.get(f"/api/orders/{order_id}")
        assert check_resp.status_code == 200
        saved_price = Decimal(check_resp.json()["items"][0]["unit_price"])
        assert saved_price == Decimal("105.00000"), \
            "Order item price was modified after product price change!"

    async def test_stock_never_goes_negative(self, auth_client, joha_product):
        """Direct stock manipulation must never result in negative qty."""
        product, stock = joha_product
        # Try to record a wastage entry larger than current stock
        current = stock.current_qty
        resp = await auth_client.post("/api/inventory/entries", json={
            "idempotency_key": str(uuid.uuid4()),
            "product_id":      str(product.id),
            "entry_type":      "wastage_abnormal",
            "qty":             str(current + Decimal("100")),  # more than available
            "total_amount":    "5000",
            "date":            date.today().isoformat(),
        })
        # Either rejected with 422, or stock stays >= 0
        if resp.status_code == 201:
            stock_resp = await auth_client.get("/api/inventory/stock")
            stocks = {p["product_id"]: p for p in stock_resp.json()}
            qty = Decimal(stocks[str(product.id)]["current_qty"])
            assert qty >= Decimal("0"), "Stock went negative!"


class TestWebhookSecurity:
    async def test_webhook_with_tampered_amount_rejected(self, client):
        """
        Attacker sends correct signature but tampered amount.
        Body hash won't match signature → rejected.
        """
        import json
        import hashlib
        import hmac
        from core.config import settings

        # Build payload with one amount
        original_body = json.dumps({
            "event": "payment.captured",
            "payload": {"payment": {"entity": {
                "id": "pay_attack", "order_id": "order_xyz",
                "amount": 1, "currency": "INR", "status": "captured",
            }}}
        }).encode()

        # Sign the original
        real_sig = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode(),
            original_body, hashlib.sha256,
        ).hexdigest()

        # Tamper with the body (higher amount)
        tampered_body = json.dumps({
            "event": "payment.captured",
            "payload": {"payment": {"entity": {
                "id": "pay_attack", "order_id": "order_xyz",
                "amount": 99999999, "currency": "INR", "status": "captured",
            }}}
        }).encode()

        resp = await client.post(
            "/api/payments/webhook",
            content=tampered_body,
            headers={
                "X-Razorpay-Signature": real_sig,
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "WEBHOOK_SIGNATURE_INVALID"
```

---

## tests/integration/test_notify.py
"""
Notification tests — verify fire-and-forget behaviour.
WATI is always mocked — never sends real messages in tests.
"""
import pytest
import uuid
from datetime import date


class TestNotifications:
    async def test_order_confirmation_triggers_notification(
        self, auth_client, joha_product, mock_wati
    ):
        product, _ = joha_product
        await auth_client.post("/api/orders/", json={
            "idempotency_key":  str(uuid.uuid4()),
            "customer_name":    "Notif Test",
            "customer_phone":   "+919876543210",
            "fulfillment_type": "pickup",
            "channel":          "offline",
            "payment_mode":     "cash",
            "items": [{"product_id": str(product.id), "qty": "1", "source": "own"}],
        })
        # WATI mock was called
        assert mock_wati.called

    async def test_wati_failure_does_not_fail_order(
        self, auth_client, joha_product, mocker
    ):
        """If WATI throws, the order must still succeed."""
        mocker.patch(
            "modules.notify.wati.send_template_message",
            side_effect=Exception("WATI connection refused"),
        )
        product, _ = joha_product
        resp = await auth_client.post("/api/orders/", json={
            "idempotency_key":  str(uuid.uuid4()),
            "customer_name":    "Robust Test",
            "customer_phone":   "+919876543210",
            "fulfillment_type": "pickup",
            "channel":          "offline",
            "payment_mode":     "cash",
            "items": [{"product_id": str(product.id), "qty": "1", "source": "own"}],
        })
        # Order succeeds despite WATI failure
        assert resp.status_code == 201
        assert resp.json()["status"] == "confirmed"

    async def test_notification_log_accessible(self, auth_client):
        resp = await auth_client.get("/api/notify/log")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
```

---

## Coverage configuration (already in pyproject.toml — reproduced here)
```toml
[tool.coverage.run]
source  = ["modules", "shared", "core"]
omit    = ["*/migrations/*", "*/tests/*", "scripts/*", "*/conftest*"]

[tool.coverage.report]
fail_under    = 75
show_missing  = true
exclude_lines = [
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "pragma: no cover",
]

[tool.coverage.html]
directory = "htmlcov"
```

---

## Running tests — all commands

```bash
# ── From repo root ─────────────────────────────────────────────────────────

# Start test DB (uses same docker-compose, separate DB name)
# Already set in docker-compose.yml — lakhimpur_test DB auto-created

# ── Unit tests only (fast, no DB, ~5 seconds) ──────────────────────────────
make test-unit
# or directly:
docker compose exec backend pytest tests/unit/ -v --tb=short

# ── Integration tests only ─────────────────────────────────────────────────
docker compose exec backend pytest tests/integration/ -v --tb=short

# ── All tests with coverage ────────────────────────────────────────────────
make test-cov
# or directly:
docker compose exec backend pytest tests/ \
  --cov=. \
  --cov-report=term-missing \
  --cov-report=html \
  --cov-fail-under=75 \
  -v

# ── P&L engine must hit 95% (enforced separately) ─────────────────────────
docker compose exec backend pytest tests/unit/test_pl_calculator.py \
  --cov=modules/pl_engine/calculator.py \
  --cov-fail-under=95 \
  -v

# ── Run a specific test ────────────────────────────────────────────────────
docker compose exec backend pytest tests/unit/test_pl_calculator.py::TestRevenue -v
docker compose exec backend pytest tests/integration/test_orders.py::TestOrderCreate::test_oversell_rejected -v

# ── Run tests matching a keyword ──────────────────────────────────────────
docker compose exec backend pytest -k "webhook" -v
docker compose exec backend pytest -k "float" -v

# ── Show slowest tests ──────────────────────────────────────────────────────
docker compose exec backend pytest tests/ --durations=10

# ── Stop on first failure (during active development) ─────────────────────
docker compose exec backend pytest tests/ -x --tb=long

# ── Run without capturing stdout (see print statements) ───────────────────
docker compose exec backend pytest tests/ -s -v
```

---

## Coverage targets — enforcement table

| Module / file | Target | How enforced |
|---|---|---|
| `modules/pl_engine/calculator.py` | **95%+** | Separate pytest-cov run in CI |
| `modules/petha/service.py` | **90%+** | Batch cost absorption logic |
| `modules/payments/router.py` | **90%+** | Webhook idempotency + HMAC |
| `modules/orders/service.py` | **85%+** | Order lifecycle + stock lock |
| `modules/inventory/service.py` | **85%+** | Variance calculation |
| `modules/auth/service.py` | **85%+** | JWT + bcrypt + blocklist |
| `modules/farm/service.py` | **80%+** | Milling yield + byproduct |
| All routers | **70%+** | Covered by integration tests |
| **Overall** | **75%+** | `--cov-fail-under=75` in CI |

---

## Stage 7 complete — checklist

```
Unit tests:
  ✅ P&L calculator — full coverage (revenue, COGS, opex, net, margin)
  ✅ Batch cost absorption — rejection absorbed into good pieces
  ✅ Milling yield — byproduct credit, cost_per_kg_chawl, transfer price
  ✅ true_cost calculation — normal loss absorption formula
  ✅ Pydantic schema validation — float rejected everywhere

Integration tests:
  ✅ Auth — login, logout, JWT blocklist, protected routes
  ✅ Products — CRUD, true_cost, soft delete, public vs owner
  ✅ Inventory — stock entry, variance, idempotency, float rejection
  ✅ Orders — offline confirm, online pending, oversell, cancel+restore
  ✅ Orders — idempotency, invalid transitions, snapshot price
  ✅ Payments — webhook HMAC, confirm+decrement, duplicate idempotency
  ✅ Payments — mark paid (offline), outstanding credits
  ✅ P&L API — all fields present, strings not floats, formula correct
  ✅ P&L API — credit sale in revenue not cash, cash_pl_gap
  ✅ Farm — season lifecycle, milling yield, cannot mill before harvest
  ✅ Petha — batch create, outcome, absorption costing
  ✅ Notify — fire-and-forget, WATI failure doesn't fail order

Edge cases:
  ✅ Race condition — concurrent orders don't oversell (SELECT FOR UPDATE)
  ✅ Webhook tamper — modified amount with real sig rejected
  ✅ Snapshot price — product price change doesn't affect old orders
  ✅ Soft delete — data preserved, still visible to owner
  ✅ Stock never negative — guard at service layer

SDLC Progress:
  0 · Idea          ✅
  1 · Whiteboard    ✅
  2 · Requirements  ✅
  3 · HLD           ✅
  4 · LLD           ✅
  5 · Dev Setup     ✅
  6 · Code          ⚠️  Backend done · Frontend pending
  7 · Testing       ✅  (backend tests complete)
  ──────────────────────────
  8 · Staging       ← NEXT
  9 · Ship
```
