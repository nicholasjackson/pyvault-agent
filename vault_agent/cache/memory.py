# Copyright 2024 Nicholas Jackson
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""In-memory cache with TTL support."""

import time
from typing import Any, Optional, Dict, Tuple
from threading import Lock

from ..utils.exceptions import CacheError


class CacheEntry:
    """Represents a single cache entry with expiration."""

    def __init__(self, value: Any, ttl: int):
        self.value = value
        self.expires_at = time.time() + ttl

    def is_expired(self) -> bool:
        """Check if the cache entry has expired."""
        return time.time() >= self.expires_at


class MemoryCache:
    """Thread-safe in-memory cache with TTL support."""

    def __init__(self, default_ttl: int = 300, max_size: int = 1000):
        """
        Initialize the memory cache.

        Args:
            default_ttl: Default TTL in seconds for cache entries.
            max_size: Maximum number of entries to store.
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = Lock()
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value from the cache.

        Args:
            key: The cache key.

        Returns:
            The cached value or None if not found or expired.
        """
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if not entry.is_expired():
                    self._hits += 1
                    return entry.value
                else:
                    del self._cache[key]

            self._misses += 1
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Store a value in the cache.

        Args:
            key: The cache key.
            value: The value to cache.
            ttl: Optional TTL in seconds (uses default if not provided).
        """
        if ttl is None:
            ttl = self.default_ttl

        with self._lock:
            if len(self._cache) >= self.max_size:
                self._evict_expired()

                if len(self._cache) >= self.max_size:
                    self._evict_oldest()

            self._cache[key] = CacheEntry(value, ttl)

    def delete(self, key: str) -> bool:
        """
        Remove a key from the cache.

        Args:
            key: The cache key.

        Returns:
            True if the key was removed, False if not found.
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def _evict_expired(self) -> None:
        """Remove expired entries from the cache."""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.expires_at <= current_time
        ]
        for key in expired_keys:
            del self._cache[key]

    def _evict_oldest(self) -> None:
        """Remove the oldest entry from the cache."""
        if not self._cache:
            return

        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].expires_at
        )
        del self._cache[oldest_key]

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._cache),
                "max_size": self.max_size,
            }