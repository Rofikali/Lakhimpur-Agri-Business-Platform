from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session, require_owner
from modules.finance.models import Asset, FixedCost

router = APIRouter(prefix="/api/finance", tags=["finance"])


class FixedCostCreate(BaseModel):
    name: str
    category: str
    monthly_amount: Decimal

    @field_validator("monthly_amount", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float):
            raise ValueError("No float")
        return Decimal(str(v))


class AssetCreate(BaseModel):
    name: str
    cost: Decimal
    useful_life_years: int = Field(ge=1)
    purchase_date: date

    @field_validator("cost", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float):
            raise ValueError("No float")
        return Decimal(str(v))


@router.get("/fixed-costs")
async def list_fixed_costs(
    owner: dict = Depends(require_owner), db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(select(FixedCost).where(FixedCost.deleted_at.is_(None)))
    return [
        {
            "id": str(f.id),
            "name": f.name,
            "category": f.category,
            "monthly_amount": str(f.monthly_amount),
            "is_active": f.is_active,
        }
        for f in result.scalars().all()
    ]


@router.post("/fixed-costs", status_code=201)
async def create_fixed_cost(
    body: FixedCostCreate,
    owner: dict = Depends(require_owner),
    db: AsyncSession = Depends(get_db_session),
):
    fc = FixedCost(name=body.name, category=body.category, monthly_amount=body.monthly_amount)
    db.add(fc)
    await db.flush()
    return {"id": str(fc.id), "name": fc.name, "monthly_amount": str(fc.monthly_amount)}


@router.get("/assets")
async def list_assets(
    owner: dict = Depends(require_owner), db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(select(Asset).where(Asset.deleted_at.is_(None)))
    assets = result.scalars().all()
    total_depreciation = sum((a.monthly_depreciation for a in assets), Decimal("0"))
    return {
        "assets": [
            {
                "id": str(a.id),
                "name": a.name,
                "cost": str(a.cost),
                "useful_life_years": a.useful_life_years,
                "monthly_depreciation": str(a.monthly_depreciation),
                "purchase_date": a.purchase_date.isoformat(),
                "is_active": a.is_active,
            }
            for a in assets
        ],
        "total_monthly_depreciation": str(total_depreciation),
    }


@router.post("/assets", status_code=201)
async def create_asset(
    body: AssetCreate,
    owner: dict = Depends(require_owner),
    db: AsyncSession = Depends(get_db_session),
):
    depreciation = body.cost / Decimal(str(body.useful_life_years * 12))
    asset = Asset(
        name=body.name,
        cost=body.cost,
        useful_life_years=body.useful_life_years,
        monthly_depreciation=depreciation,
        purchase_date=body.purchase_date,
    )
    db.add(asset)
    await db.flush()
    return {
        "id": str(asset.id),
        "name": asset.name,
        "monthly_depreciation": str(asset.monthly_depreciation),
    }
