"""
P&L Calculator — pure function, no DB.
All arithmetic: Python Decimal — never float.
Called by PLService after data is fetched.
"""

from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from typing import Any


DP5 = Decimal("0.00001")
ZERO = Decimal("0.00000")


@dataclass
class PLResult:
    month: str
    from_cache: bool = False
    warnings: list[str] = field(default_factory=list)

    rev_online: Decimal = ZERO
    rev_offline: Decimal = ZERO
    rev_credit: Decimal = ZERO
    rev_total: Decimal = ZERO

    cogs_opening: Decimal = ZERO
    cogs_own_prod: Decimal = ZERO
    cogs_purchased: Decimal = ZERO
    cogs_norm_loss: Decimal = ZERO
    cogs_consumed: Decimal = ZERO
    cogs_closing: Decimal = ZERO
    cogs_total: Decimal = ZERO

    gross_profit: Decimal = ZERO
    abnormal_loss: Decimal = ZERO

    opex_fixed: Decimal = ZERO
    opex_deprec: Decimal = ZERO
    opex_provisions: Decimal = ZERO
    opex_total: Decimal = ZERO

    net_profit: Decimal = ZERO
    net_margin_pct: Decimal = ZERO

    cash_inflow: Decimal = ZERO
    cash_outflow: Decimal = ZERO
    net_cash_flow: Decimal = ZERO
    cash_pl_gap: Decimal = ZERO

    price_variance: Decimal = ZERO
    cost_variance: Decimal = ZERO

    def to_dict(self) -> dict:
        def s(v):
            return str(v.quantize(DP5, ROUND_HALF_UP))

        return {
            "month": self.month,
            "from_cache": self.from_cache,
            "warnings": self.warnings,
            "rev_online": s(self.rev_online),
            "rev_offline": s(self.rev_offline),
            "rev_credit": s(self.rev_credit),
            "rev_total": s(self.rev_total),
            "cogs_opening": s(self.cogs_opening),
            "cogs_own_prod": s(self.cogs_own_prod),
            "cogs_purchased": s(self.cogs_purchased),
            "cogs_norm_loss": s(self.cogs_norm_loss),
            "cogs_consumed": s(self.cogs_consumed),
            "cogs_closing": s(self.cogs_closing),
            "cogs_total": s(self.cogs_total),
            "gross_profit": s(self.gross_profit),
            "abnormal_loss": s(self.abnormal_loss),
            "opex_fixed": s(self.opex_fixed),
            "opex_deprec": s(self.opex_deprec),
            "opex_provisions": s(self.opex_provisions),
            "opex_total": s(self.opex_total),
            "net_profit": s(self.net_profit),
            "net_margin_pct": s(self.net_margin_pct),
            "cash_inflow": s(self.cash_inflow),
            "cash_outflow": s(self.cash_outflow),
            "net_cash_flow": s(self.net_cash_flow),
            "cash_pl_gap": s(self.cash_pl_gap),
            "price_variance": s(self.price_variance),
            "cost_variance": s(self.cost_variance),
        }


def calculate(
    month: str,
    entries: list,  # StockEntry rows
    monthly_stk: list,  # MonthlyStock rows
    assets: list,  # Asset rows
    products: dict,  # {product_id: Product}
    from_cache: bool = False,
) -> PLResult:
    r = PLResult(month=month, from_cache=from_cache)

    def _sum(rows, key="total_amount") -> Decimal:
        return sum((getattr(e, key) or ZERO for e in rows), ZERO)

    # ── Revenue ────────────────────────────────────────────────────────────
    sales = [e for e in entries if e.entry_type == "sale"]
    online = [e for e in sales if e.channel == "online"]
    offline = [e for e in sales if e.channel == "offline"]
    credit = [e for e in sales if e.pay_mode == "credit"]
    cash_s = [e for e in sales if e.pay_mode != "credit"]

    r.rev_online = _sum(online)
    r.rev_offline = _sum(offline)
    r.rev_credit = _sum(credit)
    r.rev_total = r.rev_online + r.rev_offline

    # Price variance
    r.price_variance = sum(
        (e.price_variance or ZERO for e in sales if e.price_variance is not None), ZERO
    )

    # ── COGS ───────────────────────────────────────────────────────────────
    # Opening stock
    r.cogs_opening = sum((ms.value for ms in monthly_stk if ms.stock_type == "opening"), ZERO)
    if not any(ms.stock_type == "opening" for ms in monthly_stk):
        r.warnings.append("Opening stock missing — COGS and net profit are inaccurate")

    # Own production cost: own-source sales × product.farm_cost
    own_sales = [e for e in sales if e.source == "own"]
    for e in own_sales:
        p = products.get(str(e.product_id))
        if p:
            r.cogs_own_prod += (p.farm_cost or ZERO) * (e.qty or ZERO)

    # External purchases
    purchases = [e for e in entries if e.entry_type == "purchase"]
    r.cogs_purchased = _sum(purchases)

    # Cost variance
    r.cost_variance = sum(
        (e.cost_variance or ZERO for e in purchases if e.cost_variance is not None), ZERO
    )

    # Normal loss absorbed
    r.cogs_norm_loss = _sum([e for e in entries if e.entry_type == "wastage_normal"])

    # Own consumption at market value
    r.cogs_consumed = _sum([e for e in entries if e.entry_type == "consumption"])

    # Closing stock
    r.cogs_closing = sum((ms.value for ms in monthly_stk if ms.stock_type == "closing"), ZERO)

    r.cogs_total = (
        r.cogs_opening
        + r.cogs_own_prod
        + r.cogs_purchased
        + r.cogs_norm_loss
        + r.cogs_consumed
        - r.cogs_closing
    )

    r.gross_profit = r.rev_total - r.cogs_total

    # ── Abnormal loss ──────────────────────────────────────────────────────
    r.abnormal_loss = _sum([e for e in entries if e.entry_type == "wastage_abnormal"])

    # ── Operating expenses ─────────────────────────────────────────────────
    r.opex_fixed = _sum([e for e in entries if e.entry_type == "fixed_cost"])
    r.opex_provisions = _sum([e for e in entries if e.entry_type == "provision"])
    r.opex_deprec = sum((a.monthly_depreciation for a in assets), ZERO)
    r.opex_total = r.opex_fixed + r.opex_provisions + r.opex_deprec

    # ── Net profit ─────────────────────────────────────────────────────────
    r.net_profit = r.gross_profit - r.abnormal_loss - r.opex_total
    if r.rev_total > ZERO:
        r.net_margin_pct = r.net_profit / r.rev_total * Decimal("100")

    # ── Cash flow ──────────────────────────────────────────────────────────
    r.cash_inflow = _sum(cash_s)
    r.cash_outflow = _sum(purchases) + _sum([e for e in entries if e.entry_type == "fixed_cost"])
    capex_out = _sum([e for e in entries if e.entry_type == "capex"])
    r.net_cash_flow = r.cash_inflow - r.cash_outflow - capex_out
    r.cash_pl_gap = r.rev_credit  # credit sales counted in P&L but not cash

    return r
