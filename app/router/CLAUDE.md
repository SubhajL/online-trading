# Go Order Router

**Technology**: Go 1.21+ | Gin | WebSocket | zerolog
**Entry Point**: `cmd/router/main.go`
**Parent Context**: This extends [../../CLAUDE.md](../../CLAUDE.md)

---

## Development Commands

### This Package

```bash
# From app/router directory
go build -o bin/router ./cmd/router     # Build
go test -v ./...                         # Run all tests
go test -v -race ./...                   # With race detection
go test -v ./internal/orders/...         # Specific package
go test -cover ./...                     # With coverage

# Linting
golangci-lint run                        # Lint
golangci-lint run --fix                  # Auto-fix
```

### From Root

```bash
make dev-router          # Start with hot reload
make test-router         # Run go test with coverage
make lint                # Lint all (includes golangci-lint)
make build-router        # Build binary
```

### Pre-PR Checklist

```bash
go fmt ./... && golangci-lint run && go test -v -race ./...
```

---

## Architecture

### Directory Structure

```
app/router/
├── cmd/
│   └── router/
│       └── main.go           # Entry point
├── internal/
│   ├── api/                  # API definitions
│   │   └── types.go          # Request/response types
│   ├── auth/                 # Authentication
│   │   └── hmac.go           # Binance HMAC signing
│   ├── binance/              # Binance integration
│   │   ├── client.go         # REST client
│   │   ├── spot.go           # Spot API
│   │   └── futures.go        # USD-M Futures API
│   ├── config/               # Configuration
│   │   └── config.go         # Env-based config
│   ├── filters/              # Order validation
│   │   └── validator.go      # Lot size, price filters
│   ├── handlers/             # HTTP handlers
│   │   ├── order.go          # Order endpoints
│   │   └── health.go         # Health endpoints
│   ├── health/               # Health checks
│   │   └── health.go         # Liveness/readiness
│   ├── metrics/              # Observability
│   │   ├── collector.go      # Prometheus metrics
│   │   └── middleware.go     # Request metrics
│   ├── models/               # Domain models
│   │   └── order.go          # Order types
│   ├── orders/               # Order management
│   │   ├── service.go        # Order service
│   │   └── reconciler.go     # Order reconciliation
│   ├── rest/                 # REST implementation
│   │   └── server.go         # Gin server setup
│   └── websocket/            # WebSocket handlers
│       ├── client.go         # WS client
│       └── stream.go         # User data stream
├── go.mod                    # Dependencies
├── go.sum                    # Dependency lock
├── Makefile                  # Build targets
└── Dockerfile                # Container image
```

### Code Organization Patterns

#### Package Structure

```go
// ✅ DO: Keep packages focused and small
// internal/orders/service.go
package orders

type Service struct {
    client    *binance.Client
    validator *filters.Validator
    metrics   *metrics.Collector
}

func NewService(client *binance.Client, ...) *Service {
    return &Service{...}
}

func (s *Service) SubmitOrder(ctx context.Context, req OrderRequest) (*Order, error) {
    // Implementation
}
```

#### Error Handling

```go
// ✅ DO: Define domain-specific errors
var (
    ErrOrderRejected    = errors.New("order rejected by exchange")
    ErrInsufficientFunds = errors.New("insufficient funds")
    ErrInvalidQuantity  = errors.New("quantity does not meet lot size")
)

// ✅ DO: Wrap errors with context
if err := s.validator.Validate(order); err != nil {
    return nil, fmt.Errorf("validate order: %w", err)
}

// ✅ DO: Use structured logging
log.Error().
    Err(err).
    Str("order_id", order.ID).
    Str("symbol", order.Symbol).
    Msg("order submission failed")
```

#### HTTP Handlers

```go
// ✅ DO: Use Gin context properly
func (h *OrderHandler) SubmitOrder(c *gin.Context) {
    var req OrderRequest
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }

    order, err := h.service.SubmitOrder(c.Request.Context(), req)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }

    c.JSON(http.StatusCreated, order)
}
```

#### Idempotency

