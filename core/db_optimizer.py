"""
Database Performance Optimization
Query optimization, indexing, connection pooling, and performance monitoring
"""
import time
import logging
from typing import Dict, List, Any, Optional, Callable
from functools import wraps
from sqlalchemy import create_engine, text, event, Index
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.engine import Engine
from contextlib import asynccontextmanager
import asyncio

from core.security_config import get_security_settings
from core.cache_manager import cache_manager, query_cache

logger = logging.getLogger(__name__)


class DatabaseOptimizer:
    """Database performance optimization and monitoring"""
    
    def __init__(self):
        self.settings = get_security_settings()
        self.query_stats = {}
        self.slow_queries = []
        self.connection_stats = {
            "total_connections": 0,
            "active_connections": 0,
            "query_count": 0,
            "average_query_time": 0.0
        }
    
    def create_optimized_engine(self, database_url: str) -> Engine:
        """Create optimized database engine with connection pooling"""
        
        # Connection pool configuration
        pool_config = {
            "poolclass": QueuePool,
            "pool_size": self.settings.DATABASE_POOL_SIZE,
            "max_overflow": self.settings.DATABASE_MAX_OVERFLOW,
            "pool_pre_ping": True,  # Validate connections
            "pool_recycle": 3600,   # Recycle connections every hour
            "pool_timeout": 30,     # Connection timeout
        }
        
        # Create engine with optimizations
        engine = create_engine(
            database_url,
            **pool_config,
            echo=False,  # Set to True for SQL debugging
            future=True,
            connect_args={
                "application_name": "izishop_microservice",
                "connect_timeout": 10,
            } if "postgresql" in database_url else {}
        )
        
        # Add event listeners for monitoring
        self._add_event_listeners(engine)
        
        return engine
    
    def _add_event_listeners(self, engine: Engine):
        """Add event listeners for performance monitoring"""
        
        @event.listens_for(engine, "connect")
        def receive_connect(dbapi_connection, connection_record):
            self.connection_stats["total_connections"] += 1
            logger.debug("Database connection established")
        
        @event.listens_for(engine, "checkout")
        def receive_checkout(dbapi_connection, connection_record, connection_proxy):
            self.connection_stats["active_connections"] += 1
        
        @event.listens_for(engine, "checkin")
        def receive_checkin(dbapi_connection, connection_record):
            self.connection_stats["active_connections"] -= 1
        
        @event.listens_for(engine, "before_cursor_execute")
        def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            context._query_start_time = time.time()
        
        @event.listens_for(engine, "after_cursor_execute")
        def receive_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            total_time = time.time() - context._query_start_time
            
            # Update query stats
            self.connection_stats["query_count"] += 1
            self._update_query_stats(statement, total_time)
            
            # Log slow queries
            if total_time > 1.0:  # Queries slower than 1 second
                self.slow_queries.append({
                    "statement": statement[:200] + "..." if len(statement) > 200 else statement,
                    "time": total_time,
                    "timestamp": time.time()
                })
                logger.warning(f"Slow query detected: {total_time:.3f}s")
    
    def _update_query_stats(self, statement: str, execution_time: float):
        """Update query execution statistics"""
        # Extract table name from query
        statement_lower = statement.lower().strip()
        table_name = "unknown"
        
        if statement_lower.startswith("select"):
            # Simple table extraction (can be improved)
            words = statement_lower.split()
            if "from" in words:
                from_index = words.index("from")
                if from_index + 1 < len(words):
                    table_name = words[from_index + 1].split()[0]
        
        # Update stats
        if table_name not in self.query_stats:
            self.query_stats[table_name] = {
                "count": 0,
                "total_time": 0.0,
                "avg_time": 0.0,
                "min_time": float('inf'),
                "max_time": 0.0
            }
        
        stats = self.query_stats[table_name]
        stats["count"] += 1
        stats["total_time"] += execution_time
        stats["avg_time"] = stats["total_time"] / stats["count"]
        stats["min_time"] = min(stats["min_time"], execution_time)
        stats["max_time"] = max(stats["max_time"], execution_time)
        
        # Update global average
        total_queries = sum(s["count"] for s in self.query_stats.values())
        total_time = sum(s["total_time"] for s in self.query_stats.values())
        self.connection_stats["average_query_time"] = total_time / total_queries if total_queries > 0 else 0.0
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get database performance statistics"""
        return {
            "connection_stats": self.connection_stats.copy(),
            "query_stats": self.query_stats.copy(),
            "slow_queries_count": len(self.slow_queries),
            "recent_slow_queries": self.slow_queries[-10:] if self.slow_queries else []
        }
    
    def suggest_indexes(self, table_stats: Dict[str, Any]) -> List[Dict[str, str]]:
        """Suggest database indexes based on query patterns"""
        suggestions = []
        
        for table_name, stats in table_stats.items():
            if stats["count"] > 100 and stats["avg_time"] > 0.1:  # Frequent, slow queries
                suggestions.append({
                    "table": table_name,
                    "suggestion": f"Consider adding indexes to frequently queried columns in {table_name}",
                    "reason": f"Table has {stats['count']} queries with avg time {stats['avg_time']:.3f}s"
                })
        
        return suggestions


class OptimizedSession:
    """Enhanced database session with caching and optimization"""
    
    def __init__(self, session: Session, cache_enabled: bool = True):
        self.session = session
        self.cache_enabled = cache_enabled
    
    async def cached_query(
        self,
        query_key: str,
        query_func: Callable,
        ttl: int = 1800,
        *args,
        **kwargs
    ):
        """Execute query with caching"""
        if not self.cache_enabled:
            return query_func(*args, **kwargs)
        
        return await query_cache.get_or_set(
            query_key=query_key,
            query_func=query_func,
            ttl=ttl,
            *args,
            **kwargs
        )
    
    def bulk_insert_optimized(self, model_class, data_list: List[Dict], batch_size: int = 1000):
        """Optimized bulk insert with batching"""
        total_inserted = 0
        
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]
            
            # Use bulk_insert_mappings for better performance
            self.session.bulk_insert_mappings(model_class, batch)
            total_inserted += len(batch)
            
            # Commit periodically to avoid large transactions
            if total_inserted % (batch_size * 5) == 0:
                self.session.commit()
        
        self.session.commit()
        return total_inserted
    
    def bulk_update_optimized(self, model_class, data_list: List[Dict], batch_size: int = 1000):
        """Optimized bulk update with batching"""
        total_updated = 0
        
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]
            
            # Use bulk_update_mappings for better performance
            self.session.bulk_update_mappings(model_class, batch)
            total_updated += len(batch)
            
            # Commit periodically
            if total_updated % (batch_size * 5) == 0:
                self.session.commit()
        
        self.session.commit()
        return total_updated


def optimized_query(
    cache_key: str = None,
    ttl: int = 1800,
    enable_cache: bool = True
):
    """
    Decorator for optimized database queries with caching
    
    Args:
        cache_key: Custom cache key
        ttl: Cache TTL in seconds
        enable_cache: Enable/disable caching
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not enable_cache:
                return await func(*args, **kwargs)
            
            # Generate cache key
            key = cache_key or f"{func.__module__}.{func.__name__}"
            
            # Try cache first
            result = await cache_manager.get(key)
            if result is not None:
                return result
            
            # Execute query
            start_time = time.time()
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            # Cache result
            await cache_manager.set(key, result, ttl=ttl)
            
            # Log performance
            if execution_time > 0.5:
                logger.warning(f"Slow query in {func.__name__}: {execution_time:.3f}s")
            
            return result
        return wrapper
    return decorator


