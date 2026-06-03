# =============================================================================
# Lakhimpur Biz — Engineering Makefile
# =============================================================================

SHELL := /bin/bash

ROOT_DIR := $(shell pwd)
BACKEND  := $(ROOT_DIR)/backend
FRONTEND := $(ROOT_DIR)/frontend
COMPOSE  := docker compose
HAS_DOCKER := $(shell docker info >/dev/null 2>&1 && echo 1 || echo 0)
UV       := cd $(BACKEND) && uv run

.DEFAULT_GOAL := help

.PHONY: \
	up up-all down restart ps \
	dev dev-be dev-fe preview-fe \
	fe-lint fe-typecheck fe-build fe-check \
	install lock clean \
	migrate rollback revision seed reset-db \
	test test-unit test-fast test-cov test-pl \
	lint format typecheck quality \
	gen-keys shell shell-db \
	logs logs-be logs-pg logs-redis \
	health help

# =============================================================================
# SERVICES
# =============================================================================

up: ## Start backend services; Docker when available, Codespaces local otherwise
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		echo "Using Docker Compose"; \
		$(COMPOSE) up -d db redis backend; \
	else \
		echo "Docker daemon unavailable; using Codespaces local services"; \
		bash .devcontainer/start-services.sh; \
	fi
	@echo ""
	@echo "✓ Backend services ready"
	@echo "  API:  http://localhost:8000  (run make dev-be if backend is not already running)"
	@echo "  Docs: http://localhost:8000/docs"

up-all: ## Start backend services and frontend stack
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		echo "Using Docker Compose"; \
		$(COMPOSE) up -d; \
	else \
		echo "Docker daemon unavailable; using Codespaces local services"; \
		bash .devcontainer/start-services.sh; \
		echo "Run make dev-be and make dev-fe in separate terminals"; \
	fi

down: ## Stop services
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		$(COMPOSE) down; \
	else \
		su postgres -c "pg_ctl stop -D /var/lib/postgres/data" >/dev/null 2>&1 || true; \
		pkill redis-server >/dev/null 2>&1 || true; \
		echo "✓ Local services stopped"; \
	fi

restart: down up ## Restart backend services

ps: ## Show service status
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		$(COMPOSE) ps; \
	else \
		su postgres -c "pg_ctl status -D /var/lib/postgres/data" || true; \
		redis-cli ping || true; \
	fi

# =============================================================================
# DEVELOPMENT
# =============================================================================

dev: ## Show dev commands
	@echo "Run one of:"
	@echo "  make dev-be  # FastAPI"
	@echo "  make dev-fe  # Nuxt frontend"
	@echo "  make up      # DB + Redis first"

dev-be: ## FastAPI backend with hot reload
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		$(COMPOSE) up backend; \
	else \
		bash .devcontainer/start-services.sh; \
		cd $(BACKEND) && uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-dir modules --reload-dir shared --reload-dir core; \
	fi

dev-fe: ## Nuxt frontend with hot reload
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		$(COMPOSE) up frontend; \
	else \
		cd $(FRONTEND) && pnpm run dev --no-fork --host 0.0.0.0 --port 3000; \
	fi

preview-fe: ## Preview built Nuxt frontend
	cd $(FRONTEND) && pnpm run preview --host 0.0.0.0 --port 3000

fe-lint: ## Frontend ESLint
	cd $(FRONTEND) && pnpm run lint

fe-typecheck: ## Frontend typecheck
	cd $(FRONTEND) && pnpm run typecheck

fe-build: ## Frontend production build
	cd $(FRONTEND) && pnpm run build

fe-check: fe-lint fe-typecheck fe-build ## Full frontend quality gate

# =============================================================================
# INSTALLATION
# =============================================================================

install: ## Install/build dependencies
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		$(COMPOSE) build backend; \
		$(COMPOSE) build frontend; \
	else \
		cd $(BACKEND) && uv sync --all-groups; \
		cd $(FRONTEND) && pnpm install; \
	fi

lock: ## Update backend uv lockfile
	cd $(BACKEND) && uv lock

clean: ## Cleanup local Python artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# =============================================================================
# DATABASE
# =============================================================================

migrate: ## Alembic upgrade
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		$(COMPOSE) run --rm backend alembic upgrade head; \
	else \
		bash .devcontainer/start-services.sh; \
		cd $(BACKEND) && uv run alembic upgrade head; \
	fi

rollback: ## Alembic downgrade
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		$(COMPOSE) run --rm backend alembic downgrade -1; \
	else \
		cd $(BACKEND) && uv run alembic downgrade -1; \
	fi

revision: ## New migration (MSG="...")
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		$(COMPOSE) run --rm backend alembic revision --autogenerate -m "$(MSG)"; \
	else \
		cd $(BACKEND) && uv run alembic revision --autogenerate -m "$(MSG)"; \
	fi

seed: ## Seed database
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		$(COMPOSE) run --rm backend python scripts/seed.py; \
	else \
		bash .devcontainer/start-services.sh; \
		cd $(BACKEND) && uv run python scripts/seed.py; \
	fi

