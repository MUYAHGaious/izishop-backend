"""
Enterprise Rate Limiting Service
Memory-based and Redis-based rate limiting with enterprise features
"""
import time
import json
import logging
from typing import Dict, Any, Optional, Tuple
from collections import defaultdict, deque
from datetime import datetime, timedelta
from core.security_config import get_security_settings

logger = logging.getLogger(__name__)


class MemoryRateLimiter:
    """In-memory rate limiter with sliding window algorithm"""
    
    def __init__(self):
        self.clients = defaultdict(deque)
        self.settings = get_security_settings()
        self.cleanup_interval = 60  # Cleanup every minute
        self.last_cleanup = time.time()
    
    def is_allowed(
        self,
        identifier: str,
        limit: int = None,
        window: int = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request is allowed under rate limit
        
        Returns:
            Tuple of (is_allowed, metadata)
        """
        current_time = time.time()
        
        # Use settings defaults if not provided
        if limit is None:
            limit = self.settings.RATE_LIMIT_REQUESTS_PER_MINUTE
        if window is None:
            window = 60  # 60 seconds
        
        # Cleanup old entries periodically
        if current_time - self.last_cleanup > self.cleanup_interval:
            self._cleanup_expired_entries(current_time, window)
        
        # Get client's request history
        client_requests = self.clients[identifier]
        
        # Remove expired requests (sliding window)
        cutoff_time = current_time - window
        while client_requests and client_requests[0] <= cutoff_time:
            client_requests.popleft()
        
        # Check if under limit
        current_count = len(client_requests)
        is_allowed = current_count < limit
        
        if is_allowed:
            client_requests.append(current_time)
        
        # Calculate metadata
        remaining = max(0, limit - current_count - (1 if is_allowed else 0))
        reset_time = int(current_time + window)
        
        metadata = {
            "limit": limit,
            "remaining": remaining,
            "reset": reset_time,
            "current_count": current_count + (1 if is_allowed else 0)
        }
        
        return is_allowed, metadata
    
    def _cleanup_expired_entries(self, current_time: float, window: int):
        """Clean up expired entries from all clients"""
        cutoff_time = current_time - window
        
        clients_to_remove = []
        for identifier, requests in self.clients.items():
            # Remove expired requests
            while requests and requests[0] <= cutoff_time:
                requests.popleft()
            
            # Remove clients with no recent requests
            if not requests:
                clients_to_remove.append(identifier)
        
        for identifier in clients_to_remove:
            del self.clients[identifier]
        
        self.last_cleanup = current_time
        logger.debug(f"Rate limiter cleanup: removed {len(clients_to_remove)} inactive clients")


class RedisRateLimiter:
    """Redis-based rate limiter for production use"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.settings = get_security_settings()
        self.fallback_limiter = MemoryRateLimiter()
    
    def is_allowed(
        self,
        identifier: str,
        limit: int = None,
        window: int = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Check if request is allowed with Redis backend"""
        
        # Fallback to memory limiter if Redis unavailable
        if not self.redis:
            logger.warning("Redis unavailable, falling back to memory rate limiter")
            return self.fallback_limiter.is_allowed(identifier, limit, window)
        
        try:
            return self._redis_sliding_window(identifier, limit, window)
        except Exception as e:
            logger.error(f"Redis rate limiter error: {e}, falling back to memory")
            return self.fallback_limiter.is_allowed(identifier, limit, window)
    
    def _redis_sliding_window(
        self,
        identifier: str,
        limit: int,
        window: int
    ) -> Tuple[bool, Dict[str, Any]]:
        """Sliding window rate limiting using Redis"""
        current_time = time.time()
        
        # Use settings defaults
        if limit is None:
            limit = self.settings.RATE_LIMIT_REQUESTS_PER_MINUTE
        if window is None:
            window = 60
        
        pipe = self.redis.pipeline()
        key = f"rate_limit:{identifier}"
        
        # Remove expired entries
        cutoff_time = current_time - window
        pipe.zremrangebyscore(key, 0, cutoff_time)
        
        # Count current requests
        pipe.zcard(key)
        
        # Add current request
        pipe.zadd(key, {str(current_time): current_time})
        
        # Set expiration
        pipe.expire(key, window + 1)
        
        results = pipe.execute()
        current_count = results[1]
        
        is_allowed = current_count < limit
        
        if not is_allowed:
            # Remove the request we just added if not allowed
            self.redis.zrem(key, str(current_time))
        
        remaining = max(0, limit - current_count - (1 if is_allowed else 0))
        reset_time = int(current_time + window)
        
        metadata = {
            "limit": limit,
            "remaining": remaining,
            "reset": reset_time,
            "current_count": current_count + (1 if is_allowed else 0)
        }
        
        return is_allowed, metadata


class EnterpriseRateLimiter:
    """Enterprise rate limiter with advanced features"""
    
    def __init__(self, redis_client=None):
        self.settings = get_security_settings()
        
        # Choose backend based on availability
        if redis_client:
            self.limiter = RedisRateLimiter(redis_client)
            logger.info("Using Redis-based rate limiting")
        else:
            self.limiter = MemoryRateLimiter()
            logger.info("Using memory-based rate limiting")
        
        # User tier configurations
        self.tier_limits = {
            "admin": {"requests": 1000, "window": 60},
            "premium": {"requests": 200, "window": 60},
            "user": {"requests": 100, "window": 60},
            "guest": {"requests": 20, "window": 60}
        }
    
    def check_rate_limit(
        self,
        identifier: str,
        user_tier: str = "user",
        endpoint_type: str = "general"
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Advanced rate limiting with user tiers and endpoint types
        """
        
        # Get limits for user tier
        tier_config = self.tier_limits.get(user_tier, self.tier_limits["user"])
        base_limit = tier_config["requests"]
        window = tier_config["window"]
        
        # Adjust limits based on endpoint type
        endpoint_multipliers = {
            "auth": 0.5,      # Auth endpoints more restrictive
            "upload": 0.2,    # File uploads very restrictive
            "search": 2.0,    # Search more permissive
            "read": 3.0,      # Read operations most permissive
            "general": 1.0    # Default
        }
        
        multiplier = endpoint_multipliers.get(endpoint_type, 1.0)
        adjusted_limit = int(base_limit * multiplier)
        
        # Create unique identifier per endpoint type
        full_identifier = f"{identifier}:{endpoint_type}"
        
        is_allowed, metadata = self.limiter.is_allowed(
            full_identifier,
            adjusted_limit,
            window
        )
        
        # Add tier information to metadata
        metadata.update({
            "user_tier": user_tier,
            "endpoint_type": endpoint_type,
            "base_limit": base_limit,
            "adjusted_limit": adjusted_limit,
            "multiplier": multiplier
        })
        
        # Log rate limit violations
        if not is_allowed:
            logger.warning(
                f"Rate limit exceeded - Identifier: {identifier}, "
                f"Tier: {user_tier}, Endpoint: {endpoint_type}, "
                f"Limit: {adjusted_limit}/{window}s"
            )
        
        return is_allowed, metadata
    
    def get_client_stats(self, identifier: str) -> Dict[str, Any]:
        """Get rate limiting statistics for a client"""
        stats = {}
        
        for endpoint_type in ["auth", "upload", "search", "read", "general"]:
            full_identifier = f"{identifier}:{endpoint_type}"
            _, metadata = self.limiter.is_allowed(full_identifier, 1, 60)
            stats[endpoint_type] = metadata
        
        return stats


# Global rate limiter instance
try:
    # Try to initialize Redis if available
    import redis
    redis_client = None
    try:
        settings = get_security_settings()
        if hasattr(settings, 'REDIS_URL') and settings.REDIS_URL:
            redis_client = redis.from_url(settings.REDIS_URL)
            # Test connection
            redis_client.ping()
            logger.info("Redis connection established for rate limiting")
    except Exception as e:
        logger.info(f"Redis not available for rate limiting: {e}")
        redis_client = None
    
    rate_limiter = EnterpriseRateLimiter(redis_client)
    
except ImportError:
    logger.info("Redis package not available, using memory-based rate limiting")
    rate_limiter = EnterpriseRateLimiter(None)