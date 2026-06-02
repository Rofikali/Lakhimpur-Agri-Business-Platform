"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2025-05-15
"""

from collections.abc import Sequence

from alembic import op

# Import all models so Base.metadata is populated for the initial schema.
from modules.auth.models import Owner  # noqa: F401
from modules.farm.models import FarmInput, FarmMilling, FarmSeason  # noqa: F401
from modules.finance.models import Asset, FixedCost  # noqa: F401
from modules.inventory.models import InventoryStock, MonthlyStock, StockEntry  # noqa: F401
from modules.notify.models import Notification  # noqa: F401
from modules.orders.models import Order, OrderItem, Payment  # noqa: F401
from modules.petha.models import PethaBatch, PethaBatchCost  # noqa: F401
from modules.products.models import Product  # noqa: F401
from shared.models.base import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
