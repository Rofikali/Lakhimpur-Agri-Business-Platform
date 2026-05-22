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
    "DATABASE_URL", "postgresql+asyncpg://postgres:testpassword@localhost:5432/lakhimpur_test"
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
        await conn.run_sync(Base.metadata.drop_all)  # clean slate
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
    conn = await test_engine.connect()
    tx = await conn.begin()
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
    resp = await client.post(
        "/api/auth/login",
        json={
            "username": "testadmin",
            "password": "TestPass123!",
        },
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return client


# ── Product fixture ───────────────────────────────────────────────────────────
@pytest.fixture
async def joha_product(db) -> tuple[Product, InventoryStock]:
    p = Product(
        name="Joha Rice",
        slug="joha-rice",
        category="rice",
        unit="kg",
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
        name="Narikal Petha",
        slug="narikal-petha",
        category="petha",
        unit="pc",
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
        monthly_depreciation=Decimal("100.00000"),  # 12000 / 120
        purchase_date=date(2024, 1, 1),
        is_active=True,
    )
    db.add(a)
    await db.flush()
    return a


# ── Fixed cost fixture ────────────────────────────────────────────────────────
@pytest.fixture
async def stall_rent(db) -> FixedCost:
    fc = FixedCost(
        name="Stall rent", category="stall", monthly_amount=Decimal("1200.00000"), is_active=True
    )
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
def make_webhook_payload(
    rzp_order_id: str, rzp_payment_id: str, amount_paise: int = 10500
) -> tuple[bytes, str]:
    """Returns (body_bytes, valid_signature)"""
    payload = {
        "entity": "event",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": rzp_payment_id,
                    "order_id": rzp_order_id,
                    "amount": amount_paise,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return body, sig
