import pytest
import uuid
from decimal import Decimal
from datetime import date


class TestStockEntry:
    async def test_purchase_increases_stock(self, auth_client, joha_product):
        product, stock = joha_product
        initial_qty = Decimal(str(stock.current_qty))

        resp = await auth_client.post(
            "/api/inventory/entries",
            json={
                "idempotency_key": str(uuid.uuid4()),
                "product_id": str(product.id),
                "entry_type": "purchase",
                "qty": "20",
                "unit_cost": "70",
                "total_amount": "1400",
                "source": "external",
                "date": date.today().isoformat(),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        new_qty = Decimal(data["new_stock_qty"])
        assert new_qty == initial_qty + Decimal("20")

    async def test_purchase_calculates_cost_variance(self, auth_client, joha_product):
        """
        Joha Rice true_cost = 80.00000
        Buying at 70/kg → cost variance = (70 - 80) × 20 = -200 (favourable)
        """
        product, _ = joha_product
        resp = await auth_client.post(
            "/api/inventory/entries",
            json={
                "idempotency_key": str(uuid.uuid4()),
                "product_id": str(product.id),
                "entry_type": "purchase",
                "qty": "20",
                "unit_cost": "70",
                "total_amount": "1400",
                "source": "external",
                "date": date.today().isoformat(),
            },
        )
        assert resp.status_code == 201
        variance = Decimal(resp.json()["cost_variance"])
        assert variance == Decimal("-200")  # favourable — bought below standard

    async def test_idempotency_key_prevents_duplicate_entry(self, auth_client, joha_product):
        product, stock = joha_product
        idem_key = str(uuid.uuid4())
        payload = {
            "idempotency_key": idem_key,
            "product_id": str(product.id),
            "entry_type": "purchase",
            "qty": "10",
            "unit_cost": "80",
            "total_amount": "800",
            "source": "external",
            "date": date.today().isoformat(),
        }
        # First request
        r1 = await auth_client.post("/api/inventory/entries", json=payload)
        assert r1.status_code == 201
        qty_after_first = Decimal(r1.json()["new_stock_qty"])

        # Duplicate request with same idempotency_key
        r2 = await auth_client.post("/api/inventory/entries", json=payload)
        assert r2.status_code == 201
        qty_after_second = Decimal(r2.json()["new_stock_qty"])

        # Stock must NOT be increased twice
        assert qty_after_first == qty_after_second

    async def test_float_qty_rejected(self, auth_client, joha_product):
        product, _ = joha_product
        resp = await auth_client.post(
            "/api/inventory/entries",
            json={
                "idempotency_key": str(uuid.uuid4()),
                "product_id": str(product.id),
                "entry_type": "purchase",
                "qty": 50.5,  # ← float — must be rejected
                "total_amount": "3000",
                "date": date.today().isoformat(),
            },
        )
        assert resp.status_code == 422


class TestMonthlyStock:
    async def test_set_opening_stock(self, auth_client, joha_product):
        product, _ = joha_product
        resp = await auth_client.post(
            "/api/inventory/monthly-stock",
            json={
                "product_id": str(product.id),
                "month": "2025-05",
                "stock_type": "opening",
                "qty": "100",
                "value": "8000",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["stock_type"] == "opening"
        assert data["qty"] == "100.00000"
        assert data["value"] == "8000.00000"

    async def test_get_monthly_stock(self, auth_client, joha_product):
        product, _ = joha_product
        await auth_client.post(
            "/api/inventory/monthly-stock",
            json={
                "product_id": str(product.id),
                "month": "2025-04",
                "stock_type": "opening",
                "qty": "80",
                "value": "6400",
            },
        )
        resp = await auth_client.get("/api/inventory/monthly-stock?month=2025-04")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
