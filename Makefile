COMPOSE ?= docker compose
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
PYTEST ?= $(if $(wildcard .venv/bin/pytest),.venv/bin/pytest,pytest)
RUFF ?= $(if $(wildcard .venv/bin/ruff),.venv/bin/ruff,ruff)
ALEMBIC ?= $(if $(wildcard .venv/bin/alembic),.venv/bin/alembic,alembic)

.PHONY: up down logs test lint migrate migrate-host seed seed-host ingest ingest-host listings-host benchmark-data benchmark-baseline benchmark-optimized benchmark-compare benchmark-cache quote-worker web

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api

test:
	$(PYTEST) -q

lint:
	$(RUFF) check app tests scripts

migrate:
	$(COMPOSE) exec api alembic upgrade head

migrate-host:
	$(ALEMBIC) upgrade head

seed:
	$(COMPOSE) exec api python scripts/seed_database.py

seed-host:
	$(PYTHON) scripts/seed_database.py

seed-demo-host:
	$(PYTHON) scripts/seed_demo_portfolio.py

ingest:
	$(COMPOSE) exec api python scripts/ingest_market_data.py

ingest-host:
	$(PYTHON) scripts/ingest_market_data.py

listings-host:
	$(PYTHON) scripts/sync_listings.py

# Expand local search + market coverage (Docker API + DB).
expand-data:
	$(COMPOSE) exec api python scripts/sync_listings.py
	$(COMPOSE) exec -e MARKET_DATA_PROVIDER=yahoo api python scripts/ingest_market_data.py --refresh-universe
	$(COMPOSE) exec -e MARKET_DATA_PROVIDER=yahoo api python scripts/ingest_market_data.py --universe sp500 --limit 40
	$(COMPOSE) exec -e MARKET_DATA_PROVIDER=yahoo api python scripts/ingest_market_data.py \
		--ticker AAPL --ticker MSFT --ticker NVDA --ticker AMZN \
		--ticker GOOGL --ticker META --ticker TSLA --ticker SPY \
		--start 2024-01-02

benchmark-data:
	PYTHONPATH=. $(PYTHON) scripts/generate_benchmark_data.py

benchmark-baseline:
	$(ALEMBIC) downgrade 0004_phase7_fundamentals
	PYTHONPATH=. $(PYTHON) scripts/benchmark_price_history.py --label baseline

benchmark-optimized:
	$(ALEMBIC) upgrade head
	PYTHONPATH=. $(PYTHON) scripts/benchmark_price_history.py --label optimized

benchmark-compare:
	PYTHONPATH=. $(PYTHON) scripts/compare_benchmarks.py \
		benchmarks/results/baseline.json \
		benchmarks/results/optimized.json

benchmark-cache:
	PYTHONPATH=. $(PYTHON) scripts/benchmark_cache.py --label cache-enabled

quote-worker:
	PYTHONPATH=. $(PYTHON) -m app.workers.quote_worker

web:
	cd web && npm install && npm run dev
