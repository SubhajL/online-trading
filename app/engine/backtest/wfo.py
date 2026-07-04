"""
Walk-Forward Optimization (WFO) Runner

Implements walk-forward analysis for strategy validation:
1. Split data into rolling train/test windows
2. Optimize parameters on training data
3. Validate performance on out-of-sample test data
4. Aggregate results across all windows

This prevents overfitting by ensuring parameters work on unseen data.
"""

from collections.abc import Iterator
import dataclasses
from datetime import datetime, timedelta
from decimal import Decimal
import itertools
import logging
import multiprocessing as mp
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .charts import ChartGenerator
from .metrics import MetricsCalculator
from .runner import BacktestRunner
from .types import BacktestConfig, BacktestMetrics, BacktestResult

logger = logging.getLogger(__name__)


class WFOWindow:
    """Single walk-forward optimization window"""

    def __init__(
        self,
        window_id: int,
        train_start: datetime,
        train_end: datetime,
        test_start: datetime,
        test_end: datetime,
    ):
        self.window_id = window_id
        self.train_start = train_start
        self.train_end = train_end
        self.test_start = test_start
        self.test_end = test_end

    def __repr__(self) -> str:
        return (
            f"WFOWindow(id={self.window_id}, "
            f"train={self.train_start.date()}-{self.train_end.date()}, "
            f"test={self.test_start.date()}-{self.test_end.date()})"
        )


class ParameterGrid:
    """Parameter grid generator for optimization"""

    def __init__(self, parameter_ranges: dict[str, list]):
        self.parameter_ranges = parameter_ranges

    def generate_combinations(self) -> Iterator[dict[str, Any]]:
        """Generate all parameter combinations"""
        keys = list(self.parameter_ranges.keys())
        values = list(self.parameter_ranges.values())

        for combination in itertools.product(*values):
            yield dict(zip(keys, combination, strict=False))

    def count_combinations(self) -> int:
        """Count total parameter combinations"""
        count = 1
        for values in self.parameter_ranges.values():
            count *= len(values)
        return count


class WFOResult:
    """Walk-forward optimization result"""

    def __init__(self):
        self.windows: list[WFOWindow] = []
        self.training_results: list[BacktestResult] = []
        self.testing_results: list[BacktestResult] = []
        self.best_parameters: list[dict[str, Any]] = []
        self.aggregate_metrics: BacktestMetrics | None = None
        self.parameter_stability: dict[str, float] = {}
        self.total_runtime_ms: int = 0
        self.optimization_summary: dict[str, Any] = {}

    def get_test_only_metrics(self) -> BacktestMetrics:
        """Get metrics from test periods only (true out-of-sample performance)"""
        if not self.testing_results:
            return BacktestMetrics()

        # Aggregate all test results
        all_trades = []
        all_equity_points = []
        all_drawdown_points = []

        for result in self.testing_results:
            all_trades.extend(result.trades)
            all_equity_points.extend(result.equity_curve)
            all_drawdown_points.extend(result.drawdown_curve)

        if not all_trades:
            return BacktestMetrics()

        # Calculate aggregate metrics
        initial_balance = Decimal(10000)  # Should match config
        metrics_calc = MetricsCalculator(initial_balance)

        return metrics_calc.calculate_metrics(
            all_trades,
            all_equity_points,
            all_drawdown_points,
            self.total_runtime_ms,
        )


