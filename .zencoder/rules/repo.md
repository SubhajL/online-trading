---
description: Repository Information Overview
alwaysApply: true
---

# Online Trading Platform Information

## Summary
A comprehensive monorepo for a real-time online trading platform with microservices architecture, featuring a Python trading engine, Go API router, NestJS BFF, and Next.js frontend.

## Structure
- **app/engine**: Python FastAPI trading engine with event-driven architecture
- **app/router**: Go API router and order execution service
- **app/bff**: NestJS Backend-for-Frontend service
- **app/ui**: Next.js frontend application
- **infra**: Infrastructure configurations (Docker, Prometheus, Grafana)
- **tests**: Test suites for various components
- **scripts**: Utility scripts for development and deployment

## Projects

### Python Trading Engine (app/engine)
**Configuration File**: app/engine/config.yaml

#### Language & Runtime
**Language**: Python
**Version**: 3.13
**Build System**: pip/setuptools
**Package Manager**: pip

#### Dependencies
**Main Dependencies**:
- fastapi>=0.109.0
- pydantic>=2.0.0
- asyncpg>=0.29.0
- numpy>=1.24.0
- pandas>=2.0.0
- websockets>=12.0
- redis>=5.0.0

#### Build & Installation
```bash
cd app/engine
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

#### Docker
**Dockerfile**: app/engine/Dockerfile
**Image**: trading-engine
**Configuration**: Runs FastAPI server with async event bus

#### Testing
**Framework**: pytest
**Test Location**: app/engine/tests
**Naming Convention**: test_*.py
**Run Command**:
```bash
cd app/engine
pytest -v --cov=app
```

### Go Router (app/router)
**Configuration File**: app/router/go.mod

#### Language & Runtime
**Language**: Go
**Version**: 1.21
**Build System**: Go modules
**Package Manager**: go mod

#### Dependencies
**Main Dependencies**:
- github.com/gin-gonic/gin v1.10.1
- github.com/gorilla/websocket v1.5.3
- github.com/rs/zerolog v1.34.0
- github.com/shopspring/decimal v1.3.1

#### Build & Installation
```bash
cd app/router
go mod download
go build -o bin/router main.go
```

#### Docker
**Dockerfile**: app/router/Dockerfile
**Image**: trading-router
**Configuration**: Handles order execution and exchange communication

#### Testing
**Framework**: Go testing package
**Test Location**: app/router/internal
**Naming Convention**: *_test.go
**Run Command**:
```bash
cd app/router
go test -v -race ./...
```

### NestJS BFF (app/bff)
**Configuration File**: app/bff/package.json

#### Language & Runtime
**Language**: TypeScript
**Version**: 5.5.3
**Build System**: NestJS CLI
**Package Manager**: pnpm

#### Dependencies
**Main Dependencies**:
- @nestjs/common ^10.3.10
- @nestjs/core ^10.3.10
- @nestjs/platform-express ^10.3.10
- @nestjs/websockets ^10.3.10
- typeorm ^0.3.20
- socket.io ^4.7.5

#### Build & Installation
```bash
cd app/bff
pnpm install
pnpm run build
```

#### Docker
**Dockerfile**: app/bff/Dockerfile
**Image**: trading-bff
**Configuration**: Serves REST/WebSocket APIs

#### Testing
**Framework**: Jest
**Test Location**: app/bff/src/**/*.spec.ts
**Run Command**:
```bash
cd app/bff
pnpm run test
```

### Next.js UI (app/ui)
**Configuration File**: app/ui/package.json

#### Language & Runtime
**Language**: TypeScript
**Version**: 5.7.3
**Build System**: Next.js
**Package Manager**: pnpm

#### Dependencies
**Main Dependencies**:
- next 15.2.0
- react ^18.3.1
- react-dom ^18.3.1
- lightweight-charts ^4.1.3
- socket.io-client ^4.8.1

#### Build & Installation
```bash
cd app/ui
pnpm install
pnpm run build
```

#### Docker
**Dockerfile**: app/ui/Dockerfile
**Image**: trading-ui
**Configuration**: Serves static assets and client-side application

#### Testing
**Framework**: Vitest
**Test Location**: app/ui/src/**/*.spec.ts
**Run Command**:
```bash
cd app/ui
pnpm run test
```

## Infrastructure

### Database
- **TimescaleDB**: PostgreSQL extension for time-series data
- **Redis**: In-memory data store for caching and pub/sub

### Monitoring
- **Prometheus**: Metrics collection
- **Grafana**: Visualization dashboards

### Deployment
- **Docker Compose**: Multi-container orchestration
- **Nginx**: Load balancer and reverse proxy