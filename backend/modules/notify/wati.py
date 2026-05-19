"""WATI (WhatsApp Business API) client."""

import httpx
import logging
from core.config import settings

logger = logging.getLogger("notify.wati")


async def send_template_message(phone: str, template: str, params: list[str]) -> bool:
    """
    Send a WhatsApp template message via WATI.
    Returns True on success, False on failure.
    Failure is logged but NEVER raises — notifications are non-critical.
    """
    if not settings.WATI_ENABLED:
        logger.info(f"WATI disabled — skipping message to {phone[:7]}****")
        return True

    url = f"{settings.WATI_BASE_URL}/sendTemplateMessage"
    headers = {
        "Authorization": f"Bearer {settings.WATI_API_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {
        "whatsappNumber": phone.replace("+", "").replace("-", ""),
        "template_name": template,
        "broadcast_name": template,
        "parameters": [{"name": f"param{i + 1}", "value": v} for i, v in enumerate(params)],
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code == 200:
                logger.info(f"WhatsApp sent: {template} → {phone[:7]}****")
                return True
            else:
                logger.error(f"WATI error {resp.status_code}: {resp.text[:200]}")
                return False
    except Exception as e:
        logger.error(f"WATI exception: {e}")
        return False
