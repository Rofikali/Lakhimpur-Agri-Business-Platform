# Lakhimpur Agri-Business Platform

Farm-direct rice and traditional Assamese petha — sold online and offline
from Lakhimpur district, Assam. Built by a solo engineer.

## What it does

- **Shop** (`/shop`) — customers browse Joha Rice, Bora Saul, Kali Jeera,
  Narikal Petha and Septa Petha, pay via UPI/Razorpay, choose pickup or delivery
- **Dashboard** (`/dashboard`) — owner manages inventory, orders, P&L,
  farm seasons, petha batches, and sees real-time profit to ₹0.00001

## Tech stack

| Layer        | Technology                        |
|---|---|
| Backend      | FastAPI (Python 3.11), async      |
| Frontend     | NuxtJS 3 (Vue 3 + TypeScript)     |
| Database     | PostgreSQL 15 — NUMERIC(15,5)     |
| Cache        | Redis 7                           |
| Payments     | Razorpay (UPI + cards)            |
| Notify       | WATI (WhatsApp Business API)      |
| Deploy       | Railway (backend) + Vercel (frontend) |
| Monitoring   | Sentry + OpenTelemetry            |

## Prerequisites

- Docker + Docker Compose
- make
- openssl (for RSA key generation)

## First-time setup

```bash
# 1. Clone
git clone https://github.com/yourusername/lakhimpur-biz.git
cd lakhimpur-biz

# 2. Generate JWT RSA keys (do once, keep private.pem secret)
openssl genrsa -out backend/private.pem 2048
openssl rsa -in backend/private.pem -pubout -out backend/public.pem

# 3. Copy env files and fill in values
cp backend/.env.example  backend/.env.local
cp frontend/.env.example frontend/.env.local
# Edit backend/.env.local — add JWT_PRIVATE_KEY, JWT_PUBLIC_KEY,
#   RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET (TEST keys)

# 4. Start everything
make up      # starts backend, frontend, postgres, redis
make migrate # runs Alembic migrations
make seed    # creates owner account + 5 default products
```

Open <http://localhost:3000/login> — username: `admin`, password: `changeme123`

## Daily workflow

```bash
make up          # start services
make logs        # watch backend logs
make test-unit   # fast unit tests (no DB)
make test-cov    # full tests + coverage
make lint        # ruff + black check
make format      # auto-fix formatting
make migrate     # run new migrations
make generate-migration MSG="describe change"
make down        # stop (data persists)
```

## Project structure

```
lakhimpur-biz/
├── backend/          FastAPI app
│   ├── core/         config, db, redis, security, middleware
│   ├── modules/      auth, products, inventory, orders, payments,
│   │                 pl_engine, farm, petha, notify
│   ├── shared/       base models, exceptions, utils
│   ├── migrations/   Alembic
│   └── scripts/      seed.py
├── frontend/         NuxtJS app
│   ├── pages/        dashboard/ + shop/
│   ├── components/   dashboard/ + shop/ + shared/
│   ├── composables/
│   └── stores/       Pinia
├── docker-compose.yml
└── Makefile
```

## API documentation

Running locally: <http://localhost:8000/docs> (disabled in production)

## Deployment

Push to `main` → GitHub Actions:

1. Runs all tests (backend + frontend)
2. Deploys backend to Railway
3. Deploys frontend to Vercel

Set secrets in GitHub repo settings — see Stage 5 documentation.

## Environment variables

See `backend/.env.example` and `frontend/.env.example` for all required variables.
Production secrets live in Railway and Vercel dashboards — never in git.

### Root Project Layout

    lakhimpur-biz/               # Root repository directory
    ├── backend/                  # FastAPI Application (Python backend stack)
    ├── frontend/                 # NuxtJS Application (Vue/TypeScript frontend stack)
    ├── docker-compose.yml        # Orchestration layer for local multi-container development
    ├── Makefile                  # Automation script containing shortcuts for daily dev workflows
    ├── .gitignore                # Explicit file exclusion patterns for Git version control
    ├── .pre-commit-config.yaml   # Hooks for formatting, linting, and quality gates before commits
    └── README.md                 # Project summary, onboarding info, and quick-start manuals

# Project Setup Guide

This document contains instructions for the first-time setup of the **lakhimpur-biz** project, along with the project's `.gitignore` configuration.

---

## First-Time Setup (Step-by-Step)

### 1. Create Git Repository and Clone

Run the following commands to initialize your repository and link it to GitHub:

```bash
git init lakhimpur-biz
cd lakhimpur-biz
git remote add origin https://github.com/yourusername/lakhimpur-biz.git
```

### 2. Generate RSA-2048 Key Pair for JWT

Generate the required cryptographic keys.
> ⚠️ **CRITICAL:** Do this **ONCE**. Keep `private.pem` secret and never commit it to version control.

```bash
# Generate keys
openssl genrsa -out backend/private.pem 2048
openssl rsa -in backend/private.pem -pubout -out backend/public.pem

# Convert private key to single-line format for .env configuration
awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;} END {printf "\n"}' backend/private.pem
```

- **Action Required:** Copy the output of the `awk` command into `JWT_PRIVATE_KEY` inside `backend/.env.local`.
- **Action Required:** Repeat the process or format `public.pem` to fill `JWT_PUBLIC_KEY` in `backend/.env.local`.

