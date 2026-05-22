aily dev workflow

# Morning — start working

    make up             # start all services
    make logs           # check everything is healthy

# During development

# Edit backend files → uvicorn auto-reloads

# Edit frontend files → Nuxt HMR updates browser

# Before committing

    make lint           # must pass
    make test-unit      # fast — run often
    git add . && git commit -m "feat: add petha batch expiry alert"

# pre-commit hooks run automatically

# Adding a new DB column (never drop columns)

    make generate-migration MSG="add product description field"

# Review the generated file in migrations/versions/

    make migrate

# Full test before pushing to main

    make test-cov

# End of day

    make down           # stop all services (data persists in ./data/)

### Add New Package Production Only Dependency

    uv sync --no-dev ( Production Only )
    uv add fastapi-users

### Add New Package Dev Only Dependency

    uv add --dev pytest-xdist

### Update Packages

    uv lock --upgrade

    or:

    uv sync --upgrade

## Install packeges 
    pacman -Syu --noconfirm

    pacman -S --noconfirm \
    python \
    python-pip \
    nodejs \
    npm \
    postgresql \
    redis \
    git \
    base-devel \
    curl

sudo pacman -S less
sudo pacman -S git-lfs
git lfs install

### install Docker
    pacman -Syu --noconfirm
    pacman -S --noconfirm docker docker-compose


## Install redis 
    pacman -S redis

    
## Run FastApi
    uv run uvicorn main:app --reload


## Running tests — all commands

# ── From repo root ─────────────────────────────────────────────────────────

# Start test DB (uses same docker-compose, separate DB name)
# Already set in docker-compose.yml — lakhimpur_test DB auto-created

# ── Unit tests only (fast, no DB, ~5 seconds) ──────────────────────────────
make test-unit
# or directly:
docker compose exec backend pytest tests/unit/ -v --tb=short

# ── Integration tests only ─────────────────────────────────────────────────
docker compose exec backend pytest tests/integration/ -v --tb=short

# ── All tests with coverage ────────────────────────────────────────────────
make test-cov
# or directly:
docker compose exec backend pytest tests/ \
  --cov=. \
  --cov-report=term-missing \
  --cov-report=html \
  --cov-fail-under=75 \
  -v

# ── P&L engine must hit 95% (enforced separately) ─────────────────────────
docker compose exec backend pytest tests/unit/test_pl_calculator.py \
  --cov=modules/pl_engine/calculator.py \
  --cov-fail-under=95 \
  -v

# ── Run a specific test ────────────────────────────────────────────────────
docker compose exec backend pytest tests/unit/test_pl_calculator.py::TestRevenue -v
docker compose exec backend pytest tests/integration/test_orders.py::TestOrderCreate::test_oversell_rejected -v

# ── Run tests matching a keyword ──────────────────────────────────────────
docker compose exec backend pytest -k "webhook" -v
docker compose exec backend pytest -k "float" -v

# ── Show slowest tests ──────────────────────────────────────────────────────
docker compose exec backend pytest tests/ --durations=10

# ── Stop on first failure (during active development) ─────────────────────
docker compose exec backend pytest tests/ -x --tb=long

# ── Run without capturing stdout (see print statements) ───────────────────
docker compose exec backend pytest tests/ -s -v

## Stage 7 complete — checklist
Unit tests:
  ✅ P&L calculator — full coverage (revenue, COGS, opex, net, margin)
  ✅ Batch cost absorption — rejection absorbed into good pieces
  ✅ Milling yield — byproduct credit, cost_per_kg_chawl, transfer price
  ✅ true_cost calculation — normal loss absorption formula
  ✅ Pydantic schema validation — float rejected everywhere

Integration tests:
  ✅ Auth — login, logout, JWT blocklist, protected routes
  ✅ Products — CRUD, true_cost, soft delete, public vs owner
  ✅ Inventory — stock entry, variance, idempotency, float rejection
  ✅ Orders — offline confirm, online pending, oversell, cancel+restore
  ✅ Orders — idempotency, invalid transitions, snapshot price
  ✅ Payments — webhook HMAC, confirm+decrement, duplicate idempotency
  ✅ Payments — mark paid (offline), outstanding credits
  ✅ P&L API — all fields present, strings not floats, formula correct
  ✅ P&L API — credit sale in revenue not cash, cash_pl_gap
  ✅ Farm — season lifecycle, milling yield, cannot mill before harvest
  ✅ Petha — batch create, outcome, absorption costing
  ✅ Notify — fire-and-forget, WATI failure doesn't fail order

Edge cases:
  ✅ Race condition — concurrent orders don't oversell (SELECT FOR UPDATE)
  ✅ Webhook tamper — modified amount with real sig rejected
  ✅ Snapshot price — product price change doesn't affect old orders
  ✅ Soft delete — data preserved, still visible to owner
  ✅ Stock never negative — guard at service layer

SDLC Progress:
  0 · Idea          ✅
  1 · Whiteboard    ✅
  2 · Requirements  ✅
  3 · HLD           ✅
  4 · LLD           ✅
  5 · Dev Setup     ✅
  6 · Code          ⚠️  Backend done · Frontend pending
  7 · Testing       ✅  (backend tests complete)
  ──────────────────────────
  8 · Staging       ← NEXT
  9 · Ship
  
GitHub repository secrets — set in repo Settings → Secrets → Actions
Secret name	Value	Used by
JWT_PRIVATE_KEY_TEST	Test RSA private key (different from prod)	Backend CI tests
JWT_PUBLIC_KEY_TEST	Test RSA public key	Backend CI tests
RAILWAY_TOKEN	From railway.app → Account → Tokens	Deploy backend
VERCEL_TOKEN	From vercel.com → Settings → Tokens	Deploy frontend
VERCEL_ORG_ID	From vercel.com → Team settings	Deploy frontend
VERCEL_PROJECT_ID	From vercel.com → Project settings	Deploy frontend
CODECOV_TOKEN	From codecov.io (optional)	Coverage reports
