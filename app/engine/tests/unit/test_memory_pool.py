"""
Unit tests for memory pool.
Following T-3: Pure logic unit tests without external dependencies.
Following T-4: Avoiding heavy mocking.
"""

import pytest
import numpy as np
import threading
import time
from typing import Any

from app.engine.core.memory_pool import (
    create_pool,
    acquire,
    release,
    get_pool_stats,
    trim_pool,
    ArrayPool,
    PooledArray,
    PoolStats,
    PoolExhaustedError,
    ArrayCorruptedError,
)


class TestCreatePool:
    """Tests for pool creation."""

    def test_create_pool_initialization(self):
        """Pool allocates arrays with correct shape/dtype."""
        pool = create_pool(shape=(100, 10), dtype=np.float64, capacity=5)

        assert pool.shape == (100, 10)
        assert pool.dtype == np.float64
        assert pool.capacity == 5
        assert len(pool.free) == 5
        assert len(pool.used) == 0

    def test_create_pool_different_dtypes(self):
        """Pool supports different numpy dtypes."""
        int_pool = create_pool(shape=(50,), dtype=np.int32, capacity=3)
        float_pool = create_pool(shape=(50,), dtype=np.float32, capacity=3)

        assert int_pool.dtype == np.int32
        assert float_pool.dtype == np.float32

    def test_create_pool_validation(self):
        """Pool creation validates parameters."""
        with pytest.raises(ValueError):
            create_pool(shape=(100,), dtype=np.float64, capacity=0)

        with pytest.raises(ValueError):
            create_pool(shape=(), dtype=np.float64, capacity=5)


class TestAcquireRelease:
    """Tests for array acquisition and release."""

    def test_acquire_from_pool(self):
        """Returns array from pool when available."""
        pool = create_pool(shape=(10, 5), dtype=np.float32, capacity=3)

        array = acquire(pool)

        assert isinstance(array, PooledArray)
        assert array.shape == (10, 5)
        assert array.dtype == np.float32
        assert np.all(array.data == 0)  # Should be zeroed
        assert len(pool.free) == 2
        assert len(pool.used) == 1

    def test_acquire_pool_exhausted(self):
        """Allocates new array when pool empty."""
        pool = create_pool(shape=(10,), dtype=np.float64, capacity=2)

        # Acquire all from pool
        arr1 = acquire(pool)
        arr2 = acquire(pool)

        assert len(pool.free) == 0
        assert len(pool.used) == 2

        # Should allocate new array
        arr3 = acquire(pool)

        assert arr3 is not None
        assert len(pool.used) == 3
        assert pool.stats.allocations == 1  # One new allocation

    def test_release_returns_to_pool(self):
        """Released arrays available for reacquisition."""
        pool = create_pool(shape=(5, 5), dtype=np.int32, capacity=2)

        arr1 = acquire(pool)
        original_id = id(arr1._array)

        release(arr1)

        assert len(pool.free) == 2
        assert len(pool.used) == 0

        # Should get same array back
        arr2 = acquire(pool)
        assert id(arr2._array) == original_id

    def test_release_validates_array_integrity(self):
        """Detects corrupted arrays via checksum."""
        pool = create_pool(shape=(10,), dtype=np.float64, capacity=2)

        array = acquire(pool)
        array._checksum = 0xDEADBEEF  # Corrupt checksum

        with pytest.raises(ArrayCorruptedError):
            release(array)

    def test_release_zeros_array(self):
        """Released arrays are properly zeroed."""
        pool = create_pool(shape=(5,), dtype=np.float64, capacity=2)

        array = acquire(pool)
        array.data[:] = 42.0  # Modify array

        release(array)

        # Reacquire and check it's zeroed
        array2 = acquire(pool)
        assert np.all(array2.data == 0)


class TestPoolStats:
    """Tests for pool statistics tracking."""

    def test_pool_stats_tracking(self):
        """Accurately tracks utilization and hit rate."""
        pool = create_pool(shape=(10,), dtype=np.float64, capacity=2)

        # Initial stats
        stats = get_pool_stats(pool)
        assert stats.hit_rate == 1.0
        assert stats.utilization == 0.0

        # Acquire arrays
        arr1 = acquire(pool)
        arr2 = acquire(pool)

        stats = get_pool_stats(pool)
        assert stats.hit_rate == 1.0  # All from pool
        assert stats.utilization == 1.0  # Pool fully used

        # Force allocation
        arr3 = acquire(pool)

        stats = get_pool_stats(pool)
        assert stats.hit_rate == 2 / 3  # 2 hits, 1 miss
        assert stats.allocations == 1

    def test_pool_stats_memory_usage(self):
        """Tracks memory usage accurately."""
        pool = create_pool(shape=(1000, 100), dtype=np.float64, capacity=5)

        stats = get_pool_stats(pool)
        expected_memory = 1000 * 100 * 8 * 5  # shape * dtype_size * capacity
        assert stats.memory_bytes == expected_memory

    def test_pool_stats_average_hold_time(self):
        """Tracks average array hold time."""
        pool = create_pool(shape=(10,), dtype=np.float64, capacity=2)

        arr1 = acquire(pool)
        time.sleep(0.1)
        release(arr1)

        stats = get_pool_stats(pool)
        assert stats.avg_hold_time >= 0.1
        assert stats.avg_hold_time < 0.2


class TestTrimPool:
    """Tests for pool trimming."""

    def test_trim_pool_lru_eviction(self):
        """Removes least recently used arrays."""
        pool = create_pool(shape=(10,), dtype=np.float64, capacity=3)

        # Force expansion
        arrays = [acquire(pool) for _ in range(5)]
        for arr in arrays:
            release(arr)

        assert len(pool.free) == 5

        # Trim to 3
        freed = trim_pool(pool, target_size=3)

        assert freed == 2
        assert len(pool.free) == 3

    def test_trim_pool_no_trim_needed(self):
        """Does nothing when pool within target."""
        pool = create_pool(shape=(10,), dtype=np.float64, capacity=3)

        freed = trim_pool(pool, target_size=5)

        assert freed == 0
        assert len(pool.free) == 3

    def test_trim_pool_minimum_size(self):
        """Maintains minimum pool size."""
        pool = create_pool(shape=(10,), dtype=np.float64, capacity=5)

        freed = trim_pool(pool, target_size=0)

        assert freed == 4  # Keeps at least 1
        assert len(pool.free) == 1


class TestConcurrency:
    """Tests for thread safety."""

    def test_concurrent_acquire_release(self):
        """Thread-safe under concurrent access."""
        pool = create_pool(shape=(100,), dtype=np.float64, capacity=10)
        errors = []

        def worker():
            try:
                for _ in range(100):
                    arr = acquire(pool)
                    arr.data[:] = np.random.random(100)
                    time.sleep(0.0001)
                    release(arr)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(pool.used) == 0  # All released

    def test_memory_leak_detection(self):
        """Identifies arrays held too long."""
        pool = create_pool(shape=(10,), dtype=np.float64, capacity=2)
        pool.max_hold_seconds = 0.1

        arr = acquire(pool)
        time.sleep(0.2)

        stats = get_pool_stats(pool)
        assert len(stats.potential_leaks) == 1
        assert arr in stats.potential_leaks
