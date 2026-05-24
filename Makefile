# ── Config ────────────────────────────────────────────────────────────────────
UV      := cd backend && uv run
PG_DATA := /var/lib/postgres/data

.PHONY: up down dev-be dev-fe migrate rollback seed reset-db \
        gen-keys install test test-unit test-cov test-pl \
        lint format typecheck shell help

# ── Services ──────────────────────────────────────────────────────────────────
up:                                            ## Start PostgreSQL + Redis
	@sudo -u postgres pg_ctl status -D $(PG_DATA) > /dev/null 2>&1 \
	  || sudo -u postgres pg_ctl start -D $(PG_DATA) \
	       -l /var/log/postgresql.log -o "-p 5432" -w
	@redis-cli ping > /dev/null 2>&1 \
	  || redis-server --daemonize yes --bind 127.0.0.1 \
	       --logfile /var/log/redis.log
	@echo "✓ PostgreSQL + Redis running"
	@echo ""
	@echo "Now run in two terminals:"
	@echo "  Terminal 1: make dev-be"
	@echo "  Terminal 2: make dev-fe"

down:                                          ## Stop all services
	@sudo -u postgres pg_ctl stop -D $(PG_DATA) 2>/dev/null || true
	@pkill redis-server 2>/dev/null || true
	@echo "✓ Services stopped"

# ── Dev servers ───────────────────────────────────────────────────────────────
dev-be:                                        ## Run backend (hot reload)
	$(UV) uvicorn main:app \
	  --host 0.0.0.0 --port 8000 --reload \
	  --reload-dir modules --reload-dir core --reload-dir shared

dev-fe:                                        ## Run frontend (hot reload)
	cd frontend && pnpm run dev

# ── Keys ──────────────────────────────────────────────────────────────────────
gen-keys:                                      ## Generate RSA JWT keys → print for .env.local
	@openssl genrsa -out /tmp/jwt_priv.pem 2048 2>/dev/null
	@openssl rsa -in /tmp/jwt_priv.pem -pubout -out /tmp/jwt_pub.pem 2>/dev/null
	@echo ""
	@echo "Add these to backend/.env.local:"
	@echo ""
	@printf 'JWT_PRIVATE_KEY='
	@awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' /tmp/jwt_priv.pem
	@echo ""
	@printf 'JWT_PUBLIC_KEY='
	@awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' /tmp/jwt_pub.pem
	@echo ""
	@rm /tmp/jwt_priv.pem /tmp/jwt_pub.pem
	@echo "(keys deleted from /tmp)"

# ── Install ───────────────────────────────────────────────────────────────────
install:                                       ## Sync all deps (uv + npm)
	cd backend  && uv sync --all-groups
	cd frontend && npm install

lock:                                          ## Update uv.lock
	cd backend && uv lock

# ── Database ──────────────────────────────────────────────────────────────────
migrate:                                       ## Run Alembic migrations (head)
	$(UV) alembic upgrade head

rollback:                                      ## Roll back one migration
	$(UV) alembic downgrade -1

generate-migration:                            ## New migration — MSG=required
	$(UV) alembic revision --autogenerate -m "$(MSG)"

seed:                                          ## Seed DB (owner + 5 products)
	$(UV) python scripts/seed.py

reset-db:                                      ## ⚠ Wipe + remigrate + reseed
	$(UV) alembic downgrade base
	$(UV) alembic upgrade head
	$(UV) python scripts/seed.py

shell-db:                                      ## PostgreSQL shell
	psql -U postgres -d lakhimpur_dev

# ── Tests ─────────────────────────────────────────────────────────────────────
test:                                          ## All tests
	$(UV) pytest tests/ -v

test-unit:                                     ## Unit tests only (fast, no DB)
	$(UV) pytest tests/unit/ -v --tb=short

test-cov:                                      ## Tests + coverage (must hit 75%)
	$(UV) pytest tests/ \
	  --cov=. --cov-report=term-missing \
	  --cov-report=html:htmlcov \
	  --cov-fail-under=75 -v

test-pl:                                       ## P&L engine only (must hit 95%)
	$(UV) pytest tests/unit/test_pl_calculator.py \
	  --cov=modules/pl_engine/calculator.py \
	  --cov-fail-under=95 -v

test-fast:                                     ## Parallel test run (fastest)
	$(UV) pytest tests/ -n auto --tb=short

# ── Code quality ──────────────────────────────────────────────────────────────
lint:                                          ## ruff + black check
	$(UV) ruff check .
	$(UV) black --check .

format:                                        ## Auto-fix formatting
	$(UV) ruff check --fix .
	$(UV) black .

typecheck:                                     ## mypy type check
	$(UV) mypy modules/ core/ shared/ --ignore-missing-imports

# ── Dev utilities ─────────────────────────────────────────────────────────────
shell:                                         ## IPython REPL in project env
	$(UV) ipython

logs-pg:                                       ## Tail PostgreSQL logs
	tail -f /var/log/postgresql.log

logs-redis:                                    ## Tail Redis logs
	tail -f /var/log/redis.log

health:                                        ## Check backend health
	curl -s http://localhost:8000/health | python -m json.tool
	curl -s http://localhost:8000/health/ready | python -m json.tool

help:                                          ## Show all commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'
