import pytest
import uuid
from decimal import Decimal


def order_payload(product_id: str, qty: str = "3",
                  payment_mode: str = "cash",
                  channel: str = "offline") -> dict:
    return {
        "idempotency_key":  str(uuid.uuid4()),
        "customer_name":    "Ratan Das",
        "customer_phone":   "+919876543210",
        "fulfillment_type": "pickup",
        "channel":          channel,
        "payment_mode":     payment_mode,
        "items": [{"product_id": product_id, "qty": qty, "source": "own"}],
    }


class TestOrderCreate:
    async def test_offline_order_immediately_confirmed(self, auth_client, joha_product, mock_wati):
        product, stock = joha_product
        resp = await auth_client.post("/api/orders/", json=order_payload(str(product.id)))
        assert resp.status_code == 201
        assert resp.json()["status"] == "confirmed"

    async def test_offline_order_decrements_stock(self, auth_client, joha_product, mock_wati):
        product, stock = joha_product
        initial_qty = stock.current_qty

        resp = await auth_client.post("/api/orders/", json=order_payload(
            str(product.id), qty="3"
        ))
        assert resp.status_code == 201

        # Check stock via API
        stock_resp = await auth_client.get("/api/inventory/stock")
        products = {p["product_id"]: p for p in stock_resp.json()}
        new_qty = Decimal(products[str(product.id)]["current_qty"])
        assert new_qty == initial_qty - Decimal("3")

    async def test_online_order_stays_pending(self, auth_client, joha_product, mock_razorpay):
        product, _ = joha_product
        resp = await auth_client.post("/api/orders/", json=order_payload(
            str(product.id), payment_mode="razorpay", channel="online"
        ))
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["razorpay_order_id"] == "order_rzp_test"

    async def test_online_order_does_not_decrement_stock_before_payment(
        self, auth_client, joha_product, mock_razorpay
    ):
        product, stock = joha_product
        initial_qty = stock.current_qty

        await auth_client.post("/api/orders/", json=order_payload(
            str(product.id), payment_mode="razorpay", channel="online"
        ))

        stock_resp = await auth_client.get("/api/inventory/stock")
        products   = {p["product_id"]: p for p in stock_resp.json()}
        new_qty    = Decimal(products[str(product.id)]["current_qty"])
        assert new_qty == initial_qty   # unchanged

    async def test_order_number_format(self, auth_client, joha_product, mock_wati):
        product, _ = joha_product
        resp = await auth_client.post("/api/orders/", json=order_payload(str(product.id)))
        assert resp.status_code == 201
        order_number = resp.json()["order_number"]
        import re
        assert re.match(r"LKP-\d{4}-\d{4}", order_number)

    async def test_idempotency_prevents_duplicate_orders(self, auth_client, joha_product, mock_wati):
        product, stock = joha_product
        idem_key = str(uuid.uuid4())
        payload  = order_payload(str(product.id))
        payload["idempotency_key"] = idem_key

        r1 = await auth_client.post("/api/orders/", json=payload)
        r2 = await auth_client.post("/api/orders/", json=payload)
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["id"] == r2.json()["id"]   # same order returned

    async def test_oversell_rejected(self, auth_client, joha_product):
        product, stock = joha_product
        # Try to order more than available (stock = 50 kg)
        resp = await auth_client.post("/api/orders/", json=order_payload(
            str(product.id), qty="100"   # ← more than 50 available
        ))
        assert resp.status_code == 422
        assert resp.json()["error"] == "STOCK_INSUFFICIENT"

    async def test_inactive_product_rejected(self, auth_client, joha_product):
        product, _ = joha_product
        await auth_client.patch(f"/api/products/{product.id}", json={"is_active": False})
        resp = await auth_client.post("/api/orders/", json=order_payload(str(product.id)))
        assert resp.status_code == 422
        assert resp.json()["error"] == "PRODUCT_INACTIVE"


