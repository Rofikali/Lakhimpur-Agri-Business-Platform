from decimal import Decimal
from pydantic import BaseModel, Field, field_validator, ConfigDict, computed_field
from typing import Any
import uuid


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    category: str = Field(pattern=r"^(rice|petha)$")
    unit: str = Field(pattern=r"^(kg|pc|cup)$")
    sell_price: Decimal
    farm_cost: Decimal = Decimal("0")
    labor_cost: Decimal = Decimal("0")
    overhead_cost: Decimal = Decimal("0")
    packaging_cost: Decimal = Decimal("0")
    normal_loss_percent: Decimal = Decimal("0")
    is_own_farm: bool = True
    low_stock_threshold: Decimal = Decimal("5")
    description: str | None = None

    @field_validator(
        "sell_price",
        "farm_cost",
        "labor_cost",
        "overhead_cost",
        "packaging_cost",
        "normal_loss_percent",
        mode="before",
    )
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float):
            raise ValueError("Use string or Decimal for money — never float")
        return Decimal(str(v))


class ProductUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    sell_price: Decimal | None = None
    farm_cost: Decimal | None = None
    labor_cost: Decimal | None = None
    overhead_cost: Decimal | None = None
    packaging_cost: Decimal | None = None
    normal_loss_percent: Decimal | None = None
    is_active: bool | None = None
    low_stock_threshold: Decimal | None = None

    @field_validator(
        "sell_price",
        "farm_cost",
        "labor_cost",
        "overhead_cost",
        "packaging_cost",
        "normal_loss_percent",
        mode="before",
    )
    @classmethod
    def no_float(cls, v: Any) -> Decimal | None:
        if v is None:
            return None
        if isinstance(v, float):
            raise ValueError("Use string or Decimal for money — never float")
        return Decimal(str(v))


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    category: str
    unit: str
    sell_price: str
    farm_cost: str
    labor_cost: str
    overhead_cost: str
    packaging_cost: str
    normal_loss_percent: str
    true_cost: str
    gross_margin: str
    margin_pct: str
    is_own_farm: bool
    is_active: bool
    low_stock_threshold: str
    current_qty: str  # from inventory_stock join
    image_url: str | None

    @field_validator(
        "sell_price",
        "farm_cost",
        "labor_cost",
        "overhead_cost",
        "packaging_cost",
        "normal_loss_percent",
        "true_cost",
        "gross_margin",
        "margin_pct",
        "low_stock_threshold",
        "current_qty",
        mode="before",
    )
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v) if v is not None else "0"
