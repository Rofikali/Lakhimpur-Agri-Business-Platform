### petha/models.py
from sqlalchemy.orm import Mapped, mapped_column
from shared.models.base import Base, TimestampMixin, MONEY, QTY
from sqlalchemy import String, Enum as SAEnum, Date, ForeignKey, Text, UniqueConstraint, Integer
import enum, uuid
from decimal import Decimal
from datetime import date, datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import JSONB


class PethaVariety(str, enum.Enum):
    septa = "septa"
    narikal = "narikal"


class BatchStatus(str, enum.Enum):
    in_production = "in_production"
    completed = "completed"
    expired = "expired"


class PethaBatch(Base, TimestampMixin):
    __tablename__ = "petha_batches"
    variety: Mapped[str] = mapped_column(SAEnum(PethaVariety))
    status: Mapped[str] = mapped_column(SAEnum(BatchStatus), default="in_production")
    batch_date: Mapped[date] = mapped_column(Date)
    planned_pieces: Mapped[int] = mapped_column(Integer)
    good_pieces: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rejected_pieces: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_ingredient_cost: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    total_labor_cost: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    total_overhead_cost: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    total_batch_cost: Mapped[Decimal] = mapped_column(MONEY)  # GENERATED ALWAYS
    cost_per_piece: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    shelf_life_days: Mapped[int] = mapped_column(Integer, default=7)
    expiry_date: Mapped[date] = mapped_column(Date)  # GENERATED ALWAYS
    recipe_snapshot: Mapped[dict] = mapped_column(JSONB)
    abnormal_loss_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_lines = relationship("PethaBatchCost", back_populates="batch", cascade="all")


class PethaBatchCost(Base):
    __tablename__ = "petha_batch_costs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("petha_batches.id"))
    cost_type: Mapped[str] = mapped_column(SAEnum("ingredient", "labor", "fuel", "overhead"))
    description: Mapped[str] = mapped_column(Text)
    qty: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    unit_cost: Mapped[Decimal] = mapped_column(MONEY)
    total_amount: Mapped[Decimal] = mapped_column(MONEY)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.utcnow())
    batch = relationship("PethaBatch", back_populates="cost_lines")
