# ==================================================================================
# Makefile for Online Trading Platform Monorepo
# ==================================================================================

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[0;33m
BLUE := \033[0;34m
PURPLE := \033[0;35m
CYAN := \033[0;36m
WHITE := \033[0;37m
RESET := \033[0m

# Default shell
SHELL := /bin/bash

# Project configuration
PROJECT_NAME := online-trading-platform
PYTHON_VERSION := 3.11
NODE_VERSION := 18
GO_VERSION := 1.21

# Directory paths
ENGINE_DIR := app/engine
ROUTER_DIR := app/router
BFF_DIR := app/bff
UI_DIR := app/ui
INFRA_DIR := infra

# Docker configuration
DOCKER_COMPOSE_FILE := docker-compose.yml
DOCKER_COMPOSE_DEV_FILE := docker-compose.dev.yml

# Default target
.DEFAULT_GOAL := help

# ==================================================================================
# Help
# ==================================================================================

.PHONY: help
help: ## Show this help message
	@echo "$(CYAN)Online Trading Platform - Development Commands$(RESET)"
	@echo ""
	@echo "$(YELLOW)Available commands:$(RESET)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(YELLOW)Usage:$(RESET)"
	@echo "  make <command>"
	@echo ""

# ==================================================================================
# Environment Setup
# ==================================================================================

.PHONY: setup
setup: setup-python setup-node setup-go setup-git-hooks ## Complete development environment setup
	@echo "$(GREEN)✅ Development environment setup complete!$(RESET)"

.PHONY: setup-python
setup-python: ## Setup Python environment for engine
	@echo "$(BLUE)🐍 Setting up Python environment...$(RESET)"
	@cd $(ENGINE_DIR) && \
		python -m venv .venv && \
		source .venv/bin/activate && \
		pip install --upgrade pip && \
		pip install -e ".[dev]"
	@echo "$(GREEN)✅ Python environment ready$(RESET)"

.PHONY: setup-node
setup-node: ## Setup Node.js dependencies
	@echo "$(BLUE)📦 Setting up Node.js dependencies...$(RESET)"
	@if ! command -v pnpm &> /dev/null; then \
		echo "$(YELLOW)Installing pnpm...$(RESET)"; \
		npm install -g pnpm; \
	fi
	@pnpm install
	@echo "$(GREEN)✅ Node.js dependencies installed$(RESET)"

.PHONY: setup-go
setup-go: ## Setup Go dependencies
	@echo "$(BLUE)🔧 Setting up Go dependencies...$(RESET)"
	@cd $(ROUTER_DIR) && go mod download
	@echo "$(GREEN)✅ Go dependencies ready$(RESET)"

.PHONY: setup-git-hooks
setup-git-hooks: ## Install git hooks
	@echo "$(BLUE)🔗 Setting up git hooks...$(RESET)"
	@if command -v pre-commit &> /dev/null; then \
		pre-commit install; \
		pre-commit install --hook-type commit-msg; \
		echo "$(GREEN)✅ Git hooks installed$(RESET)"; \
	else \
		echo "$(YELLOW)⚠️  pre-commit not found, skipping git hooks setup$(RESET)"; \
	fi

# ==================================================================================
# Development
# ==================================================================================

.PHONY: dev
dev: ## Start all services in development mode
	@echo "$(BLUE)🚀 Starting all services in development mode...$(RESET)"
	@docker-compose -f $(DOCKER_COMPOSE_DEV_FILE) up --build

.PHONY: dev-engine
dev-engine: ## Start Python engine in development mode
	@echo "$(BLUE)🐍 Starting Python engine...$(RESET)"
	@cd $(ENGINE_DIR) && \
		source .venv/bin/activate && \
		uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: dev-router
dev-router: ## Start Go router in development mode
	@echo "$(BLUE)🔧 Starting Go router...$(RESET)"
	@cd $(ROUTER_DIR) && \
		go run main.go

.PHONY: dev-bff
dev-bff: ## Start NestJS BFF in development mode
	@echo "$(BLUE)📱 Starting NestJS BFF...$(RESET)"
	@cd $(BFF_DIR) && \
		pnpm run start:dev

.PHONY: dev-ui
dev-ui: ## Start Next.js UI in development mode
	@echo "$(BLUE)🎨 Starting Next.js UI...$(RESET)"
	@cd $(UI_DIR) && \
		pnpm run dev

.PHONY: dev-stop
dev-stop: ## Stop all development services
	@echo "$(YELLOW)🛑 Stopping all services...$(RESET)"
	@docker-compose -f $(DOCKER_COMPOSE_DEV_FILE) down

# ==================================================================================
# Building
# ==================================================================================

.PHONY: build
build: build-engine build-router build-bff build-ui ## Build all components
	@echo "$(GREEN)✅ All components built successfully$(RESET)"

.PHONY: build-engine
build-engine: ## Build Python engine
	@echo "$(BLUE)🐍 Building Python engine...$(RESET)"
	@cd $(ENGINE_DIR) && \
		source .venv/bin/activate && \
		python -m build

.PHONY: build-router
build-router: ## Build Go router
	@echo "$(BLUE)🔧 Building Go router...$(RESET)"
	@cd $(ROUTER_DIR) && \
		go build -o bin/router main.go

.PHONY: build-bff
build-bff: ## Build NestJS BFF
	@echo "$(BLUE)📱 Building NestJS BFF...$(RESET)"
	@cd $(BFF_DIR) && \
		pnpm run build

.PHONY: build-ui
build-ui: ## Build Next.js UI
	@echo "$(BLUE)🎨 Building Next.js UI...$(RESET)"
	@cd $(UI_DIR) && \
		pnpm run build

.PHONY: build-docker
build-docker: ## Build all Docker images
	@echo "$(BLUE)🐳 Building Docker images...$(RESET)"
	@docker-compose build

# ==================================================================================
# Testing
# ==================================================================================

.PHONY: test
test: test-engine test-router test-bff test-ui ## Run all tests
	@echo "$(GREEN)✅ All tests completed$(RESET)"

.PHONY: test-engine
test-engine: ## Run Python engine tests
	@echo "$(BLUE)🐍 Running Python engine tests...$(RESET)"
	@cd $(ENGINE_DIR) && \
		source .venv/bin/activate && \
		pytest -v --cov=app --cov-report=term-missing --cov-report=html

.PHONY: test-router
test-router: ## Run Go router tests
	@echo "$(BLUE)🔧 Running Go router tests...$(RESET)"
	@cd $(ROUTER_DIR) && \
		go test -v -race -coverprofile=coverage.out ./...

.PHONY: test-bff
test-bff: ## Run NestJS BFF tests
	@echo "$(BLUE)📱 Running NestJS BFF tests...$(RESET)"
	@cd $(BFF_DIR) && \
		pnpm run test

.PHONY: test-ui
test-ui: ## Run Next.js UI tests
	@echo "$(BLUE)🎨 Running Next.js UI tests...$(RESET)"
	@cd $(UI_DIR) && \
		pnpm run test

.PHONY: test-watch
test-watch: ## Run tests in watch mode
	@echo "$(BLUE)👀 Running tests in watch mode...$(RESET)"
	@pnpm run test:watch

.PHONY: test-coverage
test-coverage: ## Generate test coverage reports
	@echo "$(BLUE)📊 Generating test coverage reports...$(RESET)"
	@make test-engine
	@make test-router
	@cd $(BFF_DIR) && pnpm run test:cov
	@cd $(UI_DIR) && pnpm run test:coverage

# ==================================================================================
# Code Quality
# ==================================================================================

.PHONY: lint
lint: lint-engine lint-router lint-bff lint-ui ## Run linting for all components
	@echo "$(GREEN)✅ Linting completed$(RESET)"

.PHONY: lint-engine
lint-engine: ## Run Python linting
	@echo "$(BLUE)🐍 Linting Python code...$(RESET)"
	@cd $(ENGINE_DIR) && \
		source .venv/bin/activate && \
		ruff check . && \
		mypy .

.PHONY: lint-router
lint-router: ## Run Go linting
	@echo "$(BLUE)🔧 Linting Go code...$(RESET)"
	@cd $(ROUTER_DIR) && \
		go vet ./... && \
		golangci-lint run

.PHONY: lint-bff
lint-bff: ## Run NestJS linting
	@echo "$(BLUE)📱 Linting NestJS code...$(RESET)"
	@cd $(BFF_DIR) && \
		pnpm run lint

.PHONY: lint-ui
lint-ui: ## Run Next.js linting
	@echo "$(BLUE)🎨 Linting Next.js code...$(RESET)"
	@cd $(UI_DIR) && \
		pnpm run lint

.PHONY: lint-fix
lint-fix: ## Auto-fix linting issues
	@echo "$(BLUE)🔧 Auto-fixing linting issues...$(RESET)"
	@cd $(ENGINE_DIR) && source .venv/bin/activate && ruff check --fix .
	@cd $(BFF_DIR) && pnpm run lint:fix
	@cd $(UI_DIR) && pnpm run lint:fix

.PHONY: format
format: ## Format all code
	@echo "$(BLUE)✨ Formatting code...$(RESET)"
	@cd $(ENGINE_DIR) && source .venv/bin/activate && ruff format .
	@cd $(ROUTER_DIR) && go fmt ./...
	@pnpm run format

.PHONY: format-check
format-check: ## Check code formatting
	@echo "$(BLUE)📋 Checking code formatting...$(RESET)"
	@cd $(ENGINE_DIR) && source .venv/bin/activate && ruff format --check .
	@cd $(ROUTER_DIR) && test -z $$(gofmt -l .)
	@pnpm run format:check

.PHONY: typecheck
typecheck: ## Run type checking
	@echo "$(BLUE)🔍 Running type checks...$(RESET)"
	@cd $(ENGINE_DIR) && source .venv/bin/activate && mypy .
	@pnpm run typecheck

# ==================================================================================
# Database
# ==================================================================================

.PHONY: db-up
db-up: ## Start database services
	@echo "$(BLUE)🗄️  Starting database services...$(RESET)"
	@docker-compose up -d postgres redis

.PHONY: db-down
db-down: ## Stop database services
	@echo "$(YELLOW)🗄️  Stopping database services...$(RESET)"
	@docker-compose down postgres redis

.PHONY: db-migrate
db-migrate: ## Run database migrations
	@echo "$(BLUE)🗄️  Running database migrations...$(RESET)"
	@cd $(ENGINE_DIR) && \
		source .venv/bin/activate && \
		alembic upgrade head

.PHONY: db-migrate-create
db-migrate-create: ## Create new database migration
	@echo "$(BLUE)🗄️  Creating new migration...$(RESET)"
	@read -p "Migration name: " name; \
	cd $(ENGINE_DIR) && \
		source .venv/bin/activate && \
		alembic revision --autogenerate -m "$$name"

.PHONY: db-reset
db-reset: ## Reset database (WARNING: destroys all data)
	@echo "$(RED)⚠️  WARNING: This will destroy all database data!$(RESET)"
	@read -p "Are you sure? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		docker-compose down -v; \
		docker-compose up -d postgres redis; \
		sleep 5; \
		make db-migrate; \
	fi

# ==================================================================================
# Infrastructure
# ==================================================================================

.PHONY: infra-up
infra-up: ## Start all infrastructure services
	@echo "$(BLUE)🏗️  Starting infrastructure services...$(RESET)"
	@docker-compose up -d

.PHONY: infra-down
infra-down: ## Stop all infrastructure services
	@echo "$(YELLOW)🏗️  Stopping infrastructure services...$(RESET)"
	@docker-compose down

.PHONY: infra-logs
infra-logs: ## View infrastructure logs
	@docker-compose logs -f

.PHONY: monitoring-up
monitoring-up: ## Start monitoring stack (Prometheus, Grafana)
	@echo "$(BLUE)📊 Starting monitoring stack...$(RESET)"
	@docker-compose up -d prometheus grafana

.PHONY: monitoring-down
monitoring-down: ## Stop monitoring stack
	@echo "$(YELLOW)📊 Stopping monitoring stack...$(RESET)"
	@docker-compose down prometheus grafana

# ==================================================================================
# Utilities
# ==================================================================================

.PHONY: clean
clean: ## Clean all build artifacts and dependencies
	@echo "$(YELLOW)🧹 Cleaning build artifacts...$(RESET)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".next" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true
	@cd $(ROUTER_DIR) && rm -f bin/router 2>/dev/null || true
	@echo "$(GREEN)✅ Cleanup completed$(RESET)"

.PHONY: clean-docker
clean-docker: ## Clean Docker containers, images, and volumes
	@echo "$(YELLOW)🐳 Cleaning Docker resources...$(RESET)"
	@docker-compose down -v --remove-orphans
	@docker system prune -f
	@docker volume prune -f

.PHONY: deps-update
deps-update: ## Update all dependencies
	@echo "$(BLUE)📦 Updating dependencies...$(RESET)"
	@cd $(ENGINE_DIR) && source .venv/bin/activate && pip install --upgrade pip && pip install -e ".[dev]" --upgrade
	@pnpm update --recursive
	@cd $(ROUTER_DIR) && go get -u ./... && go mod tidy

.PHONY: deps-audit
deps-audit: ## Audit dependencies for security issues
	@echo "$(BLUE)🔍 Auditing dependencies...$(RESET)"
	@cd $(ENGINE_DIR) && source .venv/bin/activate && pip-audit
	@pnpm audit
	@cd $(ROUTER_DIR) && go list -json -deps ./... | nancy sleuth

.PHONY: logs
logs: ## Show logs from all services
	@docker-compose logs -f --tail=100

.PHONY: status
status: ## Show status of all services
	@echo "$(BLUE)📊 Service Status:$(RESET)"
	@docker-compose ps

.PHONY: shell-engine
shell-engine: ## Open shell in Python engine container
	@docker-compose exec engine bash

.PHONY: shell-router
shell-router: ## Open shell in Go router container
	@docker-compose exec router sh

.PHONY: shell-bff
shell-bff: ## Open shell in NestJS BFF container
	@docker-compose exec bff sh

.PHONY: pre-commit
pre-commit: ## Run pre-commit hooks on all files
	@echo "$(BLUE)🔗 Running pre-commit hooks...$(RESET)"
	@pre-commit run --all-files

.PHONY: security-check
security-check: ## Run security checks
	@echo "$(BLUE)🔒 Running security checks...$(RESET)"
	@cd $(ENGINE_DIR) && source .venv/bin/activate && bandit -r . -f json || true
	@pnpm audit || true
	@cd $(ROUTER_DIR) && gosec ./... || true

# ==================================================================================
# Production
# ==================================================================================

.PHONY: prod-build
prod-build: ## Build production images
	@echo "$(BLUE)🏭 Building production images...$(RESET)"
	@docker-compose -f docker-compose.prod.yml build

.PHONY: prod-up
prod-up: ## Start production services
	@echo "$(BLUE)🏭 Starting production services...$(RESET)"
	@docker-compose -f docker-compose.prod.yml up -d

.PHONY: prod-down
prod-down: ## Stop production services
	@echo "$(YELLOW)🏭 Stopping production services...$(RESET)"
	@docker-compose -f docker-compose.prod.yml down

.PHONY: prod-logs
prod-logs: ## View production logs
	@docker-compose -f docker-compose.prod.yml logs -f

# ==================================================================================
# CI/CD
# ==================================================================================

.PHONY: ci
ci: lint test build ## Run full CI pipeline
	@echo "$(GREEN)✅ CI pipeline completed successfully$(RESET)"

.PHONY: release
release: ## Create a new release
	@echo "$(BLUE)🚀 Creating new release...$(RESET)"
	@./scripts/release.sh

# ==================================================================================
# Documentation
# ==================================================================================

.PHONY: docs
docs: ## Generate documentation
	@echo "$(BLUE)📚 Generating documentation...$(RESET)"
	@cd $(ENGINE_DIR) && source .venv/bin/activate && mkdocs build

.PHONY: docs-serve
docs-serve: ## Serve documentation locally
	@echo "$(BLUE)📚 Serving documentation...$(RESET)"
	@cd $(ENGINE_DIR) && source .venv/bin/activate && mkdocs serve

# ==================================================================================
# Backup and Restore
# ==================================================================================

.PHONY: backup
backup: ## Create database backup
	@echo "$(BLUE)💾 Creating database backup...$(RESET)"
	@./scripts/backup.sh

.PHONY: restore
restore: ## Restore database from backup
	@echo "$(BLUE)💾 Restoring database from backup...$(RESET)"
	@./scripts/restore.sh

# ==================================================================================
# Special targets
# ==================================================================================

.PHONY: check-tools
check-tools: ## Check if required tools are installed
	@echo "$(BLUE)🔧 Checking required tools...$(RESET)"
	@command -v python3 >/dev/null 2>&1 || { echo "$(RED)❌ Python 3 is required$(RESET)"; exit 1; }
	@command -v node >/dev/null 2>&1 || { echo "$(RED)❌ Node.js is required$(RESET)"; exit 1; }
	@command -v go >/dev/null 2>&1 || { echo "$(RED)❌ Go is required$(RESET)"; exit 1; }
	@command -v docker >/dev/null 2>&1 || { echo "$(RED)❌ Docker is required$(RESET)"; exit 1; }
	@command -v docker-compose >/dev/null 2>&1 || { echo "$(RED)❌ Docker Compose is required$(RESET)"; exit 1; }
	@echo "$(GREEN)✅ All required tools are installed$(RESET)"

# ==================================================================================
# Contract Generation
# ==================================================================================

.PHONY: contracts
contracts: ## Generate typed models from JSONSchema contracts
	@echo "$(BLUE)📝 Generating contract models from JSONSchema...$(RESET)"
	@python3 scripts/codegen_contracts.py
	@echo "$(GREEN)✅ Contract generation complete$(RESET)"

# Prevent make from interpreting file names as targets
.PHONY: $(shell grep -E '^[a-zA-Z_-]+:' $(MAKEFILE_LIST) | awk -F':' '{print $$1}')