class DatabaseIndexManager:
    """Manage database indexes for performance optimization"""
    
    def __init__(self, engine: Engine):
        self.engine = engine
    
    def create_performance_indexes(self):
        """Create essential indexes for performance"""
        
        indexes_to_create = [
            # User table indexes
            {
                "name": "idx_users_email",
                "table": "users",
                "columns": ["email"],
                "unique": True
            },
            {
                "name": "idx_users_role_active",
                "table": "users", 
                "columns": ["role", "is_active"]
            },
            
            # Shop table indexes
            {
                "name": "idx_shops_owner_active",
                "table": "shops",
                "columns": ["owner_id", "is_active"]
            },
            {
                "name": "idx_shops_name_search",
                "table": "shops",
                "columns": ["name"]
            },
            
            # Product table indexes
            {
                "name": "idx_products_shop_active",
                "table": "products",
                "columns": ["shop_id", "is_active"]
            },
            {
                "name": "idx_products_category_price",
                "table": "products",
                "columns": ["category_id", "price"]
            },
            {
                "name": "idx_products_search",
                "table": "products",
                "columns": ["name", "description"]
            },
            
            # Order table indexes
            {
                "name": "idx_orders_customer_status",
                "table": "orders",
                "columns": ["customer_id", "status"]
            },
            {
                "name": "idx_orders_shop_date",
                "table": "orders",
                "columns": ["shop_id", "created_at"]
            },
        ]
        
        created_count = 0
        
        with self.engine.connect() as connection:
            for index_config in indexes_to_create:
                try:
                    # Check if index exists
                    result = connection.execute(text(f"""
                        SELECT indexname FROM pg_indexes 
                        WHERE indexname = '{index_config['name']}'
                    """)).fetchone()
                    
                    if not result:
                        # Create index
                        columns_str = ", ".join(index_config["columns"])
                        unique_str = "UNIQUE" if index_config.get("unique") else ""
                        
                        sql = f"""
                            CREATE {unique_str} INDEX CONCURRENTLY IF NOT EXISTS {index_config['name']} 
                            ON {index_config['table']} ({columns_str})
                        """
                        
                        connection.execute(text(sql))
                        created_count += 1
                        logger.info(f"Created index: {index_config['name']}")
                
                except Exception as e:
                    logger.error(f"Failed to create index {index_config['name']}: {e}")
        
        return created_count
    
    def analyze_table_statistics(self) -> Dict[str, Any]:
        """Analyze table statistics for optimization"""
        stats = {}
        
        with self.engine.connect() as connection:
            # Get table sizes
            result = connection.execute(text("""
                SELECT 
                    schemaname,
                    tablename,
                    attname,
                    n_distinct,
                    correlation
                FROM pg_stats 
                WHERE schemaname = 'public'
                ORDER BY tablename, attname
            """))
            
            for row in result:
                table_name = row.tablename
                if table_name not in stats:
                    stats[table_name] = {"columns": []}
                
                stats[table_name]["columns"].append({
                    "name": row.attname,
                    "distinct_values": row.n_distinct,
                    "correlation": row.correlation
                })
        
        return stats


# Global database optimizer instance
db_optimizer = DatabaseOptimizer()


# Connection pooling utilities
class ConnectionPoolManager:
    """Manage database connection pools across services"""
    
    def __init__(self):
        self.pools = {}
    
    def get_pool(self, service_name: str, database_url: str):
        """Get or create connection pool for service"""
        if service_name not in self.pools:
            engine = db_optimizer.create_optimized_engine(database_url)
            self.pools[service_name] = sessionmaker(bind=engine)
            logger.info(f"Created connection pool for {service_name}")
        
        return self.pools[service_name]
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        return {
            "active_pools": len(self.pools),
            "pool_names": list(self.pools.keys()),
            "global_stats": db_optimizer.get_performance_stats()
        }


# Global connection pool manager
pool_manager = ConnectionPoolManager()


# Performance monitoring decorator
def monitor_query_performance(func):
    """Decorator to monitor query performance"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            # Log performance metrics
            logger.info(f"Query {func.__name__} executed in {execution_time:.3f}s")
            
            # Alert on slow queries
            if execution_time > 2.0:
                logger.warning(f"Very slow query detected: {func.__name__} took {execution_time:.3f}s")
            
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Query {func.__name__} failed after {execution_time:.3f}s: {e}")
            raise
    return wrapper