"""
Factory Boy factories for generating realistic test data.
Use these in tests instead of manually building DB objects.
"""
import uuid
import factory
from decimal import Decimal
from datetime import date, timedelta
from factory.alchemy import SQLAlchemyModelFactory
from modules.auth.models import Owner
from modules.products.models import Product
from modules.inventory.models import InventoryStock, StockEntry
from modules.orders.models import Order, OrderItem, Payment
from modules.farm.models import FarmSeason, FarmInput
from modules.petha.models import PethaBatch
from modules.finance.models import Asset, FixedCost
from core.security import hash_password


class BaseFactory(SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session_persistence = "flush"


class OwnerFactory(BaseFactory):
    class Meta:
        model = Owner

    username      = factory.Sequence(lambda n: f"owner_{n}")
    password_hash = factory.LazyFunction(lambda: hash_password("TestPass123!"))


class ProductFactory(BaseFactory):
    class Meta:
        model = Product

    name                 = factory.Sequence(lambda n: f"Product {n}")
    slug                 = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))
    category             = "rice"
    unit                 = "kg"
    sell_price           = Decimal("100.00000")
    farm_cost            = Decimal("50.00000")
    labor_cost           = Decimal("5.00000")
    overhead_cost        = Decimal("3.00000")
    packaging_cost       = Decimal("7.00000")
    normal_loss_percent  = Decimal("0.00000")
    true_cost            = Decimal("65.00000")
    is_active            = True
    is_own_farm          = True
    low_stock_threshold  = Decimal("5.000")


class StockFactory(BaseFactory):
    class Meta:
        model = InventoryStock

    product_id  = factory.LazyFunction(uuid.uuid4)
    current_qty = Decimal("50.000")


class OrderFactory(BaseFactory):
    class Meta:
        model = Order

    idempotency_key  = factory.LazyFunction(uuid.uuid4)
    order_number     = factory.Sequence(lambda n: f"LKP-2025-{n:04d}")
    customer_name    = factory.Faker("name")
    customer_phone   = "+919876543210"
    fulfillment_type = "pickup"
    channel          = "offline"
    status           = "pending"
    total_amount     = Decimal("315.00000")
    discount_amount  = Decimal("0.00000")
    final_amount     = Decimal("315.00000")


class AssetFactory(BaseFactory):
    class Meta:
        model = Asset

    name                 = factory.Sequence(lambda n: f"Asset {n}")
    cost                 = Decimal("12000.00000")
    useful_life_years    = 10
    monthly_depreciation = Decimal("100.00000")
    purchase_date        = factory.LazyFunction(lambda: date(2024, 1, 1))
    is_active            = True


class FixedCostFactory(BaseFactory):
    class Meta:
        model = FixedCost

    name           = factory.Sequence(lambda n: f"Fixed cost {n}")
    category       = "stall"
    monthly_amount = Decimal("1200.00000")
    is_active      = True


class FarmSeasonFactory(BaseFactory):
    class Meta:
        model = FarmSeason

    variety                = "joha"
    area_bigha             = Decimal("3.500")
    status                 = "active"
    start_date             = factory.LazyFunction(lambda: date(2025, 6, 1))
    total_cultivation_cost = Decimal("40000.00000")


class PethaBatchFactory(BaseFactory):
    class Meta:
        model = PethaBatch

    variety               = "narikal"
    status                = "in_production"
    batch_date            = factory.LazyFunction(lambda: date.today())
    planned_pieces        = 30
    shelf_life_days       = 7
    total_ingredient_cost = Decimal("90.00000")
    total_labor_cost      = Decimal("150.00000")
    total_overhead_cost   = Decimal("25.00000")
    total_batch_cost      = Decimal("265.00000")
    expiry_date           = factory.LazyFunction(lambda: date.today() + timedelta(days=7))
    recipe_snapshot       = {"petha_guri_kg": "1.5"}