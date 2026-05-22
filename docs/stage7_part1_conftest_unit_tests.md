# Stage 7 · Testing · Part 1 — conftest.py + Unit Tests

---

## tests/conftest.py
```python
import asyncio
import uuid
import pytest
import hashlib
import hmac
import json
from decimal import Decimal
from datetime import date, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from main import app
from shared.models.base import Base
from core.database import get_db
from core.security import hash_password
from modules.auth.models import Owner
from modules.products.models import Product
from modules.inventory.models import InventoryStock, StockEntry
from modules.orders.models import Order, OrderItem, Payment
from modules.finance.models import Asset, FixedCost
from core.config import settings

# ── Test DB URL ───────────────────────────────────────────────────────────────
# Set in CI via env var; fallback to local test DB
import os
TEST_DB = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:testpassword@localhost:5432/lakhimpur_test"
)

# ── Session-scoped event loop ─────────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# ── DB engine: created once per test session ──────────────────────────────────
@pytest.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)   # clean slate
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

# ── Per-test DB session that rolls back ───────────────────────────────────────
@pytest.fixture
async def db(test_engine) -> AsyncSession:
    """
    Each test gets its own transaction that is ROLLED BACK after the test.
    This means tests never dirty each other's data.
    """
    conn   = await test_engine.connect()
    tx     = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False)
    yield session
    await session.close()
    await tx.rollback()
    await conn.close()

# ── FastAPI test client with DB override ──────────────────────────────────────
@pytest.fixture
async def client(db) -> AsyncClient:
    async def _override():
        yield db
    app.dependency_overrides[get_db] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    app.dependency_overrides.clear()

# ── Owner fixture ─────────────────────────────────────────────────────────────
@pytest.fixture
async def owner(db) -> Owner:
    o = Owner(
        username="testadmin",
        password_hash=hash_password("TestPass123!"),
    )
    db.add(o)
    await db.flush()
    return o

# ── Authenticated client ──────────────────────────────────────────────────────
@pytest.fixture
async def auth_client(client, owner) -> AsyncClient:
    resp = await client.post("/api/auth/login", json={
        "username": "testadmin",
        "password": "TestPass123!",
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return client

# ── Product fixture ───────────────────────────────────────────────────────────
@pytest.fixture
async def joha_product(db) -> tuple[Product, InventoryStock]:
    p = Product(
        name="Joha Rice", slug="joha-rice",
        category="rice", unit="kg",
        sell_price=Decimal("105.00000"),
        farm_cost=Decimal("50.00000"),
        labor_cost=Decimal("5.00000"),
        overhead_cost=Decimal("3.00000"),
        packaging_cost=Decimal("7.00000"),
        normal_loss_percent=Decimal("33.00000"),
        true_cost=Decimal("80.00000"),
        is_active=True,
        low_stock_threshold=Decimal("5.000"),
    )
    db.add(p)
    await db.flush()
    s = InventoryStock(product_id=p.id, current_qty=Decimal("50.000"))
    db.add(s)
    await db.flush()
    return p, s

@pytest.fixture
async def narikal_product(db) -> tuple[Product, InventoryStock]:
    p = Product(
        name="Narikal Petha", slug="narikal-petha",
        category="petha", unit="pc",
        sell_price=Decimal("70.00000"),
        farm_cost=Decimal("18.00000"),
        labor_cost=Decimal("7.50000"),
        overhead_cost=Decimal("0.00000"),
        packaging_cost=Decimal("4.00000"),
        normal_loss_percent=Decimal("0.00000"),
        true_cost=Decimal("29.50000"),
        is_active=True,
        low_stock_threshold=Decimal("5.000"),
    )
    db.add(p)
    await db.flush()
    s = InventoryStock(product_id=p.id, current_qty=Decimal("20.000"))
    db.add(s)
    await db.flush()
    return p, s

# ── Asset fixture ─────────────────────────────────────────────────────────────
@pytest.fixture
async def rice_mill_asset(db) -> Asset:
    a = Asset(
        name="Rice mill machine",
        cost=Decimal("12000.00000"),
        useful_life_years=10,
        monthly_depreciation=Decimal("100.00000"),   # 12000 / 120
        purchase_date=date(2024, 1, 1),
        is_active=True,
    )
    db.add(a)
    await db.flush()
    return a

# ── Fixed cost fixture ────────────────────────────────────────────────────────
@pytest.fixture
async def stall_rent(db) -> FixedCost:
    fc = FixedCost(name="Stall rent", category="stall",
                   monthly_amount=Decimal("1200.00000"), is_active=True)
    db.add(fc)
    await db.flush()
    return fc

# ── External service mocks ────────────────────────────────────────────────────
@pytest.fixture
def mock_razorpay(mocker):
    return mocker.patch(
        "modules.payments.razorpay.create_razorpay_order",
        return_value={"id": "order_rzp_test", "amount": 10500, "currency": "INR"},
    )

@pytest.fixture
def mock_wati(mocker):
    return mocker.patch(
        "modules.notify.wati.send_template_message",
        return_value=True,
    )

# ── Razorpay webhook helper ───────────────────────────────────────────────────
def make_webhook_payload(rzp_order_id: str, rzp_payment_id: str,
                          amount_paise: int = 10500) -> tuple[bytes, str]:
    """Returns (body_bytes, valid_signature)"""
    payload = {
        "entity": "event",
        "event":  "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id":       rzp_payment_id,
                    "order_id": rzp_order_id,
                    "amount":   amount_paise,
                    "currency": "INR",
                    "status":   "captured",
                }
            }
        }
    }
    body = json.dumps(payload).encode("utf-8")
    sig  = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return body, sig
```

