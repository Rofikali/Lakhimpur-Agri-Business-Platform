import uuid
from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, Numeric, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column, Mapped, relationship

from shared.models.base import Base, TimestampMixin, MONEY, QTY


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    unit: Mapped[str] = mapped_column(String(10), nullable=False)

    sell_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    farm_cost: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    labor_cost: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    overhead_cost: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    packaging_cost: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    normal_loss_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    true_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))

    is_own_farm: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    low_stock_threshold: Mapped[Decimal] = mapped_column(QTY, default=Decimal("5"))
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships (back_populates defined in the other models)
    stock = relationship("InventoryStock", back_populates="product", uselist=False)
    stock_entries = relationship("StockEntry", back_populates="product")
    order_items = relationship("OrderItem", back_populates="product")
