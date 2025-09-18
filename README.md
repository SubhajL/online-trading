# Online Trading Platform

A comprehensive monorepo for a real-time online trading platform with microservices architecture.

## Architecture

This monorepo contains the following components:

- **`app/engine`** - Python-based trading engine (FastAPI)
- **`app/router`** - Go-based API router and load balancer
- **`app/bff`** - NestJS Backend-for-Frontend service
- **`app/ui`** - Next.js frontend application
- **`infra`** - Infrastructure configurations (Docker, Prometheus, Grafana)

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Go 1.21+
- Docker & Docker Compose
- pnpm (Node package manager)

### Installation

1. **Clone the repository and navigate to it:**
   ```bash
   cd "online trader"
   ```

2. **Setup the development environment:**
   ```bash
   make setup
   ```

3. **Start all services in development mode:**
   ```bash
   make dev
   ```

### Individual Service Development

Start individual services for focused development:

```bash
# Start only the Python engine
make dev-engine

# Start only the Go router
make dev-router

# Start only the NestJS BFF
make dev-bff

# Start only the Next.js UI
make dev-ui
```

## Development Workflow

### Code Quality

```bash
# Run linting for all components
make lint

# Auto-fix linting issues
make lint-fix

# Format code
make format

# Run type checking
make typecheck
```

### Testing

```bash
# Run all tests
make test

# Run tests for specific components
make test-engine
make test-router
make test-bff
make test-ui

# Run tests in watch mode
make test-watch

# Generate coverage reports
make test-coverage
```

### Building

```bash
# Build all components
make build

# Build specific components
make build-engine
make build-router
make build-bff
make build-ui

# Build Docker images
make build-docker
```

## Configuration Files

### Root Level Configuration

- **`.gitignore`** - Comprehensive ignore patterns for Python, Node.js, Go, and IDEs
- **`.editorconfig`** - Consistent formatting across different editors
- **`.env.example`** - Template for environment variables
- **`.pre-commit-config.yaml`** - Git hooks for code quality
- **`pyproject.toml`** - Python project configuration with Ruff and MyPy
- **`pnpm-workspace.yaml`** - Node.js monorepo workspace configuration
- **`Makefile`** - Development commands and automation
- **`docker-compose.yml`** - Container orchestration for all services

### Environment Variables

Copy the example environment file and configure:

```bash
cp .env.example .env
```

Key configuration sections:
- Database (PostgreSQL, Redis)
- Binance API credentials
- Authentication & Security
- Service ports and URLs
- Monitoring and logging

## Database

### Starting Database Services

```bash
# Start PostgreSQL and Redis
make db-up

# Run database migrations
make db-migrate

# Create new migration
make db-migrate-create

# Reset database (WARNING: destroys data)
make db-reset
```

## Infrastructure

### Monitoring Stack

```bash
# Start Prometheus and Grafana
make monitoring-up

# View all service logs
make logs

# Check service status
make status
```

Access points:
- **Grafana**: http://localhost:3001 (admin/admin)
- **Prometheus**: http://localhost:9090

### Full Infrastructure

```bash
# Start all infrastructure services
make infra-up

# Stop all services
make infra-down
```

## Utilities

### Dependency Management

```bash
# Update all dependencies
make deps-update

# Audit dependencies for security issues
make deps-audit
```

### Cleanup

```bash
# Clean build artifacts
make clean

# Clean Docker resources
make clean-docker
```

### Security

```bash
# Run security checks
make security-check

# Run pre-commit hooks
make pre-commit
```

## Production Deployment

```bash
# Build production images
make prod-build

# Start production services
make prod-up

# View production logs
make prod-logs
```

## Code Quality Tools

### Python (Engine)
- **Ruff**: Fast Python linter and formatter
- **MyPy**: Static type checking
- **Bandit**: Security vulnerability scanner
- **Pytest**: Testing framework with coverage

### JavaScript/TypeScript (BFF & UI)
- **ESLint**: Code linting
- **Prettier**: Code formatting
- **TypeScript**: Static type checking
- **Jest**: Testing framework

### Go (Router)
- **go fmt**: Code formatting
- **go vet**: Static analysis
- **golangci-lint**: Comprehensive linting
- **go test**: Testing with race detection

## Git Hooks

Pre-commit hooks are configured to run automatically:
- Code formatting and linting
- Type checking
- Security scans
- Test execution
- Conventional commit message validation

Install hooks:
```bash
make setup-git-hooks
```

## Directory Structure

```
online trader/
├── app/
│   ├── engine/          # Python trading engine
│   ├── router/          # Go API router
│   ├── bff/            # NestJS backend-for-frontend
│   └── ui/             # Next.js frontend
├── infra/
│   ├── prometheus/     # Monitoring configuration
│   ├── grafana/       # Dashboard configuration
│   ├── nginx/         # Load balancer configuration
│   ├── postgres/      # Database initialization
│   └── redis/         # Cache configuration
├── .gitignore
├── .editorconfig
├── .env.example
├── .pre-commit-config.yaml
├── pyproject.toml
├── pnpm-workspace.yaml
├── Makefile
├── docker-compose.yml
└── README.md
```

## Contributing

1. Create a feature branch
2. Make your changes
3. Run the full CI pipeline: `make ci`
4. Submit a pull request

## License

MIT License - see LICENSE file for details.