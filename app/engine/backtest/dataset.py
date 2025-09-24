"""
Dataset adapters for backtesting: TimescaleDB fetcher and CSV loader.
"""

import csv
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Iterator

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from ..models import Candle, TimeFrame

logger = logging.getLogger(__name__)


class CandleDataset:
    """
    Base class for candle data loading.
    """

    def __init__(self):
        """Initialize dataset."""
        pass

    def load_candles(
        self,
        symbol: str,
        timeframe: TimeFrame,
        start_time: datetime,
        end_time: datetime
    ) -> List[Candle]:
        """
        Load candles for the specified time range.

        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            start_time: Start time (inclusive)
            end_time: End time (inclusive)

        Returns:
            List of candles ordered by time
        """
        raise NotImplementedError

    def get_available_symbols(self) -> List[str]:
        """Get list of available symbols."""
        raise NotImplementedError

    def get_date_range(self, symbol: str, timeframe: TimeFrame) -> tuple[datetime, datetime]:
        """Get available date range for symbol."""
        raise NotImplementedError


class TimescaleDataset(CandleDataset):
    """
    Loads candle data from TimescaleDB.
    """

    def __init__(self, database_url: str):
        """
        Initialize TimescaleDB dataset.

        Args:
            database_url: Database connection URL
        """
        super().__init__()
        self.engine = create_engine(database_url)
        self.Session = sessionmaker(bind=self.engine)

    def load_candles(
        self,
        symbol: str,
        timeframe: TimeFrame,
        start_time: datetime,
        end_time: datetime
    ) -> List[Candle]:
        """
        Load candles from TimescaleDB.

        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            start_time: Start time (inclusive)
            end_time: End time (inclusive)

        Returns:
            List of candles ordered by time
        """
        try:
            with self.Session() as session:
                query = text("""
                    SELECT
                        symbol,
                        tf,
                        open_time,
                        close_time,
                        open,
                        high,
                        low,
                        close,
                        volume,
                        quote_volume,
                        trades,
                        taker_buy_volume,
                        taker_buy_quote_volume
                    FROM candles
                    WHERE symbol = :symbol
                        AND tf = :timeframe
                        AND open_time >= :start_time
                        AND open_time <= :end_time
                    ORDER BY open_time ASC
                """)

                result = session.execute(query, {
                    'symbol': symbol,
                    'timeframe': timeframe.value,
                    'start_time': start_time,
                    'end_time': end_time
                })

                candles = []
                for row in result:
                    candle = Candle(
                        symbol=row.symbol,
                        timeframe=TimeFrame(row.tf),
                        open_time=row.open_time,
                        close_time=row.close_time,
                        open_price=Decimal(str(row.open)),
                        high_price=Decimal(str(row.high)),
                        low_price=Decimal(str(row.low)),
                        close_price=Decimal(str(row.close)),
                        volume=Decimal(str(row.volume)),
                        quote_volume=Decimal(str(row.quote_volume)),
                        trades=row.trades,
                        taker_buy_base_volume=Decimal(str(row.taker_buy_volume)),
                        taker_buy_quote_volume=Decimal(str(row.taker_buy_quote_volume))
                    )
                    candles.append(candle)

                logger.info(f"Loaded {len(candles)} candles for {symbol} {timeframe.value}")
                return candles

        except Exception as e:
            logger.error(f"Error loading candles from TimescaleDB: {e}")
            return []

    def get_available_symbols(self) -> List[str]:
        """Get list of available symbols."""
        try:
            with self.Session() as session:
                result = session.execute(text("SELECT DISTINCT symbol FROM candles ORDER BY symbol"))
                return [row[0] for row in result]
        except Exception as e:
            logger.error(f"Error getting symbols: {e}")
            return []

    def get_date_range(self, symbol: str, timeframe: TimeFrame) -> tuple[datetime, datetime]:
        """Get available date range for symbol."""
        try:
            with self.Session() as session:
                result = session.execute(text("""
                    SELECT MIN(open_time), MAX(open_time)
                    FROM candles
                    WHERE symbol = :symbol AND tf = :timeframe
                """), {'symbol': symbol, 'timeframe': timeframe.value})

                row = result.first()
                if row and row[0] and row[1]:
                    return row[0], row[1]

        except Exception as e:
            logger.error(f"Error getting date range: {e}")

        # Default fallback
        return datetime(2020, 1, 1), datetime.now()


