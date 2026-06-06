# Governance

## Code standards

### Python — enforced by ruff + black + mypy

```toml
# pyproject.toml — non-negotiable rules

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "F",    # pyflakes (unused imports, undefined names)
    "I",    # isort (import order)
    "N",    # pep8-naming
    "UP",   # pyupgrade (modern Python syntax)
    "B",    # flake8-bugbear (common bugs)
    "SIM",  # flake8-simplify
]

[tool.black]
line-length = 100
target-version = ["py312"]
```

**Enforced automatically:**
- `make format` — auto-fix before committing
- `make lint` — fail CI if any issue remains
- pre-commit hooks block commits that don't pass lint

### Naming conventions

```python
# Files: snake_case
modules/pl_engine/calculator.py

# Classes: PascalCase
class OrderService:
class ProductRepository:
class StockInsufficientError(AppException):

# Functions and variables: snake_case
async def create_order(self, data, bg_tasks):
current_qty = stock.current_qty

# Constants: UPPER_SNAKE_CASE
MARKUP_PCT = Decimal("0.12")
DP5 = Decimal("0.00001")

# Private helpers: leading underscore
def _calculate_true_cost(...):
def _next_order_number(self):

# Type aliases: UPPER_SNAKE_CASE
MONEY = Numeric(precision=15, scale=5)
QTY   = Numeric(precision=10, scale=3)
```

### TypeScript / Vue — enforced by ESLint + TypeScript strict

```json
// tsconfig.json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true
  }
}
```

---

## Money rules — never negotiate these

These are non-negotiable. Breaking them corrupts financial records.

```
RULE 1: Never use float for money. Use Decimal (Python) or string (JSON).
RULE 2: All money columns in DB are NUMERIC(15,5). Never FLOAT or DOUBLE.
RULE 3: All money in JSON API responses are strings. Never number/float.
RULE 4: All money in Pinia stores are strings. Parse to display only.
RULE 5: Only the MoneyDisplay.vue component converts string → display format.
RULE 6: All money calculations use Python Decimal on the backend. Never JS Number.
RULE 7: Pydantic validators on all money input fields reject float with ValueError.
```

**Violation detection:**

```bash
# Search for float money usage in Python
grep -r "float(.*price\|float(.*cost\|float(.*amount" backend/

# Search for number money in JSON responses
# (money fields should always have "" quotes in API tests)
```

---

## Git workflow

### Branch strategy

```
main          ← production-ready, protected, CI must pass
staging       ← staging environment, merges from feature branches
feature/*     ← new features, one per feature
fix/*         ← bug fixes
hotfix/*      ← urgent production fixes (merge directly to main + staging)
docs/*        ← documentation only changes
```

### Commit message convention (Conventional Commits)

```
type(scope): short description

Types:
  feat      New feature
  fix       Bug fix
  docs      Documentation only
  refactor  Code change, no feature/fix
  test      Tests only
  chore     Build, deps, config
  perf      Performance improvement

Examples:
  feat(orders): add offline order creation
  fix(pl): correct normal loss absorption formula
  fix(db): correct DATABASE_URL scheme to asyncpg
  docs(api): add webhook endpoint documentation
  test(orders): add duplicate webhook idempotency test
  chore(deps): upgrade FastAPI to 0.111.0
  refactor(inventory): extract variance calculation to helper

Scope = module name: orders, products, inventory, pl, farm, petha, auth, etc.
```

### Pull request rules

```
Before opening a PR:
  ✅ make format  (no lint errors)
  ✅ make test-cov  (coverage ≥ 75%)
  ✅ make typecheck  (no mypy errors)
  ✅ Self-reviewed the diff

PR description must include:
  - What changed and why
  - How to test it
  - Any DB migration included?
  - Any env var changes?

PR merge rules:
  - CI must pass (all checks green)
  - No direct push to main
  - Squash merge preferred for feature branches
```

---

## Code review checklist

When reviewing any PR, check each category:

### Financial correctness
```
☐ Money values use Decimal, not float
☐ NUMERIC(15,5) in any new DB columns that store money
☐ Pydantic validators reject float on money inputs
☐ API responses return money as strings
☐ P&L formula changes have corresponding unit test
☐ Stock movement properly creates a stock_entry row
```

### Data integrity
```
☐ Soft delete used (deleted_at), never DELETE on financial tables
☐ Idempotency key present on all mutation endpoints
☐ FK constraints correct in migrations
☐ No N+1 queries (selectinload used for relationships)
☐ Atomic transactions for multi-step operations
```

### Security
```
☐ Auth dependency (require_owner) on all owner-only routes
☐ No secrets in code or logs
☐ Phone numbers masked in logs
☐ New endpoints have rate limiting if needed
☐ Input validation present (Pydantic schema)
```

### Testing
```
☐ New feature has unit tests
☐ New API endpoint has integration test
☐ Edge cases covered (empty input, zero stock, zero pieces)
☐ Test coverage not reduced
```

---

## Release process

### Deploy to staging

```bash
git checkout staging
git merge feature/my-feature
git push origin staging
# GitHub Actions CI runs automatically
# If green → auto-deploys to Railway (staging) + Vercel (preview)
# Run smoke tests: make smoke-staging
```

