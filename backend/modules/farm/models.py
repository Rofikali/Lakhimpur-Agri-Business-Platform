### farm/models.py
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import MONEY, QTY, Base, TimestampMixin


class FarmVariety(str, enum.Enum):
    joha = "joha"
    bora_saul = "bora_saul"
    kali_jeera = "kali_jeera"


class SeasonStatus(str, enum.Enum):
    planning = "planning"
    active = "active"
    harvested = "harvested"
    milled = "milled"
    complete = "complete"
    failed = "failed"


class FarmSeason(Base, TimestampMixin):
    __tablename__ = "farm_seasons"
    variety: Mapped[str] = mapped_column(SAEnum(FarmVariety, name="farm_variety"))
    area_bigha: Mapped[Decimal] = mapped_column(QTY)
    status: Mapped[str] = mapped_column(SAEnum(SeasonStatus, name="farm_season_status"), default="planning")
    start_date: Mapped[date] = mapped_column(Date)
    harvest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    dhan_qty_kg: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    chawl_qty_kg: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    total_cultivation_cost: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    milling_yield_percent: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    cost_per_kg_dhan: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    cost_per_kg_chawl: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    transfer_price_per_kg: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    inputs = relationship("FarmInput", back_populates="season", cascade="all")
    millings = relationship("FarmMilling", back_populates="season")


class FarmInput(Base):
    __tablename__ = "farm_inputs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm_seasons.id"))
    input_type: Mapped[str] = mapped_column(
        SAEnum("seed", "fertilizer", "pesticide", "labor", "irrigation", "transport", "other", name="farm_input_type")
    )
    description: Mapped[str] = mapped_column(Text)
    qty: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit_cost: Mapped[Decimal] = mapped_column(MONEY)
    total_amount: Mapped[Decimal] = mapped_column(MONEY)
    date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.utcnow())
    season = relationship("FarmSeason", back_populates="inputs")


class FarmMilling(Base, TimestampMixin):
    __tablename__ = "farm_millings"
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farm_seasons.id"))
    dhan_sent_kg: Mapped[Decimal] = mapped_column(QTY)
    chawl_received_kg: Mapped[Decimal] = mapped_column(QTY)
    husk_recovered_kg: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    bran_recovered_kg: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    broken_rice_kg: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    milling_charges: Mapped[Decimal] = mapped_column(MONEY)
    husk_market_price: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    bran_market_price: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    broken_market_price: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    yield_percent: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    milling_date: Mapped[date] = mapped_column(Date)
    season = relationship("FarmSeason", back_populates="millings")
