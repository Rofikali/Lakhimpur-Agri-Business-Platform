### finance/models.py + notify/models.py
from sqlalchemy.orm import Mapped, mapped_column
from shared.models.base import Base, TimestampMixin, MONEY, QTY
from sqlalchemy import String, Enum as SAEnum, Date, ForeignKey, Text, UniqueConstraint, Integer, Boolean
import enum, uuid
from decimal import Decimal
from datetime import date, datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import JSONB



# class FixedCost(Base, TimestampMixin):
#     __tablename__ = "fixed_costs"
#     name: Mapped[str] = mapped_column(String(200))
#     category: Mapped[str] = mapped_column(
#         SAEnum("stall", "fuel", "transport", "drawing", "provision", "misc")
#     )
#     monthly_amount: Mapped[Decimal] = mapped_column(MONEY)
#     is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# class Asset(Base, TimestampMixin):
#     __tablename__ = "assets"
#     name: Mapped[str] = mapped_column(String(200))
#     cost: Mapped[Decimal] = mapped_column(MONEY)
#     useful_life_years: Mapped[int] = mapped_column(Integer)
#     monthly_depreciation: Mapped[Decimal] = mapped_column(MONEY)  # GENERATED ALWAYS
#     purchase_date: Mapped[date] = mapped_column(Date)
#     is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_phone: Mapped[str] = mapped_column(String(15))
    recipient_type: Mapped[str] = mapped_column(SAEnum("owner", "customer"))
    channel: Mapped[str] = mapped_column(SAEnum("whatsapp", "sms"))
    template_name: Mapped[str] = mapped_column(String(100))
    message_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(SAEnum("pending", "sent", "failed"), default="pending")
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.utcnow())
