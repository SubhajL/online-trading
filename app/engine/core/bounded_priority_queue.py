"""
Memory-safe priority queue with TTL support.
"""

import asyncio
import heapq
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Generic, List, Optional, TypeVar

from app.engine.core.clock import Clock, SystemClock


T = TypeVar("T")


class QueueFullError(Exception):
    """Raised when queue is at maximum capacity."""

    pass


@dataclass
class QueueItem(Generic[T]):
    """Item in the priority queue with expiration."""

    data: T
    priority: int
    added_at: datetime
    expires_at: datetime

    def __lt__(self, other: "QueueItem") -> bool:
        """Compare by priority (higher priority = smaller value for min-heap)."""
        return -self.priority < -other.priority


@dataclass
class QueueStats:
    """Statistics for the queue."""

    current_size: int
    max_size: int
    total_added: int
    total_retrieved: int
    expired_count: int
    oldest_item_age: Optional[float] = None


class BoundedPriorityQueue(Generic[T]):
    """
    Thread-safe priority queue with size limits and TTL.

    Items expire after TTL and are removed to prevent memory leaks.
    Higher priority values are retrieved first.
    """

    def __init__(
        self, max_size: int, ttl_seconds: float, clock: Optional[Clock] = None
    ):
        """Initialize queue with bounds."""
        self._max_size = max_size
        self._default_ttl = ttl_seconds
        self._clock = clock or SystemClock()

        # Thread-safe heap
        self._heap: List[QueueItem[T]] = []
        self._lock = asyncio.Lock()

        # Statistics
        self._total_added = 0
        self._total_retrieved = 0
        self._expired_count = 0

        # Event for waiting
        self._item_available = asyncio.Event()

    async def put_with_ttl(
        self, item: T, priority: int, custom_ttl: Optional[float] = None
    ) -> None:
        """
        Add item with priority and TTL.

        Args:
            item: The data to store
            priority: Higher values retrieved first
            custom_ttl: Override default TTL for this item

        Raises:
            QueueFullError: If queue is at max capacity
        """
        async with self._lock:
            # Clean expired items first
            self._cleanup_expired_unsafe()

            # Check capacity
            if len(self._heap) >= self._max_size:
                raise QueueFullError(f"Queue at maximum capacity: {self._max_size}")

            # Create queue item
            now = self._clock.now()
            ttl = custom_ttl if custom_ttl is not None else self._default_ttl
            queue_item = QueueItem(
                data=item,
                priority=priority,
                added_at=now,
                expires_at=now + timedelta(seconds=ttl),
            )

            # Add to heap
            heapq.heappush(self._heap, queue_item)
            self._total_added += 1

            # Signal item available
            self._item_available.set()

    async def get_not_expired(self) -> Optional[QueueItem[T]]:
        """
        Get highest priority non-expired item.

        Returns None if queue is empty or all items expired.
        """
        async with self._lock:
            now = self._clock.now()

            while self._heap:
                # Peek at highest priority
                item = heapq.heappop(self._heap)

                if item.expires_at > now:
                    # Valid item
                    self._total_retrieved += 1
                    return item
                else:
                    # Expired
                    self._expired_count += 1

            # No valid items
            self._item_available.clear()
            return None

    async def wait_for_item(
        self, timeout: Optional[float] = None
    ) -> Optional[QueueItem[T]]:
        """
        Wait for an item to become available.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            Item if available, None if timeout
        """
        try:
            await asyncio.wait_for(self._item_available.wait(), timeout=timeout)
            return await self.get_not_expired()
        except asyncio.TimeoutError:
            return None

    async def get_all_valid(self) -> List[QueueItem[T]]:
        """Get all non-expired items in priority order."""
        async with self._lock:
            self._cleanup_expired_unsafe()

            # Return sorted copy
            valid_items = list(self._heap)
            valid_items.sort(key=lambda x: -x.priority)
            return valid_items

    async def cleanup_expired(self) -> int:
        """
        Remove all expired items.

        Returns:
            Number of items removed
        """
        async with self._lock:
            return self._cleanup_expired_unsafe()

    def _cleanup_expired_unsafe(self) -> int:
        """
        Remove expired items without lock.

        Must be called within lock context.
        """
        now = self._clock.now()
        valid_items = []
        removed = 0

        # Filter out expired
        while self._heap:
            item = heapq.heappop(self._heap)
            if item.expires_at > now:
                valid_items.append(item)
            else:
                removed += 1
                self._expired_count += 1

        # Rebuild heap with valid items
        self._heap = valid_items
        heapq.heapify(self._heap)

        return removed

    async def clear(self) -> None:
        """Remove all items from queue."""
        async with self._lock:
            self._heap.clear()
            self._item_available.clear()

    def get_stats(self) -> QueueStats:
        """Get queue statistics."""
        oldest_age = None
        if self._heap:
            now = self._clock.now()
            oldest = min(self._heap, key=lambda x: x.added_at)
            oldest_age = (now - oldest.added_at).total_seconds()

        return QueueStats(
            current_size=len(self._heap),
            max_size=self._max_size,
            total_added=self._total_added,
            total_retrieved=self._total_retrieved,
            expired_count=self._expired_count,
            oldest_item_age=oldest_age,
        )

    def __len__(self) -> int:
        """Get current queue size."""
        return len(self._heap)
