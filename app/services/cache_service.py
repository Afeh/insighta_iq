"""
Caching layer for query results.
Supports both Redis (if available) and in-memory caching with TTL.
"""

import json
import time
from typing import Any, Optional, Dict
from abc import ABC, abstractmethod
import hashlib


class CacheBackend(ABC):
    """Abstract cache backend interface."""
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        pass
    
    @abstractmethod
    def delete(self, key: str) -> None:
        pass
    
    @abstractmethod
    def clear(self) -> None:
        pass


class InMemoryCache(CacheBackend):
    """Simple in-memory cache with TTL support."""
    
    def __init__(self):
        self._cache: Dict[str, tuple] = {}  # key -> (value, expiry_time)
    
    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        
        value, expiry = self._cache[key]
        if time.time() > expiry:
            del self._cache[key]
            return None
        
        return value
    
    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        expiry = time.time() + ttl
        self._cache[key] = (value, expiry)
    
    def delete(self, key: str) -> None:
        if key in self._cache:
            del self._cache[key]
    
    def clear(self) -> None:
        self._cache.clear()
    
    def cleanup_expired(self) -> None:
        """Remove expired entries (called periodically)."""
        current_time = time.time()
        self._cache = {
            k: v for k, v in self._cache.items()
            if v[1] > current_time
        }


try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class RedisCache(CacheBackend):
    """Redis-based cache backend."""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        if not REDIS_AVAILABLE:
            raise ImportError("redis package not installed")
        
        self.client = redis.from_url(redis_url, decode_responses=True)
    
    def get(self, key: str) -> Optional[Any]:
        value = self.client.get(key)
        if value is None:
            return None
        return json.loads(value)
    
    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        self.client.setex(
            key,
            ttl,
            json.dumps(value, default=str)
        )
    
    def delete(self, key: str) -> None:
        self.client.delete(key)
    
    def clear(self) -> None:
        self.client.flushdb()


def get_cache_backend() -> CacheBackend:
    """
    Factory function to get the appropriate cache backend.
    Tries Redis first, falls back to in-memory cache.
    """
    try:
        if REDIS_AVAILABLE:
            cache = RedisCache()
            # Test connection
            cache.client.ping()
            return cache
    except Exception:
        pass
    
    # Fallback to in-memory cache
    return InMemoryCache()


# Global cache instance
_cache_instance: Optional[CacheBackend] = None


def get_cache() -> CacheBackend:
    """Get or create the global cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = get_cache_backend()
    return _cache_instance


def generate_cache_key(prefix: str, **params) -> str:
    """Generate a deterministic cache key from parameters."""
    # Create a canonical representation of parameters
    items = sorted(params.items())
    key_str = json.dumps(items, sort_keys=True, default=str)
    
    # Create a hash to keep key length reasonable
    hash_val = hashlib.md5(key_str.encode()).hexdigest()
    return f"{prefix}:{hash_val}"


# Query cache prefixes
QUERY_CACHE_PREFIX = "query"
PROFILE_COUNT_CACHE_PREFIX = "profile_count"
