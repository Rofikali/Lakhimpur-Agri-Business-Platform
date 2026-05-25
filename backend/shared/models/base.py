# cat > backend / shared / models / base.py << "EOF"

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import MetaData, Numeric, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ── Naming convention (Alembic constraint names) ──────────────────────────────
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ── Single declarative base ───────────────────────────────────────────────────
class Base(DeclarativeBase):
    metadata = metadata


# ── Column type aliases ───────────────────────────────────────────────────────
# Use these everywhere — never plain float

MONEY = Numeric(precision=15, scale=5)  # ₹ amounts  e.g. 105.00000
QTY = Numeric(precision=10, scale=3)  # Quantities e.g. 3.500


# ── Shared mixin — every model inherits this ──────────────────────────────────
class TimestampMixin:
    """
    Provides: id (UUID PK), created_at, updated_at, deleted_at.
    Inherit alongside Base: class MyModel(Base, TimestampMixin)
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        default=None,
    )


# EOF
# echo "✓ base.py fixed"

# # backend/shared/models/base.py

# from sqlalchemy import MetaData
# from sqlalchemy.orm import DeclarativeBase

# NAMING_CONVENTION = {
#     "ix": "ix_%(column_0_label)s",
#     "uq": "uq_%(table_name)s_%(column_0_name)s",
#     "ck": "ck_%(table_name)s_%(constraint_name)s",
#     "fk": ("fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"),
#     "pk": "pk_%(table_name)s",
# }

# metadata = MetaData(naming_convention=NAMING_CONVENTION)


# class MONEY(DeclarativeBase):
#     # metadata = metadata
#     pass

# class Base(DeclarativeBase):
#     metadata = metadata
