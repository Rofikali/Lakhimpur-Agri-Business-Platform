import uuid

from modules.farm.models import FarmInput, FarmMilling, FarmSeason
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class FarmRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_season(self, **kwargs) -> FarmSeason:
        s = FarmSeason(**kwargs)
        self.db.add(s)
        await self.db.flush()
        await self.db.refresh(s)
        return s

    async def get_season(self, season_id: uuid.UUID) -> FarmSeason | None:
        result = await self.db.execute(
            select(FarmSeason)
            .where(FarmSeason.id == season_id)
            .options(selectinload(FarmSeason.inputs), selectinload(FarmSeason.millings))
        )
        return result.scalar_one_or_none()

    async def list_seasons(self) -> list[FarmSeason]:
        result = await self.db.execute(select(FarmSeason).order_by(FarmSeason.start_date.desc()))
        return list(result.scalars().all())

    async def add_input(self, season_id: uuid.UUID, **kwargs) -> FarmInput:
        fi = FarmInput(season_id=season_id, **kwargs)
        self.db.add(fi)
        await self.db.flush()
        return fi

    async def add_milling(self, season_id: uuid.UUID, **kwargs) -> FarmMilling:
        fm = FarmMilling(season_id=season_id, **kwargs)
        self.db.add(fm)
        await self.db.flush()
        return fm

    async def save(self, obj) -> None:
        self.db.add(obj)
        await self.db.flush()
