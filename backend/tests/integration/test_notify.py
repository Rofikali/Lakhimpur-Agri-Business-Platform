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