class CSVDataset(CandleDataset):
    """
    Loads candle data from CSV files.
    """

    def __init__(self, data_directory: str):
        """
        Initialize CSV dataset.

        Args:
            data_directory: Directory containing CSV files
        """
        super().__init__()
        self.data_directory = Path(data_directory)

    def _get_csv_path(self, symbol: str, timeframe: TimeFrame) -> Path:
        """
        Get CSV file path for symbol and timeframe.

        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe

        Returns:
            Path to CSV file
        """
        filename = f"{symbol.lower()}_{timeframe.value}.csv"
        return self.data_directory / filename

    def load_candles(
        self,
        symbol: str,
        timeframe: TimeFrame,
        start_time: datetime,
        end_time: datetime
    ) -> List[Candle]:
        """
        Load candles from CSV file.

        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            start_time: Start time (inclusive)
            end_time: End time (inclusive)

        Returns:
            List of candles ordered by time
        """
        csv_path = self._get_csv_path(symbol, timeframe)

        if not csv_path.exists():
            logger.error(f"CSV file not found: {csv_path}")
            return []

        try:
            candles = []

            with open(csv_path, 'r') as file:
                reader = csv.DictReader(file)

                for row in reader:
                    # Parse timestamp - handle different formats
                    timestamp_str = row.get('timestamp') or row.get('open_time')
                    if not timestamp_str:
                        continue

                    try:
                        # Try ISO format first
                        open_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    except ValueError:
                        # Try Unix timestamp
                        try:
                            open_time = datetime.fromtimestamp(int(timestamp_str) / 1000)
                        except ValueError:
                            logger.warning(f"Could not parse timestamp: {timestamp_str}")
                            continue

                    # Filter by date range
                    if not (start_time <= open_time <= end_time):
                        continue

                    # Calculate close time (approximate)
                    close_time = self._calculate_close_time(open_time, timeframe)

                    candle = Candle(
                        symbol=symbol,
                        timeframe=timeframe,
                        open_time=open_time,
                        close_time=close_time,
                        open_price=Decimal(row['open']),
                        high_price=Decimal(row['high']),
                        low_price=Decimal(row['low']),
                        close_price=Decimal(row['close']),
                        volume=Decimal(row['volume']),
                        quote_volume=Decimal(row.get('quote_volume', '0')),
                        trades=int(row.get('trades', '0')),
                        taker_buy_base_volume=Decimal(row.get('taker_buy_volume', '0')),
                        taker_buy_quote_volume=Decimal(row.get('taker_buy_quote_volume', '0'))
                    )
                    candles.append(candle)

            logger.info(f"Loaded {len(candles)} candles from CSV: {csv_path}")
            return candles

        except Exception as e:
            logger.error(f"Error loading CSV file {csv_path}: {e}")
            return []

    def _calculate_close_time(self, open_time: datetime, timeframe: TimeFrame) -> datetime:
        """
        Calculate close time based on open time and timeframe.

        Args:
            open_time: Candle open time
            timeframe: Candle timeframe

        Returns:
            Calculated close time
        """
        # Map timeframe to minutes
        timeframe_minutes = {
            TimeFrame.M1: 1,
            TimeFrame.M5: 5,
            TimeFrame.M15: 15,
            TimeFrame.M30: 30,
            TimeFrame.H1: 60,
            TimeFrame.H4: 240,
            TimeFrame.D1: 1440
        }

        minutes = timeframe_minutes.get(timeframe, 5)  # Default to 5 minutes
        return open_time + pd.Timedelta(minutes=minutes)

    def get_available_symbols(self) -> List[str]:
        """Get list of available symbols from CSV files."""
        if not self.data_directory.exists():
            return []

        symbols = set()
        for csv_file in self.data_directory.glob("*.csv"):
            # Extract symbol from filename (e.g., "btcusdt_15m.csv" -> "BTCUSDT")
            name_parts = csv_file.stem.split('_')
            if len(name_parts) >= 2:
                symbol = name_parts[0].upper()
                symbols.add(symbol)

        return sorted(list(symbols))

    def get_date_range(self, symbol: str, timeframe: TimeFrame) -> tuple[datetime, datetime]:
        """Get available date range for symbol."""
        csv_path = self._get_csv_path(symbol, timeframe)

        if not csv_path.exists():
            return datetime(2020, 1, 1), datetime.now()

        try:
            # Read first and last rows to get date range
            with open(csv_path, 'r') as file:
                reader = csv.DictReader(file)
                rows = list(reader)

                if not rows:
                    return datetime(2020, 1, 1), datetime.now()

                first_row = rows[0]
                last_row = rows[-1]

                # Parse timestamps
                first_time_str = first_row.get('timestamp') or first_row.get('open_time')
                last_time_str = last_row.get('timestamp') or last_row.get('open_time')

                if not first_time_str or not last_time_str:
                    return datetime(2020, 1, 1), datetime.now()

                try:
                    first_time = datetime.fromisoformat(first_time_str.replace('Z', '+00:00'))
                    last_time = datetime.fromisoformat(last_time_str.replace('Z', '+00:00'))
                except ValueError:
                    # Try Unix timestamp
                    first_time = datetime.fromtimestamp(int(first_time_str) / 1000)
                    last_time = datetime.fromtimestamp(int(last_time_str) / 1000)

                return first_time, last_time

        except Exception as e:
            logger.error(f"Error getting date range from CSV: {e}")
            return datetime(2020, 1, 1), datetime.now()