reset-db: ## Reset database schema and seed data
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		$(COMPOSE) run --rm backend alembic downgrade base; \
		$(COMPOSE) run --rm backend alembic upgrade head; \
		$(COMPOSE) run --rm backend python scripts/seed.py; \
	else \
		bash .devcontainer/start-services.sh; \
		cd $(BACKEND) && uv run alembic downgrade base; \
		cd $(BACKEND) && uv run alembic upgrade head; \
		cd $(BACKEND) && uv run python scripts/seed.py; \
	fi

shell-db: ## PostgreSQL shell
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		$(COMPOSE) exec db psql -U postgres -d lakhimpur_dev; \
	else \
		psql postgresql://postgres:devpassword@127.0.0.1:5432/lakhimpur_dev; \
	fi

# =============================================================================
# TESTING
# =============================================================================

test: ## All backend tests
	@if [ "$(HAS_DOCKER)" = "1" ]; then $(COMPOSE) run --rm backend pytest tests/ -v; else cd $(BACKEND) && uv run pytest tests/ -v; fi

test-unit: ## Backend unit tests
	@if [ "$(HAS_DOCKER)" = "1" ]; then $(COMPOSE) run --rm backend pytest tests/unit/ -v --tb=short; else cd $(BACKEND) && uv run pytest tests/unit/ -v --tb=short; fi

test-fast: ## Backend parallel tests
	@if [ "$(HAS_DOCKER)" = "1" ]; then $(COMPOSE) run --rm backend pytest tests/ -n auto --tb=short; else cd $(BACKEND) && uv run pytest tests/ -n auto --tb=short; fi

test-cov: ## Backend coverage
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		$(COMPOSE) run --rm backend pytest tests/ --cov=. --cov-report=term-missing --cov-report=html:htmlcov --cov-fail-under=75; \
	else \
		cd $(BACKEND) && uv run pytest tests/ --cov=. --cov-report=term-missing --cov-report=html:htmlcov --cov-fail-under=75; \
	fi

test-pl: ## P&L engine coverage
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		$(COMPOSE) run --rm backend pytest tests/unit/test_pl_calculator.py --cov=modules/pl_engine/calculator.py --cov-fail-under=95; \
	else \
		cd $(BACKEND) && uv run pytest tests/unit/test_pl_calculator.py --cov=modules/pl_engine/calculator.py --cov-fail-under=95; \
	fi

# =============================================================================
# QUALITY
# =============================================================================

lint: ## Ruff lint
	@if [ "$(HAS_DOCKER)" = "1" ]; then $(COMPOSE) run --rm backend ruff check .; else cd $(BACKEND) && uv run ruff check .; fi

format: ## Format backend code
	@if [ "$(HAS_DOCKER)" = "1" ]; then \
		$(COMPOSE) run --rm backend ruff check . --fix; \
		$(COMPOSE) run --rm backend black .; \
	else \
		cd $(BACKEND) && uv run ruff check . --fix; \
		cd $(BACKEND) && uv run black .; \
	fi

typecheck: ## mypy type checking
	@if [ "$(HAS_DOCKER)" = "1" ]; then $(COMPOSE) run --rm backend mypy . --explicit-package-bases; else cd $(BACKEND) && uv run mypy . --explicit-package-bases; fi

quality: lint typecheck test ## Full backend quality gate

# =============================================================================
# UTILITIES
# =============================================================================

gen-keys: ## Generate JWT RSA keys
	@openssl genrsa -out /tmp/jwt_priv.pem 2048 2>/dev/null
	@openssl rsa -in /tmp/jwt_priv.pem -pubout -out /tmp/jwt_pub.pem 2>/dev/null
	@echo ""
	@echo "Add to backend/.env.local:"
	@echo ""
	@printf 'JWT_PRIVATE_KEY='
	@awk 'NF {sub(/\r/, ""); printf "%s\\n",$$0;}' /tmp/jwt_priv.pem
	@echo ""
	@printf 'JWT_PUBLIC_KEY='
	@awk 'NF {sub(/\r/, ""); printf "%s\\n",$$0;}' /tmp/jwt_pub.pem
	@echo ""
	@rm -f /tmp/jwt_priv.pem /tmp/jwt_pub.pem

shell: ## Backend shell
	@if [ "$(HAS_DOCKER)" = "1" ]; then $(COMPOSE) run --rm backend ipython; else cd $(BACKEND) && uv run ipython; fi

logs: logs-be ## Follow backend logs

logs-be: ## Follow FastAPI logs
	@if [ "$(HAS_DOCKER)" = "1" ]; then $(COMPOSE) logs -f backend; else echo "FastAPI runs in your make dev-be terminal"; fi

logs-pg: ## Follow PostgreSQL logs
	@if [ "$(HAS_DOCKER)" = "1" ]; then $(COMPOSE) logs -f db; else tail -f /tmp/postgres.log; fi

logs-redis: ## Follow Redis logs
	@if [ "$(HAS_DOCKER)" = "1" ]; then $(COMPOSE) logs -f redis; else tail -f /tmp/redis.log; fi

health: ## Backend health checks
	curl -s http://localhost:8000/health | python -m json.tool
	curl -s http://localhost:8000/health/ready | python -m json.tool

# =============================================================================
# HELP
# =============================================================================

help: ## Show commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-24s\033[0m %s\n", $$1, $$2}'
