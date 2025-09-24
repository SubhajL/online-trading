#!/bin/bash
#
# Walk-Forward Optimization Runner Script
#
# Usage: ./scripts/run_wfo.sh --symbol BTCUSDT --tf 1h --start 2024-01-01 --end 2024-12-31 --param-ranges params.json
#
# This script runs walk-forward optimization with parameter tuning.
#

set -e

# Default values
CONFIG_FILE="config.yaml"
DATA_SOURCE="timescale"
DATABASE_URL="postgresql://postgres:password@localhost:5432/trading"
BALANCE=10000
OUTPUT_DIR="artifacts/wfo"
TRAIN_DAYS=90
TEST_DAYS=30
STEP_DAYS=30
MAX_WORKERS=""

# Print usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Required Options:"
    echo "  --symbol SYMBOL         Trading symbol (e.g., BTCUSDT)"
    echo "  --tf TIMEFRAME          Timeframe (e.g., 15m, 1h, 4h, 1d)"
    echo "  --start DATE            Start date (YYYY-MM-DD)"
    echo "  --end DATE              End date (YYYY-MM-DD)"
    echo "  --param-ranges FILE     JSON file with parameter ranges"
    echo ""
    echo "Optional Options:"
    echo "  --config FILE           Config file path (default: config.yaml)"
    echo "  --balance AMOUNT        Initial balance (default: 10000)"
    echo "  --train-days DAYS       Training period length (default: 90)"
    echo "  --test-days DAYS        Testing period length (default: 30)"
    echo "  --step-days DAYS        Step between windows (default: 30)"
    echo "  --data-source TYPE      Data source: timescale, csv (default: timescale)"
    echo "  --database-url URL      Database URL (default: postgresql://postgres:password@localhost:5432/trading)"
    echo "  --data-dir DIR          Data directory for CSV source"
    echo "  --output-dir DIR        Output directory (default: artifacts/wfo)"
    echo "  --max-workers N         Max parallel workers"
    echo "  --help                  Show this help message"
    echo ""
    echo "Parameter Ranges File Format (JSON):"
    echo "{"
    echo "  \"fee_bps_spot\": [8, 10, 12],"
    echo "  \"slippage_bps\": [1, 2, 3],"
    echo "  \"tp_ladder\": ["
    echo "    [{\"r\": 1.5, \"size\": 0.5}, {\"r\": 2.0, \"size\": 0.5}],"
    echo "    [{\"r\": 1.5, \"size\": 0.4}, {\"r\": 2.0, \"size\": 0.3}, {\"r\": 3.0, \"size\": 0.3}]"
    echo "  ]"
    echo "}"
    echo ""
    echo "Examples:"
    echo "  # Basic WFO"
    echo "  $0 --symbol BTCUSDT --tf 1h --start 2024-01-01 --end 2024-12-31 \\"
    echo "     --param-ranges param_ranges.json"
    echo ""
    echo "  # WFO with custom windows"
    echo "  $0 --symbol ETHUSDT --tf 4h --start 2024-01-01 --end 2024-12-31 \\"
    echo "     --param-ranges params.json --train-days 120 --test-days 60 --step-days 45"
    echo ""
    echo "  # Generate example parameter ranges file"
    echo "  python -m backtest.wfo_runner --example > param_ranges.json"
    exit 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --symbol)
            SYMBOL="$2"
            shift 2
            ;;
        --tf)
            TIMEFRAME="$2"
            shift 2
            ;;
        --start)
            START_DATE="$2"
            shift 2
            ;;
        --end)
            END_DATE="$2"
            shift 2
            ;;
        --param-ranges)
            PARAM_RANGES="$2"
            shift 2
            ;;
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --balance)
            BALANCE="$2"
            shift 2
            ;;
        --train-days)
            TRAIN_DAYS="$2"
            shift 2
            ;;
        --test-days)
            TEST_DAYS="$2"
            shift 2
            ;;
        --step-days)
            STEP_DAYS="$2"
            shift 2
            ;;
        --data-source)
            DATA_SOURCE="$2"
            shift 2
            ;;
        --database-url)
            DATABASE_URL="$2"
            shift 2
            ;;
        --data-dir)
            DATA_DIR="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --max-workers)
            MAX_WORKERS="$2"
            shift 2
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

# Check required parameters
if [[ -z "$SYMBOL" || -z "$TIMEFRAME" || -z "$START_DATE" || -z "$END_DATE" || -z "$PARAM_RANGES" ]]; then
    echo "Error: Missing required parameters"
    echo ""
    usage
fi

# Validate files exist
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Error: Config file not found: $CONFIG_FILE"
    exit 1
fi