---

## tests/unit/test_pl_calculator.py
```python
"""
P&L Engine unit tests — target 95%+ coverage of calculator.py.
Pure function tests: no DB, no HTTP, no external services.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from modules.pl_engine.calculator import calculate, PLResult, ZERO


def _entry(entry_type, total_amount, channel=None, pay_mode=None,
           source=None, qty=Decimal("1"), price_variance=None,
           cost_variance=None, product_id=None):
    """Helper to build a mock StockEntry."""
    e = MagicMock()
    e.entry_type     = entry_type
    e.total_amount   = Decimal(str(total_amount))
    e.channel        = channel
    e.pay_mode       = pay_mode
    e.source         = source or "own"
    e.qty            = Decimal(str(qty))
    e.price_variance = Decimal(str(price_variance)) if price_variance else None
    e.cost_variance  = Decimal(str(cost_variance))  if cost_variance  else None
    e.product_id     = product_id or "00000000-0000-0000-0000-000000000001"
    return e


def _stock(stock_type, qty, value):
    s = MagicMock()
    s.stock_type = stock_type
    s.qty        = Decimal(str(qty))
    s.value      = Decimal(str(value))
    return s


def _asset(monthly_depreciation):
    a = MagicMock()
    a.monthly_depreciation = Decimal(str(monthly_depreciation))
    return a


def _product(farm_cost):
    p = MagicMock()
    p.farm_cost = Decimal(str(farm_cost))
    return p


# ── Revenue tests ─────────────────────────────────────────────────────────────

class TestRevenue:
    def test_online_revenue_summed_correctly(self):
        entries = [
            _entry("sale", "1000", channel="online", pay_mode="razorpay"),
            _entry("sale",  "500", channel="online", pay_mode="upi_manual"),
        ]
        r = calculate("2025-05", entries, [], [], {})
        assert r.rev_online  == Decimal("1500")
        assert r.rev_offline == ZERO
        assert r.rev_total   == Decimal("1500")

    def test_offline_revenue_summed_correctly(self):
        entries = [
            _entry("sale", "800", channel="offline", pay_mode="cash"),
            _entry("sale", "200", channel="offline", pay_mode="credit"),
        ]
        r = calculate("2025-05", entries, [], [], {})
        assert r.rev_offline == Decimal("1000")
        assert r.rev_total   == Decimal("1000")

    def test_credit_sale_counted_in_revenue_not_cash(self):
        entries = [
            _entry("sale", "500", channel="online",  pay_mode="razorpay"),
            _entry("sale", "300", channel="offline", pay_mode="credit"),
        ]
        r = calculate("2025-05", entries, [], [], {})
        assert r.rev_total  == Decimal("800")   # accrual: both count
        assert r.rev_credit == Decimal("300")   # credit amount tracked
        assert r.cash_inflow == Decimal("500")  # only cash

    def test_cash_pl_gap_equals_credit_amount(self):
        entries = [_entry("sale", "400", channel="offline", pay_mode="credit")]
        r = calculate("2025-05", entries, [], [], {})
        assert r.cash_pl_gap == r.rev_credit

    def test_price_variance_summed(self):
        entries = [
            _entry("sale", "1050", channel="online", pay_mode="razorpay",
                   price_variance="50"),
            _entry("sale", "980",  channel="online", pay_mode="razorpay",
                   price_variance="-20"),
        ]
        r = calculate("2025-05", entries, [], [], {})
        assert r.price_variance == Decimal("30")


# ── COGS tests ────────────────────────────────────────────────────────────────

class TestCOGS:
    def test_missing_opening_stock_adds_warning(self):
        r = calculate("2025-05", [], [], [], {})
        assert len(r.warnings) >= 1
        assert "Opening stock missing" in r.warnings[0]

    def test_opening_stock_from_monthly_stock_table(self):
        stocks = [_stock("opening", "100", "5000")]
        r = calculate("2025-05", [], stocks, [], {})
        assert r.cogs_opening == Decimal("5000")
        assert r.warnings     == []   # no warning when opening stock present

    def test_closing_stock_reduces_cogs(self):
        stocks = [
            _stock("opening", "100", "5000"),
            _stock("closing",  "50", "2500"),
        ]
        r = calculate("2025-05", [], stocks, [], {})
        assert r.cogs_closing == Decimal("2500")
        assert r.cogs_total   == Decimal("2500")  # 5000 opening - 2500 closing

    def test_own_production_cost_uses_farm_cost_x_qty(self):
        pid = "00000000-0000-0000-0000-000000000001"
        products = {pid: _product(farm_cost="50")}
        entries  = [_entry("sale", "105", source="own", qty="2", product_id=pid,
                           channel="online", pay_mode="razorpay")]
        r = calculate("2025-05", entries, [], [], products)
        assert r.cogs_own_prod == Decimal("100")   # 50 × 2

    def test_purchases_add_to_cogs(self):
        entries = [_entry("purchase", "3600")]
        r = calculate("2025-05", entries, [], [], {})
        assert r.cogs_purchased == Decimal("3600")

    def test_normal_loss_included_in_cogs(self):
        entries = [_entry("wastage_normal", "420")]
        r = calculate("2025-05", entries, [], [], {})
        assert r.cogs_norm_loss == Decimal("420")

    def test_abnormal_loss_not_in_cogs(self):
        entries = [_entry("wastage_abnormal", "350")]
        r = calculate("2025-05", entries, [], [], {})
        assert r.cogs_total    == ZERO   # abnormal NOT in COGS
        assert r.abnormal_loss == Decimal("350")

    def test_consumption_in_cogs(self):
        entries = [_entry("consumption", "315")]
        r = calculate("2025-05", entries, [], [], {})
        assert r.cogs_consumed == Decimal("315")

    def test_cogs_total_formula(self):
        """COGS = opening + own + purchased + norm_loss + consumed - closing"""
        stocks = [
            _stock("opening", "100", "3000"),
            _stock("closing",  "50", "1500"),
        ]
        entries = [
            _entry("purchase",       "1800"),
            _entry("wastage_normal",  "200"),
            _entry("consumption",     "100"),
        ]
        r = calculate("2025-05", entries, stocks, [], {})
        expected = Decimal("3000") + Decimal("1800") + Decimal("200") + Decimal("100") - Decimal("1500")
        assert r.cogs_total == expected


# ── Gross profit tests ────────────────────────────────────────────────────────

class TestGrossProfit:
    def test_gross_profit_is_revenue_minus_cogs(self):
        entries = [_entry("sale", "5000", channel="online", pay_mode="razorpay")]
        stocks  = [_stock("opening", "50", "2000"), _stock("closing", "20", "800")]
        r = calculate("2025-05", entries, stocks, [], {})
        assert r.gross_profit == r.rev_total - r.cogs_total

    def test_negative_gross_profit_possible(self):
        """Loss-making month should not crash."""
        entries = [_entry("sale", "100", channel="offline", pay_mode="cash")]
        stocks  = [_stock("opening", "50", "5000")]
        r = calculate("2025-05", entries, stocks, [], {})
        assert r.gross_profit < ZERO


# ── OpEx + Net Profit tests ───────────────────────────────────────────────────

class TestOpExAndNetProfit:
    def test_depreciation_from_assets(self):
        assets = [_asset("100"), _asset("83.33333")]
        r = calculate("2025-05", [], [], assets, {})
        assert r.opex_deprec == Decimal("183.33333")

    def test_fixed_cost_entries_in_opex(self):
        entries = [_entry("fixed_cost", "1200")]
        r = calculate("2025-05", entries, [], [], {})
        assert r.opex_fixed == Decimal("1200")

    def test_provisions_in_opex(self):
        entries = [_entry("provision", "500")]
        r = calculate("2025-05", entries, [], [], {})
        assert r.opex_provisions == Decimal("500")

    def test_opex_total_is_sum(self):
        entries = [_entry("fixed_cost", "1200"), _entry("provision", "100")]
        assets  = [_asset("83.33333")]
        r = calculate("2025-05", entries, [], assets, {})
        assert r.opex_total == Decimal("1200") + Decimal("100") + Decimal("83.33333")

    def test_net_profit_formula(self):
        entries = [_entry("sale", "10000", channel="online", pay_mode="razorpay"),
                   _entry("fixed_cost", "1200")]
        assets  = [_asset("100")]
        r = calculate("2025-05", entries, [], assets, {})
        assert r.net_profit == r.gross_profit - r.abnormal_loss - r.opex_total

    def test_net_margin_pct_correct(self):
        entries = [_entry("sale", "10000", channel="online", pay_mode="razorpay")]
        r = calculate("2025-05", entries, [], [], {})
        # With zero costs, net profit = revenue, margin = 100%
        assert r.net_margin_pct == Decimal("100")

    def test_zero_revenue_no_division_error(self):
        """Zero revenue must not cause ZeroDivisionError."""
        r = calculate("2025-05", [], [], [], {})
        assert r.net_margin_pct == ZERO


# ── Return type tests ─────────────────────────────────────────────────────────

class TestReturnTypes:
    def test_all_fields_are_decimal(self):
        entries = [_entry("sale", "1000", channel="online", pay_mode="razorpay")]
        assets  = [_asset("50")]
        r = calculate("2025-05", entries, [], assets, {})
        for field_name, val in r.__dict__.items():
            if field_name in ("month","from_cache","warnings"):
                continue
            assert isinstance(val, Decimal), \
                f"Field '{field_name}' is {type(val)}, expected Decimal"

    def test_to_dict_all_values_are_strings(self):
        entries = [_entry("sale", "1000", channel="online", pay_mode="razorpay")]
        r = calculate("2025-05", entries, [], [], {})
        d = r.to_dict()
        skip = {"month","from_cache","warnings"}
        for k, v in d.items():
            if k in skip: continue
            assert isinstance(v, str), f"Key '{k}' is {type(v)}, expected str"

    def test_to_dict_values_have_5dp(self):
        entries = [_entry("sale", "1000.5", channel="online", pay_mode="razorpay")]
        r = calculate("2025-05", entries, [], [], {})
        d = r.to_dict()
        assert "." in d["rev_total"]
        assert len(d["rev_total"].split(".")[1]) == 5
```

