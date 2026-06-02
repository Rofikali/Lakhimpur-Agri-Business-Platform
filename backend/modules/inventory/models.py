### inventory/models.py

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import MONEY, QTY, Base, TimestampMixin


class EntryType(str, enum.Enum):
    sale = "sale"
    purchase = "purchase"
    wastage_normal = "wastage_normal"
    wastage_abnormal = "wastage_abnormal"
    consumption = "consumption"
    opening_stock = "opening_stock"
    closing_stock = "closing_stock"
    production = "production"
    capex = "capex"
    fixed_cost = "fixed_cost"
    provision = "provision"


class StockEntry(Base, TimestampMixin):
    __tablename__ = "stock_entries"

    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    entry_type: Mapped[str] = mapped_column(SAEnum(EntryType, name="stock_entry_type"))
    qty: Mapped[Decimal] = mapped_column(QTY)
    unit_cost: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(MONEY)
    standard_unit_cost: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    price_variance: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    cost_variance: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    source: Mapped[str | None] = mapped_column(SAEnum("own", "external", "internal", name="stock_entry_source"), nullable=True)
    channel: Mapped[str | None] = mapped_column(SAEnum("online", "offline", name="stock_entry_channel"), nullable=True)
    pay_mode: Mapped[str | None] = mapped_column(nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    product = relationship("Product", back_populates="stock_entries")


class InventoryStock(Base):
    """One row per product — live stock level."""

    __tablename__ = "inventory_stock"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), unique=True)
    current_qty: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.utcnow())
    product = relationship("Product", back_populates="stock")


class MonthlyStock(Base):
    """Opening and closing stock values for COGS accuracy."""

    __tablename__ = "monthly_stock"
    __table_args__ = (UniqueConstraint("product_id", "month", "stock_type"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    month: Mapped[str] = mapped_column(String(7))  # "2025-05"
    stock_type: Mapped[str] = mapped_column(SAEnum("opening", "closing", name="monthly_stock_type"))
    qty: Mapped[Decimal] = mapped_column(QTY)
    value: Mapped[Decimal] = mapped_column(MONEY)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.utcnow())