class WFORunner:
    """
    Walk-Forward Optimization Runner

    Performs systematic parameter optimization with proper train/test separation
    to validate strategy robustness and prevent overfitting.
    """

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.base_runner = BacktestRunner(config_path)

    def _load_config(self) -> dict[str, Any]:
        """Load WFO configuration"""
        try:
            with open(self.config_path) as file:
                config = yaml.safe_load(file)

            # Validate WFO specific config
            wfo_config = config.get("wfo", {})
            required = ["train_days", "test_days", "step_days"]
            for key in required:
                if key not in wfo_config:
                    logger.warning(f"Missing WFO config: {key}, using default")

            return config

        except Exception as e:
            logger.error(f"Error loading WFO config: {e}")
            raise

    def generate_windows(
        self,
        start_date: datetime,
        end_date: datetime,
        train_days: int = 90,
        test_days: int = 30,
        step_days: int = 30,
    ) -> list[WFOWindow]:
        """
        Generate walk-forward windows.

        Args:
            start_date: Overall start date
            end_date: Overall end date
            train_days: Training period length in days
            test_days: Testing period length in days
            step_days: Step size between windows in days

        Returns:
            List of WFO windows
        """
        windows = []
        window_id = 1
        current_date = start_date

        while True:
            # Calculate window dates
            train_start = current_date
            train_end = train_start + timedelta(days=train_days)
            test_start = train_end
            test_end = test_start + timedelta(days=test_days)

            # Check if we have enough data
            if test_end > end_date:
                break

            window = WFOWindow(window_id, train_start, train_end, test_start, test_end)
            windows.append(window)

            # Move to next window
            current_date += timedelta(days=step_days)
            window_id += 1

        logger.info(f"Generated {len(windows)} WFO windows")
        return windows

    def run_wfo(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        parameter_ranges: dict[str, list],
        initial_balance: Decimal = Decimal(10000),
        data_source: str = "timescale",
        max_workers: int | None = None,
        **data_source_kwargs,
    ) -> WFOResult:
        """
        Run walk-forward optimization.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            parameter_ranges: Dictionary of parameter name -> list of values
            initial_balance: Starting balance
            data_source: Data source type
            max_workers: Max parallel workers
            **data_source_kwargs: Data source arguments

        Returns:
            WFO results
        """
        start_time = datetime.now()
        logger.info(f"Starting WFO for {symbol} {timeframe}")

        # Parse dates
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)

        # Get WFO parameters
        wfo_config = self.config.get("wfo", {})
        train_days = wfo_config.get("train_days", 90)
        test_days = wfo_config.get("test_days", 30)
        step_days = wfo_config.get("step_days", 30)

        # Generate windows
        windows = self.generate_windows(
            start_dt,
            end_dt,
            train_days,
            test_days,
            step_days,
        )

        if not windows:
            raise ValueError("No valid WFO windows generated")

        # Create parameter grid
        param_grid = ParameterGrid(parameter_ranges)
        total_combinations = param_grid.count_combinations()

        logger.info(
            f"Optimizing {total_combinations} parameter combinations across {len(windows)} windows",
        )

        # Initialize result
        result = WFOResult()
        result.windows = windows

        # Set max workers
        if max_workers is None:
            max_workers = min(mp.cpu_count(), len(windows))

        # Process each window
        for window in windows:
            logger.info(f"Processing {window}")

            # 1. Optimization phase (training data)
            best_params, best_training_result = self._optimize_window(
                window,
                symbol,
                timeframe,
                parameter_ranges,
                initial_balance,
                data_source,
                max_workers,
                **data_source_kwargs,
            )

            result.best_parameters.append(best_params)
            result.training_results.append(best_training_result)

            # 2. Validation phase (test data with best parameters)
            test_result = self._validate_window(
                window,
                symbol,
                timeframe,
                best_params,
                initial_balance,
                data_source,
                **data_source_kwargs,
            )

            result.testing_results.append(test_result)

            logger.info(
                f"Window {window.window_id} complete - "
                f"Train PnL: {best_training_result.metrics.total_pnl_pct:.2f}%, "
                f"Test PnL: {test_result.metrics.total_pnl_pct:.2f}%",
            )

        # Calculate aggregate results
        result.total_runtime_ms = int(
            (datetime.now() - start_time).total_seconds() * 1000,
        )
        result.aggregate_metrics = result.get_test_only_metrics()
        result.parameter_stability = self._analyze_parameter_stability(
            result.best_parameters,
        )
        result.optimization_summary = self._create_optimization_summary(result)

        logger.info(
            f"WFO complete - Aggregate test PnL: {result.aggregate_metrics.total_pnl_pct:.2f}%",
        )
        return result

    def _optimize_window(
        self,
        window: WFOWindow,
        symbol: str,
        timeframe: str,
        parameter_ranges: dict[str, list],
        initial_balance: Decimal,
        data_source: str,
        max_workers: int,
        **data_source_kwargs,
    ) -> tuple[dict[str, Any], BacktestResult]:
        """Optimize parameters for a single window"""
        param_grid = ParameterGrid(parameter_ranges)

        # Run backtests for all parameter combinations
        best_result = None
        best_params = None
        best_score = float("-inf")

        # For now, run sequentially (can parallelize later)
        for params in param_grid.generate_combinations():
            try:
                # Update config with parameters
                config = self._update_config_with_params(params)

                # Create temporary runner with updated config
                temp_runner = BacktestRunner(self.config_path)  # type: ignore[arg-type]
                temp_runner.config = config

                # Run backtest on training data
                result = temp_runner.run_backtest(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=window.train_start.strftime("%Y-%m-%d"),
                    end_date=window.train_end.strftime("%Y-%m-%d"),
                    initial_balance=initial_balance,
                    data_source=data_source,
                    **data_source_kwargs,
                )

                # Score result (using Sharpe ratio as primary metric)
                score = self._score_result(result)

                if score > best_score:
                    best_score = score
                    best_result = result
                    best_params = params

            except Exception as e:
                logger.warning(f"Failed backtest with params {params}: {e}")
                continue

        if best_result is None:
            raise RuntimeError(f"No successful backtests for window {window.window_id}")

        return best_params, best_result

    def _validate_window(
        self,
        window: WFOWindow,
        symbol: str,
        timeframe: str,
        params: dict[str, Any],
        initial_balance: Decimal,
        data_source: str,
        **data_source_kwargs,
    ) -> BacktestResult:
        """Validate parameters on test data"""
        # Update config with best parameters
        config = self._update_config_with_params(params)

        # Create temporary runner
        temp_runner = BacktestRunner(self.config_path)  # type: ignore[arg-type]
        temp_runner.config = config

        # Run backtest on test data
        return temp_runner.run_backtest(
            symbol=symbol,
            timeframe=timeframe,
            start_date=window.test_start.strftime("%Y-%m-%d"),
            end_date=window.test_end.strftime("%Y-%m-%d"),
            initial_balance=initial_balance,
            data_source=data_source,
            **data_source_kwargs,
        )

    def _update_config_with_params(self, params: dict[str, Any]) -> BacktestConfig:
        """Build a new config from the base config plus optimization parameters"""
        updates: dict[str, Any] = {}

        if "fee_bps_spot" in params:
            updates["fee_bps_spot"] = Decimal(str(params["fee_bps_spot"]))
        if "slippage_bps" in params:
            updates["slippage_bps"] = Decimal(str(params["slippage_bps"]))
        if "pivot_n" in params:
            updates["pivot_n"] = int(params["pivot_n"])
        if "retest_max_wait_bars" in params:
            updates["retest_max_wait_bars"] = int(params["retest_max_wait_bars"])
        if "cooldown_seconds" in params:
            updates["cooldown_seconds"] = int(params["cooldown_seconds"])
        if "risk_per_trade" in params:
            updates["risk_per_trade"] = Decimal(str(params["risk_per_trade"]))
        if "warmup_bars" in params:
            updates["warmup_bars"] = int(params["warmup_bars"])

        return dataclasses.replace(self.base_runner.config, **updates)

    def _score_result(self, result: BacktestResult) -> float:
        """Score a backtest result for optimization"""
        metrics = result.metrics

        # Multi-objective scoring function
        # Prioritize: Sharpe ratio, total return, max drawdown
        sharpe_score = float(metrics.sharpe_ratio) if metrics.sharpe_ratio else 0
        return_score = float(metrics.total_pnl_pct) / 100  # Normalize to 0-1 range
        drawdown_penalty = float(metrics.max_drawdown_pct) / 100  # Penalty for high drawdown

        # Weighted composite score
        score = sharpe_score * 0.5 + return_score * 0.3 - drawdown_penalty * 0.2

        return score

    def _analyze_parameter_stability(
        self,
        parameter_sets: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Analyze parameter stability across windows"""
        if not parameter_sets:
            return {}

        stability = {}
        param_names = parameter_sets[0].keys()

        for param_name in param_names:
            values = [params[param_name] for params in parameter_sets]

            if all(isinstance(v, (int, float)) for v in values):
                # Numerical parameter - calculate coefficient of variation
                mean_val = np.mean(values)
                std_val = np.std(values)
                cv = std_val / mean_val if mean_val != 0 else float("inf")
                stability[param_name] = 1 / (1 + cv)  # Higher is more stable
            else:
                # Categorical parameter - calculate mode frequency
                unique_values = list(set(values))
                mode_count = max(values.count(v) for v in unique_values)
                stability[param_name] = mode_count / len(values)

        return stability

    def _create_optimization_summary(self, result: WFOResult) -> dict[str, Any]:
        """Create optimization summary statistics"""
        if not result.testing_results:
            return {}

        test_returns = [r.metrics.total_pnl_pct for r in result.testing_results]
        train_returns = [r.metrics.total_pnl_pct for r in result.training_results]

        return {
            "total_windows": len(result.windows),
            "avg_test_return": float(np.mean(test_returns)),  # type: ignore[arg-type]
            "std_test_return": float(np.std(test_returns)),  # type: ignore[arg-type]
            "avg_train_return": float(np.mean(train_returns)),  # type: ignore[arg-type]
            "std_train_return": float(np.std(train_returns)),  # type: ignore[arg-type]
            "overfitting_ratio": float(np.mean(train_returns)) / float(np.mean(test_returns))  # type: ignore[arg-type]
            if np.mean(test_returns) != 0  # type: ignore[arg-type]
            else float("inf"),
            "win_rate": len([r for r in test_returns if r > 0]) / len(test_returns)
            if test_returns
            else 0,
            "best_test_window": int(np.argmax(test_returns)) + 1,  # type: ignore[arg-type]
            "worst_test_window": int(np.argmin(test_returns)) + 1,  # type: ignore[arg-type]
            "parameter_stability": result.parameter_stability,
        }

    def save_wfo_results(
        self,
        result: WFOResult,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        output_dir: str = "artifacts/wfo",
    ) -> str:
        """Save WFO results to files"""
        # Create output directory
        period_str = f"{start_date}_{end_date}".replace("-", "")
        artifacts_dir = Path(output_dir) / f"{symbol}_{timeframe}_{period_str}_wfo"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # 1. Save aggregate test results (main report)
        test_metrics = result.get_test_only_metrics()
        self._save_wfo_report(result, artifacts_dir / "wfo_report.json")

        # 2. Save detailed window results
        self._save_window_results(result, artifacts_dir / "windows.csv")

        # 3. Save parameter analysis
        self._save_parameter_analysis(result, artifacts_dir / "parameters.json")

        # 4. Generate charts
        if result.testing_results:
            self._generate_wfo_charts(result, artifacts_dir)

        logger.info(f"WFO results saved to: {artifacts_dir}")
        return str(artifacts_dir)

    def _save_wfo_report(self, result: WFOResult, path: Path):
        """Save main WFO report"""
        test_metrics = result.get_test_only_metrics()

        report = {
            "wfo_summary": result.optimization_summary,
            "aggregate_test_metrics": {
                "total_pnl": float(test_metrics.total_pnl),
                "total_pnl_pct": float(test_metrics.total_pnl_pct),
                "total_trades": test_metrics.total_trades,
                "hit_rate_pct": float(test_metrics.hit_rate_pct),
                "profit_factor": float(test_metrics.profit_factor)
                if test_metrics.profit_factor
                else None,
                "sharpe_ratio": float(test_metrics.sharpe_ratio)
                if test_metrics.sharpe_ratio
                else None,
                "max_drawdown_pct": float(test_metrics.max_drawdown_pct),
                "avg_r": float(test_metrics.avg_r),
            },
            "parameter_stability": result.parameter_stability,
            "runtime_ms": result.total_runtime_ms,
        }

        import json

        with open(path, "w") as f:
            json.dump(report, f, indent=2, default=str)

    def _save_window_results(self, result: WFOResult, path: Path):
        """Save detailed window results to CSV"""
        import csv

        with open(path, "w", newline="") as f:
            fieldnames = [
                "window_id",
                "train_start",
                "train_end",
                "test_start",
                "test_end",
                "best_parameters",
                "train_pnl_pct",
                "test_pnl_pct",
                "train_trades",
                "test_trades",
                "train_hit_rate",
                "test_hit_rate",
            ]

            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for i, window in enumerate(result.windows):
                train_result = (
                    result.training_results[i] if i < len(result.training_results) else None
                )
                test_result = result.testing_results[i] if i < len(result.testing_results) else None
                best_params = result.best_parameters[i] if i < len(result.best_parameters) else {}

                writer.writerow(
                    {
                        "window_id": window.window_id,
                        "train_start": window.train_start.strftime("%Y-%m-%d"),
                        "train_end": window.train_end.strftime("%Y-%m-%d"),
                        "test_start": window.test_start.strftime("%Y-%m-%d"),
                        "test_end": window.test_end.strftime("%Y-%m-%d"),
                        "best_parameters": str(best_params),
                        "train_pnl_pct": float(train_result.metrics.total_pnl_pct)
                        if train_result
                        else 0,
                        "test_pnl_pct": float(test_result.metrics.total_pnl_pct)
                        if test_result
                        else 0,
                        "train_trades": train_result.metrics.total_trades if train_result else 0,
                        "test_trades": test_result.metrics.total_trades if test_result else 0,
                        "train_hit_rate": float(train_result.metrics.hit_rate_pct)
                        if train_result
                        else 0,
                        "test_hit_rate": float(test_result.metrics.hit_rate_pct)
                        if test_result
                        else 0,
                    },
                )

    def _save_parameter_analysis(self, result: WFOResult, path: Path):
        """Save parameter analysis"""
        import json

        analysis = {
            "parameter_stability": result.parameter_stability,
            "parameter_history": result.best_parameters,
            "optimization_summary": result.optimization_summary,
        }

        with open(path, "w") as f:
            json.dump(analysis, f, indent=2, default=str)

    def _generate_wfo_charts(self, result: WFOResult, output_dir: Path):
        """Generate WFO specific charts"""
        chart_gen = ChartGenerator()

        # 1. Train vs Test performance comparison
        self._create_train_test_comparison_chart(
            result,
            output_dir / "train_vs_test.png",
        )

        # 2. Rolling window performance
        self._create_rolling_performance_chart(
            result,
            output_dir / "rolling_performance.png",
        )

        # 3. Parameter stability chart
        self._create_parameter_stability_chart(
            result,
            output_dir / "parameter_stability.png",
        )

    def _create_train_test_comparison_chart(self, result: WFOResult, path: Path):
        """Create train vs test performance comparison"""
        import matplotlib.pyplot as plt

        train_returns = [r.metrics.total_pnl_pct for r in result.training_results]
        test_returns = [r.metrics.total_pnl_pct for r in result.testing_results]
        windows = list(range(1, len(result.windows) + 1))

        fig, ax = plt.subplots(figsize=(12, 6))

        ax.bar(
            [w - 0.2 for w in windows],
            train_returns,  # type: ignore[arg-type]
            0.4,
            label="Training",
            alpha=0.7,
        )
        ax.bar(
            [w + 0.2 for w in windows],
            test_returns,  # type: ignore[arg-type]
            0.4,
            label="Testing",
            alpha=0.7,
        )

        ax.set_xlabel("WFO Window")
        ax.set_ylabel("Return (%)")
        ax.set_title("Train vs Test Performance by Window")
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(path, dpi=300, bbox_inches="tight")
        plt.close()

    def _create_rolling_performance_chart(self, result: WFOResult, path: Path):
        """Create rolling performance chart"""
        import matplotlib.pyplot as plt

        test_returns = [r.metrics.total_pnl_pct for r in result.testing_results]
        windows = list(range(1, len(result.windows) + 1))

        fig, ax = plt.subplots(figsize=(12, 6))

        ax.plot(windows, test_returns, marker="o", linewidth=2, markersize=6)  # type: ignore[arg-type]
        ax.axhline(y=0, color="red", linestyle="--", alpha=0.7)

        ax.set_xlabel("WFO Window")
        ax.set_ylabel("Test Return (%)")
        ax.set_title("Rolling Out-of-Sample Performance")
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(path, dpi=300, bbox_inches="tight")
        plt.close()

    def _create_parameter_stability_chart(self, result: WFOResult, path: Path):
        """Create parameter stability chart"""
        import matplotlib.pyplot as plt

        if not result.parameter_stability:
            return

        params = list(result.parameter_stability.keys())
        stability_scores = list(result.parameter_stability.values())

        fig, ax = plt.subplots(figsize=(10, 6))

        bars = ax.bar(params, stability_scores)
        ax.set_ylabel("Stability Score")
        ax.set_title("Parameter Stability Across WFO Windows")
        ax.set_ylim(0, 1)

        # Color bars by stability level
        for bar, score in zip(bars, stability_scores, strict=False):
            if score >= 0.8:
                bar.set_color("green")
            elif score >= 0.6:
                bar.set_color("orange")
            else:
                bar.set_color("red")

        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(path, dpi=300, bbox_inches="tight")
        plt.close()