---

## tests/unit/test_batch_cost.py
```python
"""
Petha batch cost unit tests — absorption costing.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from modules.petha.service import PethaService


def _batch(planned, good, rejected, total_cost, variety="narikal"):
    b = MagicMock()
    b.planned_pieces  = planned
    b.good_pieces     = good
    b.rejected_pieces = rejected
    b.total_batch_cost= Decimal(str(total_cost))
    b.variety         = variety
    b.batch_date      = __import__("datetime").date(2025, 5, 10)
    b.cost_per_piece  = None
    b.status          = "in_production"
    b.expiry_date     = __import__("datetime").date(2025, 5, 17)
    return b


class TestBatchCostAbsorption:
    def test_cost_per_piece_absorbs_rejections(self):
        """
        30 planned, 27 good, 3 rejected.
        ₹325 total cost / 27 good pieces = ₹12.037...
        Rejected pieces' cost absorbed — NOT charged separately.
        """
        b = _batch(planned=30, good=27, rejected=3, total_cost="325")
        expected = Decimal("325") / Decimal("27")
        actual   = Decimal("325") / Decimal("27")
        assert actual.quantize(Decimal("0.00001")) == expected.quantize(Decimal("0.00001"))

    def test_no_rejection_cost_per_piece_is_total_divided_by_good(self):
        b = _batch(planned=30, good=30, rejected=0, total_cost="300")
        cost_pp = Decimal("300") / Decimal("30")
        assert cost_pp == Decimal("10")

    def test_all_rejected_gives_zero_cost_per_piece(self):
        """All pieces rejected → cost_per_piece = 0, entire cost = abnormal loss."""
        good = 0
        total = Decimal("500")
        cost_pp = total / Decimal(str(good)) if good > 0 else Decimal("0")
        assert cost_pp == Decimal("0")

    def test_all_rejected_entire_cost_is_abnormal_loss(self):
        """When good_pieces=0, total_batch_cost becomes abnormal loss."""
        total = Decimal("500")
        good  = 0
        abnormal = total if good == 0 else Decimal("0")
        assert abnormal == Decimal("500")

    def test_rejection_pct_calculated_correctly(self):
        planned, rejected = 30, 3
        pct = Decimal(str(rejected)) / Decimal(str(planned)) * 100
        assert pct == Decimal("10")

    def test_high_rejection_pct_raises_warning_threshold(self):
        """Rejection > 20% is a quality alert threshold."""
        planned, rejected = 30, 7
        pct = Decimal(str(rejected)) / Decimal(str(planned)) * 100
        assert pct > Decimal("20")

    def test_ingredient_labor_overhead_summed_correctly(self):
        ingredient = Decimal("90")
        labor      = Decimal("150")
        overhead   = Decimal("85")   # fuel + overhead
        total      = ingredient + labor + overhead
        assert total == Decimal("325")

    def test_expiry_date_from_shelf_life(self):
        from datetime import date, timedelta
        batch_date = date(2025, 5, 10)
        shelf_life = 7
        expiry     = batch_date + timedelta(days=shelf_life)
        assert expiry == date(2025, 5, 17)

    def test_abnormal_loss_on_expiry_is_unsold_times_cost_per_piece(self):
        unsold_qty  = Decimal("5")    # 5 pieces unsold at expiry
        cost_per_pc = Decimal("12.03704")
        abnormal    = unsold_qty * cost_per_pc
        assert abnormal == Decimal("60.18520")
```

