"""
Farm milling yield and cost calculation unit tests.
"""

from decimal import Decimal


def calc_milling(
    dhan_sent,
    chawl_received,
    husk_kg,
    bran_kg,
    broken_kg,
    husk_price,
    bran_price,
    broken_price,
    milling_charges,
    cultivation_cost,
):
    """Replicate milling calculation from FarmService."""
    ZERO = Decimal("0")
    dhan = Decimal(str(dhan_sent))
    chawl = Decimal(str(chawl_received))
    milling = Decimal(str(milling_charges))
    farm_cost = Decimal(str(cultivation_cost))

    yield_pct = chawl / dhan * 100 if dhan > ZERO else ZERO
    byproduct = (
        Decimal(str(husk_kg)) * Decimal(str(husk_price))
        + Decimal(str(bran_kg)) * Decimal(str(bran_price))
        + Decimal(str(broken_kg)) * Decimal(str(broken_price))
    )
    total_cost = farm_cost + milling
    net_cost = total_cost - byproduct
    cost_per_kg = net_cost / chawl if chawl > ZERO else ZERO
    transfer_price = cost_per_kg * Decimal("1.12")
    return {
        "yield_pct": yield_pct,
        "byproduct": byproduct,
        "cost_per_kg_chawl": cost_per_kg,
        "transfer_price": transfer_price,
    }


class TestMillingYield:
    def test_yield_percentage_correct(self):
        r = calc_milling(
            dhan_sent=1200,
            chawl_received=780,
            husk_kg=240,
            bran_kg=96,
            broken_kg=24,
            husk_price=2,
            bran_price=18,
            broken_price=30,
            milling_charges=1800,
            cultivation_cost=40000,
        )
        assert r["yield_pct"].quantize(Decimal("0.01")) == Decimal("65.00")

    def test_byproduct_revenue_calculated_correctly(self):
        r = calc_milling(
            dhan_sent=1200,
            chawl_received=780,
            husk_kg=240,
            bran_kg=96,
            broken_kg=24,
            husk_price=2,
            bran_price=18,
            broken_price=30,
            milling_charges=1800,
            cultivation_cost=40000,
        )
        # 240×2 + 96×18 + 24×30 = 480 + 1728 + 720 = 2928
        assert r["byproduct"] == Decimal("2928")

    def test_byproduct_credited_against_cost(self):
        """By-product revenue REDUCES effective cost of chawl."""
        r_with_byproduct = calc_milling(1200, 780, 240, 96, 24, 2, 18, 30, 1800, 40000)
        r_no_byproduct = calc_milling(1200, 780, 0, 0, 0, 0, 0, 0, 1800, 40000)
        assert r_with_byproduct["cost_per_kg_chawl"] < r_no_byproduct["cost_per_kg_chawl"]

    def test_transfer_price_is_cost_plus_12_percent(self):
        r = calc_milling(1200, 780, 240, 96, 24, 2, 18, 30, 1800, 40000)
        expected = r["cost_per_kg_chawl"] * Decimal("1.12")
        assert abs(r["transfer_price"] - expected) < Decimal("0.00001")

    def test_zero_chawl_no_division_error(self):
        r = calc_milling(
            dhan_sent=1200,
            chawl_received=0,
            husk_kg=0,
            bran_kg=0,
            broken_kg=0,
            husk_price=0,
            bran_price=0,
            broken_price=0,
            milling_charges=0,
            cultivation_cost=40000,
        )
        assert r["cost_per_kg_chawl"] == Decimal("0")

    def test_normal_loss_is_dhan_minus_chawl(self):
        """Normal loss = dhan sent - chawl received (absorbed into cost)."""
        dhan, chawl = Decimal("1200"), Decimal("780")
        normal_loss_kg = dhan - chawl
        assert normal_loss_kg == Decimal("420")


# ── true_cost calculation tests ────────────────────────────────────────────────


class TestTrueCost:
    """Test the normal loss absorption formula in products service."""

    def _calc(self, farm, labor, overhead, packaging, loss_pct):
        from modules.products.service import _calculate_true_cost

        return _calculate_true_cost(
            Decimal(str(farm)),
            Decimal(str(labor)),
            Decimal(str(overhead)),
            Decimal(str(packaging)),
            Decimal(str(loss_pct)),
        )

    def test_zero_loss_no_absorption(self):
        cost = self._calc(farm=50, labor=5, overhead=3, packaging=7, loss_pct=0)
        assert cost == Decimal("65")

    def test_33_pct_loss_absorbed_correctly(self):
        """
        33% loss: to get 1kg chawl, need 1/(1-0.33) = 1.4925kg dhan.
        Loss absorb = 50 × (0.33 / 0.67) = 24.626...
        true_cost ≈ 50 + 24.626 + 5 + 3 + 7 = 89.626...
        """
        cost = self._calc(farm=50, labor=5, overhead=3, packaging=7, loss_pct=33)
        assert cost > Decimal("65")  # more than without loss
        assert cost > Decimal("85")  # significant absorption

    def test_zero_farm_cost_no_loss_absorption(self):
        """If farm_cost=0, loss absorption = 0 regardless of loss%."""
        cost = self._calc(farm=0, labor=10, overhead=5, packaging=3, loss_pct=50)
        assert cost == Decimal("18")

    def test_true_cost_always_decimal(self):
        cost = self._calc(farm=50, labor=5, overhead=3, packaging=7, loss_pct=33)
        assert isinstance(cost, Decimal)
