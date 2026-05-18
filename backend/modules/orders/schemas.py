import uuid
from decimal import Decimal
from datetime import date
from typing import Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class OrderItemCreate(BaseModel):
    product_id: uuid.UUID
    qty: Decimal = Field(gt=Decimal("0"))
    source: str = "own"

    @field_validator("qty", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float):
            raise ValueError("Use string for qty — never float")
        return Decimal(str(v))


class OrderCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    idempotency_key: uuid.UUID
    customer_name: str = Field(min_length=2, max_length=100)
    customer_phone: str = Field(pattern=r"^\+?91[6-9]\d{9}$")
    customer_address: str | None = None
    fulfillment_type: str = Field(pattern=r"^(pickup|delivery)$")
    channel: str = Field(pattern=r"^(online|offline)$")
    payment_mode: str = Field(pattern=r"^(razorpay|cash|upi_manual|credit)$")
    credit_due_date: date | None = None
    items: list[OrderItemCreate] = Field(min_length=1, max_length=20)


class StatusUpdate(BaseModel):
    status: str
    cancel_reason: str | None = None
