.PHONY: build test clean run docker-build docker-run

# Build variables
BINARY_NAME=router
DOCKER_IMAGE=online-trader/router
VERSION?=latest

# Build the application
build:
	go build -o bin/$(BINARY_NAME) cmd/router/main.go

# Run tests
test:
	go test -v ./...

# Run tests with coverage
test-coverage:
	go test -v -coverprofile=coverage.out ./...
	go tool cover -html=coverage.out -o coverage.html

# Clean build artifacts
clean:
	rm -rf bin/
	rm -f coverage.out coverage.html

# Run the application locally
run:
	go run cmd/router/main.go

# Build Docker image
docker-build:
	docker build -t $(DOCKER_IMAGE):$(VERSION) .

# Run Docker container
docker-run:
	docker run -p 8080:8080 --env-file .env $(DOCKER_IMAGE):$(VERSION)

# Format code
fmt:
	go fmt ./...

# Lint code
lint:
	golangci-lint run

# Install dependencies
deps:
	go mod download
	go mod tidy

# Generate mocks (if using mockery)
generate:
	go generate ./...

# Development hot reload (requires air)
dev:
	air

# Run all checks
check: fmt lint test

# Help
help:
	@echo "Available targets:"
	@echo "  build         - Build the application"
	@echo "  test          - Run tests"
	@echo "  test-coverage - Run tests with coverage"
	@echo "  clean         - Clean build artifacts"
	@echo "  run           - Run the application locally"
	@echo "  docker-build  - Build Docker image"
	@echo "  docker-run    - Run Docker container"
	@echo "  fmt           - Format code"
	@echo "  lint          - Lint code"
	@echo "  deps          - Install dependencies"
	@echo "  generate      - Generate code"
	@echo "  dev           - Run with hot reload"
	@echo "  check         - Run all checks"