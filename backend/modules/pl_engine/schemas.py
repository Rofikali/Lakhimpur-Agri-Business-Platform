
from pydantic import BaseModel


class PLResponse(BaseModel):
    month: str
    from_cache: bool
    warnings: list[str]

    rev_online: str
    rev_offline: str
    rev_credit: str
    rev_total: str

    cogs_opening: str
    cogs_own_prod: str
    cogs_purchased: str
    cogs_norm_loss: str
    cogs_consumed: str
    cogs_closing: str
    cogs_total: str

    gross_profit: str
    abnormal_loss: str

    opex_fixed: str
    opex_deprec: str
    opex_provisions: str
    opex_total: str

    net_profit: str
    net_margin_pct: str

    cash_inflow: str
    cash_outflow: str
    net_cash_flow: str
    cash_pl_gap: str

    price_variance: str
    cost_variance: str


class BreakevenResponse(BaseModel):
    product_id: str
    product_name: str
    sell_price: str
    variable_cost: str
    contribution_margin: str
    fixed_costs_monthly: str
    breakeven_qty: str
    breakeven_revenue: str