class StreamingDataset:
    """
    Streams candle data for real-time backtesting simulation.
    """

    def __init__(self, dataset: CandleDataset):
        """
        Initialize streaming dataset.

        Args:
            dataset: Underlying dataset to stream from
        """
        self.dataset = dataset
        self.current_candles: List[Candle] = []
        self.current_index = 0

    def start_stream(
        self,
        symbol: str,
        timeframe: TimeFrame,
        start_time: datetime,
        end_time: datetime
    ) -> None:
        """
        Start streaming candles for the specified range.

        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            start_time: Start time
            end_time: End time
        """
        self.current_candles = self.dataset.load_candles(
            symbol, timeframe, start_time, end_time
        )
        self.current_index = 0
        logger.info(f"Started streaming {len(self.current_candles)} candles")

    def next_candle(self) -> Optional[Candle]:
        """
        Get next candle in stream.

        Returns:
            Next candle or None if stream is finished
        """
        if self.current_index >= len(self.current_candles):
            return None

        candle = self.current_candles[self.current_index]
        self.current_index += 1
        return candle

    def has_more(self) -> bool:
        """Check if more candles are available."""
        return self.current_index < len(self.current_candles)

    def get_progress(self) -> float:
        """Get streaming progress as percentage."""
        if not self.current_candles:
            return 100.0

        return (self.current_index / len(self.current_candles)) * 100.0


def create_dataset(source: str, **kwargs) -> CandleDataset:
    """
    Factory function to create dataset based on source type.

    Args:
        source: Dataset source ("timescale" or "csv")
        **kwargs: Additional arguments for dataset creation

    Returns:
        Configured dataset instance
    """
    if source.lower() == "timescale":
        database_url = kwargs.get("database_url")
        if not database_url:
            raise ValueError("database_url required for TimescaleDB dataset")
        return TimescaleDataset(database_url)

    elif source.lower() == "csv":
        data_directory = kwargs.get("data_directory")
        if not data_directory:
            raise ValueError("data_directory required for CSV dataset")
        return CSVDataset(data_directory)

    else:
        raise ValueError(f"Unknown dataset source: {source}")


def export_candles_to_csv(
    candles: List[Candle],
    output_path: str,
    include_headers: bool = True
) -> None:
    """
    Export candles to CSV format.

    Args:
        candles: List of candles to export
        output_path: Output CSV file path
        include_headers: Whether to include column headers
    """
    with open(output_path, 'w', newline='') as file:
        fieldnames = [
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'quote_volume', 'trades', 'taker_buy_volume', 'taker_buy_quote_volume'
        ]

        writer = csv.DictWriter(file, fieldnames=fieldnames)

        if include_headers:
            writer.writeheader()

        for candle in candles:
            writer.writerow({
                'timestamp': candle.open_time.isoformat(),
                'open': str(candle.open_price),
                'high': str(candle.high_price),
                'low': str(candle.low_price),
                'close': str(candle.close_price),
                'volume': str(candle.volume),
                'quote_volume': str(candle.quote_volume),
                'trades': candle.trades,
                'taker_buy_volume': str(candle.taker_buy_base_volume),
                'taker_buy_quote_volume': str(candle.taker_buy_quote_volume)
            })

    logger.info(f"Exported {len(candles)} candles to {output_path}")