### Deploy to production

```bash
# Staging must be green and smoke-tested first
git checkout main
git merge staging
git push origin main
# GitHub Actions CI + deploy runs
# Monitor Railway logs for 10 minutes after deploy
# Monitor Sentry for new errors
```

### Rollback procedure

```bash
# If production deploy is broken:

# Option 1: Revert commit (preferred)
git revert HEAD
git push origin main
# CI will re-deploy with reverted code

# Option 2: Railway redeploy previous version
# Railway Dashboard → Deployments → Previous → Redeploy

# If DB migration caused the issue:
railway run alembic downgrade -1
# Then rollback code
```

---

## Financial compliance

### What constitutes a financial record
These must never be deleted, always have `created_at`, and must be immutable:

- `stock_entries` — every stock movement
- `orders` + `order_items` + `payments` — every transaction
- `farm_seasons` + `farm_inputs` + `farm_millings` — cost of goods
- `petha_batches` + `petha_batch_costs` — manufacturing costs
- `fixed_costs` (history) — period expenses
- `assets` — depreciation register
- `monthly_stock` — opening/closing stock for COGS

### Correction procedure
**Never edit a financial record.** If an entry was wrong:

```python
# ❌ Wrong — edit existing entry
entry.total_amount = Decimal("1500")
await db.flush()

# ✅ Correct — reverse + new entry
await service.add_stock_entry(StockEntryCreate(
    idempotency_key=uuid4(),
    product_id=original.product_id,
    entry_type=original.entry_type,
    qty=original.qty,
    total_amount=-original.total_amount,   # negative = reversal
    note=f"Reversal of entry {original.id} — incorrect amount",
    date=date.today(),
))
# Then add the correct entry
```

### GST / Income Tax readiness

```
Monthly close checklist (run at month end):
  ☐ Record opening stock for all products
  ☐ Verify all purchases have correct invoices and amounts
  ☐ Record closing stock (physical count)
  ☐ Verify P&L shows expected figures
  ☐ Download P&L report as PDF (Dashboard → Reports → P&L → Export)
  ☐ Archive to Google Drive / local backup

Annual:
  ☐ Full year P&L export
  ☐ Asset register (assets table) exported
  ☐ All stock_entries for the year exported (for CA)
  ☐ PostgreSQL dump taken (pg_dump) and stored offline
```

### Data retention enforcement

```bash
# Check for any accidental hard deletes (should return 0)
psql -U postgres lakhimpur_dev -c "
SELECT COUNT(*) FROM stock_entries WHERE deleted_at IS NOT NULL;
"
# deleted_at should be NULL for all entries — soft delete only

# Monthly backup
pg_dump -U postgres lakhimpur_dev | gzip > backup_$(date +%Y%m).sql.gz
# Store on Cloudflare R2 or external drive — minimum 7 years
```

---

## Incident response

### Severity levels

| Level | Definition | Response time | Example |
|---|---|---|---|
| P0 | Site completely down | 15 min | Database unreachable, all requests failing |
| P1 | Critical feature broken | 1 hour | Payments not processing, orders not saving |
| P2 | Important feature degraded | 4 hours | P&L cache broken, notifications failing |
| P3 | Minor issue | Next business day | Slow page load, missing image |

### P0 runbook

```bash
# 1. Check Railway status
open https://railway.app/status

# 2. Check health endpoints
curl https://your-api.railway.app/health
curl https://your-api.railway.app/health/ready

# 3. Check Railway logs for last 50 lines
railway logs --tail 50

# 4. Check Sentry for errors
open https://sentry.io/your-org/lakhimpur-production/

# 5. If DB issue — check PostgreSQL
railway run psql -c "SELECT 1;"

# 6. If Redis issue — restart Redis on Railway
# Railway Dashboard → Redis service → Restart

# 7. If code issue — rollback
git revert HEAD && git push origin main

# 8. Notify customers if > 30 min outage
# Update WhatsApp status: "Temporary maintenance. Back in 30 min."
```

---

## Dependency management

### Adding a new package

```bash
# Production dependency
cd backend && uv add package-name
# Updates pyproject.toml [dependencies] + uv.lock

# Dev dependency
cd backend && uv add --dev package-name
# Updates pyproject.toml [dependency-groups.dev] + uv.lock

# Always commit both pyproject.toml and uv.lock
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore(deps): add package-name"
```

### Upgrading packages

```bash
# Upgrade specific package
cd backend && uv add package-name@latest

# Upgrade all (careful — review changes)
cd backend && uv lock --upgrade
make test-cov   # must pass before committing

# Check for security vulnerabilities
cd backend && uv run pip-audit
```

### Pinning policy

All packages are pinned in `uv.lock` with exact hashes.
`pyproject.toml` uses `>=` version constraints (minimum supported).
`uv.lock` pins exact versions used in CI and production.

```toml
# pyproject.toml — minimum version
"fastapi>=0.111.0"

# uv.lock — exact version (auto-managed)
# fastapi==0.111.1
# (plus all transitive dependencies pinned)
```