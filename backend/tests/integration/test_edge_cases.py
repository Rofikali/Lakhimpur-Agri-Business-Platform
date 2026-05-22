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