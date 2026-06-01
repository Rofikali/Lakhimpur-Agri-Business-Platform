# Business Context

## Why this exists

A solo farmer-entrepreneur in Lakhimpur district, Assam grows premium rice
varieties (Joha, Bora Saul, Kali Jeera) and makes traditional Assamese petha
(Narikal and Septa). The business was entirely offline — WhatsApp orders, cash
payments, no cost tracking, no P&L visibility.

This platform gives the business:
- A public shop that customers can browse and pay via UPI
- An owner dashboard with real-time inventory, orders, and accurate profit/loss
- Proper CA/MBA-grade cost accounting (not just revenue tracking)

---

## Products

| Product | Category | Unit | Farm cost | Sell price | Margin |
|---|---|---|---|---|---|
| Joha Rice | rice | kg | ₹50/kg (own farm) | ₹105/kg | ~38% |
| Bora Saul | rice | kg | ₹50/kg (own farm) | ₹90/kg | ~28% |
| Kali Jeera | rice | kg | ₹50/kg (own farm) | ₹110/kg | ~40% |
| Narikal Petha | petha | piece | ~₹29.50 | ₹70 | ~58% |
| Septa Petha | petha | piece | ~₹25.00 | ₹60 | ~58% |

**Excluded from platform:** hen/cock (offline only), tea stall (offline anchor).

---

## Pricing principle

Online price = Offline price. No channel price discrimination.
Customers who walk to the stall pay the same as those who order online.

---

## Cost model — CA/MBA framework

Every rupee of cost is tracked across four layers:

```
true_cost = farm_cost + labor_cost + overhead_cost + packaging_cost
            + normal_loss_absorption
```

### Layer 1 — Farm cost
Raw material cost per unit. For own-farm rice: cost of cultivating 1 kg dhan,
milling it to chawl, accounting for normal milling loss (33% for most rice
varieties). For petha: ingredient cost per piece.

### Layer 2 — Labor cost
Direct labor per unit. Milling labor, packaging labor, petha-making labor.

### Layer 3 — Overhead cost
Fuel, utilities, stall electricity. Allocated per unit.

### Layer 4 — Packaging cost
Bag, sticker, string per unit.

### Normal loss absorption
Milling loss (dhan → chawl conversion loses ~33-35%) is a **normal loss** —
absorbed into the cost of good output, not treated as a P&L expense.

```
loss_absorb = farm_cost × (loss% / (1 − loss%))

Example: farm_cost=50, loss%=33%
loss_absorb = 50 × (0.33 / 0.67) = ₹24.63/kg
```

### Abnormal loss
Petha batch expiry with unsold pieces, crop failure, pest damage.
Treated as a **separate P&L line below gross profit** — not absorbed into product cost.

---

## P&L structure

```
Revenue (accrual basis)
  + Online sales
  + Offline sales
  ─────────────────
  = Total Revenue

COGS
  + Opening stock value
  + Own production cost  (farm_cost × qty sold)
  + External purchases
  + Normal milling loss  (absorbed)
  + Consumption          (own use at market price)
  − Closing stock value
  ─────────────────────
  = Total COGS

Gross Profit = Revenue − COGS

  − Abnormal loss        (expiry, crop failure)
  ─────────────────────
  = Adjusted Gross Profit

Operating Expenses
  − Fixed costs          (stall rent, fuel, transport)
  − Owner salary         (drawing — a cost, not hidden profit)
  − Depreciation         (assets / useful life months)
  ─────────────────────
  = Net Profit

Cash Flow Reconciliation
  Net cash flow = cash_inflow − cash_outflow − capex
  Cash−P&L gap  = credit sales outstanding
```

### Working capital interest
Every rupee locked in inventory has an opportunity cost.
At 12% annual rate, 500 kg of Joha Rice worth ₹34,250 held for 45 days:
```
WC cost = ₹34,250 × 0.12 / 365 × 45 = ₹507.29
```
This appears as a provision in P&L.

---

## Business model

| Channel | Volume | Payment | Notes |
|---|---|---|---|
| Online (WhatsApp link → shop) | ~60% | Razorpay UPI | Pickup or delivery |
| Offline (stall walk-in) | ~30% | Cash / UPI | Logged manually by owner |
| Credit (local shops, regulars) | ~10% | Collect later | Outstanding tracked separately |

---

## Scale constraints (current)

- Single district: Lakhimpur only
- Single owner: no staff logins needed
- ~10-30 orders/day peak
- ~5 product SKUs
- ~2-3 petha batches/week
- ~2-3 farm seasons/year