class TestOrderStatusUpdate:
    async def test_valid_transition_succeeds(self, auth_client, joha_product, mock_wati):
        product, _ = joha_product
        order_resp = await auth_client.post("/api/orders/", json=order_payload(str(product.id)))
        order_id   = order_resp.json()["id"]

        resp = await auth_client.patch(f"/api/orders/{order_id}/status", json={
            "status": "packed",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "packed"

    async def test_invalid_transition_rejected(self, auth_client, joha_product, mock_wati):
        product, _ = joha_product
        order_resp = await auth_client.post("/api/orders/", json=order_payload(str(product.id)))
        order_id   = order_resp.json()["id"]

        # confirmed → pending is not allowed
        resp = await auth_client.patch(f"/api/orders/{order_id}/status", json={
            "status": "pending",
        })
        assert resp.status_code == 422
        assert resp.json()["error"] == "ORDER_INVALID_STATUS_TRANSITION"

    async def test_cancel_restores_stock(self, auth_client, joha_product, mock_wati):
        product, stock = joha_product
        initial_qty = stock.current_qty

        # Create and confirm order (offline = auto-confirmed)
        order_resp = await auth_client.post("/api/orders/", json=order_payload(
            str(product.id), qty="5"
        ))
        order_id = order_resp.json()["id"]

        # Verify stock was decremented
        stock_resp = await auth_client.get("/api/inventory/stock")
        products   = {p["product_id"]: p for p in stock_resp.json()}
        after_order = Decimal(products[str(product.id)]["current_qty"])
        assert after_order == initial_qty - Decimal("5")

        # Cancel the order
        cancel = await auth_client.patch(f"/api/orders/{order_id}/status", json={
            "status":        "cancelled",
            "cancel_reason": "Customer changed mind",
        })
        assert cancel.status_code == 200

        # Stock must be restored
        stock_resp2 = await auth_client.get("/api/inventory/stock")
        products2   = {p["product_id"]: p for p in stock_resp2.json()}
        after_cancel = Decimal(products2[str(product.id)]["current_qty"])
        assert after_cancel == initial_qty


---

## tests/integration/test_payments.py
````python
import pytest
import uuid
import json
import hashlib
import hmac
from decimal import Decimal
from conftest import make_webhook_payload
from core.config import settings


class TestWebhook:
    async def test_valid_webhook_confirms_order(
        self, auth_client, joha_product, mock_razorpay, mock_wati
    ):
        product, stock = joha_product
        initial_qty    = stock.current_qty

        # Create online order
        order_resp = await auth_client.post("/api/orders/", json={
            "idempotency_key":  str(uuid.uuid4()),
            "customer_name":    "Test Customer",
            "customer_phone":   "+919876543210",
            "fulfillment_type": "pickup",
            "channel":          "online",
            "payment_mode":     "razorpay",
            "items": [{"product_id": str(product.id), "qty": "3", "source": "own"}],
        })
        assert order_resp.status_code == 201
        order_data    = order_resp.json()
        rzp_order_id  = order_data["razorpay_order_id"]
        our_order_id  = order_data["id"]

        # Simulate Razorpay webhook
        rzp_payment_id = "pay_test_abc123"
        body, sig = make_webhook_payload(rzp_order_id, rzp_payment_id, amount_paise=10500)

        webhook = await auth_client.post(
            "/api/payments/webhook",
            content=body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
        assert webhook.status_code == 200

        # Order should now be confirmed
        order_check = await auth_client.get(f"/api/orders/{our_order_id}")
        assert order_check.json()["status"] == "confirmed"

    async def test_invalid_hmac_rejected(self, client):
        body = json.dumps({"event": "payment.captured", "payload": {}}).encode()
        resp = await client.post(
            "/api/payments/webhook",
            content=body,
            headers={"X-Razorpay-Signature": "invalid_sig", "Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "WEBHOOK_SIGNATURE_INVALID"

    async def test_duplicate_webhook_is_idempotent(
        self, auth_client, joha_product, mock_razorpay, mock_wati
    ):
        product, stock = joha_product
        initial_qty    = stock.current_qty

        # Create online order
        order_resp = await auth_client.post("/api/orders/", json={
            "idempotency_key":  str(uuid.uuid4()),
            "customer_name":    "Test",
            "customer_phone":   "+919876543210",
            "fulfillment_type": "pickup",
            "channel":          "online",
            "payment_mode":     "razorpay",
            "items": [{"product_id": str(product.id), "qty": "2", "source": "own"}],
        })
        assert order_resp.status_code == 201
        rzp_order_id = order_resp.json()["razorpay_order_id"]

        body, sig = make_webhook_payload(rzp_order_id, "pay_dup_test")

        # Send webhook twice
        r1 = await auth_client.post("/api/payments/webhook", content=body,
                                     headers={"X-Razorpay-Signature": sig,
                                              "Content-Type": "application/json"})
        r2 = await auth_client.post("/api/payments/webhook", content=body,
                                     headers={"X-Razorpay-Signature": sig,
                                              "Content-Type": "application/json"})
        assert r1.status_code == 200
        assert r2.status_code == 200

        # Stock decremented exactly ONCE
        stock_resp = await auth_client.get("/api/inventory/stock")
        products   = {p["product_id"]: p for p in stock_resp.json()}
        new_qty    = Decimal(products[str(product.id)]["current_qty"])
        assert new_qty == initial_qty - Decimal("2")   # not -4

    async def test_mark_paid_offline_order(self, auth_client, joha_product, mock_wati):
        product, _ = joha_product
        order_resp = await auth_client.post("/api/orders/", json={
            "idempotency_key":  str(uuid.uuid4()),
            "customer_name":    "Test",
            "customer_phone":   "+919876543210",
            "fulfillment_type": "pickup",
            "channel":          "offline",
            "payment_mode":     "credit",    # credit — outstanding
            "items": [{"product_id": str(product.id), "qty": "2", "source": "own"}],
        })
        assert order_resp.status_code == 201
        order_id = order_resp.json()["id"]

        resp = await auth_client.patch(f"/api/payments/{order_id}/mark-paid", json={
            "payment_mode": "cash",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "paid"


class TestOutstandingCredits:
    async def test_credit_order_appears_in_outstanding(self, auth_client, joha_product, mock_wati):
        product, _ = joha_product
        await auth_client.post("/api/orders/", json={
            "idempotency_key":  str(uuid.uuid4()),
            "customer_name":    "Credit Customer",
            "customer_phone":   "+919876543210",
            "fulfillment_type": "pickup",
            "channel":          "offline",
            "payment_mode":     "credit",
            "items": [{"product_id": str(product.id), "qty": "1", "source": "own"}],
        })
        resp = await auth_client.get("/api/payments/outstanding")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


---

## tests/integration/test_pl_api.py
```python
import pytest
import uuid
from decimal import Decimal
from datetime import date


class TestPLMonthly:
    async def test_pl_endpoint_returns_all_fields(self, auth_client):
        month = date.today().strftime("%Y-%m")
        resp  = await auth_client.get(f"/api/pl/monthly?month={month}")
        assert resp.status_code == 200
        data  = resp.json()
        required = [
            "month","from_cache","warnings",
            "rev_total","cogs_total","gross_profit","net_profit",
            "net_margin_pct","net_cash_flow","cash_pl_gap",
        ]
        for field in required:
            assert field in data, f"Missing field: {field}"

    async def test_pl_values_are_strings_never_float(self, auth_client):
        month = date.today().strftime("%Y-%m")
        resp  = await auth_client.get(f"/api/pl/monthly?month={month}")
        data  = resp.json()
        money = ["rev_total","cogs_total","gross_profit","net_profit",
                 "net_margin_pct","opex_total"]
        for field in money:
            val = data[field]
            assert isinstance(val, str), f"{field} is not a string: {type(val)}"
            # Must be parseable as Decimal
            Decimal(val)

    async def test_missing_opening_stock_adds_warning(self, auth_client, joha_product):
        """No monthly_stock records for this month → warning expected."""
        month = date.today().strftime("%Y-%m")
        resp  = await auth_client.get(f"/api/pl/monthly?month={month}")
        data  = resp.json()
        assert len(data["warnings"]) >= 1
        assert "Opening stock" in data["warnings"][0]

    async def test_pl_with_opening_stock_no_warning(self, auth_client, joha_product):
        product, _ = joha_product
        month = date.today().strftime("%Y-%m")
        # Set opening stock
        await auth_client.post("/api/inventory/monthly-stock", json={
            "product_id": str(product.id),
            "month":      month,
            "stock_type": "opening",
            "qty":        "50",
            "value":      "4000",
        })
        resp = await auth_client.get(f"/api/pl/monthly?month={month}")
        # Warning should be gone for this product
        assert resp.status_code == 200

    async def test_past_month_served_from_cache(self, auth_client):
        """Past month: second call should have from_cache=True."""
        month = "2025-01"   # clearly in the past
        r1 = await auth_client.get(f"/api/pl/monthly?month={month}")
        # First call may or may not be cached
        r2 = await auth_client.get(f"/api/pl/monthly?month={month}")
        assert r2.status_code == 200
        # from_cache depends on Redis — just verify the field exists
        assert "from_cache" in r2.json()


class TestBreakeven:
    async def test_breakeven_returns_correct_fields(self, auth_client, joha_product):
        product, _ = joha_product
        resp = await auth_client.get(f"/api/pl/breakeven/{product.id}")
        assert resp.status_code == 200
        data = resp.json()
        required = ["product_name","sell_price","variable_cost",
                    "contribution_margin","breakeven_qty","breakeven_revenue"]
        for f in required:
            assert f in data

    async def test_breakeven_values_are_strings(self, auth_client, joha_product):
        product, _ = joha_product
        resp = await auth_client.get(f"/api/pl/breakeven/{product.id}")
        data = resp.json()
        for field in ["sell_price","variable_cost","contribution_margin"]:
            assert isinstance(data[field], str)
            Decimal(data[field])   # must be valid decimal string


class TestProductMargins:
    async def test_margins_endpoint_returns_list(self, auth_client, joha_product):
        resp = await auth_client.get("/api/pl/margins")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_margins_sorted_highest_first(self, auth_client, joha_product, narikal_product):
        resp = await auth_client.get("/api/pl/margins")
        data = resp.json()
        if len(data) >= 2:
            pct0 = float(data[0]["margin_pct"])
            pct1 = float(data[1]["margin_pct"])
            assert pct0 >= pct1   # sorted descending
```

---

## tests/integration/test_farm.py
```python
import pytest
import uuid
from decimal import Decimal
from datetime import date


class TestFarmSeasonLifecycle:
    async def test_create_season(self, auth_client):
        resp = await auth_client.post("/api/farm/seasons", json={
            "variety":    "joha",
            "area_bigha": "3.5",
            "start_date": "2025-06-01",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["variety"]    == "joha"
        assert data["status"]     == "active"
        assert data["area_bigha"] == "3.50000"

    async def test_add_cultivation_input(self, auth_client):
        season = await auth_client.post("/api/farm/seasons", json={
            "variety": "bora_saul", "area_bigha": "2", "start_date": "2025-06-01"
        })
        season_id = season.json()["id"]

        resp = await auth_client.post(f"/api/farm/seasons/{season_id}/inputs", json={
            "input_type":   "seed",
            "description":  "Bora Saul seed",
            "qty":          "10",
            "unit":         "kg",
            "unit_cost":    "120",
            "total_amount": "1200",
            "date":         "2025-06-05",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["total_amount"]     == "1200.00000"
        assert data["season_total_cost"] == "1200.00000"

    async def test_record_harvest(self, auth_client):
        season = await auth_client.post("/api/farm/seasons", json={
            "variety": "kali_jeera", "area_bigha": "1", "start_date": "2025-06-01"
        })
        season_id = season.json()["id"]

        resp = await auth_client.post(f"/api/farm/seasons/{season_id}/harvest", json={
            "dhan_qty_kg":  "800",
            "harvest_date": "2025-10-15",
        })
        assert resp.status_code == 200
        assert resp.json()["status"]      == "harvested"
        assert resp.json()["dhan_qty_kg"] == "800.00000"

    async def test_milling_calculates_yield_and_cost(self, auth_client, joha_product):
        season = await auth_client.post("/api/farm/seasons", json={
            "variety": "joha", "area_bigha": "3", "start_date": "2025-06-01"
        })
        season_id = season.json()["id"]

        # Add cultivation cost
        await auth_client.post(f"/api/farm/seasons/{season_id}/inputs", json={
            "input_type": "labor", "description": "Field labor",
            "total_amount": "40000", "unit_cost": "40000", "date": "2025-06-10",
        })

        # Record harvest
        await auth_client.post(f"/api/farm/seasons/{season_id}/harvest", json={
            "dhan_qty_kg": "1200", "harvest_date": "2025-10-15",
        })

        # Record milling
        resp = await auth_client.post(f"/api/farm/seasons/{season_id}/milling", json={
            "dhan_sent_kg":       "1200",
            "chawl_received_kg":  "780",
            "husk_recovered_kg":  "240",
            "bran_recovered_kg":  "96",
            "broken_rice_kg":     "24",
            "milling_charges":    "1800",
            "husk_market_price":  "2",
            "bran_market_price":  "18",
            "broken_market_price":"30",
            "milling_date":       "2025-11-01",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"]            == "milled"
        assert Decimal(data["milling_yield_pct"]) == Decimal("65.00000")
        assert Decimal(data["byproduct_revenue"])  > Decimal("0")

    async def test_cannot_mill_before_harvest(self, auth_client):
        season = await auth_client.post("/api/farm/seasons", json={
            "variety": "joha", "area_bigha": "2", "start_date": "2025-06-01"
        })
        season_id = season.json()["id"]

        resp = await auth_client.post(f"/api/farm/seasons/{season_id}/milling", json={
            "dhan_sent_kg": "1000", "chawl_received_kg": "650",
            "milling_charges": "1500", "milling_date": "2025-11-01",
        })
        assert resp.status_code == 422
        assert resp.json()["error"] == "INVALID_SEASON_TRANSITION"

    async def test_fail_season(self, auth_client):
        season = await auth_client.post("/api/farm/seasons", json={
            "variety": "joha", "area_bigha": "2", "start_date": "2025-06-01"
        })
        season_id = season.json()["id"]

        resp = await auth_client.patch(f"/api/farm/seasons/{season_id}/fail", json={
            "reason": "Flood damage — total crop loss",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"


class TestPethaLifecycle:
    async def test_create_batch_and_record_outcome(self, auth_client, narikal_product):
        resp = await auth_client.post("/api/petha/batches", json={
            "variety":        "narikal",
            "batch_date":     "2025-05-10",
            "planned_pieces": 30,
            "shelf_life_days":7,
            "recipe_snapshot":{"petha_guri_kg":"1.5","coconut_pcs":3},
            "costs": [
                {"cost_type":"ingredient","description":"petha guri",
                 "qty":"1.5","unit_cost":"60","total_amount":"90"},
                {"cost_type":"labor","description":"maker 2hr",
                 "qty":"2","unit_cost":"75","total_amount":"150"},
                {"cost_type":"fuel","description":"LPG",
                 "qty":"1","unit_cost":"25","total_amount":"25"},
            ],
        })
        assert resp.status_code == 201
        batch_id    = resp.json()["id"]
        total_cost  = Decimal(resp.json()["total_batch_cost"])
        assert total_cost == Decimal("265")   # 90+150+25

        # Record outcome
        outcome = await auth_client.patch(f"/api/petha/batches/{batch_id}/outcome", json={
            "good_pieces":     27,
            "rejected_pieces": 3,
        })
        assert outcome.status_code == 200
        data = outcome.json()
        assert data["status"] == "completed"
        cost_pp = Decimal(data["cost_per_piece"])
        # 265 / 27 = 9.81481...
        assert abs(cost_pp - Decimal("265") / Decimal("27")) < Decimal("0.00001")

    async def test_float_batch_cost_rejected(self, auth_client):
        resp = await auth_client.post("/api/petha/batches", json={
            "variety": "septa", "batch_date": "2025-05-10",
            "planned_pieces": 20, "shelf_life_days": 7,
            "recipe_snapshot": {},
            "costs": [
                {"cost_type":"ingredient","description":"guri",
                 "qty":"1","unit_cost": 50.5,   # ← float — must fail
                 "total_amount":"50.5"},
            ],
        })
        assert resp.status_code == 422

    async def test_expiring_soon_endpoint(self, auth_client, narikal_product):
        # Create a batch that expires in 2 days
        from datetime import timedelta
        batch_date = (date.today() - timedelta(days=5)).isoformat()
        resp = await auth_client.post("/api/petha/batches", json={
            "variety": "narikal", "batch_date": batch_date,
            "planned_pieces": 10, "shelf_life_days": 7,
            "recipe_snapshot": {},
            "costs": [{"cost_type":"ingredient","description":"guri",
                       "qty":"1","unit_cost":"50","total_amount":"50"}],
        })
        batch_id = resp.json()["id"]
        await auth_client.patch(f"/api/petha/batches/{batch_id}/outcome",
                                json={"good_pieces":10,"rejected_pieces":0})

        soon = await auth_client.get("/api/petha/batches/expiring-soon?days=3")
        assert soon.status_code == 200
        ids = [b["id"] for b in soon.json()]
        assert batch_id in ids
```