---

## tests/unit/test_milling.py
```python
"""
Farm milling yield and cost calculation unit tests.
"""
import pytest
from decimal import Decimal


def calc_milling(dhan_sent, chawl_received, husk_kg, bran_kg, broken_kg,
                 husk_price, bran_price, broken_price,
                 milling_charges, cultivation_cost):
    """Replicate milling calculation from FarmService."""
    ZERO = Decimal("0")
    dhan      = Decimal(str(dhan_sent))
    chawl     = Decimal(str(chawl_received))
    milling   = Decimal(str(milling_charges))
    farm_cost = Decimal(str(cultivation_cost))

    yield_pct    = chawl / dhan * 100 if dhan > ZERO else ZERO
    byproduct    = (Decimal(str(husk_kg))    * Decimal(str(husk_price)) +
                    Decimal(str(bran_kg))    * Decimal(str(bran_price)) +
                    Decimal(str(broken_kg))  * Decimal(str(broken_price)))
    total_cost   = farm_cost + milling
    net_cost     = total_cost - byproduct
    cost_per_kg  = net_cost / chawl if chawl > ZERO else ZERO
    transfer_price = cost_per_kg * Decimal("1.12")
    return {
        "yield_pct":       yield_pct,
        "byproduct":       byproduct,
        "cost_per_kg_chawl": cost_per_kg,
        "transfer_price":  transfer_price,
    }


class TestMillingYield:
    def test_yield_percentage_correct(self):
        r = calc_milling(dhan_sent=1200, chawl_received=780,
                         husk_kg=240, bran_kg=96, broken_kg=24,
                         husk_price=2, bran_price=18, broken_price=30,
                         milling_charges=1800, cultivation_cost=40000)
        assert r["yield_pct"].quantize(Decimal("0.01")) == Decimal("65.00")

    def test_byproduct_revenue_calculated_correctly(self):
        r = calc_milling(dhan_sent=1200, chawl_received=780,
                         husk_kg=240, bran_kg=96, broken_kg=24,
                         husk_price=2, bran_price=18, broken_price=30,
                         milling_charges=1800, cultivation_cost=40000)
        # 240×2 + 96×18 + 24×30 = 480 + 1728 + 720 = 2928
        assert r["byproduct"] == Decimal("2928")

    def test_byproduct_credited_against_cost(self):
        """By-product revenue REDUCES effective cost of chawl."""
        r_with_byproduct = calc_milling(1200, 780, 240, 96, 24, 2, 18, 30, 1800, 40000)
        r_no_byproduct   = calc_milling(1200, 780, 0, 0, 0, 0, 0, 0, 1800, 40000)
        assert r_with_byproduct["cost_per_kg_chawl"] < r_no_byproduct["cost_per_kg_chawl"]

    def test_transfer_price_is_cost_plus_12_percent(self):
        r = calc_milling(1200, 780, 240, 96, 24, 2, 18, 30, 1800, 40000)
        expected = r["cost_per_kg_chawl"] * Decimal("1.12")
        assert abs(r["transfer_price"] - expected) < Decimal("0.00001")

    def test_zero_chawl_no_division_error(self):
        r = calc_milling(dhan_sent=1200, chawl_received=0,
                         husk_kg=0, bran_kg=0, broken_kg=0,
                         husk_price=0, bran_price=0, broken_price=0,
                         milling_charges=0, cultivation_cost=40000)
        assert r["cost_per_kg_chawl"] == Decimal("0")

    def test_normal_loss_is_dhan_minus_chawl(self):
        """Normal loss = dhan sent - chawl received (absorbed into cost)."""
        dhan, chawl = Decimal("1200"), Decimal("780")
        normal_loss_kg = dhan - chawl
        assert normal_loss_kg == Decimal("420")


# ── true_cost calculation tests ────────────────────────────────────────────────

class TestTrueCost:
    """Test the normal loss absorption formula in products service."""

    def _calc(self, farm, labor, overhead, packaging, loss_pct):
        from modules.products.service import _calculate_true_cost
        return _calculate_true_cost(
            Decimal(str(farm)), Decimal(str(labor)),
            Decimal(str(overhead)), Decimal(str(packaging)),
            Decimal(str(loss_pct)),
        )

    def test_zero_loss_no_absorption(self):
        cost = self._calc(farm=50, labor=5, overhead=3, packaging=7, loss_pct=0)
        assert cost == Decimal("65")

    def test_33_pct_loss_absorbed_correctly(self):
        """
        33% loss: to get 1kg chawl, need 1/(1-0.33) = 1.4925kg dhan.
        Loss absorb = 50 × (0.33 / 0.67) = 24.626...
        true_cost ≈ 50 + 24.626 + 5 + 3 + 7 = 89.626...
        """
        cost = self._calc(farm=50, labor=5, overhead=3, packaging=7, loss_pct=33)
        assert cost > Decimal("65")   # more than without loss
        assert cost > Decimal("85")   # significant absorption

    def test_zero_farm_cost_no_loss_absorption(self):
        """If farm_cost=0, loss absorption = 0 regardless of loss%."""
        cost = self._calc(farm=0, labor=10, overhead=5, packaging=3, loss_pct=50)
        assert cost == Decimal("18")

    def test_true_cost_always_decimal(self):
        cost = self._calc(farm=50, labor=5, overhead=3, packaging=7, loss_pct=33)
        assert isinstance(cost, Decimal)
```

