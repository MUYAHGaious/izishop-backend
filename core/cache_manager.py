"""
Enterprise Cache Management System
Multi-layer caching with Redis, in-memory, and database query optimization
"""
import json
import time
import hashlib
import logging
from typing import Any, Optional, Dict, List, Callable, Union
from functools import wraps
from datetime import datetime, timedelta
import asyncio
import redis.asyncio as redis
from core.security_config import get_security_settings

logger = logging.getLogger(__name__)


class CacheLevel:
    """Cache level constants"""
    MEMORY = "memory"
    REDIS = "redis"
    DATABASE = "database"


class CacheManager:
    """Enterprise multi-layer cache management"""
    
    def __init__(self):
        self.settings = get_security_settings()
        self.redis_client = None
        self.memory_cache = {}
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0
        }
        self._setup_redis()
    
    async def _setup_redis(self):
        """Setup Redis connection"""
        try:
            self.redis_client = redis.from_url(
                self.settings.REDIS_URL,
                password=getattr(self.settings, 'REDIS_PASSWORD', None),
                decode_responses=True
            )
            await self.redis_client.ping()
            logger.info("Redis cache connection established")
        except Exception as e:
            logger.warning(f"Redis cache connection failed: {e}")
            self.redis_client = None
    
    def _generate_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate consistent cache key"""
        key_data = f"{prefix}:{args}:{sorted(kwargs.items())}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Get value from multi-layer cache"""
        try:
            # Layer 1: Memory cache (fastest)
            if key in self.memory_cache:
                entry = self.memory_cache[key]
                if entry["expires"] > time.time():
                    self.cache_stats["hits"] += 1
                    logger.debug(f"Cache HIT (memory): {key}")
                    return entry["value"]
                else:
                    del self.memory_cache[key]
            
            # Layer 2: Redis cache
            if self.redis_client:
                try:
                    value = await self.redis_client.get(key)
                    if value is not None:
                        # Store in memory cache for faster access
                        self.memory_cache[key] = {
                            "value": json.loads(value),
                            "expires": time.time() + 300  # 5 minutes in memory
                        }
                        self.cache_stats["hits"] += 1
                        logger.debug(f"Cache HIT (redis): {key}")
                        return json.loads(value)
                except Exception as e:
                    logger.error(f"Redis get error: {e}")
            
            # Cache miss
            self.cache_stats["misses"] += 1
            logger.debug(f"Cache MISS: {key}")
            return default
            
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return default
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: int = 3600,
        memory_ttl: int = 300
    ):
        """Set value in multi-layer cache"""
        try:
            serialized_value = json.dumps(value, default=str)
            
            # Layer 1: Memory cache
            self.memory_cache[key] = {
                "value": value,
                "expires": time.time() + memory_ttl
            }
            
            # Layer 2: Redis cache
            if self.redis_client:
                try:
                    await self.redis_client.setex(key, ttl, serialized_value)
                except Exception as e:
                    logger.error(f"Redis set error: {e}")
            
            self.cache_stats["sets"] += 1
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            
        except Exception as e:
            logger.error(f"Cache set error: {e}")
    
    async def delete(self, key: str):
        """Delete from all cache layers"""
        try:
            # Remove from memory
            if key in self.memory_cache:
                del self.memory_cache[key]
            
            # Remove from Redis
            if self.redis_client:
                try:
                    await self.redis_client.delete(key)
                except Exception as e:
                    logger.error(f"Redis delete error: {e}")
            
            self.cache_stats["deletes"] += 1
            logger.debug(f"Cache DELETE: {key}")
            
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
    
    async def clear_pattern(self, pattern: str):
        """Clear cache keys matching pattern"""
        try:
            # Clear memory cache
            keys_to_delete = [k for k in self.memory_cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self.memory_cache[key]
            
            # Clear Redis cache
            if self.redis_client:
                try:
                    keys = await self.redis_client.keys(f"*{pattern}*")
                    if keys:
                        await self.redis_client.delete(*keys)
                except Exception as e:
                    logger.error(f"Redis pattern delete error: {e}")
            
            logger.info(f"Cleared cache pattern: {pattern}")
            
        except Exception as e:
            logger.error(f"Clear cache pattern error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (self.cache_stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "stats": self.cache_stats.copy(),
            "hit_rate": round(hit_rate, 2),
            "memory_cache_size": len(self.memory_cache),
            "redis_available": self.redis_client is not None
        }
    
    def cleanup_memory_cache(self):
        """Remove expired entries from memory cache"""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self.memory_cache.items()
            if entry["expires"] <= current_time
        ]
        
        for key in expired_keys:
            del self.memory_cache[key]
        
        logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")


