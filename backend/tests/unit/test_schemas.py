"""
Pydantic schema validation tests.
Most critical: float MUST be rejected for all money fields.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from modules.inventory.schemas import StockEntryCreate
from modules.orders.schemas import OrderCreate, OrderItemCreate
from modules.products.schemas import ProductCreate


class TestFloatRejection:
    """Float must NEVER be accepted for money or quantity fields."""

    def test_product_sell_price_rejects_float(self):
        with pytest.raises(ValidationError, match="never float"):
            ProductCreate(
                name="Test Rice",
                category="rice",
                unit="kg",
                sell_price=105.5,  # ← float — must fail
                farm_cost="50",
            )

    def test_product_farm_cost_rejects_float(self):
        with pytest.raises(ValidationError, match="never float"):
            ProductCreate(
                name="Test Rice",
                category="rice",
                unit="kg",
                sell_price="105",
                farm_cost=50.0,  # ← float — must fail
            )

    def test_order_item_qty_rejects_float(self):
        with pytest.raises(ValidationError, match="never float"):
            OrderItemCreate(product_id=uuid.uuid4(), qty=3.5)  # ← float

    def test_stock_entry_qty_rejects_float(self):
        with pytest.raises(ValidationError, match="never float"):
            StockEntryCreate(
                idempotency_key=uuid.uuid4(),
                product_id=uuid.uuid4(),
                entry_type="purchase",
                qty=50.0,  # ← float — must fail
                total_amount="3600",
                date=date.today(),
            )


class TestDecimalAccepted:
    """String and Decimal should both be accepted."""

    def test_string_decimal_accepted_for_sell_price(self):
        p = ProductCreate(
            name="Joha Rice",
            category="rice",
            unit="kg",
            sell_price="105.00000",
            farm_cost="50",
        )
        assert p.sell_price == Decimal("105.00000")

    def test_decimal_object_accepted(self):
        p = ProductCreate(
            name="Joha Rice",
            category="rice",
            unit="kg",
            sell_price=Decimal("105"),
            farm_cost=Decimal("50"),
        )
        assert p.sell_price == Decimal("105")

    def test_integer_string_accepted(self):
        p = ProductCreate(
            name="Joha Rice",
            category="rice",
            unit="kg",
            sell_price="105",
            farm_cost="50",
        )
        assert p.sell_price == Decimal("105")


class TestOrderValidation:
    def test_valid_order_passes(self):
        o = OrderCreate(
            idempotency_key=uuid.uuid4(),
            customer_name="Ratan Das",
            customer_phone="+919876543210",
            fulfillment_type="pickup",
            channel="online",
            payment_mode="razorpay",
            items=[OrderItemCreate(product_id=uuid.uuid4(), qty="3")],
        )
        assert len(o.items) == 1

    def test_invalid_phone_rejected(self):
        with pytest.raises(ValidationError):
            OrderCreate(
                idempotency_key=uuid.uuid4(),
                customer_name="Test",
                customer_phone="1234567890",  # invalid Indian format
                fulfillment_type="pickup",
                channel="online",
                payment_mode="cash",
                items=[OrderItemCreate(product_id=uuid.uuid4(), qty="1")],
            )

    def test_empty_items_rejected(self):
        with pytest.raises(ValidationError):
            OrderCreate(
                idempotency_key=uuid.uuid4(),
                customer_name="Test",
                customer_phone="+919876543210",
                fulfillment_type="pickup",
                channel="online",
                payment_mode="cash",
                items=[],  # ← empty list — must fail
            )

    def test_invalid_payment_mode_rejected(self):
        with pytest.raises(ValidationError):
            OrderCreate(
                idempotency_key=uuid.uuid4(),
                customer_name="Test",
                customer_phone="+919876543210",
                fulfillment_type="pickup",
                channel="online",
                payment_mode="btc",  # ← invalid
                items=[OrderItemCreate(product_id=uuid.uuid4(), qty="1")],
            )

    def test_delivery_with_no_address_allowed(self):
        """Address not required by schema — validated in service layer."""
        o = OrderCreate(
            idempotency_key=uuid.uuid4(),
            customer_name="Test",
            customer_phone="+919876543210",
            fulfillment_type="delivery",
            channel="online",
            payment_mode="razorpay",
            items=[OrderItemCreate(product_id=uuid.uuid4(), qty="1")],
        )
        assert o.fulfillment_type == "delivery"


class TestProductSchemaValidation:
    def test_invalid_category_rejected(self):
        with pytest.raises(ValidationError):
            ProductCreate(
                name="Test",
                category="vegetable",  # invalid
                unit="kg",
                sell_price="100",
            )

    def test_invalid_unit_rejected(self):
        with pytest.raises(ValidationError):
            ProductCreate(
                name="Test",
                category="rice",
                unit="litre",  # invalid — only kg/pc/cup
                sell_price="100",
            )
