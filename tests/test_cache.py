"""Tests for the memory cache module."""

import time
import pytest
from vault_agent.cache import MemoryCache


class TestMemoryCache:
    """Test cases for MemoryCache."""

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = MemoryCache(default_ttl=5)

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        cache.set("key2", {"nested": "value"})
        assert cache.get("key2") == {"nested": "value"}

    def test_cache_expiration(self):
        """Test that cache entries expire."""
        cache = MemoryCache(default_ttl=1)

        cache.set("key1", "value1", ttl=1)
        assert cache.get("key1") == "value1"

        time.sleep(1.5)
        assert cache.get("key1") is None

    def test_cache_miss(self):
        """Test cache miss returns None."""
        cache = MemoryCache()
        assert cache.get("nonexistent") is None

    def test_delete(self):
        """Test deleting cache entries."""
        cache = MemoryCache()

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        assert cache.delete("key1") is True
        assert cache.get("key1") is None

        assert cache.delete("nonexistent") is False

    def test_clear(self):
        """Test clearing the cache."""
        cache = MemoryCache()

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_cache_stats(self):
        """Test cache statistics."""
        cache = MemoryCache(max_size=10)

        assert cache.get("miss1") is None
        assert cache.get("miss2") is None

        cache.set("hit1", "value1")
        assert cache.get("hit1") == "value1"

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 2
        assert stats["size"] == 1
        assert stats["max_size"] == 10

    def test_max_size_eviction(self):
        """Test that cache evicts entries when max size is reached."""
        cache = MemoryCache(default_ttl=60, max_size=3)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        assert cache.get_stats()["size"] == 3

        cache.set("key4", "value4")

        assert cache.get_stats()["size"] == 3
        assert cache.get("key4") == "value4"