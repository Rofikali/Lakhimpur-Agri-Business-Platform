import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel, field_validator


class WebhookPayload(BaseModel):
    """Razorpay webhook body (parsed from JSON)."""

    entity: str
    event: str
    payload: dict


class MarkPaidRequest(BaseModel):
    payment_mode: str  # "cash" | "upi_manual" | "credit"
    credit_due_date: date | None = None


class PaymentResponse(BaseModel):
    order_id: uuid.UUID
    payment_mode: str
    status: str
    amount: str
    paid_at: Any | None

    @field_validator("amount", mode="before")
    @classmethod
    def to_str(cls, v: Any) -> str:
        return str(v)
