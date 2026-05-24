import logging

from core.config import settings
from modules.notify import wati
from modules.notify.templates import TEMPLATES

logger = logging.getLogger("notify")


class NotifyService:
    """
    Stateless notification service.
    All methods are fire-and-forget — they never raise.
    Called as FastAPI BackgroundTasks.
    """

    async def order_confirmed(self, order) -> None:
        """Customer: Your order LKP-2025-0042 is confirmed."""
        tmpl = TEMPLATES["order_confirmed"]
        await wati.send_template_message(
            phone=order.customer_phone,
            template=tmpl["name"],
            params=tmpl["params"](order),
        )

    async def new_order_to_owner(self, order) -> None:
        """Owner: New order received."""
        if not settings.OWNER_WHATSAPP:
            return
        tmpl = TEMPLATES["new_order_owner"]
        await wati.send_template_message(
            phone=settings.OWNER_WHATSAPP,
            template=tmpl["name"],
            params=tmpl["params"](order),
        )

    async def order_status_updated(self, order, new_status: str) -> None:
        """Customer: Your order status changed."""
        template_map = {
            "packed": "order_packed",
            "out_for_delivery": "order_packed",
            "picked_up": "order_ready_pickup",
            "delivered": "order_delivered",
        }
        tmpl_name = template_map.get(new_status)
        if not tmpl_name:
            return
        tmpl = TEMPLATES[tmpl_name]
        await wati.send_template_message(
            phone=order.customer_phone,
            template=tmpl["name"],
            params=tmpl["params"](order),
        )

    async def low_stock_alert(self, product_name: str, current_qty, threshold) -> None:
        """Owner: Low stock warning."""
        if not settings.OWNER_WHATSAPP:
            return
        tmpl = TEMPLATES["low_stock_alert"]
        await wati.send_template_message(
            phone=settings.OWNER_WHATSAPP,
            template=tmpl["name"],
            params=tmpl["params"](product_name, current_qty, threshold),
        )

    async def petha_expiry_alert(self, variety: str, days_left: int, batch_date) -> None:
        """Owner: Petha batch expiring soon."""
        if not settings.OWNER_WHATSAPP:
            return
        tmpl = TEMPLATES["petha_expiry_alert"]
        await wati.send_template_message(
            phone=settings.OWNER_WHATSAPP,
            template=tmpl["name"],
            params=tmpl["params"](variety, days_left, batch_date),
        )

    async def daily_summary(self, orders_count: int, revenue, net_profit) -> None:
        """Owner: Daily business summary."""
        if not settings.OWNER_WHATSAPP:
            return
        tmpl = TEMPLATES["daily_summary"]
        await wati.send_template_message(
            phone=settings.OWNER_WHATSAPP,
            template=tmpl["name"],
            params=tmpl["params"](orders_count, revenue, net_profit),
        )
