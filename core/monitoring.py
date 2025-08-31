"""
Enterprise Monitoring and Observability System
Comprehensive metrics collection, health monitoring, and performance tracking
"""
import time
import asyncio
import logging
import psutil
from typing import Dict, List, Any, Optional
from functools import wraps
from datetime import datetime, timedelta
from collections import defaultdict, deque
import json

from core.security_config import get_security_settings
from core.cache_manager import cache_manager

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collect and aggregate system and application metrics"""
    
    def __init__(self):
        self.settings = get_security_settings()
        self.metrics = defaultdict(lambda: defaultdict(list))
        self.counters = defaultdict(int)
        self.gauges = defaultdict(float)
        self.histograms = defaultdict(lambda: deque(maxlen=1000))
        self.last_cleanup = time.time()
    
    def increment_counter(self, name: str, value: int = 1, labels: Dict[str, str] = None):
        """Increment a counter metric"""
        key = self._create_metric_key(name, labels)
        self.counters[key] += value
        logger.debug(f"Counter {key} incremented by {value}")
    
    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge metric value"""
        key = self._create_metric_key(name, labels)
        self.gauges[key] = value
        logger.debug(f"Gauge {key} set to {value}")
    
    def record_histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """Record a histogram value"""
        key = self._create_metric_key(name, labels)
        self.histograms[key].append({
            "value": value,
            "timestamp": time.time()
        })
        logger.debug(f"Histogram {key} recorded value {value}")
    
    def _create_metric_key(self, name: str, labels: Dict[str, str] = None) -> str:
        """Create a unique key for metric with labels"""
        if not labels:
            return name
        
        label_str = ",".join([f"{k}={v}" for k, v in sorted(labels.items())])
        return f"{name}{{{label_str}}}"
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Get current system metrics"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Network I/O
            net_io = psutil.net_io_counters()
            
            return {
                "cpu": {
                    "percent": cpu_percent,
                    "count": psutil.cpu_count()
                },
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "percent": memory.percent,
                    "used": memory.used
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.used / disk.total * 100
                },
                "network": {
                    "bytes_sent": net_io.bytes_sent,
                    "bytes_recv": net_io.bytes_recv,
                    "packets_sent": net_io.packets_sent,
                    "packets_recv": net_io.packets_recv
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            return {}
    
    def get_application_metrics(self) -> Dict[str, Any]:
        """Get application-specific metrics"""
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "histograms": {
                name: {
                    "count": len(values),
                    "latest": values[-1] if values else None,
                    "avg": sum(v["value"] for v in values) / len(values) if values else 0
                }
                for name, values in self.histograms.items()
            },
            "cache_stats": cache_manager.get_stats(),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def cleanup_old_metrics(self):
        """Clean up old histogram data"""
        current_time = time.time()
        cutoff_time = current_time - 3600  # Keep 1 hour of data
        
        for name, values in self.histograms.items():
            # Remove old values
            while values and values[0]["timestamp"] < cutoff_time:
                values.popleft()
        
        self.last_cleanup = current_time
        logger.debug("Cleaned up old metrics")


class HealthChecker:
    """Monitor service health and dependencies"""
    
    def __init__(self):
        self.settings = get_security_settings()
        self.health_checks = {}
        self.last_check_results = {}
    
    def register_health_check(self, name: str, check_func, timeout: int = 5):
        """Register a health check function"""
        self.health_checks[name] = {
            "func": check_func,
            "timeout": timeout
        }
        logger.info(f"Registered health check: {name}")
    
    async def run_health_check(self, name: str) -> Dict[str, Any]:
        """Run a specific health check"""
        if name not in self.health_checks:
            return {
                "status": "error",
                "message": f"Health check '{name}' not found"
            }
        
        check_config = self.health_checks[name]
        start_time = time.time()
        
        try:
            # Run check with timeout
            result = await asyncio.wait_for(
                check_config["func"](),
                timeout=check_config["timeout"]
            )
            
            duration = time.time() - start_time
            
            health_result = {
                "status": "healthy" if result.get("healthy", True) else "unhealthy",
                "duration_ms": round(duration * 1000, 2),
                "timestamp": datetime.utcnow().isoformat(),
                "details": result
            }
            
        except asyncio.TimeoutError:
            health_result = {
                "status": "timeout",
                "duration_ms": check_config["timeout"] * 1000,
                "timestamp": datetime.utcnow().isoformat(),
                "message": f"Health check timed out after {check_config['timeout']}s"
            }
            
        except Exception as e:
            health_result = {
                "status": "error",
                "duration_ms": round((time.time() - start_time) * 1000, 2),
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }
        
        self.last_check_results[name] = health_result
        return health_result
    
    async def run_all_health_checks(self) -> Dict[str, Any]:
        """Run all registered health checks"""
        results = {}
        overall_status = "healthy"
        
        # Run all checks concurrently
        tasks = [
            (name, self.run_health_check(name))
            for name in self.health_checks.keys()
        ]
        
        for name, task in tasks:
            result = await task
            results[name] = result
            
            if result["status"] not in ["healthy"]:
                overall_status = "unhealthy"
        
        return {
            "overall_status": overall_status,
            "checks": results,
            "timestamp": datetime.utcnow().isoformat()
        }


class PerformanceMonitor:
    """Monitor application performance and detect anomalies"""
    
    def __init__(self):
        self.request_times = deque(maxlen=1000)
        self.error_counts = defaultdict(int)
        self.slow_queries = deque(maxlen=100)
        self.response_time_buckets = defaultdict(int)
    
    def record_request(self, duration: float, status_code: int, endpoint: str):
        """Record request performance metrics"""
        self.request_times.append({
            "duration": duration,
            "status_code": status_code,
            "endpoint": endpoint,
            "timestamp": time.time()
        })
        
        # Categorize response times
        if duration < 0.1:
            bucket = "fast"
        elif duration < 0.5:
            bucket = "medium"
        elif duration < 2.0:
            bucket = "slow"
        else:
            bucket = "very_slow"
        
        self.response_time_buckets[bucket] += 1
        
        # Count errors
        if status_code >= 400:
            self.error_counts[f"{status_code}"] += 1
        
        # Record slow requests
        if duration > 2.0:
            self.slow_queries.append({
                "endpoint": endpoint,
                "duration": duration,
                "status_code": status_code,
                "timestamp": time.time()
            })
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        if not self.request_times:
            return {"no_data": True}
        
        # Calculate stats from recent requests
        recent_times = [r["duration"] for r in self.request_times]
        
        return {
            "request_stats": {
                "total_requests": len(self.request_times),
                "avg_response_time": sum(recent_times) / len(recent_times),
                "min_response_time": min(recent_times),
                "max_response_time": max(recent_times),
                "p50": self._percentile(recent_times, 50),
                "p95": self._percentile(recent_times, 95),
                "p99": self._percentile(recent_times, 99)
            },
            "response_time_distribution": dict(self.response_time_buckets),
            "error_counts": dict(self.error_counts),
            "slow_queries_count": len(self.slow_queries),
            "recent_slow_queries": list(self.slow_queries)[-10:],
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile from data"""
        if not data:
            return 0.0
        
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * percentile / 100
        f = int(k)
        c = k - f
        
        if f + 1 < len(sorted_data):
            return sorted_data[f] + c * (sorted_data[f + 1] - sorted_data[f])
        else:
            return sorted_data[f]


# Global instances
metrics_collector = MetricsCollector()
health_checker = HealthChecker()
performance_monitor = PerformanceMonitor()


# Decorators for monitoring
def monitor_performance(func):
    """Decorator to monitor function performance"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        func_name = f"{func.__module__}.{func.__name__}"
        
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            
            # Record metrics
            metrics_collector.record_histogram("function_duration", duration, {"function": func_name})
            metrics_collector.increment_counter("function_calls", 1, {"function": func_name, "status": "success"})
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            
            # Record error metrics
            metrics_collector.record_histogram("function_duration", duration, {"function": func_name})
            metrics_collector.increment_counter("function_calls", 1, {"function": func_name, "status": "error"})
            metrics_collector.increment_counter("function_errors", 1, {"function": func_name, "error": type(e).__name__})
            
            raise
    
    return wrapper


def track_endpoint_performance(func):
    """Decorator to track API endpoint performance"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        endpoint = func.__name__
        status_code = 200
        
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            
            # Extract status code from response if available
            if hasattr(result, 'status_code'):
                status_code = result.status_code
            
            performance_monitor.record_request(duration, status_code, endpoint)
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            status_code = 500  # Server error
            
            performance_monitor.record_request(duration, status_code, endpoint)
            raise
    
    return wrapper


# Health check functions
async def check_database_health():
    """Check database connectivity"""
    try:
        from backend.database.connection import engine
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return {"healthy": True, "message": "Database connection OK"}
    except Exception as e:
        return {"healthy": False, "error": str(e)}


async def check_redis_health():
    """Check Redis connectivity"""
    try:
        await cache_manager.redis_client.ping()
        return {"healthy": True, "message": "Redis connection OK"}
    except Exception as e:
        return {"healthy": False, "error": str(e)}


async def check_system_resources():
    """Check system resource usage"""
    try:
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        
        issues = []
        if cpu_percent > 80:
            issues.append(f"High CPU usage: {cpu_percent}%")
        if memory.percent > 85:
            issues.append(f"High memory usage: {memory.percent}%")
        
        return {
            "healthy": len(issues) == 0,
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "issues": issues
        }
    except Exception as e:
        return {"healthy": False, "error": str(e)}


# Register default health checks
health_checker.register_health_check("database", check_database_health)
health_checker.register_health_check("redis", check_redis_health)
health_checker.register_health_check("system_resources", check_system_resources)


# Monitoring middleware
class MonitoringMiddleware:
    """Middleware for automatic monitoring integration"""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        start_time = time.time()
        status_code = 200
        
        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)
        
        try:
            await self.app(scope, receive, send_wrapper)
            
        finally:
            duration = time.time() - start_time
            endpoint = scope.get("path", "unknown")
            
            # Record request metrics
            performance_monitor.record_request(duration, status_code, endpoint)
            metrics_collector.increment_counter("http_requests_total", 1, {
                "method": scope.get("method", "unknown"),
                "endpoint": endpoint,
                "status": str(status_code)
            })
            metrics_collector.record_histogram("http_request_duration", duration, {
                "method": scope.get("method", "unknown"),
                "endpoint": endpoint
            })


# Background monitoring task
async def monitoring_background_task():
    """Background task for continuous monitoring"""
    while True:
        try:
            # Collect system metrics
            system_metrics = metrics_collector.get_system_metrics()
            if system_metrics:
                # Store in cache for API access
                await cache_manager.set("system_metrics", system_metrics, ttl=60)
            
            # Run health checks
            health_results = await health_checker.run_all_health_checks()
            await cache_manager.set("health_status", health_results, ttl=60)
            
            # Clean up old metrics
            if time.time() - metrics_collector.last_cleanup > 3600:
                metrics_collector.cleanup_old_metrics()
            
            # Log warnings for unhealthy services
            if health_results["overall_status"] != "healthy":
                logger.warning(f"Health check failed: {health_results}")
            
            await asyncio.sleep(60)  # Run every minute
            
        except Exception as e:
            logger.error(f"Monitoring background task error: {e}")
            await asyncio.sleep(60)