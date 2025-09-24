#!/bin/bash
#
# Backtest Runner Script
#
# Usage: ./scripts/run_backtest.sh --symbol BTCUSDT --tf 15m --start 2024-01-01 --end 2024-03-31
#
# This script runs a single backtest with the specified parameters.
#

set -e

# Default values
CONFIG_FILE="config.yaml"
DATA_SOURCE="timescale"
DATABASE_URL="postgresql://postgres:password@localhost:5432/trading"
BALANCE=10000
OUTPUT_DIR="artifacts/backtest"

# Print usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Required Options:"
    echo "  --symbol SYMBOL     Trading symbol (e.g., BTCUSDT)"
    echo "  --tf TIMEFRAME      Timeframe (e.g., 15m, 1h, 4h, 1d)"
    echo "  --start DATE        Start date (YYYY-MM-DD)"
    echo "  --end DATE          End date (YYYY-MM-DD)"
    echo ""
    echo "Optional Options:"
    echo "  --config FILE       Config file path (default: config.yaml)"
    echo "  --balance AMOUNT    Initial balance (default: 10000)"
    echo "  --data-source TYPE  Data source: timescale, csv (default: timescale)"
    echo "  --database-url URL  Database URL (default: postgresql://postgres:password@localhost:5432/trading)"
    echo "  --data-dir DIR      Data directory for CSV source"
    echo "  --output-dir DIR    Output directory (default: artifacts/backtest)"
    echo "  --save-db          Save results to database"
    echo "  --help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  # Basic backtest"
    echo "  $0 --symbol BTCUSDT --tf 15m --start 2024-01-01 --end 2024-03-31"
    echo ""
    echo "  # Backtest with CSV data"
    echo "  $0 --symbol BTCUSDT --tf 1h --start 2024-01-01 --end 2024-02-29 \\"
    echo "     --data-source csv --data-dir ./data/csv"
    echo ""
    echo "  # Backtest with custom balance and save to database"
    echo "  $0 --symbol ETHUSDT --tf 4h --start 2024-01-01 --end 2024-06-30 \\"
    echo "     --balance 50000 --save-db"
    exit 1
}

# Parse command line arguments
POSITIONAL=()
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
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --balance)
            BALANCE="$2"
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
        --save-db)
            SAVE_DB="--save-db"
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

# Check required parameters
if [[ -z "$SYMBOL" || -z "$TIMEFRAME" || -z "$START_DATE" || -z "$END_DATE" ]]; then
    echo "Error: Missing required parameters"
    echo ""
    usage
fi

# Validate config file exists
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Error: Config file not found: $CONFIG_FILE"
    echo "Please create config.yaml or specify --config path"
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

# Print configuration
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                               BACKTEST CONFIGURATION                         ║"
echo "╠══════════════════════════════════════════════════════════════════════════════╣"
echo "║ Symbol:        $SYMBOL"
echo "║ Timeframe:     $TIMEFRAME"
echo "║ Start Date:    $START_DATE"
echo "║ End Date:      $END_DATE"
echo "║ Initial Balance: \$$BALANCE"
echo "║ Data Source:   $DATA_SOURCE"
echo "║ Config File:   $CONFIG_FILE"
echo "║ Output Dir:    $OUTPUT_DIR"
if [[ "$DATA_SOURCE" == "csv" ]]; then
    echo "║ Data Directory: $DATA_DIR"
else
    echo "║ Database URL:  $DATABASE_URL"
fi
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Build command arguments
CMD_ARGS=(
    --symbol "$SYMBOL"
    --tf "$TIMEFRAME"
    --start "$START_DATE"
    --end "$END_DATE"
    --config "$CONFIG_FILE"
    --balance "$BALANCE"
    --data-source "$DATA_SOURCE"
    --output-dir "$OUTPUT_DIR"
)

if [[ "$DATA_SOURCE" == "csv" ]]; then
    CMD_ARGS+=(--data-dir "$DATA_DIR")
else
    CMD_ARGS+=(--database-url "$DATABASE_URL")
fi

if [[ -n "$SAVE_DB" ]]; then
    CMD_ARGS+=(--save-db)
fi

# Set Python path to include engine
export PYTHONPATH="$(pwd)/app/engine:$PYTHONPATH"

# Run backtest
echo "Starting backtest..."
echo ""

python -m backtest.runner "${CMD_ARGS[@]}"

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                              BACKTEST COMPLETED                             ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"