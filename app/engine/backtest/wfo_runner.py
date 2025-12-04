"""
Walk-Forward Optimization CLI Runner

Command-line interface for running walk-forward optimization.
"""

import argparse
from decimal import Decimal
import json
import logging
from pathlib import Path
import sys

import yaml

from .wfo import WFORunner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """CLI entry point for WFO runner"""
    parser = argparse.ArgumentParser(description="Walk-Forward Optimization Runner")

    # Basic parameters
    parser.add_argument(
        "--symbol", required=True, help="Trading symbol (e.g., BTCUSDT)"
    )
    parser.add_argument("--tf", required=True, help="Timeframe (e.g., 15m, 1h)")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--config", required=True, help="Path to config.yaml")

    # WFO specific parameters
    parser.add_argument(
        "--train-days", type=int, default=90, help="Training period length (days)"
    )
    parser.add_argument(
        "--test-days", type=int, default=30, help="Testing period length (days)"
    )
    parser.add_argument(
        "--step-days", type=int, default=30, help="Step size between windows (days)"
    )

    # Optimization parameters
    parser.add_argument(
        "--param-ranges", required=True, help="JSON file with parameter ranges"
    )
    parser.add_argument("--balance", type=float, default=10000, help="Initial balance")

    # Data source
    parser.add_argument(
        "--data-source",
        default="timescale",
        choices=["timescale", "csv"],
        help="Data source",
    )
    parser.add_argument("--data-dir", help="Data directory for CSV source")
    parser.add_argument("--database-url", help="Database URL for TimescaleDB")

    # Output
    parser.add_argument(
        "--output-dir", default="artifacts/wfo", help="Output directory"
    )
    parser.add_argument("--max-workers", type=int, help="Maximum parallel workers")

    args = parser.parse_args()

    # Load parameter ranges
    try:
        with open(args.param_ranges) as f:
            parameter_ranges = json.load(f)
    except Exception as e:
        logger.error(f"Error loading parameter ranges: {e}")
        sys.exit(1)

    # Update config with WFO parameters
    try:
        config_path = Path(args.config)
        with open(config_path) as f:
            config = yaml.safe_load(f)

        if "wfo" not in config:
            config["wfo"] = {}

        config["wfo"]["train_days"] = args.train_days
        config["wfo"]["test_days"] = args.test_days
        config["wfo"]["step_days"] = args.step_days

        # Write updated config to temporary file
        temp_config_path = config_path.parent / f"temp_wfo_{config_path.name}"
        with open(temp_config_path, "w") as f:
            yaml.safe_dump(config, f)

        runner = WFORunner(str(temp_config_path))

    except Exception as e:
        logger.error(f"Error updating config: {e}")
        sys.exit(1)

    # Prepare data source kwargs
    data_source_kwargs = {}
    if args.data_source == "csv":
        if not args.data_dir:
            logger.error("--data-dir required for CSV data source")
            sys.exit(1)
        data_source_kwargs["data_directory"] = args.data_dir
    elif args.data_source == "timescale":
        database_url = (
            args.database_url or "postgresql://user:pass@localhost:5432/trading"
        )
        data_source_kwargs["database_url"] = database_url

    try:
        # Run WFO
        logger.info(f"Starting WFO for {args.symbol} {args.tf}")
        logger.info(f"Parameter ranges: {parameter_ranges}")

        result = runner.run_wfo(
            symbol=args.symbol,
            timeframe=args.tf,
            start_date=args.start,
            end_date=args.end,
            parameter_ranges=parameter_ranges,
            initial_balance=Decimal(str(args.balance)),
            data_source=args.data_source,
            max_workers=args.max_workers,
            **data_source_kwargs,
        )

        # Save results
        artifacts_path = runner.save_wfo_results(
            result,
            args.symbol,
            args.tf,
            args.start,
            args.end,
            args.output_dir,
        )

        # Print summary
        test_metrics = result.get_test_only_metrics()
        summary = result.optimization_summary

        print(f"\n{'=' * 60}")
        print("WALK-FORWARD OPTIMIZATION COMPLETED")
        print(f"{'=' * 60}")
        print(f"Results saved to: {artifacts_path}")
        print("\nOut-of-Sample Performance (Test Data Only):")
        print(f"  Total Return: {test_metrics.total_pnl_pct:.2f}%")
        print(f"  Total Trades: {test_metrics.total_trades}")
        print(f"  Hit Rate: {test_metrics.hit_rate_pct:.1f}%")
        if test_metrics.profit_factor:
            print(f"  Profit Factor: {test_metrics.profit_factor:.2f}")
        if test_metrics.sharpe_ratio:
            print(f"  Sharpe Ratio: {test_metrics.sharpe_ratio:.2f}")
        print(f"  Max Drawdown: {test_metrics.max_drawdown_pct:.2f}%")

        print("\nWFO Statistics:")
        print(f"  Total Windows: {summary.get('total_windows', 0)}")
        print(f"  Avg Test Return: {summary.get('avg_test_return', 0):.2f}%")
        print(f"  Std Test Return: {summary.get('std_test_return', 0):.2f}%")
        print(f"  Win Rate: {summary.get('win_rate', 0) * 100:.1f}%")
        print(f"  Overfitting Ratio: {summary.get('overfitting_ratio', 0):.2f}")

        print("\nParameter Stability:")
        for param, stability in result.parameter_stability.items():
            status = (
                "STABLE"
                if stability >= 0.8
                else "MODERATE"
                if stability >= 0.6
                else "UNSTABLE"
            )
            print(f"  {param}: {stability:.3f} ({status})")

        # Cleanup temporary config
        if temp_config_path.exists():
            temp_config_path.unlink()

    except Exception as e:
        logger.error(f"WFO failed: {e}")
        if temp_config_path.exists():
            temp_config_path.unlink()
        sys.exit(1)


def create_example_param_ranges():
    """Create example parameter ranges file"""
    example_ranges = {
        "fee_bps_spot": [8, 10, 12],
        "slippage_bps": [1, 2, 3],
        "tp_ladder": [
            [{"r": 1.5, "size": 0.5}, {"r": 2.0, "size": 0.5}],
            [{"r": 1.5, "size": 0.4}, {"r": 2.0, "size": 0.3}, {"r": 3.0, "size": 0.3}],
            [{"r": 2.0, "size": 0.6}, {"r": 3.0, "size": 0.4}],
        ],
    }

    print("Example parameter ranges file (save as param_ranges.json):")
    print(json.dumps(example_ranges, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--example":
        create_example_param_ranges()
    else:
        main()
