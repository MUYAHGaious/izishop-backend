"""
Performance Testing and Load Testing Utilities
Automated performance testing, load generation, and benchmarking tools
"""
import asyncio
import aiohttp
import time
import statistics
import json
import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import random

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Result of a performance test"""
    endpoint: str
    method: str
    status_code: int
    response_time: float
    error: Optional[str] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


@dataclass
class LoadTestConfig:
    """Configuration for load testing"""
    base_url: str
    endpoints: List[Dict[str, Any]]
    concurrent_users: int = 10
    duration_seconds: int = 60
    ramp_up_seconds: int = 10
    think_time_range: tuple = (1, 3)  # Random delay between requests
    headers: Dict[str, str] = None
    
    def __post_init__(self):
        if self.headers is None:
            self.headers = {}


class PerformanceTester:
    """Advanced performance testing framework"""
    
    def __init__(self):
        self.results: List[TestResult] = []
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=100)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def single_request_test(
        self,
        url: str,
        method: str = "GET",
        data: Dict = None,
        headers: Dict = None,
        expected_status: int = 200
    ) -> TestResult:
        """Test a single request"""
        start_time = time.time()
        
        try:
            async with self.session.request(
                method=method,
                url=url,
                json=data,
                headers=headers or {}
            ) as response:
                await response.read()  # Read full response
                
                response_time = time.time() - start_time
                
                result = TestResult(
                    endpoint=url,
                    method=method,
                    status_code=response.status,
                    response_time=response_time,
                    error=None if response.status == expected_status else f"Unexpected status: {response.status}"
                )
                
        except Exception as e:
            response_time = time.time() - start_time
            result = TestResult(
                endpoint=url,
                method=method,
                status_code=0,
                response_time=response_time,
                error=str(e)
            )
        
        self.results.append(result)
        return result
    
    async def load_test(self, config: LoadTestConfig) -> Dict[str, Any]:
        """Run a comprehensive load test"""
        logger.info(f"Starting load test: {config.concurrent_users} users for {config.duration_seconds}s")
        
        # Track test progress
        test_start = time.time()
        user_tasks = []
        
        # Create user simulation tasks
        for user_id in range(config.concurrent_users):
            # Stagger user start times (ramp-up)
            start_delay = (config.ramp_up_seconds / config.concurrent_users) * user_id
            
            task = asyncio.create_task(
                self._simulate_user(config, user_id, start_delay)
            )
            user_tasks.append(task)
        
        # Wait for all users to complete
        await asyncio.gather(*user_tasks)
        
        total_duration = time.time() - test_start
        
        # Analyze results
        return self._analyze_results(config, total_duration)
    
    async def _simulate_user(
        self,
        config: LoadTestConfig,
        user_id: int,
        start_delay: float
    ):
        """Simulate a single user's behavior"""
        await asyncio.sleep(start_delay)
        
        end_time = time.time() + config.duration_seconds
        
        while time.time() < end_time:
            try:
                # Choose random endpoint
                endpoint_config = random.choice(config.endpoints)
                
                url = f"{config.base_url}{endpoint_config['path']}"
                method = endpoint_config.get('method', 'GET')
                data = endpoint_config.get('data')
                expected_status = endpoint_config.get('expected_status', 200)
                
                # Make request
                await self.single_request_test(
                    url=url,
                    method=method,
                    data=data,
                    headers=config.headers,
                    expected_status=expected_status
                )
                
                # Think time (simulate user behavior)
                think_time = random.uniform(*config.think_time_range)
                await asyncio.sleep(think_time)
                
            except Exception as e:
                logger.error(f"User {user_id} error: {e}")
                await asyncio.sleep(1)  # Brief pause before retry
    
    def _analyze_results(self, config: LoadTestConfig, total_duration: float) -> Dict[str, Any]:
        """Analyze load test results"""
        if not self.results:
            return {"error": "No results to analyze"}
        
        # Filter successful requests
        successful_results = [r for r in self.results if r.error is None]
        error_results = [r for r in self.results if r.error is not None]
        
        # Calculate response time statistics
        response_times = [r.response_time for r in successful_results]
        
        if response_times:
            stats = {
                "min": min(response_times),
                "max": max(response_times),
                "mean": statistics.mean(response_times),
                "median": statistics.median(response_times),
                "p95": self._percentile(response_times, 95),
                "p99": self._percentile(response_times, 99)
            }
        else:
            stats = {"error": "No successful requests"}
        
        # Count status codes
        status_codes = {}
        for result in self.results:
            status_codes[result.status_code] = status_codes.get(result.status_code, 0) + 1
        
        # Calculate throughput
        total_requests = len(self.results)
        requests_per_second = total_requests / total_duration if total_duration > 0 else 0
        
        # Error analysis
        error_types = {}
        for error_result in error_results:
            error_key = error_result.error or "Unknown error"
            error_types[error_key] = error_types.get(error_key, 0) + 1
        
        return {
            "test_config": {
                "concurrent_users": config.concurrent_users,
                "duration_seconds": config.duration_seconds,
                "total_endpoints": len(config.endpoints)
            },
            "summary": {
                "total_requests": total_requests,
                "successful_requests": len(successful_results),
                "failed_requests": len(error_results),
                "success_rate": len(successful_results) / total_requests * 100 if total_requests > 0 else 0,
                "requests_per_second": requests_per_second,
                "total_duration": total_duration
            },
            "response_times": stats,
            "status_codes": status_codes,
            "errors": error_types,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile"""
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
    
    def get_detailed_results(self) -> List[Dict]:
        """Get detailed test results"""
        return [asdict(result) for result in self.results]
    
    def clear_results(self):
        """Clear stored results"""
        self.results.clear()


class EndpointBenchmark:
    """Benchmark specific endpoints with various scenarios"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.benchmarks = {}
    
    async def benchmark_endpoint(
        self,
        endpoint: str,
        method: str = "GET",
        payload: Dict = None,
        headers: Dict = None,
        concurrent_levels: List[int] = [1, 5, 10, 20],
        requests_per_level: int = 100
    ) -> Dict[str, Any]:
        """Benchmark an endpoint at different concurrency levels"""
        
        benchmark_results = {}
        
        for concurrency in concurrent_levels:
            logger.info(f"Benchmarking {endpoint} with {concurrency} concurrent users")
            
            async with PerformanceTester() as tester:
                # Run multiple requests concurrently
                tasks = []
                for _ in range(requests_per_level):
                    task = asyncio.create_task(
                        tester.single_request_test(
                            url=f"{self.base_url}{endpoint}",
                            method=method,
                            data=payload,
                            headers=headers
                        )
                    )
                    tasks.append(task)
                    
                    # Control concurrency
                    if len(tasks) >= concurrency:
                        await asyncio.gather(*tasks)
                        tasks.clear()
                
                # Wait for remaining tasks
                if tasks:
                    await asyncio.gather(*tasks)
                
                # Analyze this concurrency level
                response_times = [r.response_time for r in tester.results if r.error is None]
                error_count = len([r for r in tester.results if r.error is not None])
                
                if response_times:
                    benchmark_results[f"concurrency_{concurrency}"] = {
                        "avg_response_time": statistics.mean(response_times),
                        "min_response_time": min(response_times),
                        "max_response_time": max(response_times),
                        "p95_response_time": tester._percentile(response_times, 95),
                        "success_rate": (len(response_times) / requests_per_level) * 100,
                        "error_count": error_count,
                        "throughput": len(response_times) / sum(response_times) if sum(response_times) > 0 else 0
                    }
                
                tester.clear_results()
        
        self.benchmarks[endpoint] = benchmark_results
        return benchmark_results


class StressTest:
    """Stress testing to find system breaking points"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
    
    async def find_breaking_point(
        self,
        endpoint: str,
        method: str = "GET",
        payload: Dict = None,
        headers: Dict = None,
        start_users: int = 1,
        max_users: int = 100,
        step_size: int = 5,
        step_duration: int = 30,
        failure_threshold: float = 5.0  # 5% error rate
    ) -> Dict[str, Any]:
        """Find the breaking point of an endpoint"""
        
        results = []
        current_users = start_users
        
        while current_users <= max_users:
            logger.info(f"Stress testing with {current_users} concurrent users")
            
            # Create load test config for this step
            config = LoadTestConfig(
                base_url=self.base_url,
                endpoints=[{
                    "path": endpoint,
                    "method": method,
                    "data": payload
                }],
                concurrent_users=current_users,
                duration_seconds=step_duration,
                ramp_up_seconds=5,
                headers=headers or {}
            )
            
            # Run load test
            async with PerformanceTester() as tester:
                step_result = await tester.load_test(config)
                
                step_summary = {
                    "concurrent_users": current_users,
                    "success_rate": step_result["summary"]["success_rate"],
                    "avg_response_time": step_result["response_times"].get("mean", 0),
                    "requests_per_second": step_result["summary"]["requests_per_second"],
                    "error_count": step_result["summary"]["failed_requests"]
                }
                
                results.append(step_summary)
                
                # Check if we've hit the breaking point
                if step_result["summary"]["success_rate"] < (100 - failure_threshold):
                    logger.warning(f"Breaking point reached at {current_users} users")
                    break
                
                # Check if average response time is too high (>5 seconds)
                if step_result["response_times"].get("mean", 0) > 5.0:
                    logger.warning(f"Response time breaking point reached at {current_users} users")
                    break
            
            current_users += step_size
        
        return {
            "endpoint": endpoint,
            "breaking_point_users": current_users - step_size if results else None,
            "test_results": results,
            "recommendations": self._generate_recommendations(results),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def _generate_recommendations(self, results: List[Dict]) -> List[str]:
        """Generate performance recommendations based on test results"""
        recommendations = []
        
        if not results:
            return ["No test data available for recommendations"]
        
        # Analyze trends
        last_result = results[-1]
        
        if last_result["success_rate"] < 95:
            recommendations.append("High error rate detected - investigate error handling and capacity")
        
        if last_result["avg_response_time"] > 2.0:
            recommendations.append("High response times - consider caching, database optimization, or scaling")
        
        if last_result["requests_per_second"] < 10:
            recommendations.append("Low throughput - investigate bottlenecks in application or infrastructure")
        
        # Compare first vs last
        if len(results) > 1:
            first_result = results[0]
            response_time_increase = (last_result["avg_response_time"] / first_result["avg_response_time"]) - 1
            
            if response_time_increase > 2.0:  # 200% increase
                recommendations.append("Response time degrades significantly under load - implement load balancing")
        
        if not recommendations:
            recommendations.append("System performance appears stable under tested load levels")
        
        return recommendations


# Pre-configured test scenarios
class TestScenarios:
    """Common performance test scenarios for e-commerce platform"""
    
    @staticmethod
    def get_user_service_tests(base_url: str, auth_token: str = None) -> LoadTestConfig:
        """Test scenarios for user service"""
        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
        
        return LoadTestConfig(
            base_url=base_url,
            endpoints=[
                {"path": "/health", "method": "GET"},
                {"path": "/auth/verify", "method": "GET", "expected_status": 200 if auth_token else 401},
                {"path": "/users/search", "method": "GET", "expected_status": 200 if auth_token else 403}
            ],
            concurrent_users=10,
            duration_seconds=60,
            headers=headers
        )
    
    @staticmethod
    def get_shop_service_tests(base_url: str, auth_token: str = None) -> LoadTestConfig:
        """Test scenarios for shop service"""
        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
        
        return LoadTestConfig(
            base_url=base_url,
            endpoints=[
                {"path": "/health", "method": "GET"},
                {"path": "/shops", "method": "GET"},
                {"path": "/shops/featured", "method": "GET"},
                {"path": "/shops/1", "method": "GET"},
                {"path": "/cache/stats", "method": "GET", "expected_status": 200 if auth_token else 403}
            ],
            concurrent_users=15,
            duration_seconds=90,
            headers=headers
        )
    
    @staticmethod
    def get_notification_service_tests(base_url: str) -> LoadTestConfig:
        """Test scenarios for notification service"""
        return LoadTestConfig(
            base_url=base_url,
            endpoints=[
                {"path": "/health", "method": "GET"},
                {"path": "/stats", "method": "GET"}
            ],
            concurrent_users=5,
            duration_seconds=30
        )