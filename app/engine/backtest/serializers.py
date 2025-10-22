"""
Result serializers for backtesting: S3/MinIO upload and database storage.
"""

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .types import BacktestResult

logger = logging.getLogger(__name__)


class ResultSerializer:
    """
    Handles serialization and storage of backtest results.
    """

    def __init__(
        self, database_url: Optional[str] = None, s3_config: Optional[dict] = None
    ):
        """
        Initialize result serializer.

        Args:
            database_url: Database connection URL
            s3_config: S3/MinIO configuration
        """
        self.database_url = database_url
        self.s3_config = s3_config or {}

        # Initialize database connection if provided
        if database_url:
            self.engine = create_engine(database_url)
            self.Session = sessionmaker(bind=self.engine)

        # Initialize S3 client if configured
        self.s3_client = None
        if self.s3_config:
            self._init_s3_client()

    def _init_s3_client(self):
        """Initialize S3/MinIO client."""
        try:
            import boto3
            from botocore.config import Config

            # Support MinIO configuration
            endpoint_url = self.s3_config.get("endpoint_url")
            config = Config(signature_version="s3v4") if endpoint_url else None

            self.s3_client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=self.s3_config.get("access_key"),
                aws_secret_access_key=self.s3_config.get("secret_key"),
                region_name=self.s3_config.get("region", "us-east-1"),
                config=config,
            )

            logger.info("S3 client initialized")

        except ImportError:
            logger.error("boto3 not available for S3 uploads")
        except Exception as e:
            logger.error(f"Error initializing S3 client: {e}")

    def save_to_database(
        self,
        result: BacktestResult,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        run_type: str = "backtest",
    ) -> Optional[str]:
        """
        Save backtest result to database.

        Args:
            result: Backtest result
            symbol: Trading symbol
            timeframe: Timeframe
            start_date: Start date
            end_date: End date
            run_type: Type of run ("backtest" or "wfo")

        Returns:
            Report ID if saved successfully
        """
        if not self.database_url:
            logger.warning("No database URL configured")
            return None

        try:
            with self.Session() as session:
                report_id = uuid4()

                # Insert report summary
                report_query = text("""
                    INSERT INTO reports (
                        id, run_type, symbol, timeframe, start_time, end_time,
                        config_hash, git_sha, total_pnl, total_pnl_pct, profit_factor,
                        sharpe_ratio, sortino_ratio, calmar_ratio, max_drawdown_pct,
                        max_drawdown_duration_hours, total_trades, winning_trades,
                        losing_trades, hit_rate_pct, avg_win_r, avg_loss_r, avg_r,
                        largest_win_r, largest_loss_r, exposure_pct, total_fees,
                        total_slippage, total_funding, runtime_ms, artifacts_path,
                        s3_bucket, s3_key
                    ) VALUES (
                        :id, :run_type, :symbol, :timeframe, :start_time, :end_time,
                        :config_hash, :git_sha, :total_pnl, :total_pnl_pct, :profit_factor,
                        :sharpe_ratio, :sortino_ratio, :calmar_ratio, :max_drawdown_pct,
                        :max_drawdown_duration_hours, :total_trades, :winning_trades,
                        :losing_trades, :hit_rate_pct, :avg_win_r, :avg_loss_r, :avg_r,
                        :largest_win_r, :largest_loss_r, :exposure_pct, :total_fees,
                        :total_slippage, :total_funding, :runtime_ms, :artifacts_path,
                        :s3_bucket, :s3_key
                    )
                """)

                session.execute(
                    report_query,
                    {
                        "id": report_id,
                        "run_type": run_type,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "start_time": datetime.fromisoformat(start_date),
                        "end_time": datetime.fromisoformat(end_date),
                        "config_hash": result.config_hash,
                        "git_sha": result.git_sha,
                        "total_pnl": result.metrics.total_pnl,
                        "total_pnl_pct": result.metrics.total_pnl_pct,
                        "profit_factor": result.metrics.profit_factor,
                        "sharpe_ratio": result.metrics.sharpe_ratio,
                        "sortino_ratio": result.metrics.sortino_ratio,
                        "calmar_ratio": result.metrics.calmar_ratio,
                        "max_drawdown_pct": result.metrics.max_drawdown_pct,
                        "max_drawdown_duration_hours": result.metrics.max_drawdown_duration_hours,
                        "total_trades": result.metrics.total_trades,
                        "winning_trades": result.metrics.winning_trades,
                        "losing_trades": result.metrics.losing_trades,
                        "hit_rate_pct": result.metrics.hit_rate_pct,
                        "avg_win_r": result.metrics.avg_win_r,
                        "avg_loss_r": result.metrics.avg_loss_r,
                        "avg_r": result.metrics.avg_r,
                        "largest_win_r": result.metrics.largest_win_r,
                        "largest_loss_r": result.metrics.largest_loss_r,
                        "exposure_pct": result.metrics.exposure_pct,
                        "total_fees": result.metrics.total_fees,
                        "total_slippage": result.metrics.total_slippage,
                        "total_funding": result.metrics.total_funding,
                        "runtime_ms": result.metrics.runtime_ms,
                        "artifacts_path": result.artifacts_path,
                        "s3_bucket": None,  # Set when uploaded to S3
                        "s3_key": None,
                    },
                )

                # Insert individual trades
                if result.trades:
                    trade_query = text("""
                        INSERT INTO report_trades (
                            report_id, symbol, side, entry_time, exit_time,
                            entry_price, exit_price, size, gross_pnl, gross_pnl_r,
                            fees, slippage, funding, net_pnl, net_pnl_r,
                            stop_loss, take_profits, exit_reason, duration_minutes,
                            signal_type, signal_confidence, regime, market_conditions
                        ) VALUES (
                            :report_id, :symbol, :side, :entry_time, :exit_time,
                            :entry_price, :exit_price, :size, :gross_pnl, :gross_pnl_r,
                            :fees, :slippage, :funding, :net_pnl, :net_pnl_r,
                            :stop_loss, :take_profits, :exit_reason, :duration_minutes,
                            :signal_type, :signal_confidence, :regime, :market_conditions
                        )
                    """)

                    for trade in result.trades:
                        session.execute(
                            trade_query,
                            {
                                "report_id": report_id,
                                "symbol": trade.symbol,
                                "side": trade.side,
                                "entry_time": trade.entry_time,
                                "exit_time": trade.exit_time,
                                "entry_price": trade.entry_price,
                                "exit_price": trade.exit_price,
                                "size": trade.size,
                                "gross_pnl": trade.gross_pnl,
                                "gross_pnl_r": trade.gross_pnl_r,
                                "fees": trade.fees,
                                "slippage": trade.slippage,
                                "funding": trade.funding,
                                "net_pnl": trade.net_pnl,
                                "net_pnl_r": trade.net_pnl_r,
                                "stop_loss": trade.stop_loss,
                                "take_profits": json.dumps(trade.take_profits),
                                "exit_reason": trade.exit_reason.value
                                if trade.exit_reason
                                else None,
                                "duration_minutes": trade.duration_minutes,
                                "signal_type": trade.signal_type,
                                "signal_confidence": trade.signal_confidence,
                                "regime": trade.regime,
                                "market_conditions": json.dumps(
                                    trade.market_conditions
                                ),
                            },
                        )

                session.commit()
                logger.info(f"Saved backtest results to database: {report_id}")
                return str(report_id)

        except Exception as e:
            logger.error(f"Error saving to database: {e}")
            return None

    def upload_to_s3(
        self, local_path: str, s3_key: str, bucket: Optional[str] = None
    ) -> bool:
        """
        Upload file to S3/MinIO.

        Args:
            local_path: Local file path
            s3_key: S3 object key
            bucket: S3 bucket (uses config if not provided)

        Returns:
            True if upload successful
        """
        if not self.s3_client:
            logger.warning("S3 client not configured")
            return False

        bucket = bucket or self.s3_config.get("bucket")
        if not bucket:
            logger.error("No S3 bucket specified")
            return False

        try:
            local_file = Path(local_path)
            if local_file.is_dir():
                # Upload entire directory
                return self._upload_directory(local_path, s3_key, bucket)
            else:
                # Upload single file
                self.s3_client.upload_file(local_path, bucket, s3_key)
                logger.info(f"Uploaded {local_path} to s3://{bucket}/{s3_key}")
                return True

        except Exception as e:
            logger.error(f"Error uploading to S3: {e}")
            return False

    def _upload_directory(self, local_dir: str, s3_prefix: str, bucket: str) -> bool:
        """Upload directory to S3."""
        try:
            local_path = Path(local_dir)
            success_count = 0
            total_files = 0

            for file_path in local_path.rglob("*"):
                if file_path.is_file():
                    total_files += 1
                    relative_path = file_path.relative_to(local_path)
                    s3_key = f"{s3_prefix}/{relative_path}".replace("\\", "/")

                    try:
                        self.s3_client.upload_file(str(file_path), bucket, s3_key)
                        success_count += 1
                    except Exception as e:
                        logger.error(f"Failed to upload {file_path}: {e}")

            logger.info(
                f"Uploaded {success_count}/{total_files} files from {local_dir}"
            )
            return success_count == total_files

        except Exception as e:
            logger.error(f"Error uploading directory: {e}")
            return False

    def serialize_result_to_json(self, result: BacktestResult) -> str:
        """
        Serialize backtest result to JSON string.

        Args:
            result: Backtest result

        Returns:
            JSON string representation
        """

        def decimal_serializer(obj):
            """Custom serializer for Decimal and datetime objects."""
            if isinstance(obj, Decimal):
                return float(obj)
            elif isinstance(obj, datetime):
                return obj.isoformat()
            elif hasattr(obj, "value"):  # Enum objects
                return obj.value
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        result_dict = {
            "metadata": {
                "git_sha": result.git_sha,
                "config_hash": result.config_hash,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "artifacts_path": result.artifacts_path,
            },
            "config": {
                "fee_bps_spot": result.config.fee_bps_spot,
                "slippage_bps": result.config.slippage_bps,
                "funding_model": result.config.funding_model,
                "session_enabled": result.config.session_enabled,
                "tp_ladder": result.config.tp_ladder,
                "move_to_breakeven_on": result.config.move_to_breakeven_on,
                "trail_after": result.config.trail_after,
            },
            "metrics": {
                "total_pnl": result.metrics.total_pnl,
                "total_pnl_pct": result.metrics.total_pnl_pct,
                "profit_factor": result.metrics.profit_factor,
                "sharpe_ratio": result.metrics.sharpe_ratio,
                "sortino_ratio": result.metrics.sortino_ratio,
                "calmar_ratio": result.metrics.calmar_ratio,
                "max_drawdown_pct": result.metrics.max_drawdown_pct,
                "max_drawdown_duration_hours": result.metrics.max_drawdown_duration_hours,
                "total_trades": result.metrics.total_trades,
                "winning_trades": result.metrics.winning_trades,
                "losing_trades": result.metrics.losing_trades,
                "hit_rate_pct": result.metrics.hit_rate_pct,
                "avg_win_r": result.metrics.avg_win_r,
                "avg_loss_r": result.metrics.avg_loss_r,
                "avg_r": result.metrics.avg_r,
                "largest_win_r": result.metrics.largest_win_r,
                "largest_loss_r": result.metrics.largest_loss_r,
                "exposure_pct": result.metrics.exposure_pct,
                "total_fees": result.metrics.total_fees,
                "total_slippage": result.metrics.total_slippage,
                "total_funding": result.metrics.total_funding,
                "runtime_ms": result.metrics.runtime_ms,
            },
            "trades": [
                {
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "entry_time": trade.entry_time,
                    "exit_time": trade.exit_time,
                    "entry_price": trade.entry_price,
                    "exit_price": trade.exit_price,
                    "size": trade.size,
                    "gross_pnl": trade.gross_pnl,
                    "gross_pnl_r": trade.gross_pnl_r,
                    "fees": trade.fees,
                    "slippage": trade.slippage,
                    "funding": trade.funding,
                    "net_pnl": trade.net_pnl,
                    "net_pnl_r": trade.net_pnl_r,
                    "exit_reason": trade.exit_reason,
                    "duration_minutes": trade.duration_minutes,
                    "signal_type": trade.signal_type,
                    "signal_confidence": trade.signal_confidence,
                    "regime": trade.regime,
                    "market_conditions": trade.market_conditions,
                }
                for trade in result.trades
            ],
            "equity_curve": [
                {"timestamp": timestamp, "equity": equity}
                for timestamp, equity in result.equity_curve
            ],
            "drawdown_curve": [
                {"timestamp": timestamp, "drawdown": drawdown}
                for timestamp, drawdown in result.drawdown_curve
            ],
        }

        return json.dumps(result_dict, default=decimal_serializer, indent=2)

    def save_complete_results(
        self,
        result: BacktestResult,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        save_to_db: bool = True,
        upload_to_s3: bool = False,
    ) -> dict:
        """
        Save complete results to all configured destinations.

        Args:
            result: Backtest result
            symbol: Trading symbol
            timeframe: Timeframe
            start_date: Start date
            end_date: End date
            save_to_db: Whether to save to database
            upload_to_s3: Whether to upload to S3

        Returns:
            Dictionary with save status
        """
        status = {"database": False, "s3": False, "report_id": None, "s3_key": None}

        # Save to database
        if save_to_db and self.database_url:
            report_id = self.save_to_database(
                result, symbol, timeframe, start_date, end_date
            )
            if report_id:
                status["database"] = True
                status["report_id"] = report_id

        # Upload to S3
        if upload_to_s3 and result.artifacts_path and self.s3_client:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            s3_key = f"backtests/{symbol}/{timeframe}/{timestamp}"

            if self.upload_to_s3(result.artifacts_path, s3_key):
                status["s3"] = True
                status["s3_key"] = s3_key

                # Update database with S3 info if we have a report ID
                if status["report_id"]:
                    self._update_s3_info(status["report_id"], s3_key)

        return status

    def _update_s3_info(self, report_id: str, s3_key: str) -> None:
        """Update database with S3 information."""
        if not self.database_url:
            return

        try:
            with self.Session() as session:
                update_query = text("""
                    UPDATE reports
                    SET s3_bucket = :bucket, s3_key = :s3_key
                    WHERE id = :report_id
                """)

                session.execute(
                    update_query,
                    {
                        "bucket": self.s3_config.get("bucket"),
                        "s3_key": s3_key,
                        "report_id": report_id,
                    },
                )
                session.commit()

        except Exception as e:
            logger.error(f"Error updating S3 info: {e}")


def create_serializer(config: dict) -> ResultSerializer:
    """
    Factory function to create result serializer from config.

    Args:
        config: Configuration dictionary

    Returns:
        Configured result serializer
    """
    database_url = config.get("database_url")
    s3_config = config.get("s3", {})

    return ResultSerializer(database_url, s3_config)