```go
// ✅ DO: Always use client order IDs
type OrderRequest struct {
    ClientOrderID string `json:"newClientOrderId" binding:"required"`
    Symbol        string `json:"symbol" binding:"required"`
    Side          string `json:"side" binding:"required,oneof=BUY SELL"`
    Type          string `json:"type" binding:"required"`
    Quantity      string `json:"quantity" binding:"required"`
    Price         string `json:"price,omitempty"`
}

// ✅ DO: Check for duplicate before submission
if exists, _ := s.cache.Get(req.ClientOrderID); exists {
    return nil, ErrDuplicateOrder
}
```

---

## Key Files

### Core Files (understand these first)

- `cmd/router/main.go` - Entry point, DI setup
- `internal/config/config.go` - Environment configuration
- `internal/rest/server.go` - Gin router setup

### Order Flow

- `internal/handlers/order.go` - HTTP handlers for orders
- `internal/orders/service.go` - Order business logic
- `internal/filters/validator.go` - Lot size, price precision

### Binance Integration

- `internal/binance/client.go` - Base REST client
- `internal/binance/spot.go` - Spot market orders
- `internal/binance/futures.go` - USD-M Futures orders
- `internal/auth/hmac.go` - Request signing

### Health & Metrics

- `internal/health/health.go` - Liveness/readiness probes
- `internal/metrics/collector.go` - Prometheus metrics

---

## Quick Search Commands

### Find Functions

```bash
# Find function definitions
rg -n "^func " app/router/

# Find methods on a type
rg -n "func \(s \*Service\)" app/router/internal/orders/

# Find interface definitions
rg -n "^type.*interface" app/router/
```

### Find Tests

```bash
# Find all test files
fd -g "*_test.go" app/router/

# Find tests for a package
rg -n "func Test" app/router/internal/orders/

# Run specific test
go test -v -run TestSubmitOrder ./internal/orders/...
```

### Find Errors

```bash
# Find error definitions
rg -n "var.*= errors.New" app/router/

# Find error wrapping
rg -n "fmt.Errorf.*%w" app/router/
```

---

## Common Gotchas

- **Decimal Precision**: Use strings for prices/quantities to preserve precision
- **Rate Limiting**: Binance limits: 1200 req/min (weight), 10 orders/sec
- **Exchange Info**: Cache and refresh every 24h for lot size/price filters
- **Futures vs Spot**: Different endpoints, signing, and order types
- **ReduceOnly**: Required for TP orders on futures positions
- **STOP_MARKET**: Use for SL orders (not STOP_LIMIT)
- **Testnet**: Use testnet URLs for development/testing

---

## Testing Guidelines

### Unit Tests

- Location: Colocated with source (`*_test.go`)
- Pattern: Table-driven tests

```go
// ✅ DO: Use table-driven tests
func TestValidateLotSize(t *testing.T) {
    tests := []struct {
        name     string
        quantity string
        stepSize string
        want     bool
    }{
        {"valid quantity", "1.5", "0.1", true},
        {"invalid step", "1.55", "0.1", false},
        {"zero quantity", "0", "0.1", false},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got := ValidateLotSize(tt.quantity, tt.stepSize)
            if got != tt.want {
                t.Errorf("ValidateLotSize() = %v, want %v", got, tt.want)
            }
        })
    }
}
```

### Integration Tests

```go
// ✅ DO: Use build tags for integration tests
//go:build integration

func TestBinanceSpotOrder(t *testing.T) {
    if os.Getenv("BINANCE_API_KEY") == "" {
        t.Skip("BINANCE_API_KEY not set")
    }
    // Test with real API
}
```

### Running Tests

```bash
# All unit tests
go test -v ./...

# With race detection
go test -v -race ./...

# Specific package
go test -v ./internal/orders/...

# With coverage
go test -cover -coverprofile=coverage.out ./...
go tool cover -html=coverage.out
```

---

## Pre-PR Checklist

Run this before creating a PR:

```bash
# All must pass
go fmt ./... && \
goimports -w . && \
golangci-lint run && \
go test -v -race ./...
```

---

## Domain Vocabulary

Use these terms consistently:

| Term | Meaning |
|------|---------|
| `clientOrderId` | Unique order identifier (idempotency key) |
| `symbol` | Trading pair (e.g., BTCUSDT) |
| `side` | BUY or SELL |
| `type` | MARKET, LIMIT, STOP_MARKET, etc. |
| `quantity` | Order size in base asset |
| `price` | Limit price (string for precision) |
| `reduceOnly` | Only reduce existing position |
| `positionSide` | LONG, SHORT, or BOTH |