# Global cache manager instance
cache_manager = CacheManager()


def cached(
    ttl: int = 3600,
    key_prefix: str = None,
    memory_ttl: int = 300,
    skip_if_authenticated: bool = False
):
    """
    Decorator for caching function results
    
    Args:
        ttl: Redis cache TTL in seconds
        key_prefix: Custom key prefix
        memory_ttl: Memory cache TTL in seconds
        skip_if_authenticated: Skip caching for authenticated requests
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            prefix = key_prefix or f"{func.__module__}.{func.__name__}"
            cache_key = cache_manager._generate_cache_key(prefix, *args, **kwargs)
            
            # Skip caching logic
            if skip_if_authenticated:
                # Check if request has authentication (simplified check)
                request = kwargs.get('request')
                if request and hasattr(request, 'headers'):
                    auth_header = request.headers.get('Authorization')
                    if auth_header:
                        return await func(*args, **kwargs)
            
            # Try to get from cache
            cached_result = await cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            await cache_manager.set(cache_key, result, ttl=ttl, memory_ttl=memory_ttl)
            
            return result
        return wrapper
    return decorator


def cache_invalidate(pattern: str):
    """
    Decorator for invalidating cache on function execution
    
    Args:
        pattern: Cache key pattern to invalidate
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            await cache_manager.clear_pattern(pattern)
            return result
        return wrapper
    return decorator


class QueryCache:
    """Database query result caching"""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
    
    async def get_or_set(
        self,
        query_key: str,
        query_func: Callable,
        ttl: int = 1800,  # 30 minutes
        *args,
        **kwargs
    ):
        """Get query result from cache or execute and cache"""
        cache_key = f"query:{query_key}"
        
        # Try cache first
        result = await self.cache.get(cache_key)
        if result is not None:
            return result
        
        # Execute query
        result = await query_func(*args, **kwargs)
        
        # Cache result
        await self.cache.set(cache_key, result, ttl=ttl)
        
        return result
    
    async def invalidate_query(self, query_key: str):
        """Invalidate specific query cache"""
        await self.cache.delete(f"query:{query_key}")
    
    async def invalidate_table(self, table_name: str):
        """Invalidate all queries for a table"""
        await self.cache.clear_pattern(f"query:{table_name}")


class SessionCache:
    """User session caching for performance"""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
    
    async def get_user_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cached user session data"""
        cache_key = f"session:user:{user_id}"
        return await self.cache.get(cache_key)
    
    async def set_user_session(
        self,
        user_id: str,
        session_data: Dict[str, Any],
        ttl: int = 3600
    ):
        """Cache user session data"""
        cache_key = f"session:user:{user_id}"
        await self.cache.set(cache_key, session_data, ttl=ttl)
    
    async def invalidate_user_session(self, user_id: str):
        """Invalidate user session cache"""
        cache_key = f"session:user:{user_id}"
        await self.cache.delete(cache_key)
    
    async def get_shop_data(self, shop_id: str) -> Optional[Dict[str, Any]]:
        """Get cached shop data"""
        cache_key = f"shop:{shop_id}"
        return await self.cache.get(cache_key)
    
    async def set_shop_data(
        self,
        shop_id: str,
        shop_data: Dict[str, Any],
        ttl: int = 1800
    ):
        """Cache shop data"""
        cache_key = f"shop:{shop_id}"
        await self.cache.set(cache_key, shop_data, ttl=ttl)


# Global instances
query_cache = QueryCache(cache_manager)
session_cache = SessionCache(cache_manager)


# Cache middleware for automatic cleanup
class CacheMiddleware:
    """Middleware for cache management and cleanup"""
    
    def __init__(self, app):
        self.app = app
        self.cache = cache_manager
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # 5 minutes
    
    async def __call__(self, scope, receive, send):
        # Periodic cleanup
        current_time = time.time()
        if current_time - self.last_cleanup > self.cleanup_interval:
            self.cache.cleanup_memory_cache()
            self.last_cleanup = current_time
        
        await self.app(scope, receive, send)