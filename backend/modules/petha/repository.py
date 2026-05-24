import uuid

from modules.petha.models import PethaBatch, PethaBatchCost
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class PethaRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_batch(self, **kwargs) -> PethaBatch:
        b = PethaBatch(**kwargs)
        self.db.add(b)
        await self.db.flush()
        return b

    async def get_batch(self, batch_id: uuid.UUID) -> PethaBatch | None:
        result = await self.db.execute(
            select(PethaBatch)
            .where(PethaBatch.id == batch_id)
            .options(selectinload(PethaBatch.cost_lines))
        )
        return result.scalar_one_or_none()

    async def list_batches(self, include_expired: bool = False) -> list[PethaBatch]:
        q = select(PethaBatch).order_by(PethaBatch.batch_date.desc())
        if not include_expired:
            q = q.where(PethaBatch.status != "expired")
        return list((await self.db.execute(q)).scalars().all())

    async def add_cost(self, batch_id: uuid.UUID, **kwargs) -> PethaBatchCost:
        c = PethaBatchCost(batch_id=batch_id, **kwargs)
        self.db.add(c)
        await self.db.flush()
        return c

    async def save(self, obj) -> None:
        self.db.add(obj)
        await self.db.flush()

    async def get_expiring_soon(self, days: int = 3) -> list[PethaBatch]:
        from datetime import date, timedelta

        target = date.today() + timedelta(days=days)
        result = await self.db.execute(
            select(PethaBatch).where(
                PethaBatch.status == "completed", PethaBatch.expiry_date <= target
            )
        )
        return list(result.scalars().all())
