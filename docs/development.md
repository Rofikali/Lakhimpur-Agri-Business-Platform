# Development Guide

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.12+ | via uv (auto-managed) |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | 20+ | `pacman -S nodejs npm` |
| PostgreSQL | 15+ | `pacman -S postgresql` |
| Redis | 7+ | `pacman -S redis` |
| Git | any | `pacman -S git` |
| openssl | any | `pacman -S openssl` |

---

## First-time setup

### 1. Clone and enter repo

```bash
git clone https://github.com/yourusername/lakhimpur-biz.git
cd lakhimpur-biz
```

### 2. Install dependencies

```bash
make install
# Runs: uv sync --all-groups (backend) + npm install (frontend)
```

### 3. Initialise PostgreSQL

```bash
# First time only — initialise data directory
sudo -u postgres initdb -D /var/lib/postgres/data --encoding=UTF8 --locale=C.UTF-8

# Start PostgreSQL (Arch Linux / Codespaces — no systemd)
sudo -u postgres pg_ctl start \
  -D /var/lib/postgres/data \
  -l /tmp/postgres.log \
  -o "-k /tmp -p 5432" \
  -w

# Create databases
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'devpassword';"
sudo -u postgres createdb lakhimpur_dev
sudo -u postgres createdb lakhimpur_test
```

### 4. Start Redis

```bash
redis-server --daemonize yes \
  --bind 127.0.0.1 \
  --logfile /tmp/redis.log
```

### 5. Generate JWT keys

```bash
make gen-keys
# Prints JWT_PRIVATE_KEY=... and JWT_PUBLIC_KEY=... lines
# Copy both lines into backend/.env.local
```

### 6. Create and fill `.env.local`

```bash
cp backend/.env.example backend/.env.local
# Edit backend/.env.local:
# - Paste JWT_PRIVATE_KEY and JWT_PUBLIC_KEY from step 5
# - DATABASE_URL=postgresql+asyncpg://postgres:devpassword@/lakhimpur_dev?host=/tmp
# - REDIS_URL=redis://127.0.0.1:6379/0
# - RAZORPAY_KEY_ID=rzp_test_xxx (from Razorpay test dashboard)
# - RAZORPAY_KEY_SECRET=test_xxx
# - RAZORPAY_WEBHOOK_SECRET=any_local_secret
# - WATI_ENABLED=false
```

### 7. Run migrations and seed

```bash
make migrate   # Creates all 14 tables
make seed      # Creates owner account + 5 default products
```

### 8. Verify

```bash
# Terminal 1
make dev-be
# → INFO: Uvicorn running on http://0.0.0.0:8000

# Terminal 2 (new tab)
curl http://localhost:8000/health/ready
# → {"status": "ready"}
```

---

## Daily workflow

```bash
# Morning — start services
make up          # starts PostgreSQL + Redis
make dev-be      # terminal 1: backend with hot reload
make dev-fe      # terminal 2: frontend with HMR

# During development
# Edit any .py file → uvicorn auto-reloads (no restart needed)
# Edit any .vue/.ts file → Nuxt HMR updates browser instantly

# Before committing
make format      # auto-fix ruff + black
make lint        # verify no issues
make test-unit   # fast unit tests (~5 seconds, no DB)
git add .
git commit -m "feat: add product margin display"
# pre-commit hooks run automatically

# Full test suite before pushing
make test-cov    # all tests + coverage report

# Evening
make down        # stop PostgreSQL + Redis (data persists)
```

---

## Makefile command reference

```
make up              Start PostgreSQL + Redis
make down            Stop all services
make restart         Stop then start

make dev-be          Run FastAPI backend (hot reload)
make dev-fe          Run NuxtJS frontend (hot reload)

make install         uv sync --all-groups + npm install
make lock            Update uv.lock after adding packages

make migrate         Alembic upgrade head
make rollback        Alembic downgrade -1
make revision        Generate new migration (MSG=required)
make seed            Create owner + 5 default products
make reset-db        Wipe + remigrate + reseed

make test            All tests verbose
make test-unit       Unit tests only (no DB, ~5s)
make test-fast       Parallel tests (pytest-xdist)
make test-cov        Tests + coverage report (≥75% required)
make test-pl         P&L engine only (≥95% required)

make lint            ruff check + black check
make format          ruff --fix + black
make typecheck       mypy type checking

make gen-keys        Generate RSA JWT key pair
make shell           IPython REPL in project env
make shell-db        PostgreSQL psql shell
make health          curl /health + /health/ready
make logs-pg         Tail PostgreSQL log
make logs-redis      Tail Redis log

make help            Show all commands with descriptions
```

---

## Adding a dependency

```bash
# Add to backend
cd backend
uv add httpx                      # production dep → pyproject.toml
uv add --dev pytest-timeout       # dev dep → [dependency-groups.dev]
uv lock                           # update uv.lock
make install                      # sync all environments

# Add to frontend
cd frontend
npm install some-vue-library
# package.json + package-lock.json updated
```

---

## Adding a new module

Follow this checklist every time:

