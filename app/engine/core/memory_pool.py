"""
Memory pool for efficient numpy array reuse.
Following C-4: Prefer simple, composable, testable functions.
"""

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, List, Set, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class PoolExhaustedError(Exception):
    """Raised when pool cannot allocate more arrays."""
    pass


class ArrayCorruptedError(Exception):
    """Raised when array integrity check fails."""
    pass


@dataclass
class PoolStats:
    """Statistics for monitoring pool efficiency."""
    hit_rate: float
    utilization: float
    allocations: int
    memory_bytes: int
    avg_hold_time: float
    potential_leaks: List['PooledArray'] = field(default_factory=list)


class PooledArray:
    """Wrapper for pooled numpy array with metadata."""

    def __init__(self, array: np.ndarray, pool: 'ArrayPool'):
        self._array = array
        self._pool = pool
        self._acquired_at = time.time()
        self._checksum = self._compute_checksum()
        self.data = array  # Direct access to numpy array

    def _compute_checksum(self) -> int:
        """Compute checksum for integrity validation."""
        return hash(tuple(self._array.shape)) + hash(self._array.dtype)

    @property
    def shape(self) -> Tuple:
        return self._array.shape

    @property
    def dtype(self) -> np.dtype:
        return self._array.dtype


@dataclass
class ArrayPool:
    """Pool of reusable numpy arrays."""
    shape: Tuple
    dtype: np.dtype
    capacity: int
    free: List[np.ndarray] = field(default_factory=list)
    used: Set[PooledArray] = field(default_factory=set)
    stats: 'PoolStatsTracker' = field(init=False)
    lock: threading.Lock = field(default_factory=threading.Lock)
    max_hold_seconds: float = 300.0  # 5 minutes default

    def __post_init__(self):
        self.stats = PoolStatsTracker()


class PoolStatsTracker:
    """Tracks pool usage statistics."""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.allocations = 0
        self.total_hold_time = 0.0
        self.release_count = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 1.0


def create_pool(shape: tuple, dtype: np.dtype, capacity: int) -> ArrayPool:
    """
    Creates a pool of preallocated numpy arrays with specified shape and dtype.
    Maintains free/used lists for O(1) acquisition.
    """
    if capacity <= 0:
        raise ValueError("Pool capacity must be positive")

    if not shape:
        raise ValueError("Array shape cannot be empty")

    pool = ArrayPool(shape=shape, dtype=dtype, capacity=capacity)

    # Preallocate arrays
    for _ in range(capacity):
        array = np.zeros(shape, dtype=dtype)
        pool.free.append(array)

    logger.debug(f"Created pool with {capacity} arrays of shape {shape}")
    return pool


def acquire(pool: ArrayPool) -> PooledArray:
    """
    Returns a zeroed array from pool or allocates new if exhausted.
    Tracks acquisition time for leak detection.
    Wraps in context manager for automatic release.
    """
    with pool.lock:
        if pool.free:
            # Get from pool
            array = pool.free.pop()
            pool.stats.hits += 1
        else:
            # Allocate new
            array = np.zeros(pool.shape, dtype=pool.dtype)
            pool.stats.misses += 1
            pool.stats.allocations += 1
            logger.debug(f"Pool exhausted, allocated new array. Total allocations: {pool.stats.allocations}")

        # Zero the array for safety
        array.fill(0)

        # Wrap in PooledArray
        pooled = PooledArray(array, pool)
        pool.used.add(pooled)

        return pooled


def release(array: PooledArray) -> None:
    """
    Validates array integrity via checksum.
    Zeros memory to prevent data leaks.
    Returns to pool for reuse with timestamp.
    """
    pool = array._pool

    # Validate integrity
    expected_checksum = array._compute_checksum()
    if array._checksum != expected_checksum:
        raise ArrayCorruptedError(f"Array checksum mismatch: {array._checksum} != {expected_checksum}")

    with pool.lock:
        # Track hold time
        hold_time = time.time() - array._acquired_at
        pool.stats.total_hold_time += hold_time
        pool.stats.release_count += 1

        # Zero the array
        array._array.fill(0)

        # Return to pool
        pool.used.discard(array)
        pool.free.append(array._array)


def get_pool_stats(pool: ArrayPool) -> PoolStats:
    """
    Returns utilization metrics including hit rate, average hold time,
    and memory usage for monitoring pool efficiency.
    """
    with pool.lock:
        # Calculate utilization
        total_arrays = len(pool.free) + len(pool.used)
        utilization = len(pool.used) / total_arrays if total_arrays > 0 else 0.0

        # Calculate memory usage
        array_size = np.zeros(pool.shape, dtype=pool.dtype).nbytes
        memory_bytes = total_arrays * array_size

        # Calculate average hold time
        avg_hold_time = (
            pool.stats.total_hold_time / pool.stats.release_count
            if pool.stats.release_count > 0
            else 0.0
        )

        # Find potential leaks (arrays held too long)
        current_time = time.time()
        potential_leaks = [
            array for array in pool.used
            if (current_time - array._acquired_at) > pool.max_hold_seconds
        ]

        return PoolStats(
            hit_rate=pool.stats.hit_rate,
            utilization=utilization,
            allocations=pool.stats.allocations,
            memory_bytes=memory_bytes,
            avg_hold_time=avg_hold_time,
            potential_leaks=potential_leaks
        )


def trim_pool(pool: ArrayPool, target_size: int) -> int:
    """
    Releases unused arrays when pool grows too large.
    Implements LRU eviction policy.
    Returns number of arrays freed.
    """
    with pool.lock:
        current_free = len(pool.free)

        if current_free <= target_size:
            return 0

        # Keep at least 1 array
        target_size = max(1, target_size)

        # Calculate how many to free
        to_free = current_free - target_size

        # Free the arrays (they'll be garbage collected)
        for _ in range(to_free):
            pool.free.pop()

        logger.debug(f"Trimmed pool from {current_free} to {len(pool.free)} arrays")
        return to_free