### 3. Copy and Fill Environment Files

Duplicate the template environment configuration files and update their values:

```bash
cp backend/.env.example backend/.env.local
cp frontend/.env.example frontend/.env.local
```

- Fill in `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`, and **Razorpay TEST** keys inside `backend/.env.local`.
- Set `WATI_ENABLED=false` for local development to disable active WhatsApp integrations.

### 4. Start All Services

Launch the infrastructure via Docker. The initial run will download required Docker images and takes roughly 3 minutes.

```bash
make up
```

- **Services started:** Backend (Port `8000`), Frontend (Port `3000`), Postgres (Port `5432`), Redis (Port `6379`).

To monitor the application runtime:

```bash
make logs   # Follows and watches backend logs
```

### 5. Run Migrations and Seed Database

Prepare your database schema and populate it with initial bootstrap data:

```bash
make migrate   # Runs 'alembic upgrade head' to build tables
make seed      # Provisions the owner account and 5 default products
```

- **Expected Output:** `✓ Seed complete. Login: admin / changeme123`

### 6. Verify Deployment

Verify that the services are responsive and healthy:

```bash
curl http://localhost:8000/health        # Expected: {"status":"ok"}
curl http://localhost:8000/health/ready  # Expected: {"status":"ready"} (Confirms DB + Redis connection)
```

#### Local Access Points

Open these URLs in your browser to interact with the stack:

- **API Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Storefront Shop:** [http://localhost:3000/shop](http://localhost:3000/shop)
- **Admin Dashboard:** [http://localhost:3000/login](http://localhost:3000/login) (Credentials: `admin` / `changeme123`)

---

## Daily Workflow

The environment supports hot-reloading on both frontend and backend layers. Saving changes to local files triggers immediate updates inside containers.

- **Start Stack:** `make up`
- **Stop Stack:** `make down`

# Lakhimpur Agri-Business Platform

Farm-direct rice and traditional Assamese petha — sold online and offline
from Lakhimpur district, Assam. Built by a solo engineer.

## What it does

- **Shop** (`/shop`) — customers browse Joha Rice, Bora Saul, Kali Jeera,
  Narikal Petha and Septa Petha, pay via UPI/Razorpay, choose pickup or delivery
- **Dashboard** (`/dashboard`) — owner manages inventory, orders, P&L,
  farm seasons, petha batches, and sees real-time profit to ₹0.00001

## Tech stack all latests

| Layer        | Technology                        |
|---|---|
| Backend      | FastAPI (Python 3.1), async      |
| Frontend     | NuxtJS 3 (Vue 3 + TypeScript)     |
| Database     | PostgreSQL 15 — NUMERIC(15,5)     |
| Cache        | Redis 7                           |
| Payments     | Razorpay (UPI + cards)            |
| Notify       | WATI (WhatsApp Business API)      |
| Deploy       | Railway (backend) + Vercel (frontend) |
| Monitoring   | Sentry + OpenTelemetry            |

## Prerequisites

- Docker + Docker Compose
- make
- openssl (for RSA key generation)

## First-time setup

```bash
# 1. Clone
git clone https://github.com/yourusername/lakhimpur-biz.git
cd lakhimpur-biz

# 2. Generate JWT RSA keys (do once, keep private.pem secret)
openssl genrsa -out backend/private.pem 2048
openssl rsa -in backend/private.pem -pubout -out backend/public.pem

# 3. Copy env files and fill in values
cp backend/.env.example  backend/.env.local
cp frontend/.env.example frontend/.env.local
# Edit backend/.env.local — add JWT_PRIVATE_KEY, JWT_PUBLIC_KEY,
#   RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET (TEST keys)

# 4. Start everything
make up      # starts backend, frontend, postgres, redis
make migrate # runs Alembic migrations
make seed    # creates owner account + 5 default products
```

Open <http://localhost:3000/login> — username: `admin`, password: `changeme123`

## Daily workflow

```bash
make up          # start services
make logs        # watch backend logs
make test-unit   # fast unit tests (no DB)
make test-cov    # full tests + coverage
make lint        # ruff + black check
make format      # auto-fix formatting
make migrate     # run new migrations
make generate-migration MSG="describe change"
make down        # stop (data persists)
```

## Project structure

```
lakhimpur-biz/
├── backend/          FastAPI app
│   ├── core/         config, db, redis, security, middleware
│   ├── modules/      auth, products, inventory, orders, payments,
│   │                 pl_engine, farm, petha, notify
│   ├── shared/       base models, exceptions, utils
│   ├── migrations/   Alembic
│   └── scripts/      seed.py
├── frontend/         NuxtJS app
│   ├── pages/        dashboard/ + shop/
│   ├── components/   dashboard/ + shop/ + shared/
│   ├── composables/
│   └── stores/       Pinia
├── docker-compose.yml
└── Makefile
```

## API documentation

Running locally: <http://localhost:8000/docs> (disabled in production)

## Deployment

Push to `main` → GitHub Actions:

1. Runs all tests (backend + frontend)
2. Deploys backend to Railway
3. Deploys frontend to Vercel

Set secrets in GitHub repo settings — see Stage 5 documentation.

## Environment variables

See `backend/.env.example` and `frontend/.env.example` for all required variables.
Production secrets live in Railway and Vercel dashboards — never in git.

touch finance/{schemas,repository,service,router,**init**}.py