if [[ ! -f "$PARAM_RANGES" ]]; then
    echo "Error: Parameter ranges file not found: $PARAM_RANGES"
    echo ""
    echo "You can generate an example file with:"
    echo "python -m backtest.wfo_runner --example > param_ranges.json"
    exit 1
fi

# Validate data directory for CSV source
if [[ "$DATA_SOURCE" == "csv" && -z "$DATA_DIR" ]]; then
    echo "Error: --data-dir required when using CSV data source"
    exit 1
fi

if [[ "$DATA_SOURCE" == "csv" && ! -d "$DATA_DIR" ]]; then
    echo "Error: Data directory not found: $DATA_DIR"
    exit 1
fi

# Calculate estimated windows and combinations
start_epoch=$(date -d "$START_DATE" +%s)
end_epoch=$(date -d "$END_DATE" +%s)
total_days=$(( (end_epoch - start_epoch) / 86400 ))
window_days=$(( TRAIN_DAYS + TEST_DAYS ))
estimated_windows=$(( (total_days - window_days) / STEP_DAYS + 1 ))

# Count parameter combinations
param_count=$(python3 -c "
import json
with open('$PARAM_RANGES') as f:
    ranges = json.load(f)
count = 1
for values in ranges.values():
    count *= len(values)
print(count)
")

total_backtests=$(( estimated_windows * param_count ))

# Print configuration
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                       WALK-FORWARD OPTIMIZATION CONFIGURATION               ║"
echo "╠══════════════════════════════════════════════════════════════════════════════╣"
echo "║ Symbol:            $SYMBOL"
echo "║ Timeframe:         $TIMEFRAME"
echo "║ Start Date:        $START_DATE"
echo "║ End Date:          $END_DATE"
echo "║ Initial Balance:   \$$BALANCE"
echo "║ Training Days:     $TRAIN_DAYS"
echo "║ Testing Days:      $TEST_DAYS"
echo "║ Step Days:         $STEP_DAYS"
echo "║ Data Source:       $DATA_SOURCE"
echo "║ Config File:       $CONFIG_FILE"
echo "║ Param Ranges:     $PARAM_RANGES"
echo "║ Output Dir:        $OUTPUT_DIR"
if [[ -n "$MAX_WORKERS" ]]; then
    echo "║ Max Workers:       $MAX_WORKERS"
fi
echo "╠══════════════════════════════════════════════════════════════════════════════╣"
echo "║ Estimated Windows: $estimated_windows"
echo "║ Param Combinations: $param_count"
echo "║ Total Backtests:   $total_backtests"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Confirm execution for large runs
if [[ $total_backtests -gt 1000 ]]; then
    echo "⚠️  WARNING: This will run $total_backtests backtests, which may take a very long time."
    echo ""
    read -p "Do you want to continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
    echo ""
fi

# Build command arguments
CMD_ARGS=(
    --symbol "$SYMBOL"
    --tf "$TIMEFRAME"
    --start "$START_DATE"
    --end "$END_DATE"
    --param-ranges "$PARAM_RANGES"
    --config "$CONFIG_FILE"
    --balance "$BALANCE"
    --train-days "$TRAIN_DAYS"
    --test-days "$TEST_DAYS"
    --step-days "$STEP_DAYS"
    --data-source "$DATA_SOURCE"
    --output-dir "$OUTPUT_DIR"
)

if [[ "$DATA_SOURCE" == "csv" ]]; then
    CMD_ARGS+=(--data-dir "$DATA_DIR")
else
    CMD_ARGS+=(--database-url "$DATABASE_URL")
fi

if [[ -n "$MAX_WORKERS" ]]; then
    CMD_ARGS+=(--max-workers "$MAX_WORKERS")
fi

# Set Python path
export PYTHONPATH="$(pwd)/app/engine:$PYTHONPATH"

# Run WFO
echo "Starting Walk-Forward Optimization..."
echo "This may take a long time depending on the parameter space..."
echo ""

start_time=$(date +%s)

python -m backtest.wfo_runner "${CMD_ARGS[@]}"

end_time=$(date +%s)
runtime=$(( end_time - start_time ))
hours=$(( runtime / 3600 ))
minutes=$(( (runtime % 3600) / 60 ))
seconds=$(( runtime % 60 ))

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                        WALK-FORWARD OPTIMIZATION COMPLETED                  ║"
echo "║                                                                              ║"
echo "║ Total Runtime: ${hours}h ${minutes}m ${seconds}s"
echo "║ Backtests Run: $total_backtests"
echo "║ Results saved in: $OUTPUT_DIR"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "📊 Review the results:"
echo "   - wfo_report.json: Main performance metrics"
echo "   - windows.csv: Detailed window-by-window results"
echo "   - parameters.json: Parameter stability analysis"
echo "   - Charts: Visual performance analysis"