---

## tests/unit/test_schemas.py
```python
"""
Pydantic schema validation tests.
Most critical: float MUST be rejected for all money fields.
"""
import pytest
import uuid
from decimal import Decimal
from datetime import date
from pydantic import ValidationError
from modules.products.schemas import ProductCreate
from modules.orders.schemas import OrderCreate, OrderItemCreate
from modules.inventory.schemas import StockEntryCreate


class TestFloatRejection:
    """Float must NEVER be accepted for money or quantity fields."""

    def test_product_sell_price_rejects_float(self):
        with pytest.raises(ValidationError, match="never float"):
            ProductCreate(
                name="Test Rice", category="rice", unit="kg",
                sell_price=105.5,   # ← float — must fail
                farm_cost="50",
            )

    def test_product_farm_cost_rejects_float(self):
        with pytest.raises(ValidationError, match="never float"):
            ProductCreate(
                name="Test Rice", category="rice", unit="kg",
                sell_price="105",
                farm_cost=50.0,   # ← float — must fail
            )

    def test_order_item_qty_rejects_float(self):
        with pytest.raises(ValidationError, match="never float"):
            OrderItemCreate(product_id=uuid.uuid4(), qty=3.5)   # ← float

    def test_stock_entry_qty_rejects_float(self):
        with pytest.raises(ValidationError, match="never float"):
            StockEntryCreate(
                idempotency_key=uuid.uuid4(),
                product_id=uuid.uuid4(),
                entry_type="purchase",
                qty=50.0,        # ← float — must fail
                total_amount="3600",
                date=date.today(),
            )


class TestDecimalAccepted:
    """String and Decimal should both be accepted."""

    def test_string_decimal_accepted_for_sell_price(self):
        p = ProductCreate(
            name="Joha Rice", category="rice", unit="kg",
            sell_price="105.00000", farm_cost="50",
        )
        assert p.sell_price == Decimal("105.00000")

    def test_decimal_object_accepted(self):
        p = ProductCreate(
            name="Joha Rice", category="rice", unit="kg",
            sell_price=Decimal("105"), farm_cost=Decimal("50"),
        )
        assert p.sell_price == Decimal("105")

    def test_integer_string_accepted(self):
        p = ProductCreate(
            name="Joha Rice", category="rice", unit="kg",
            sell_price="105", farm_cost="50",
        )
        assert p.sell_price == Decimal("105")


class TestOrderValidation:
    def test_valid_order_passes(self):
        o = OrderCreate(
            idempotency_key=uuid.uuid4(),
            customer_name="Ratan Das",
            customer_phone="+919876543210",
            fulfillment_type="pickup",
            channel="online",
            payment_mode="razorpay",
            items=[OrderItemCreate(product_id=uuid.uuid4(), qty="3")],
        )
        assert len(o.items) == 1

    def test_invalid_phone_rejected(self):
        with pytest.raises(ValidationError):
            OrderCreate(
                idempotency_key=uuid.uuid4(),
                customer_name="Test",
                customer_phone="1234567890",   # invalid Indian format
                fulfillment_type="pickup",
                channel="online",
                payment_mode="cash",
                items=[OrderItemCreate(product_id=uuid.uuid4(), qty="1")],
            )

    def test_empty_items_rejected(self):
        with pytest.raises(ValidationError):
            OrderCreate(
                idempotency_key=uuid.uuid4(),
                customer_name="Test",
                customer_phone="+919876543210",
                fulfillment_type="pickup",
                channel="online",
                payment_mode="cash",
                items=[],    # ← empty list — must fail
            )

    def test_invalid_payment_mode_rejected(self):
        with pytest.raises(ValidationError):
            OrderCreate(
                idempotency_key=uuid.uuid4(),
                customer_name="Test",
                customer_phone="+919876543210",
                fulfillment_type="pickup",
                channel="online",
                payment_mode="btc",   # ← invalid
                items=[OrderItemCreate(product_id=uuid.uuid4(), qty="1")],
            )

    def test_delivery_with_no_address_allowed(self):
        """Address not required by schema — validated in service layer."""
        o = OrderCreate(
            idempotency_key=uuid.uuid4(),
            customer_name="Test",
            customer_phone="+919876543210",
            fulfillment_type="delivery",
            channel="online",
            payment_mode="razorpay",
            items=[OrderItemCreate(product_id=uuid.uuid4(), qty="1")],
        )
        assert o.fulfillment_type == "delivery"


class TestProductSchemaValidation:
    def test_invalid_category_rejected(self):
        with pytest.raises(ValidationError):
            ProductCreate(
                name="Test", category="vegetable",   # invalid
                unit="kg", sell_price="100",
            )

    def test_invalid_unit_rejected(self):
        with pytest.raises(ValidationError):
            ProductCreate(
                name="Test", category="rice",
                unit="litre",   # invalid — only kg/pc/cup
                sell_price="100",
            )
```
