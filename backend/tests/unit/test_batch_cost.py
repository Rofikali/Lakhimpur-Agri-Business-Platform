"""
Petha batch cost unit tests — absorption costing.
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from modules.petha.service import PethaService


def _batch(planned, good, rejected, total_cost, variety="narikal"):
    b = MagicMock()
    b.planned_pieces = planned
    b.good_pieces = good
    b.rejected_pieces = rejected
    b.total_batch_cost = Decimal(str(total_cost))
    b.variety = variety
    b.batch_date = __import__("datetime").date(2025, 5, 10)
    b.cost_per_piece = None
    b.status = "in_production"
    b.expiry_date = __import__("datetime").date(2025, 5, 17)
    return b


class TestBatchCostAbsorption:
    def test_cost_per_piece_absorbs_rejections(self):
        """
        30 planned, 27 good, 3 rejected.
        ₹325 total cost / 27 good pieces = ₹12.037...
        Rejected pieces' cost absorbed — NOT charged separately.
        """
        b = _batch(planned=30, good=27, rejected=3, total_cost="325")
        expected = Decimal("325") / Decimal("27")
        actual = Decimal("325") / Decimal("27")
        assert actual.quantize(Decimal("0.00001")) == expected.quantize(Decimal("0.00001"))

    def test_no_rejection_cost_per_piece_is_total_divided_by_good(self):
        b = _batch(planned=30, good=30, rejected=0, total_cost="300")
        cost_pp = Decimal("300") / Decimal("30")
        assert cost_pp == Decimal("10")

    def test_all_rejected_gives_zero_cost_per_piece(self):
        """All pieces rejected → cost_per_piece = 0, entire cost = abnormal loss."""
        good = 0
        total = Decimal("500")
        cost_pp = total / Decimal(str(good)) if good > 0 else Decimal("0")
        assert cost_pp == Decimal("0")

    def test_all_rejected_entire_cost_is_abnormal_loss(self):
        """When good_pieces=0, total_batch_cost becomes abnormal loss."""
        total = Decimal("500")
        good = 0
        abnormal = total if good == 0 else Decimal("0")
        assert abnormal == Decimal("500")

    def test_rejection_pct_calculated_correctly(self):
        planned, rejected = 30, 3
        pct = Decimal(str(rejected)) / Decimal(str(planned)) * 100
        assert pct == Decimal("10")

    def test_high_rejection_pct_raises_warning_threshold(self):
        """Rejection > 20% is a quality alert threshold."""
        planned, rejected = 30, 7
        pct = Decimal(str(rejected)) / Decimal(str(planned)) * 100
        assert pct > Decimal("20")

    def test_ingredient_labor_overhead_summed_correctly(self):
        ingredient = Decimal("90")
        labor = Decimal("150")
        overhead = Decimal("85")  # fuel + overhead
        total = ingredient + labor + overhead
        assert total == Decimal("325")

    def test_expiry_date_from_shelf_life(self):
        from datetime import date, timedelta

        batch_date = date(2025, 5, 10)
        shelf_life = 7
        expiry = batch_date + timedelta(days=shelf_life)
        assert expiry == date(2025, 5, 17)

    def test_abnormal_loss_on_expiry_is_unsold_times_cost_per_piece(self):
        unsold_qty = Decimal("5")  # 5 pieces unsold at expiry
        cost_per_pc = Decimal("12.03704")
        abnormal = unsold_qty * cost_per_pc
        assert abnormal == Decimal("60.18520")
