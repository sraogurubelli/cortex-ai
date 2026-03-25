.PHONY: dev test lint format migrate docker-up docker-down seed clean help

PYTHON ?= python3
PIP ?= pip

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

dev: ## Start the dev server with auto-reload
	$(PYTHON) -m uvicorn cortex.api.main:app --reload --host 0.0.0.0 --port 8000

install: ## Install all dependencies (dev + prod)
	$(PIP) install -e ".[dev]"

install-prod: ## Install production dependencies only
	$(PIP) install -r requirements.txt

# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------

lint: ## Run linters (ruff + mypy)
	ruff check cortex/ tests/
	mypy cortex/ --ignore-missing-imports

format: ## Format code with black + ruff
	black cortex/ tests/
	ruff check --fix cortex/ tests/

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

test: ## Run all tests with coverage
	pytest tests/ -v --cov=cortex --cov-report=term-missing

test-unit: ## Run unit tests only
	pytest tests/unit -v -m unit

test-integration: ## Run integration tests only
	pytest tests/integration -v -m integration

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

migrate: ## Run database migrations (alembic upgrade head)
	alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create MSG="add foo table")
	alembic revision --autogenerate -m "$(MSG)"

migrate-rollback: ## Rollback one migration
	alembic downgrade -1

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

docker-up: ## Start all services (Postgres, Redis, Qdrant, API)
	docker compose up -d

docker-down: ## Stop all services
	docker compose down

docker-build: ## Rebuild the API image
	docker compose build cortex-api

docker-logs: ## Tail logs from all services
	docker compose logs -f

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

seed: ## Seed the database with sample data
	$(PYTHON) -m cortex.platform.database.seed

clean: ## Remove build artifacts and caches
	rm -rf __pycache__ .pytest_cache htmlcov .coverage .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
