import uuid
from decimal import Decimal
from datetime import date
from typing import Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class SeasonCreate(BaseModel):
    variety: str = Field(pattern=r"^(joha|bora_saul|kali_jeera)$")
    area_bigha: Decimal = Field(gt=Decimal("0"))
    start_date: date
    notes: str | None = None

    @field_validator("area_bigha", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float):
            raise ValueError("Use string — never float")
        return Decimal(str(v))


class FarmInputCreate(BaseModel):
    input_type: str = Field(
        pattern=r"^(seed|fertilizer|pesticide|labor|irrigation|transport|other)$"
    )
    description: str
    qty: Decimal | None = None
    unit: str | None = None
    unit_cost: Decimal
    total_amount: Decimal
    date: date

    @field_validator("qty", "unit_cost", "total_amount", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal | None:
        if v is None:
            return None
        if isinstance(v, float):
            raise ValueError("No float")
        return Decimal(str(v))


class HarvestRecord(BaseModel):
    dhan_qty_kg: Decimal
    harvest_date: date
    notes: str | None = None

    @field_validator("dhan_qty_kg", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float):
            raise ValueError("No float")
        return Decimal(str(v))


class MillingRecord(BaseModel):
    dhan_sent_kg: Decimal
    chawl_received_kg: Decimal
    husk_recovered_kg: Decimal = Decimal("0")
    bran_recovered_kg: Decimal = Decimal("0")
    broken_rice_kg: Decimal = Decimal("0")
    milling_charges: Decimal
    husk_market_price: Decimal = Decimal("0")
    bran_market_price: Decimal = Decimal("0")
    broken_market_price: Decimal = Decimal("0")
    milling_date: date

    @field_validator(
        "dhan_sent_kg",
        "chawl_received_kg",
        "husk_recovered_kg",
        "bran_recovered_kg",
        "broken_rice_kg",
        "milling_charges",
        "husk_market_price",
        "bran_market_price",
        "broken_market_price",
        mode="before",
    )
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float):
            raise ValueError("No float")
        return Decimal(str(v))


class SeasonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    variety: str
    area_bigha: str
    status: str
    start_date: date
    harvest_date: date | None
    dhan_qty_kg: str | None
    chawl_qty_kg: str | None
    total_cultivation_cost: str | None
    milling_yield_percent: str | None
    cost_per_kg_dhan: str | None
    cost_per_kg_chawl: str | None
    transfer_price_per_kg: str | None

    @field_validator(
        "area_bigha",
        "dhan_qty_kg",
        "chawl_qty_kg",
        "total_cultivation_cost",
        "milling_yield_percent",
        "cost_per_kg_dhan",
        "cost_per_kg_chawl",
        "transfer_price_per_kg",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: Any) -> str | None:
        return str(v) if v is not None else None
