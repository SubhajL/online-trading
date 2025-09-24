#!/bin/bash
#
# Comprehensive Backtesting System Test Runner
#
# Runs unit tests, integration tests, and parity checks
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test categories
RUN_UNIT=true
RUN_INTEGRATION=true
RUN_PARITY=true
RUN_PERFORMANCE=false
VERBOSE=false
COVERAGE=false

# Parse command line arguments
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --unit-only         Run only unit tests"
    echo "  --integration-only  Run only integration tests"
    echo "  --parity-only       Run only parity tests"
    echo "  --performance       Include performance tests"
    echo "  --all               Run all tests (default)"
    echo "  --verbose           Verbose output"
    echo "  --coverage          Generate coverage report"
    echo "  --help              Show this help message"
    exit 1
}

while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --unit-only)
            RUN_UNIT=true
            RUN_INTEGRATION=false
            RUN_PARITY=false
            shift
            ;;
        --integration-only)
            RUN_UNIT=false
            RUN_INTEGRATION=true
            RUN_PARITY=false
            shift
            ;;
        --parity-only)
            RUN_UNIT=false
            RUN_INTEGRATION=false
            RUN_PARITY=true
            shift
            ;;
        --performance)
            RUN_PERFORMANCE=true
            shift
            ;;
        --all)
            RUN_UNIT=true
            RUN_INTEGRATION=true
            RUN_PARITY=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --coverage)
            COVERAGE=true
            shift
            ;;
        --help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

# Set Python path
export PYTHONPATH="$(pwd)/app/engine:$PYTHONPATH"

# Create test output directory
mkdir -p artifacts/test_results

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                       BACKTESTING SYSTEM TEST SUITE                         ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Test configuration
echo -e "${YELLOW}Test Configuration:${NC}"
echo "  Unit Tests:        $([ "$RUN_UNIT" = true ] && echo "✓" || echo "✗")"
echo "  Integration Tests: $([ "$RUN_INTEGRATION" = true ] && echo "✓" || echo "✗")"
echo "  Parity Tests:      $([ "$RUN_PARITY" = true ] && echo "✓" || echo "✗")"
echo "  Performance Tests: $([ "$RUN_PERFORMANCE" = true ] && echo "✓" || echo "✗")"
echo "  Verbose Output:    $([ "$VERBOSE" = true ] && echo "✓" || echo "✗")"
echo "  Coverage Report:   $([ "$COVERAGE" = true ] && echo "✓" || echo "✗")"
echo ""

# Build pytest arguments
PYTEST_ARGS=()
if [ "$VERBOSE" = true ]; then
    PYTEST_ARGS+=("-v" "--tb=long")
else
    PYTEST_ARGS+=("--tb=short")
fi

if [ "$COVERAGE" = true ]; then
    PYTEST_ARGS+=("--cov=app.engine.backtest" "--cov-report=html:artifacts/test_results/coverage")
fi

# Track overall success
OVERALL_SUCCESS=true

# Function to run test category
run_test_category() {
    local category="$1"
    local marker="$2"
    local description="$3"

    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE} $description${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"

    local test_args=("${PYTEST_ARGS[@]}")
    if [ -n "$marker" ]; then
        test_args+=("-m" "$marker")
    fi

    test_args+=("app/engine/backtest/test_backtest_system.py")

    echo "Running: pytest ${test_args[*]}"
    echo ""

    if pytest "${test_args[@]}"; then
        echo ""
        echo -e "${GREEN}✅ $category TESTS PASSED${NC}"
        echo ""
    else
        echo ""
        echo -e "${RED}❌ $category TESTS FAILED${NC}"
        echo ""
        OVERALL_SUCCESS=false
    fi
}

# Run Unit Tests
if [ "$RUN_UNIT" = true ]; then
    run_test_category "UNIT" "not integration and not parity and not performance" "UNIT TESTS - Testing individual components"
fi

# Run Integration Tests
if [ "$RUN_INTEGRATION" = true ]; then
    run_test_category "INTEGRATION" "integration" "INTEGRATION TESTS - Testing component interactions"
fi

# Run Parity Tests
if [ "$RUN_PARITY" = true ]; then
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE} PARITY TESTS - Ensuring backtest math matches live trading${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"

    # Run parity tests separately with special handling
    if python app/engine/backtest/test_parity.py; then
        echo ""
        echo -e "${GREEN}✅ PARITY TESTS PASSED - Backtest math matches live trading${NC}"
        echo ""
    else
        echo ""
        echo -e "${RED}❌ PARITY TESTS FAILED - Discrepancy between backtest and live math${NC}"
        echo ""
        OVERALL_SUCCESS=false
    fi
fi

# Run Performance Tests
if [ "$RUN_PERFORMANCE" = true ]; then
    run_test_category "PERFORMANCE" "performance" "PERFORMANCE TESTS - Benchmarking system performance"
fi

# Run quick smoke test
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE} SMOKE TEST - Quick system verification${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"

echo "Testing imports..."
if python -c "
from app.engine.backtest.types import BacktestConfig
from app.engine.backtest.simulator import BacktestSimulator
from app.engine.backtest.runner import BacktestRunner
from app.engine.backtest.wfo import WFORunner
from app.engine.paper.broker import PaperBroker
print('✅ All imports successful')
"; then
    echo -e "${GREEN}✅ SMOKE TEST PASSED${NC}"
else
    echo -e "${RED}❌ SMOKE TEST FAILED${NC}"
    OVERALL_SUCCESS=false
fi

echo ""

# Final results
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                              TEST RESULTS SUMMARY                           ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════════════════╝${NC}"

if [ "$OVERALL_SUCCESS" = true ]; then
    echo -e "${GREEN}"
    echo "  ██████╗  █████╗ ███████╗███████╗"
    echo "  ██╔══██╗██╔══██╗██╔════╝██╔════╝"
    echo "  ██████╔╝███████║███████╗███████╗"
    echo "  ██╔═══╝ ██╔══██║╚════██║╚════██║"
    echo "  ██║     ██║  ██║███████║███████║"
    echo "  ╚═╝     ╚═╝  ╚═╝╚══════╝╚══════╝"
    echo ""
    echo "🎉 ALL TESTS PASSED - System is ready for production!"
    echo -e "${NC}"

    if [ "$COVERAGE" = true ]; then
        echo ""
        echo "📊 Coverage report generated at: artifacts/test_results/coverage/index.html"
    fi

    exit 0
else
    echo -e "${RED}"
    echo "  ███████╗ █████╗ ██╗██╗     "
    echo "  ██╔════╝██╔══██╗██║██║     "
    echo "  █████╗  ███████║██║██║     "
    echo "  ██╔══╝  ██╔══██║██║██║     "
    echo "  ██║     ██║  ██║██║███████╗"
    echo "  ╚═╝     ╚═╝  ╚═╝╚═╝╚══════╝"
    echo ""
    echo "❌ SOME TESTS FAILED - Review output above for details"
    echo -e "${NC}"
    exit 1
fi