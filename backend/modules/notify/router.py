"""
Notify module has minimal HTTP surface.
Most notifications are triggered internally via BackgroundTasks.
This router exposes a test endpoint (dev only) and a log endpoint.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from modules.notify.models import Notification
from core.dependencies import require_owner, get_db_session
from core.config import settings

router = APIRouter(prefix="/api/notify", tags=["notify"])


@router.get("/log")
async def notification_log(
    limit: int = 50,
    owner: dict = Depends(require_owner),
    db: AsyncSession = Depends(get_db_session),
):
    """Recent notification history."""
    result = await db.execute(
        select(Notification).order_by(desc(Notification.created_at)).limit(limit)
    )
    return [
        {
            "id": str(n.id),
            "recipient_phone": n.recipient_phone[:7] + "****",  # masked
            "recipient_type": n.recipient_type,
            "template_name": n.template_name,
            "status": n.status,
            "sent_at": n.sent_at.isoformat() if n.sent_at else None,
            "error_message": n.error_message,
        }
        for n in result.scalars().all()
    ]


@router.post("/test")
async def send_test(owner: dict = Depends(require_owner)):
    """Dev only — sends a test WhatsApp to OWNER_WHATSAPP."""
    if settings.is_production:
        return {"error": "Not available in production"}
    from modules.notify import wati

    ok = await wati.send_template_message(
        phone=settings.OWNER_WHATSAPP or "+919999999999",
        template="order_confirmed",
        params=["TEST-0001", "Test User", "100.00", "pickup"],
    )
    return {"sent": ok, "wati_enabled": settings.WATI_ENABLED}
