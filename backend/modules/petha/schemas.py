import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BatchCostCreate(BaseModel):
    cost_type: str = Field(pattern=r"^(ingredient|labor|fuel|overhead)$")
    description: str
    qty: Decimal | None = None
    unit_cost: Decimal
    total_amount: Decimal

    @field_validator("qty", "unit_cost", "total_amount", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal | None:
        if v is None:
            return None
        if isinstance(v, float):
            raise ValueError("No float")
        return Decimal(str(v))


class BatchCreate(BaseModel):
    variety: str = Field(pattern=r"^(septa|narikal)$")
    batch_date: date
    planned_pieces: int = Field(ge=1)
    shelf_life_days: int = Field(default=7, ge=1, le=30)
    recipe_snapshot: dict
    costs: list[BatchCostCreate] = Field(min_length=1)


class BatchOutcome(BaseModel):
    good_pieces: int = Field(ge=0)
    rejected_pieces: int = Field(ge=0)


class BatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    variety: str
    status: str
    batch_date: date
    planned_pieces: int
    good_pieces: int | None
    rejected_pieces: int | None
    total_batch_cost: str
    cost_per_piece: str | None
    expiry_date: date
    days_to_expiry: int
    rejection_pct: str | None

    @field_validator("total_batch_cost", "cost_per_piece", "rejection_pct", mode="before")
    @classmethod
    def to_str(cls, v: Any) -> str | None:
        return str(v) if v is not None else None
