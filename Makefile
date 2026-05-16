# Makefile — all dev commands
.PHONY: up down restart logs shell-be shell-db shell-fe \
        migrate seed test test-unit test-cov lint format \
        generate-migration build-prod

up:                                               ## Start all services
	docker compose up -d

down:                                             ## Stop all services
	docker compose down

restart:                                          ## Restart backend only
	docker compose restart backend

logs:                                             ## Follow backend logs
	docker compose logs -f backend

logs-all:                                         ## Follow all logs
	docker compose logs -f

shell-be:                                         ## Shell into backend container
	docker compose exec backend bash

shell-db:                                         ## PostgreSQL shell
	docker compose exec db psql -U postgres -d lakhimpur_dev

shell-fe:                                         ## Shell into frontend container
	docker compose exec frontend sh

migrate:                                          ## Run Alembic migrations
	docker compose exec backend alembic upgrade head

generate-migration:                               ## Generate migration (MSG=required)
## Usage: make generate-migration MSG="add product images"
	docker compose exec backend alembic revision --autogenerate -m "$(MSG)"

rollback:                                         ## Roll back one migration
	docker compose exec backend alembic downgrade -1

seed:                                             ## Seed database (owner + products)
	docker compose exec backend python scripts/seed.py

reset-db:                                         ## ⚠ Wipe and reseed (dev only)
	docker compose exec backend alembic downgrade base
	docker compose exec backend alembic upgrade head
	docker compose exec backend python scripts/seed.py

test:                                             ## Run all tests
	docker compose exec backend pytest tests/ -v

test-unit:                                        ## Unit tests only (fast, no DB)
	docker compose exec backend pytest tests/unit/ -v

test-cov:                                         ## Tests with coverage report
	docker compose exec backend pytest tests/ --cov=. --cov-report=term-missing --cov-fail-under=75

lint:                                             ## Lint backend (ruff + black)
	docker compose exec backend ruff check .
	docker compose exec backend black --check .

format:                                           ## Auto-fix backend formatting
	docker compose exec backend ruff check --fix .
	docker compose exec backend black .

typecheck-fe:                                     ## TypeScript check frontend
	docker compose exec frontend npm run typecheck

test-fe:                                          ## Frontend tests
	docker compose exec frontend npm test

help:                                             ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'