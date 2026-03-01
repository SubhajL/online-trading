#!/bin/bash

# Online Trading Platform - Comprehensive Test Runner
# Based on the 114 test case analysis from UX_TESTING_MANUAL.md

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PARALLEL_WORKERS=${PARALLEL_WORKERS:-4}
TIMEOUT=${TIMEOUT:-30000}
RETRIES=${RETRIES:-2}
HEADLESS=${HEADLESS:-true}

# Test categories based on priority analysis
CRITICAL_TESTS="tests/e2e/tc01-auth tests/e2e/tc02-orders tests/e2e/tc05-order-management"
HIGH_PRIORITY_TESTS="tests/e2e/tc03-auto-trading tests/e2e/tc04-positions tests/e2e/tc08-alerts"
MEDIUM_PRIORITY_TESTS="tests/e2e/tc06-dashboard tests/e2e/tc07-balance tests/e2e/tc09-settings tests/e2e/tc10-market-data tests/e2e/tc11-history"
LOW_PRIORITY_TESTS="tests/e2e/tc12-error-handling tests/e2e/tc13-accessibility tests/e2e/tc14-performance tests/e2e/tc15-integration tests/e2e/tc16-advanced tests/e2e/tc17-admin tests/e2e/tc18-security"

print_header() {
    echo -e "${BLUE}================================================${NC}"
    echo -e "${BLUE}  Online Trading Platform - Test Execution${NC}"
    echo -e "${BLUE}================================================${NC}"
    echo ""
}

print_section() {
    echo -e "${YELLOW}>>> $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

check_prerequisites() {
    print_section "Checking Prerequisites"
    
    # Check if services are running
    if ! curl -s http://localhost:3000 > /dev/null; then
        print_error "UI service not running on port 3000"
        exit 1
    fi
    print_success "UI service is running"
    
    if ! curl -s http://localhost:8002/api/health > /dev/null; then
        print_error "BFF service not running on port 8002"
        exit 1
    fi
    print_success "BFF service is running"
    
    # Check if Playwright is installed
    if ! npx playwright --version > /dev/null 2>&1; then
        print_error "Playwright not installed. Run: npx playwright install"
        exit 1
    fi
    print_success "Playwright is installed"
    
    echo ""
}

run_test_suite() {
    local suite_name=$1
    local test_paths=$2
    local description=$3
    
    print_section "Running $suite_name Tests"
    echo "Description: $description"
    echo "Paths: $test_paths"
    echo ""
    
    local start_time=$(date +%s)
    
    if npx playwright test $test_paths \
        --workers=$PARALLEL_WORKERS \
        --timeout=$TIMEOUT \
        --retries=$RETRIES \
        --reporter=html,json,junit \
        --output-dir=test-results/$suite_name; then
        
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        print_success "$suite_name tests completed in ${duration}s"
        return 0
    else
        print_error "$suite_name tests failed"
        return 1
    fi
}

run_performance_tests() {
    print_section "Running Performance Tests"
    
    # Set performance-specific configuration
    export PERFORMANCE_MODE=true
    
    npx playwright test tests/e2e/tc14-performance \
        --workers=1 \
        --timeout=60000 \
        --retries=0 \
        --reporter=json \
        --output-dir=test-results/performance
    
    # Generate performance report
    node scripts/generate-performance-report.js
}

run_accessibility_tests() {
    print_section "Running Accessibility Tests"
    
    npx playwright test tests/e2e/tc13-accessibility \
        --workers=$PARALLEL_WORKERS \
        --timeout=$TIMEOUT \
        --retries=$RETRIES \
        --reporter=html,json \
        --output-dir=test-results/accessibility
}

run_mobile_tests() {
    print_section "Running Mobile Tests"
    
    npx playwright test \
        --project="Mobile Chrome" \
        --project="Mobile Safari" \
        --project="Tablet" \
        --workers=2 \
        --timeout=$TIMEOUT \
        --retries=$RETRIES \
        --reporter=html,json \
        --output-dir=test-results/mobile
}

generate_summary_report() {
    print_section "Generating Test Summary Report"
    
    # Create summary from all test results
    node scripts/generate-test-summary.js
    
    print_success "Test summary generated: test-results/summary.html"
}

# Main execution
main() {
    print_header
    
    # Parse command line arguments
    case "${1:-all}" in
        "critical")
            check_prerequisites
            run_test_suite "Critical" "$CRITICAL_TESTS" "Authentication, Orders, Order Management"
            ;;
        "high")
            check_prerequisites
            run_test_suite "High Priority" "$HIGH_PRIORITY_TESTS" "Auto-trading, Positions, Alerts"
            ;;
        "medium")
            check_prerequisites
            run_test_suite "Medium Priority" "$MEDIUM_PRIORITY_TESTS" "Dashboard, Balance, Settings, Market Data, History"
            ;;
        "low")
            check_prerequisites
            run_test_suite "Low Priority" "$LOW_PRIORITY_TESTS" "Error Handling, Accessibility, Performance, Integration, Advanced, Admin, Security"
            ;;
        "performance")
            check_prerequisites
            run_performance_tests
            ;;
        "accessibility")
            check_prerequisites
            run_accessibility_tests
            ;;
        "mobile")
            check_prerequisites
            run_mobile_tests
            ;;
        "all")
            check_prerequisites
            
            # Run tests in priority order
            run_test_suite "Critical" "$CRITICAL_TESTS" "Core trading functionality" || exit 1
            run_test_suite "High Priority" "$HIGH_PRIORITY_TESTS" "Advanced trading features" || exit 1
            run_test_suite "Medium Priority" "$MEDIUM_PRIORITY_TESTS" "UI and data features" || exit 1
            run_test_suite "Low Priority" "$LOW_PRIORITY_TESTS" "Edge cases and advanced features"
            
            # Run specialized tests
            run_performance_tests
            run_accessibility_tests
            run_mobile_tests
            
            generate_summary_report
            ;;
        *)
            echo "Usage: $0 {critical|high|medium|low|performance|accessibility|mobile|all}"
            echo ""
            echo "Test Categories:"
            echo "  critical      - TC1-2,5: Auth, Orders, Order Management (85% automatable)"
            echo "  high          - TC3-4,8: Auto-trading, Positions, Alerts"
            echo "  medium        - TC6-7,9-11: Dashboard, Balance, Settings, Market Data, History"
            echo "  low           - TC12-18: Error Handling, A11y, Performance, Integration, Advanced, Admin, Security"
            echo "  performance   - TC14: Performance and load testing"
            echo "  accessibility - TC13: Responsive design and accessibility"
            echo "  mobile        - Mobile and tablet testing across all categories"
            echo "  all           - Run complete test suite (114 test cases)"
            exit 1
            ;;
    esac
    
    print_success "Test execution completed!"
}

# Execute main function with all arguments
main "$@"
