.PHONY: help install build up down restart logs clean test lint format train-model load-test \
        failure-inject-kill-worker failure-inject-redis-down failure-inject-postgres-slow \
        failure-inject-cpu-spike failure-inject-memory-growth check-health check-metrics \
        check-grafana db-migrate db-shell redis-cli deploy-ubuntu

# Variables
DOCKER_COMPOSE := docker compose
PYTEST := pytest
RUFF := ruff
BLACK := black
MYPY := mypy

help: ## Show this help message
	@echo "Falcon ML Inference Platform - Makefile Commands"
	@echo "=================================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

install: ## Install Python dependencies locally
	pip install -r requirements.txt
	pre-commit install

build: ## Build Docker images
	$(DOCKER_COMPOSE) build

up: ## Start all services
	@echo "Starting Falcon ML Inference Platform..."
	cp .env.example .env 2>/dev/null || true
	$(DOCKER_COMPOSE) up -d
	@echo "Waiting for services to be healthy..."
	@sleep 10
	@make check-health

down: ## Stop all services
	$(DOCKER_COMPOSE) down

restart: ## Restart all services
	$(DOCKER_COMPOSE) restart

logs: ## Tail logs from all services
	$(DOCKER_COMPOSE) logs -f

logs-worker: ## Tail logs from workers only
	$(DOCKER_COMPOSE) logs -f worker-1 worker-2 worker-3

logs-nginx: ## Tail logs from nginx
	$(DOCKER_COMPOSE) logs -f nginx

clean: ## Clean up containers, volumes, and build artifacts
	$(DOCKER_COMPOSE) down -v
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

test: ## Run unit tests
	$(PYTEST) tests/ -v --cov=app --cov-report=term-missing --cov-report=html

test-integration: ## Run integration tests
	$(PYTEST) tests/integration/ -v

lint: ## Run linter (ruff)
	$(RUFF) check app/ tests/

format: ## Format code with black and ruff
	$(BLACK) app/ tests/
	$(RUFF) check --fix app/ tests/

type-check: ## Run type checker (mypy)
	$(MYPY) app/

train-model: ## Train the ML model
	python scripts/train_model.py

load-test-baseline: ## Run baseline load test (50 VUs)
	k6 run tests/load/baseline.js

load-test-stress: ## Run stress load test (500 VUs)
	k6 run tests/load/stress.js

load-test-spike: ## Run spike load test
	k6 run tests/load/spike.js

load-test-soak: ## Run soak test (10 min)
	k6 run tests/load/soak.js

load-test-all: ## Run all load tests
	@echo "Running all load tests..."
	@make load-test-baseline
	@sleep 30
	@make load-test-stress
	@sleep 30
	@make load-test-spike
	@sleep 30
	@make load-test-soak

failure-inject-kill-worker: ## Kill one worker and observe failover
	./scripts/kill_worker.sh

failure-inject-redis-down: ## Stop Redis and observe fallback
	./scripts/redis_down.sh

failure-inject-postgres-slow: ## Introduce Postgres slowness
	./scripts/postgres_slow.sh

failure-inject-cpu-spike: ## Create CPU spike on worker
	./scripts/cpu_spike.sh

failure-inject-memory-growth: ## Simulate memory growth
	./scripts/memory_growth.sh

check-health: ## Check health of all services
	@echo "Checking Nginx..."
	@curl -sf http://localhost/healthz || echo "❌ Nginx health check failed"
	@echo "Checking Workers..."
	@curl -sf http://localhost/healthz && echo "✅ Workers healthy" || echo "❌ Workers unhealthy"
	@echo "Checking Redis..."
	@docker exec falcon-redis redis-cli ping && echo "✅ Redis healthy" || echo "❌ Redis unhealthy"
	@echo "Checking Postgres..."
	@docker exec falcon-postgres pg_isready -U falcon && echo "✅ Postgres healthy" || echo "❌ Postgres unhealthy"
	@echo "Checking Prometheus..."
	@curl -sf http://localhost:9090/-/healthy && echo "✅ Prometheus healthy" || echo "❌ Prometheus unhealthy"
	@echo "Checking Grafana..."
	@curl -sf http://localhost:3000/api/health && echo "✅ Grafana healthy" || echo "❌ Grafana unhealthy"

check-metrics: ## View Prometheus metrics from a worker
	curl -s http://localhost/metrics | head -50

check-grafana: ## Open Grafana in browser
	@echo "Opening Grafana at http://localhost:3000"
	@echo "Username: admin"
	@echo "Password: admin_change_in_prod"
	open http://localhost:3000 || xdg-open http://localhost:3000 || echo "Please open http://localhost:3000 manually"

db-migrate: ## Run database migrations
	$(DOCKER_COMPOSE) exec worker-1 alembic upgrade head

db-shell: ## Open Postgres shell
	$(DOCKER_COMPOSE) exec postgres psql -U falcon -d falcon_inference

redis-cli: ## Open Redis CLI
	$(DOCKER_COMPOSE) exec redis redis-cli

demo: ## Run quick demo
	@echo "=== Falcon ML Inference Platform Demo ==="
	@echo ""
	@echo "1. Health Check:"
	@curl -s http://localhost/healthz | jq .
	@echo ""
	@echo "2. Single Inference Request:"
	@curl -s -X POST http://localhost/infer \
		-H "Content-Type: application/json" \
		-d '{"text": "This is a great product!"}' | jq .
	@echo ""
	@echo "3. Request with Idempotency Key (run twice to see deduplication):"
	@curl -s -X POST http://localhost/infer \
		-H "Content-Type: application/json" \
		-H "X-Idempotency-Key: demo-key-123" \
		-d '{"text": "Amazing service"}' | jq .
	@echo ""
	@echo "4. Metrics Sample:"
	@curl -s http://localhost/metrics | grep inference_requests_total
	@echo ""
	@echo "5. Open Grafana: http://localhost:3000 (admin/admin_change_in_prod)"
	@echo "6. Open Prometheus: http://localhost:9090"

deploy-ubuntu: ## Deploy to Ubuntu 22.04 (run on target server)
	@echo "Deploying to Ubuntu 22.04..."
	./deploy/deploy.sh

benchmark: ## Run quick benchmark
	@echo "Running quick benchmark with Apache Bench..."
	@echo "POST requests to /infer endpoint"
	ab -n 1000 -c 10 -p tests/data/sample_request.json -T application/json http://localhost/infer
