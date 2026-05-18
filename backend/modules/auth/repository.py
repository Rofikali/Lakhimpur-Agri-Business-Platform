import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from modules.auth.models import Owner


class AuthRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_by_username(self, username: str) -> Owner | None:
        result = await self.db.execute(select(Owner).where(Owner.username == username))
        return result.scalar_one_or_none()

    async def find_by_id(self, owner_id: uuid.UUID) -> Owner | None:
        result = await self.db.execute(select(Owner).where(Owner.id == owner_id))
        return result.scalar_one_or_none()
