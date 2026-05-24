import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StockEntryCreate(BaseModel):
    idempotency_key: uuid.UUID
    product_id: uuid.UUID
    entry_type: str = Field(
        pattern=r"^(sale|purchase|wastage_normal|wastage_abnormal|consumption|opening_stock|closing_stock|production|capex|fixed_cost|provision)$"
    )
    qty: Decimal
    unit_cost: Decimal | None = None
    total_amount: Decimal
    source: str | None = None
    channel: str | None = None
    pay_mode: str | None = None
    wastage_type: str | None = None
    reference_id: uuid.UUID | None = None
    reference_type: str | None = None
    date: date
    note: str | None = None

    @field_validator("qty", "unit_cost", "total_amount", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal | None:
        if v is None:
            return None
        if isinstance(v, float):
            raise ValueError("Never use float for money or quantity")
        return Decimal(str(v))


class StockEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID
    entry_type: str
    qty: str
    unit_cost: str | None
    total_amount: str
    price_variance: str | None
    cost_variance: str | None
    new_stock_qty: str
    date: date

    @field_validator(
        "qty",
        "total_amount",
        "price_variance",
        "cost_variance",
        "new_stock_qty",
        "unit_cost",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: Any) -> str | None:
        return str(v) if v is not None else None


class MonthlyStockCreate(BaseModel):
    product_id: uuid.UUID
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    stock_type: str = Field(pattern=r"^(opening|closing)$")
    qty: Decimal
    value: Decimal

    @field_validator("qty", "value", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float):
            raise ValueError("Never use float")
        return Decimal(str(v))


class CurrentStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id: uuid.UUID
    current_qty: str
    updated_at: Any

    @field_validator("current_qty", mode="before")
    @classmethod
    def to_str(cls, v: Any) -> str:
        return str(v)
