"""
Chart generation for backtesting results.
Creates equity curves, drawdown charts, and return histograms.
"""

from datetime import datetime
from decimal import Decimal
import logging

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger(__name__)


class ChartGenerator:
    """
    Generates charts for backtesting results.
    """

    def __init__(self, style: str = "seaborn-v0_8", figsize: tuple = (12, 8)):
        """
        Initialize chart generator.

        Args:
            style: Matplotlib style
            figsize: Figure size (width, height)
        """
        self.figsize = figsize

        # Set style with fallback
        try:
            plt.style.use(style)
        except OSError:
            plt.style.use("default")
            logger.warning(f"Style '{style}' not found, using default")

    def create_equity_chart(
        self,
        equity_curve: list[tuple[datetime, Decimal]],
        output_path: str,
        title: str = "Equity Curve",
    ) -> None:
        """
        Create equity curve chart.

        Args:
            equity_curve: List of (timestamp, equity) tuples
            output_path: Output file path
            title: Chart title
        """
        if not equity_curve:
            logger.warning("No equity data to plot")
            return

        # Extract data
        timestamps = [item[0] for item in equity_curve]
        equity_values = [float(item[1]) for item in equity_curve]

        # Create figure
        fig, ax = plt.subplots(figsize=self.figsize)

        # Plot equity curve
        ax.plot(timestamps, equity_values, linewidth=2, color="#2E86C1", label="Equity")

        # Add horizontal line for starting balance
        initial_balance = equity_values[0]
        ax.axhline(
            y=initial_balance,
            color="gray",
            linestyle="--",
            alpha=0.7,
            label="Initial Balance",
        )

        # Formatting
        ax.set_title(title, fontsize=16, fontweight="bold")
        ax.set_xlabel("Date", fontsize=12)
        ax.set_ylabel("Equity ($)", fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.legend()

        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

        # Format y-axis with currency
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))

        # Add statistics text box
        final_equity = equity_values[-1]
        total_return = (final_equity - initial_balance) / initial_balance * 100

        stats_text = f"Initial: ${initial_balance:,.0f}\nFinal: ${final_equity:,.0f}\nReturn: {total_return:.2f}%"
        ax.text(
            0.02,
            0.98,
            stats_text,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        )

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        logger.info(f"Equity chart saved: {output_path}")

    def create_drawdown_chart(
        self,
        drawdown_curve: list[tuple[datetime, Decimal]],
        output_path: str,
        title: str = "Drawdown",
    ) -> None:
        """
        Create drawdown chart.

        Args:
            drawdown_curve: List of (timestamp, drawdown) tuples
            output_path: Output file path
            title: Chart title
        """
        if not drawdown_curve:
            logger.warning("No drawdown data to plot")
            return

        # Extract data
        timestamps = [item[0] for item in drawdown_curve]
        drawdown_values = [
            float(item[1]) * -100 for item in drawdown_curve
        ]  # Convert to negative percentages

        # Create figure
        fig, ax = plt.subplots(figsize=self.figsize)

        # Plot drawdown
        ax.fill_between(
            timestamps, drawdown_values, 0, alpha=0.7, color="#E74C3C", label="Drawdown"
        )
        ax.plot(timestamps, drawdown_values, linewidth=1, color="#C0392B")

        # Formatting
        ax.set_title(title, fontsize=16, fontweight="bold")
        ax.set_xlabel("Date", fontsize=12)
        ax.set_ylabel("Drawdown (%)", fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.legend()

        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

        # Format y-axis
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x:.1f}%"))

        # Add statistics
        max_dd = min(drawdown_values)
        stats_text = f"Max Drawdown: {max_dd:.2f}%"
        ax.text(
            0.02,
            0.02,
            stats_text,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment="bottom",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        )

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        logger.info(f"Drawdown chart saved: {output_path}")

    def create_returns_histogram(
        self,
        returns: list[float],
        output_path: str,
        title: str = "Trade Returns Distribution",
        bins: int = 50,
    ) -> None:
        """
        Create returns histogram.

        Args:
            returns: List of return values (in R multiples)
            output_path: Output file path
            title: Chart title
            bins: Number of histogram bins
        """
        if not returns:
            logger.warning("No returns data to plot")
            return

        returns_array = np.array(returns)

        # Create figure
        fig, ax = plt.subplots(figsize=self.figsize)

        # Create histogram
        n, bins_edges, patches = ax.hist(
            returns_array, bins=bins, alpha=0.7, edgecolor="black"
        )

        # Color bars based on positive/negative
        for i, patch in enumerate(patches):
            if bins_edges[i] < 0:
                patch.set_facecolor("#E74C3C")  # Red for losses
            else:
                patch.set_facecolor("#27AE60")  # Green for wins

        # Add vertical line at zero
        ax.axvline(
            x=0, color="black", linestyle="-", linewidth=2, alpha=0.8, label="Breakeven"
        )

        # Add mean line
        mean_return = returns_array.mean()
        ax.axvline(
            x=mean_return,
            color="blue",
            linestyle="--",
            linewidth=2,
            alpha=0.8,
            label=f"Mean: {mean_return:.2f}R",
        )

        # Formatting
        ax.set_title(title, fontsize=16, fontweight="bold")
        ax.set_xlabel("Return (R multiples)", fontsize=12)
        ax.set_ylabel("Frequency", fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.legend()

        # Add statistics text box
        std_return = returns_array.std()
        win_rate = (returns_array > 0).sum() / len(returns_array) * 100

        stats_text = (
            f"Count: {len(returns)}\n"
            f"Mean: {mean_return:.2f}R\n"
            f"Std: {std_return:.2f}R\n"
            f"Win Rate: {win_rate:.1f}%"
        )

        ax.text(
            0.98,
            0.98,
            stats_text,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment="top",
            horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        )

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        logger.info(f"Returns histogram saved: {output_path}")

    def create_monthly_returns_heatmap(
        self,
        monthly_returns: list[tuple[str, Decimal]],
        output_path: str,
        title: str = "Monthly Returns Heatmap",
    ) -> None:
        """
        Create monthly returns heatmap.

        Args:
            monthly_returns: List of (month_str, return_pct) tuples
            output_path: Output file path
            title: Chart title
        """
        if not monthly_returns:
            logger.warning("No monthly returns data to plot")
            return

        # Parse data into matrix
        years = set()
        months = set()
        data_dict = {}

        for month_str, return_pct in monthly_returns:
            year, month = month_str.split("-")
            years.add(int(year))
            months.add(int(month))
            data_dict[(int(year), int(month))] = float(return_pct)

        # Create matrix
        years_sorted = sorted(years)
        months_sorted = sorted(months)

        matrix = np.full((len(years_sorted), 12), np.nan)

        for i, year in enumerate(years_sorted):
            for j in range(1, 13):  # Months 1-12
                if (year, j) in data_dict:
                    matrix[i, j - 1] = data_dict[(year, j)]

        # Create figure
        fig, ax = plt.subplots(figsize=(12, max(6, len(years_sorted))))

        # Create heatmap
        im = ax.imshow(matrix, cmap="RdYlGn", aspect="auto", vmin=-10, vmax=10)

        # Set ticks and labels
        ax.set_xticks(range(12))
        ax.set_xticklabels(
            [
                "Jan",
                "Feb",
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug",
                "Sep",
                "Oct",
                "Nov",
                "Dec",
            ]
        )
        ax.set_yticks(range(len(years_sorted)))
        ax.set_yticklabels(years_sorted)

        # Add text annotations
        for i in range(len(years_sorted)):
            for j in range(12):
                if not np.isnan(matrix[i, j]):
                    text = f"{matrix[i, j]:.1f}%"
                    ax.text(
                        j,
                        i,
                        text,
                        ha="center",
                        va="center",
                        color="white" if abs(matrix[i, j]) > 5 else "black",
                        fontweight="bold" if abs(matrix[i, j]) > 3 else "normal",
                    )

        # Add colorbar
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label("Monthly Return (%)", rotation=270, labelpad=20)

        ax.set_title(title, fontsize=16, fontweight="bold")
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        logger.info(f"Monthly returns heatmap saved: {output_path}")

    def create_combined_summary_chart(
        self,
        equity_curve: list[tuple[datetime, Decimal]],
        drawdown_curve: list[tuple[datetime, Decimal]],
        returns: list[float],
        output_path: str,
        title: str = "Backtest Summary",
    ) -> None:
        """
        Create combined summary chart with equity, drawdown, and returns.

        Args:
            equity_curve: Equity time series
            drawdown_curve: Drawdown time series
            returns: Trade returns
            output_path: Output file path
            title: Chart title
        """
        # Create figure with subplots
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))

        # Equity curve (top left)
        if equity_curve:
            timestamps = [item[0] for item in equity_curve]
            equity_values = [float(item[1]) for item in equity_curve]

            ax1.plot(timestamps, equity_values, linewidth=2, color="#2E86C1")
            ax1.set_title("Equity Curve", fontweight="bold")
            ax1.set_ylabel("Equity ($)")
            ax1.grid(True, alpha=0.3)
            ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))

        # Drawdown (top right)
        if drawdown_curve:
            timestamps = [item[0] for item in drawdown_curve]
            drawdown_values = [float(item[1]) * -100 for item in drawdown_curve]

            ax2.fill_between(timestamps, drawdown_values, 0, alpha=0.7, color="#E74C3C")
            ax2.set_title("Drawdown", fontweight="bold")
            ax2.set_ylabel("Drawdown (%)")
            ax2.grid(True, alpha=0.3)

        # Returns histogram (bottom left)
        if returns:
            returns_array = np.array(returns)
            n, bins_edges, patches = ax3.hist(
                returns_array, bins=30, alpha=0.7, edgecolor="black"
            )

            # Color bars
            for i, patch in enumerate(patches):
                if bins_edges[i] < 0:
                    patch.set_facecolor("#E74C3C")
                else:
                    patch.set_facecolor("#27AE60")

            ax3.axvline(x=0, color="black", linestyle="-", linewidth=2, alpha=0.8)
            ax3.axvline(
                x=returns_array.mean(),
                color="blue",
                linestyle="--",
                linewidth=2,
                alpha=0.8,
            )
            ax3.set_title("Returns Distribution", fontweight="bold")
            ax3.set_xlabel("Return (R multiples)")
            ax3.set_ylabel("Frequency")
            ax3.grid(True, alpha=0.3)

        # Rolling Sharpe (bottom right) - placeholder
        ax4.text(
            0.5,
            0.5,
            "Rolling Sharpe\n(Future Enhancement)",
            ha="center",
            va="center",
            transform=ax4.transAxes,
            fontsize=12,
        )
        ax4.set_title("Rolling Sharpe Ratio", fontweight="bold")

        plt.suptitle(title, fontsize=18, fontweight="bold")
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        logger.info(f"Combined summary chart saved: {output_path}")