```bash
# 1. Create folder and stub files
mkdir -p backend/modules/newmodule
touch backend/modules/newmodule/__init__.py

# 2. Create the four files in order:
#    models.py → schemas.py → repository.py → service.py → router.py

# 3. Register router in main.py
# from modules.newmodule.router import router as newmodule_router
# app.include_router(newmodule_router)

# 4. Import models in migrations/env.py
# from modules.newmodule.models import NewModel

# 5. Generate migration
make revision MSG="add newmodule tables"
make migrate

# 6. Add service factory to core/dependencies.py
# async def get_newmodule_service(db=Depends(get_db_session)):
#     from modules.newmodule.service import NewModuleService
#     return NewModuleService(...)

# 7. Write tests
touch backend/tests/unit/test_newmodule.py
touch backend/tests/integration/test_newmodule_api.py

# 8. Verify
make test
make dev-be
```

---

## Database migrations

```bash
# After changing any SQLAlchemy model:
make revision MSG="describe what changed"
# Generates: migrations/versions/XXXX_describe_what_changed.py

# Review the generated file BEFORE applying:
cat backend/migrations/versions/*.py | tail -50

# Apply
make migrate

# If something is wrong, roll back:
make rollback
```

**Rules:**
- Never edit a migration after applying it to any environment
- Never drop columns — add `deleted_at`, stop using old column
- Every migration must have a working `downgrade()` function
- Data migrations in separate files from schema migrations

---

## Environment variables reference

All variables live in `backend/.env.local` (local) or Railway/Vercel (deployed).

```bash
# Required — app won't start without these
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
JWT_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----...
JWT_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----...
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...

# Optional — have defaults
ENVIRONMENT=local                # local|staging|production
DEBUG=true                       # false in production
LOG_LEVEL=DEBUG                  # INFO in production
JWT_EXPIRY_HOURS=24
OWNER_USERNAME=admin
WATI_ENABLED=false               # true only in production
CORS_ORIGIN=http://localhost:3000
RATE_LIMIT_PER_MIN=100
RATE_LIMIT_LOGIN_PER_MIN=5
```

---

## Running tests

```bash
# Fast (no DB) — run constantly during development
make test-unit

# All tests with coverage
make test-cov

# Single test file
cd backend && uv run pytest tests/unit/test_pl_calculator.py -v

# Single test
cd backend && uv run pytest tests/integration/test_orders.py::TestOrderCreate::test_oversell_rejected -v

# Match keyword
cd backend && uv run pytest -k "webhook" -v

# Stop on first failure
cd backend && uv run pytest tests/ -x --tb=long

# Show slowest tests
cd backend && uv run pytest tests/ --durations=10
```

### Test database setup

Integration tests need `lakhimpur_test` database:

```bash
sudo -u postgres createdb lakhimpur_test
# Tests use DATABASE_URL from environment with lakhimpur_test override
# Each test wraps in a transaction that rolls back — tests never dirty each other
```

---

## Common errors and fixes

### `asyncio extension requires an async driver`
```bash
# DATABASE_URL is missing +asyncpg
# Change: postgresql://...
# To:     postgresql+asyncpg://...
sed -i 's|postgresql://|postgresql+asyncpg://|' backend/.env.local
```

### `Field required [type=missing]` (Settings validation)
```bash
# .env.local not found — check path resolution
cd backend && uv run python -c "
from core.config import settings
print(settings.DATABASE_URL)
"
# If fails: verify backend/.env.local exists and has the required keys
```

### `circular import` from `core/__init__.py`
```bash
# core/__init__.py must be empty
echo "# core package" > backend/core/__init__.py
```

### `ModuleNotFoundError: No module named 'modules.X.models'`
```bash
# Create the missing models.py file
# Follow the pattern from modules/products/models.py
touch backend/modules/X/models.py
```

### `pg_ctl: could not connect to database`
```bash
# PostgreSQL not running or wrong socket path
sudo -u postgres pg_ctl start \
  -D /var/lib/postgres/data \
  -l /tmp/postgres.log \
  -o "-k /tmp -p 5432" -w

# Verify
psql -h /tmp -U postgres -c "SELECT 1;"
```

### `redis.exceptions.ConnectionError`
```bash
redis-server --daemonize yes --bind 127.0.0.1 --logfile /tmp/redis.log
redis-cli ping   # → PONG
```

---

## VS Code recommended extensions

```json
{
  "recommendations": [
    "ms-python.python",
    "ms-python.vscode-pylance",
    "charliermarsh.ruff",
    "ms-python.black-formatter",
    "Vue.volar",
    "dbaeumer.vscode-eslint",
    "tamasfe.even-better-toml",
    "ms-vscode.makefile-tools",
    "eamodio.gitlens",
    "gruntfuggly.todo-tree"
  ]
}
```

### `.vscode/settings.json`

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/backend/.venv/bin/python",
  "editor.formatOnSave": true,
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.codeActionsOnSave": {
      "source.fixAll.ruff": "explicit",
      "source.organizeImports.ruff": "explicit"
    }
  },
  "[typescript]": { "editor.defaultFormatter": "dbaeumer.vscode-eslint" },
  "[vue]":        { "editor.defaultFormatter": "Vue.volar" }
}
```