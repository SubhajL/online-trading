"""
Single backtest runner with CLI interface.
"""

import argparse
import asyncio
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import time

import yaml

from ..models import TimeFrame
from .charts import ChartGenerator
from .dataset import StreamingDataset, create_dataset, parse_utc_date
from .metrics import MetricsCalculator
from .serializers import ResultSerializer
from .simulator import BacktestSimulator
from .types import BacktestConfig, BacktestResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BacktestRunner:
    """
    Single backtest execution runner.
    """

    def __init__(self, config_path: str):
        """
        Initialize backtest runner.

        Args:
            config_path: Path to config.yaml file
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> BacktestConfig:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Backtest config file not found: {self.config_path}")

        try:
            with open(self.config_path) as file:
                data = yaml.safe_load(file) or {}

            backtest_data = data.get("backtest")
            if backtest_data is None and "backtesting" in data:
                logger.warning(
                    "Config %s has no 'backtest' section; falling back to the 'backtesting' alias",
                    self.config_path,
                )
                backtest_data = data["backtesting"]
            if backtest_data is None:
                logger.warning(
                    "Config %s has no 'backtest' section; using BacktestConfig defaults",
                    self.config_path,
                )
                backtest_data = {}

            return BacktestConfig(
                fee_bps_spot=Decimal(str(backtest_data.get("fee_bps_spot", 10))),
                slippage_bps=Decimal(str(backtest_data.get("slippage_bps", 2))),
                funding_model=backtest_data.get("funding_model", "disabled"),
                session_enabled=backtest_data.get("session", {}).get("enabled", True),
                session_exclude=backtest_data.get("session", {}).get("exclude", []),
                news_block_before_min=backtest_data.get("news_block", {}).get(
                    "before_min",
                    15,
                ),
                news_block_after_min=backtest_data.get("news_block", {}).get(
                    "after_min",
                    15,
                ),
                tp_ladder=backtest_data.get("rr", {}).get(
                    "tp_ladder",
                    [
                        {"r": Decimal("1.5"), "size": Decimal("0.4")},
                        {"r": Decimal("2.0"), "size": Decimal("0.3")},
                        {"r": Decimal("3.0"), "size": Decimal("0.3")},
                    ],
                ),
                move_to_breakeven_on=backtest_data.get("rr", {}).get(
                    "move_to_breakeven_on",
                    "TP1",
                ),
                trail_after=backtest_data.get("rr", {}).get("trail_after", "TP2"),
                pivot_n=int(backtest_data.get("pivot_n", 3)),
                retest_max_wait_bars=int(backtest_data.get("retest_max_wait_bars", 8)),
                cooldown_seconds=int(backtest_data.get("cooldown_seconds", 300)),
                risk_per_trade=Decimal(str(backtest_data.get("risk_per_trade", "0.005"))),
                warmup_bars=int(backtest_data.get("warmup_bars", 50)),
                htf_ema_period=int(backtest_data.get("htf_ema_period", 0)),
                htf_ema_fast=int(backtest_data.get("htf_ema_fast", 0)),
                min_stop_bps=Decimal(str(backtest_data.get("min_stop_bps", 0))),
                invert_signals=bool(backtest_data.get("invert_signals", False)),
                signal_source=str(backtest_data.get("signal_source", "smc_retest")),
                allow_short=bool(backtest_data.get("allow_short", False)),
                atr_period=int(backtest_data.get("atr_period", 14)),
                atr_stop_mult=Decimal(str(backtest_data.get("atr_stop_mult", 2))),
                sma_period=int(backtest_data.get("sma_period", 200)),
                tsmom_lookback=int(backtest_data.get("tsmom_lookback", 28)),
                tsmom_deadband_bps=Decimal(str(backtest_data.get("tsmom_deadband_bps", 0))),
                ema_fast=int(backtest_data.get("ema_fast", 10)),
                ema_slow=int(backtest_data.get("ema_slow", 40)),
                donchian_entry=int(backtest_data.get("donchian_entry", 20)),
                donchian_exit=int(backtest_data.get("donchian_exit", 10)),
                max_hold_bars=int(backtest_data.get("max_hold_bars", 0)),
                trend_tp_r=Decimal(str(backtest_data.get("trend_tp_r", 0))),
                sizing_mode=str(backtest_data.get("sizing_mode", "risk")),
                notional_pct=Decimal(str(backtest_data.get("notional_pct", 1))),
                vol_target_annual_pct=Decimal(
                    str(backtest_data.get("vol_target_annual_pct", 0)),
                ),
                vol_lookback_bars=int(backtest_data.get("vol_lookback_bars", 20)),
                max_position_notional_pct=Decimal(
                    str(backtest_data.get("max_position_notional_pct", "0.10")),
                ),
                max_symbol_exposure_pct=Decimal(
                    str(backtest_data.get("max_symbol_exposure_pct", "0.25")),
                ),
                max_total_exposure_leverage=Decimal(
                    str(backtest_data.get("max_total_exposure_leverage", 3)),
                ),
                train_days=backtest_data.get("wfo", {}).get("train_days", 90),
                test_days=backtest_data.get("wfo", {}).get("test_days", 30),
            )

        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return BacktestConfig()

    def run_backtest(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        initial_balance: Decimal = Decimal(10000),
        data_source: str = "timescale",
        **data_source_kwargs,
    ) -> BacktestResult:
        """
        Run a single backtest.

        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            initial_balance: Starting balance
            data_source: Data source ("timescale" or "csv")
            **data_source_kwargs: Additional data source arguments

        Returns:
            Backtest result
        """
        start_time = time.time()
        logger.info(
            f"Starting backtest: {symbol} {timeframe} {start_date} to {end_date}",
        )

        # Parse parameters
        tf = TimeFrame(timeframe)
        start_dt = parse_utc_date(start_date)
        end_dt = parse_utc_date(end_date, end_of_day=True)

        # Create dataset
        dataset = create_dataset(data_source, **data_source_kwargs)
        streaming_dataset = StreamingDataset(dataset)

        # Initialize simulator
        simulator = BacktestSimulator(self.config, initial_balance)

        # Start data stream
        streaming_dataset.start_stream(symbol, tf, start_dt, end_dt)

        # Run simulation in a single event loop for the whole stream;
        # collect closes here so the simulator stays pure
        closes: list[Decimal] = []
        asyncio.run(self._run_simulation(simulator, streaming_dataset, closes))

        # Calculate metrics
        end_time = time.time()
        runtime_ms = int((end_time - start_time) * 1000)

        metrics_calc = MetricsCalculator(initial_balance, timeframe=tf)
        metrics = metrics_calc.calculate_metrics(
            simulator.completed_trades,
            simulator.equity_history,
            simulator.drawdown_history,
            runtime_ms,
        )
        metrics_calc.apply_benchmark(metrics, closes)

        # Get git SHA and config hash for reproducibility
        git_sha = self._get_git_sha()
        config_hash = self._calculate_config_hash()

        # Create result
        result = BacktestResult(
            config=self.config,
            metrics=metrics,
            trades=simulator.completed_trades,
            equity_curve=simulator.equity_history,
            drawdown_curve=simulator.drawdown_history,
            git_sha=git_sha,
            config_hash=config_hash,
        )

        logger.info(f"Backtest completed in {runtime_ms}ms")
        logger.info(f"Total PnL: {metrics.total_pnl} ({metrics.total_pnl_pct:.2f}%)")
        logger.info(f"Total Trades: {metrics.total_trades}")
        logger.info(f"Win Rate: {metrics.hit_rate_pct:.1f}%")
        logger.info(f"Profit Factor: {metrics.profit_factor}")
        logger.info(
            f"Buy&Hold: {metrics.benchmark_return_pct:.2f}% "
            f"(maxDD {metrics.benchmark_max_drawdown_pct:.2f}%) | "
            f"Excess return: {metrics.excess_return_pct:.2f}%",
        )

        return result

    async def _run_simulation(
        self,
        simulator: BacktestSimulator,
        streaming_dataset: StreamingDataset,
        closes: list[Decimal] | None = None,
    ) -> int:
        candle_count = 0
        while streaming_dataset.has_more():
            candle = streaming_dataset.next_candle()
            if candle:
                await simulator.process_candle(candle)
                if closes is not None:
                    closes.append(candle.close_price)
                candle_count += 1

                if candle_count % 1000 == 0:
                    progress = streaming_dataset.get_progress()
                    logger.info(f"Progress: {progress:.1f}% ({candle_count} candles)")
        return candle_count

    def save_results(
        self,
        result: BacktestResult,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        output_dir: str = "artifacts/backtest",
    ) -> str:
        """
        Save backtest results to files.

        Args:
            result: Backtest result
            symbol: Trading symbol
            timeframe: Timeframe
            start_date: Start date
            end_date: End date
            output_dir: Output directory

        Returns:
            Path to artifacts directory
        """
        # Create output directory
        period_str = f"{start_date}_{end_date}".replace("-", "")
        artifacts_dir = Path(output_dir) / f"{symbol}_{timeframe}_{period_str}"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        result.artifacts_path = str(artifacts_dir)

        # Save JSON report
        self._save_json_report(result, artifacts_dir / "report.json")

        # Save trades CSV
        self._save_trades_csv(result.trades, artifacts_dir / "trades.csv")

        # Generate and save charts
        chart_generator = ChartGenerator()

        if result.equity_curve:
            chart_generator.create_equity_chart(
                result.equity_curve,
                str(artifacts_dir / "equity.png"),
            )

        if result.drawdown_curve:
            chart_generator.create_drawdown_chart(
                result.drawdown_curve,
                str(artifacts_dir / "drawdown.png"),
            )

        if result.trades:
            chart_generator.create_returns_histogram(
                [float(t.net_pnl_r) for t in result.trades if t.net_pnl_r],
                str(artifacts_dir / "returns_histogram.png"),
            )

        logger.info(f"Results saved to: {artifacts_dir}")
        return str(artifacts_dir)

    def _save_json_report(self, result: BacktestResult, path: Path) -> None:
        """Save JSON report."""
        report = {
            "metadata": {
                "git_sha": result.git_sha,
                "config_hash": result.config_hash,
                "runtime_ms": result.metrics.runtime_ms,
                "generated_at": datetime.now(UTC).isoformat(),
            },
            "config": {
                "fee_bps_spot": float(result.config.fee_bps_spot),
                "slippage_bps": float(result.config.slippage_bps),
                "funding_model": result.config.funding_model,
                "tp_ladder": result.config.tp_ladder,
                "signal_source": result.config.signal_source,
                "allow_short": result.config.allow_short,
                "sizing_mode": result.config.sizing_mode,
                "notional_pct": float(result.config.notional_pct),
                "vol_target_annual_pct": float(result.config.vol_target_annual_pct),
                "vol_lookback_bars": result.config.vol_lookback_bars,
                "max_position_notional_pct": float(result.config.max_position_notional_pct),
                "max_symbol_exposure_pct": float(result.config.max_symbol_exposure_pct),
                "max_total_exposure_leverage": float(result.config.max_total_exposure_leverage),
            },
            "metrics": {
                "total_pnl": float(result.metrics.total_pnl),
                "total_pnl_pct": float(result.metrics.total_pnl_pct),
                "profit_factor": float(result.metrics.profit_factor)
                if result.metrics.profit_factor
                else None,
                "sharpe_ratio": float(result.metrics.sharpe_ratio)
                if result.metrics.sharpe_ratio
                else None,
                "sortino_ratio": float(result.metrics.sortino_ratio)
                if result.metrics.sortino_ratio
                else None,
                "calmar_ratio": float(result.metrics.calmar_ratio)
                if result.metrics.calmar_ratio
                else None,
                "max_drawdown_pct": float(result.metrics.max_drawdown_pct),
                "max_drawdown_duration_hours": result.metrics.max_drawdown_duration_hours,
                "total_trades": result.metrics.total_trades,
                "winning_trades": result.metrics.winning_trades,
                "losing_trades": result.metrics.losing_trades,
                "hit_rate_pct": float(result.metrics.hit_rate_pct),
                "avg_win_r": float(result.metrics.avg_win_r),
                "avg_loss_r": float(result.metrics.avg_loss_r),
                "avg_r": float(result.metrics.avg_r),
                "largest_win_r": float(result.metrics.largest_win_r),
                "largest_loss_r": float(result.metrics.largest_loss_r),
                "exposure_pct": float(result.metrics.exposure_pct),
                "total_fees": float(result.metrics.total_fees),
                "total_slippage": float(result.metrics.total_slippage),
                "total_funding": float(result.metrics.total_funding),
                "benchmark_return_pct": float(result.metrics.benchmark_return_pct),
                "benchmark_max_drawdown_pct": float(
                    result.metrics.benchmark_max_drawdown_pct,
                ),
                "benchmark_sharpe_ratio": float(result.metrics.benchmark_sharpe_ratio)
                if result.metrics.benchmark_sharpe_ratio
                else None,
                "excess_return_pct": float(result.metrics.excess_return_pct),
            },
        }

        with open(path, "w") as file:
            json.dump(report, file, indent=2, default=str)

    def _save_trades_csv(self, trades, path: Path) -> None:
        """Save trades to CSV."""
        import csv

        with open(path, "w", newline="") as file:
            if not trades:
                return

            fieldnames = [
                "symbol",
                "side",
                "entry_time",
                "exit_time",
                "entry_price",
                "exit_price",
                "size",
                "gross_pnl",
                "gross_pnl_r",
                "fees",
                "slippage",
                "funding",
                "net_pnl",
                "net_pnl_r",
                "exit_reason",
                "duration_minutes",
            ]

            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()

            for trade in trades:
                writer.writerow(
                    {
                        "symbol": trade.symbol,
                        "side": trade.side,
                        "entry_time": trade.entry_time.isoformat() if trade.entry_time else "",
                        "exit_time": trade.exit_time.isoformat() if trade.exit_time else "",
                        "entry_price": str(trade.entry_price),
                        "exit_price": str(trade.exit_price) if trade.exit_price else "",
                        "size": str(trade.size),
                        "gross_pnl": str(trade.gross_pnl) if trade.gross_pnl else "",
                        "gross_pnl_r": str(trade.gross_pnl_r) if trade.gross_pnl_r else "",
                        "fees": str(trade.fees),
                        "slippage": str(trade.slippage),
                        "funding": str(trade.funding),
                        "net_pnl": str(trade.net_pnl) if trade.net_pnl else "",
                        "net_pnl_r": str(trade.net_pnl_r) if trade.net_pnl_r else "",
                        "exit_reason": trade.exit_reason.value if trade.exit_reason else "",
                        "duration_minutes": trade.duration_minutes or "",
                    },
                )

    def _get_git_sha(self) -> str:
        """Get current git SHA for reproducibility."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                check=False,
                capture_output=True,
                text=True,
                cwd=self.config_path.parent,
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            return "unknown"

    def _calculate_config_hash(self) -> str:
        """Calculate config hash for reproducibility."""
        try:
            with open(self.config_path) as file:
                content = file.read()
            return hashlib.sha256(content.encode()).hexdigest()[:16]
        except Exception:
            return "unknown"


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Run single backtest")
    parser.add_argument(
        "--symbol",
        required=True,
        help="Trading symbol (e.g., BTCUSDT)",
    )
    parser.add_argument("--tf", required=True, help="Timeframe (e.g., 15m, 1h)")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--config", required=True, help="Path to config.yaml")
    parser.add_argument("--balance", type=float, default=10000, help="Initial balance")
    parser.add_argument(
        "--data-source",
        default="timescale",
        choices=["timescale", "csv"],
        help="Data source",
    )
    parser.add_argument("--data-dir", help="Data directory for CSV source")
    parser.add_argument("--database-url", help="Database URL for TimescaleDB")
    parser.add_argument(
        "--output-dir",
        default="artifacts/backtest",
        help="Output directory",
    )
    parser.add_argument(
        "--save-db",
        action="store_true",
        help="Save results to database",
    )

    args = parser.parse_args()

    # Initialize runner
    runner = BacktestRunner(args.config)

    # Prepare data source kwargs
    data_source_kwargs = {}
    if args.data_source == "csv":
        if not args.data_dir:
            raise ValueError("--data-dir required for CSV data source")
        data_source_kwargs["data_directory"] = args.data_dir
    elif args.data_source == "timescale":
        database_url = args.database_url or "postgresql://user:pass@localhost:5432/trading"
        data_source_kwargs["database_url"] = database_url

    try:
        # Run backtest
        result = runner.run_backtest(
            symbol=args.symbol,
            timeframe=args.tf,
            start_date=args.start,
            end_date=args.end,
            initial_balance=Decimal(str(args.balance)),
            data_source=args.data_source,
            **data_source_kwargs,
        )

        # Save results
        artifacts_path = runner.save_results(
            result,
            args.symbol,
            args.tf,
            args.start,
            args.end,
            args.output_dir,
        )

        # Optionally save to database
        if args.save_db:
            serializer = ResultSerializer()
            serializer.save_to_database(
                result,
                args.symbol,
                args.tf,
                args.start,
                args.end,
            )

        print(f"\n{'=' * 50}")
        print("BACKTEST COMPLETED")
        print(f"{'=' * 50}")
        print(f"Results saved to: {artifacts_path}")
        print(
            f"Total PnL: {result.metrics.total_pnl} ({result.metrics.total_pnl_pct:.2f}%)",
        )
        print(f"Total Trades: {result.metrics.total_trades}")
        print(f"Win Rate: {result.metrics.hit_rate_pct:.1f}%")
        if result.metrics.profit_factor:
            print(f"Profit Factor: {result.metrics.profit_factor:.2f}")
        print(f"Max Drawdown: {result.metrics.max_drawdown_pct:.2f}%")

    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        raise


if __name__ == "__main__":
    main()
