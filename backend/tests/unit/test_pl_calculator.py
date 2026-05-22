"""
P&L Engine unit tests — target 95%+ coverage of calculator.py.
Pure function tests: no DB, no HTTP, no external services.
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from modules.pl_engine.calculator import calculate, PLResult, ZERO


def _entry(
    entry_type,
    total_amount,
    channel=None,
    pay_mode=None,
    source=None,
    qty=Decimal("1"),
    price_variance=None,
    cost_variance=None,
    product_id=None,
):
    """Helper to build a mock StockEntry."""
    e = MagicMock()
    e.entry_type = entry_type
    e.total_amount = Decimal(str(total_amount))
    e.channel = channel
    e.pay_mode = pay_mode
    e.source = source or "own"
    e.qty = Decimal(str(qty))
    e.price_variance = Decimal(str(price_variance)) if price_variance else None
    e.cost_variance = Decimal(str(cost_variance)) if cost_variance else None
    e.product_id = product_id or "00000000-0000-0000-0000-000000000001"
    return e


def _stock(stock_type, qty, value):
    s = MagicMock()
    s.stock_type = stock_type
    s.qty = Decimal(str(qty))
    s.value = Decimal(str(value))
    return s


def _asset(monthly_depreciation):
    a = MagicMock()
    a.monthly_depreciation = Decimal(str(monthly_depreciation))
    return a


def _product(farm_cost):
    p = MagicMock()
    p.farm_cost = Decimal(str(farm_cost))
    return p


# ── Revenue tests ─────────────────────────────────────────────────────────────


class TestRevenue:
    def test_online_revenue_summed_correctly(self):
        entries = [
            _entry("sale", "1000", channel="online", pay_mode="razorpay"),
            _entry("sale", "500", channel="online", pay_mode="upi_manual"),
        ]
        r = calculate("2025-05", entries, [], [], {})
        assert r.rev_online == Decimal("1500")
        assert r.rev_offline == ZERO
        assert r.rev_total == Decimal("1500")

    def test_offline_revenue_summed_correctly(self):
        entries = [
            _entry("sale", "800", channel="offline", pay_mode="cash"),
            _entry("sale", "200", channel="offline", pay_mode="credit"),
        ]
        r = calculate("2025-05", entries, [], [], {})
        assert r.rev_offline == Decimal("1000")
        assert r.rev_total == Decimal("1000")

    def test_credit_sale_counted_in_revenue_not_cash(self):
        entries = [
            _entry("sale", "500", channel="online", pay_mode="razorpay"),
            _entry("sale", "300", channel="offline", pay_mode="credit"),
        ]
        r = calculate("2025-05", entries, [], [], {})
        assert r.rev_total == Decimal("800")  # accrual: both count
        assert r.rev_credit == Decimal("300")  # credit amount tracked
        assert r.cash_inflow == Decimal("500")  # only cash

    def test_cash_pl_gap_equals_credit_amount(self):
        entries = [_entry("sale", "400", channel="offline", pay_mode="credit")]
        r = calculate("2025-05", entries, [], [], {})
        assert r.cash_pl_gap == r.rev_credit

    def test_price_variance_summed(self):
        entries = [
            _entry("sale", "1050", channel="online", pay_mode="razorpay", price_variance="50"),
            _entry("sale", "980", channel="online", pay_mode="razorpay", price_variance="-20"),
        ]
        r = calculate("2025-05", entries, [], [], {})
        assert r.price_variance == Decimal("30")


# ── COGS tests ────────────────────────────────────────────────────────────────


class TestCOGS:
    def test_missing_opening_stock_adds_warning(self):
        r = calculate("2025-05", [], [], [], {})
        assert len(r.warnings) >= 1
        assert "Opening stock missing" in r.warnings[0]

    def test_opening_stock_from_monthly_stock_table(self):
        stocks = [_stock("opening", "100", "5000")]
        r = calculate("2025-05", [], stocks, [], {})
        assert r.cogs_opening == Decimal("5000")
        assert r.warnings == []  # no warning when opening stock present

    def test_closing_stock_reduces_cogs(self):
        stocks = [
            _stock("opening", "100", "5000"),
            _stock("closing", "50", "2500"),
        ]
        r = calculate("2025-05", [], stocks, [], {})
        assert r.cogs_closing == Decimal("2500")
        assert r.cogs_total == Decimal("2500")  # 5000 opening - 2500 closing

    def test_own_production_cost_uses_farm_cost_x_qty(self):
        pid = "00000000-0000-0000-0000-000000000001"
        products = {pid: _product(farm_cost="50")}
        entries = [
            _entry(
                "sale",
                "105",
                source="own",
                qty="2",
                product_id=pid,
                channel="online",
                pay_mode="razorpay",
            )
        ]
        r = calculate("2025-05", entries, [], [], products)
        assert r.cogs_own_prod == Decimal("100")  # 50 × 2

    def test_purchases_add_to_cogs(self):
        entries = [_entry("purchase", "3600")]
        r = calculate("2025-05", entries, [], [], {})
        assert r.cogs_purchased == Decimal("3600")

    def test_normal_loss_included_in_cogs(self):
        entries = [_entry("wastage_normal", "420")]
        r = calculate("2025-05", entries, [], [], {})
        assert r.cogs_norm_loss == Decimal("420")

    def test_abnormal_loss_not_in_cogs(self):
        entries = [_entry("wastage_abnormal", "350")]
        r = calculate("2025-05", entries, [], [], {})
        assert r.cogs_total == ZERO  # abnormal NOT in COGS
        assert r.abnormal_loss == Decimal("350")

    def test_consumption_in_cogs(self):
        entries = [_entry("consumption", "315")]
        r = calculate("2025-05", entries, [], [], {})
        assert r.cogs_consumed == Decimal("315")

    def test_cogs_total_formula(self):
        """COGS = opening + own + purchased + norm_loss + consumed - closing"""
        stocks = [
            _stock("opening", "100", "3000"),
            _stock("closing", "50", "1500"),
        ]
        entries = [
            _entry("purchase", "1800"),
            _entry("wastage_normal", "200"),
            _entry("consumption", "100"),
        ]
        r = calculate("2025-05", entries, stocks, [], {})
        expected = (
            Decimal("3000") + Decimal("1800") + Decimal("200") + Decimal("100") - Decimal("1500")
        )
        assert r.cogs_total == expected


# ── Gross profit tests ────────────────────────────────────────────────────────


class TestGrossProfit:
    def test_gross_profit_is_revenue_minus_cogs(self):
        entries = [_entry("sale", "5000", channel="online", pay_mode="razorpay")]
        stocks = [_stock("opening", "50", "2000"), _stock("closing", "20", "800")]
        r = calculate("2025-05", entries, stocks, [], {})
        assert r.gross_profit == r.rev_total - r.cogs_total

    def test_negative_gross_profit_possible(self):
        """Loss-making month should not crash."""
        entries = [_entry("sale", "100", channel="offline", pay_mode="cash")]
        stocks = [_stock("opening", "50", "5000")]
        r = calculate("2025-05", entries, stocks, [], {})
        assert r.gross_profit < ZERO


# ── OpEx + Net Profit tests ───────────────────────────────────────────────────


class TestOpExAndNetProfit:
    def test_depreciation_from_assets(self):
        assets = [_asset("100"), _asset("83.33333")]
        r = calculate("2025-05", [], [], assets, {})
        assert r.opex_deprec == Decimal("183.33333")

    def test_fixed_cost_entries_in_opex(self):
        entries = [_entry("fixed_cost", "1200")]
        r = calculate("2025-05", entries, [], [], {})
        assert r.opex_fixed == Decimal("1200")

    def test_provisions_in_opex(self):
        entries = [_entry("provision", "500")]
        r = calculate("2025-05", entries, [], [], {})
        assert r.opex_provisions == Decimal("500")

    def test_opex_total_is_sum(self):
        entries = [_entry("fixed_cost", "1200"), _entry("provision", "100")]
        assets = [_asset("83.33333")]
        r = calculate("2025-05", entries, [], assets, {})
        assert r.opex_total == Decimal("1200") + Decimal("100") + Decimal("83.33333")

    def test_net_profit_formula(self):
        entries = [
            _entry("sale", "10000", channel="online", pay_mode="razorpay"),
            _entry("fixed_cost", "1200"),
        ]
        assets = [_asset("100")]
        r = calculate("2025-05", entries, [], assets, {})
        assert r.net_profit == r.gross_profit - r.abnormal_loss - r.opex_total

    def test_net_margin_pct_correct(self):
        entries = [_entry("sale", "10000", channel="online", pay_mode="razorpay")]
        r = calculate("2025-05", entries, [], [], {})
        # With zero costs, net profit = revenue, margin = 100%
        assert r.net_margin_pct == Decimal("100")

    def test_zero_revenue_no_division_error(self):
        """Zero revenue must not cause ZeroDivisionError."""
        r = calculate("2025-05", [], [], [], {})
        assert r.net_margin_pct == ZERO


# ── Return type tests ─────────────────────────────────────────────────────────


class TestReturnTypes:
    def test_all_fields_are_decimal(self):
        entries = [_entry("sale", "1000", channel="online", pay_mode="razorpay")]
        assets = [_asset("50")]
        r = calculate("2025-05", entries, [], assets, {})
        for field_name, val in r.__dict__.items():
            if field_name in ("month", "from_cache", "warnings"):
                continue
            assert isinstance(val, Decimal), (
                f"Field '{field_name}' is {type(val)}, expected Decimal"
            )

    def test_to_dict_all_values_are_strings(self):
        entries = [_entry("sale", "1000", channel="online", pay_mode="razorpay")]
        r = calculate("2025-05", entries, [], [], {})
        d = r.to_dict()
        skip = {"month", "from_cache", "warnings"}
        for k, v in d.items():
            if k in skip:
                continue
            assert isinstance(v, str), f"Key '{k}' is {type(v)}, expected str"

    def test_to_dict_values_have_5dp(self):
        entries = [_entry("sale", "1000.5", channel="online", pay_mode="razorpay")]
        r = calculate("2025-05", entries, [], [], {})
        d = r.to_dict()
        assert "." in d["rev_total"]
        assert len(d["rev_total"].split(".")[1]) == 5
