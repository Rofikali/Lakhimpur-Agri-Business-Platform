import hashlib
import hmac
import razorpay
from decimal import Decimal
from core.config import settings
from shared.exceptions import RazorpayOrderCreateFailedError, WebhookSignatureInvalidError


def _client() -> razorpay.Client:
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


async def create_razorpay_order(our_order_id: str, amount: Decimal) -> dict:
    """
    Create Razorpay order. Amount in paise (multiply ₹ by 100).
    Returns {"id": "order_xxx", "amount": 59500, ...}
    """
    paise = int(amount * 100)  # Razorpay uses paise, not rupees
    try:
        client = _client()
        data = client.order.create(
            {
                "amount": paise,
                "currency": settings.RAZORPAY_CURRENCY,
                "receipt": our_order_id[:40],  # max 40 chars
                "notes": {"our_order_id": our_order_id},
            }
        )
        return data
    except Exception as e:
        raise RazorpayOrderCreateFailedError() from e


def verify_webhook_signature(payload_body: bytes, signature: str) -> None:
    """
    Verify Razorpay webhook HMAC-SHA256 signature.
    Raises WebhookSignatureInvalidError if invalid.
    """
    expected = hmac.new(
        key=settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise WebhookSignatureInvalidError()


def issue_refund(razorpay_payment_id: str, amount: Decimal) -> dict:
    """Issue full or partial refund."""
    try:
        client = _client()
        return client.payment.refund(razorpay_payment_id, {"amount": int(amount * 100)})
    except Exception as e:
        raise RazorpayOrderCreateFailedError() from e
