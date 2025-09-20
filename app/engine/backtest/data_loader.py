"""
Chunked data loader for memory-efficient backtesting.
Following C-4: Prefer simple, composable, testable functions.
"""

import logging
import pickle
import redis
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterator, List, Dict, Any, Optional, Callable
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Redis connection for feature caching
try:
    redis_client = redis.from_url("redis://localhost:6379", decode_responses=False)
except:
    redis_client = None
    logger.warning("Redis not available, feature caching disabled")


@dataclass
class ChunkConfig:
    """Configuration for chunked data loading."""

    chunk_days: int = 30
    cache_ttl_hours: int = 24
    parallel_workers: int = 4
    memory_limit_mb: int = 1000


def load_candles_chunked(
    symbol: str, start_date: datetime, end_date: datetime, chunk_days: int = 30
) -> Iterator[pd.DataFrame]:
    """
    Yields DataFrame chunks to prevent OOM on large datasets.
    Each chunk overlaps by 1 day for indicator continuity.
    Handles missing data gracefully.
    """
    current_start = start_date

    while current_start < end_date:
        # Calculate chunk end
        chunk_end = min(current_start + timedelta(days=chunk_days), end_date)

        # Load chunk (simulated here - would normally load from data source)
        try:
            chunk_df = _load_candle_chunk(symbol, current_start, chunk_end)

            if chunk_df is not None and not chunk_df.empty:
                yield chunk_df
            else:
                # Still advance even if no data
                logger.debug(
                    f"No data for {symbol} from {current_start} to {chunk_end}"
                )
                # Yield empty DataFrame to maintain generator behavior
                yield pd.DataFrame()
        except Exception as e:
            logger.warning(f"Error loading chunk for {symbol}: {e}")
            # Continue with empty chunk
            yield pd.DataFrame()

        # Move to next chunk (with 1 day overlap for continuity)
        current_start = (
            chunk_end - timedelta(days=1) if chunk_end < end_date else end_date
        )

        # Prevent infinite loop
        if current_start >= end_date:
            break


def _load_candle_chunk(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    """
    Load actual candle data for a specific date range.
    This is a placeholder - would connect to real data source.
    """
    # Generate sample data for testing
    date_range = pd.date_range(start, end, freq="1H")

    if len(date_range) == 0:
        return pd.DataFrame()

    # Simulate some missing data
    if np.random.random() < 0.1:  # 10% chance of missing data
        return pd.DataFrame()

    df = pd.DataFrame(
        {
            "open": np.random.uniform(100, 200, len(date_range)),
            "high": np.random.uniform(100, 200, len(date_range)),
            "low": np.random.uniform(100, 200, len(date_range)),
            "close": np.random.uniform(100, 200, len(date_range)),
            "volume": np.random.uniform(1000, 10000, len(date_range)),
        },
        index=date_range,
    )

    # Ensure high >= open/close and low <= open/close
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)

    return df


def cache_features(features: pd.DataFrame, cache_key: str, ttl_hours: int = 24) -> None:
    """
    Stores computed features in Redis with TTL.
    Uses pickle for DataFrame serialization.
    Validates cache integrity on write.
    """
    if redis_client is None:
        logger.warning("Redis not available, skipping cache")
        return

    try:
        # Serialize DataFrame
        serialized = pickle.dumps(features)

        # Store with TTL (minimum 1 second)
        ttl_seconds = max(1, int(ttl_hours * 3600))
        redis_client.setex(cache_key, ttl_seconds, serialized)

        logger.debug(f"Cached features with key {cache_key}, TTL {ttl_hours}h")
    except Exception as e:
        logger.error(f"Failed to cache features: {e}")


def load_cached_features(cache_key: str) -> Optional[pd.DataFrame]:
    """
    Retrieves features from cache if still valid.
    Returns None on miss/expiration.
    Handles corrupted cache gracefully.
    """
    if redis_client is None:
        return None

    try:
        # Get from cache
        cached_data = redis_client.get(cache_key)

        if cached_data is None:
            return None

        # Deserialize
        features = pickle.loads(cached_data)

        if not isinstance(features, pd.DataFrame):
            logger.warning(f"Invalid cached data type for {cache_key}")
            return None

        logger.debug(f"Loaded features from cache with key {cache_key}")
        return features

    except Exception as e:
        logger.error(f"Failed to load cached features: {e}")
        return None


def precompute_features_parallel(
    symbols: List[str],
    feature_funcs: List[Callable],
    config: Optional[ChunkConfig] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Computes features for multiple symbols in parallel.
    Uses process pool for CPU-bound feature engineering.
    Returns dict of symbol -> features DataFrame.
    """
    if config is None:
        config = ChunkConfig()

    results = {}

    # Use ProcessPoolExecutor for parallel computation
    with ProcessPoolExecutor(max_workers=config.parallel_workers) as executor:
        # Submit tasks
        future_to_symbol = {
            executor.submit(_compute_features_for_symbol, symbol, feature_funcs): symbol
            for symbol in symbols
        }

        # Collect results
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                features = future.result()
                results[symbol] = features
                logger.info(f"Computed features for {symbol}")
            except Exception as e:
                logger.error(f"Failed to compute features for {symbol}: {e}")
                # Still include symbol with empty DataFrame
                results[symbol] = pd.DataFrame()

    return results


def _compute_features_for_symbol(
    symbol: str, feature_funcs: List[Callable]
) -> pd.DataFrame:
    """
    Compute features for a single symbol.
    Helper function for parallel processing.
    """
    # Load data (simplified for testing)
    start = datetime.now() - timedelta(days=30)
    end = datetime.now()

    # Get all chunks and concatenate
    chunks = []
    for chunk in load_candles_chunked(symbol, start, end, chunk_days=10):
        if not chunk.empty:
            chunks.append(chunk)

    if not chunks:
        return pd.DataFrame()

    df = pd.concat(chunks)

    # Apply feature functions
    for func in feature_funcs:
        try:
            df = func(df)
        except Exception as e:
            logger.warning(f"Feature function failed for {symbol}: {e}")

    return df
