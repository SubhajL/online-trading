import os
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import asyncpg
import redis.asyncio as redis


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    message: str = ""
    latency_ms: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)
    last_check: datetime = field(default_factory=datetime.now)


@dataclass
class HealthConfig:
    check_interval: int  # seconds
    timeout: int  # seconds
    failure_threshold: int
    recovery_threshold: int
    include_details: bool
    
    @classmethod
    def from_env(cls) -> "HealthConfig":
        return cls(
            check_interval=int(os.getenv("HEALTH_CHECK_INTERVAL", "30")),
            timeout=int(os.getenv("HEALTH_CHECK_TIMEOUT", "5")),
            failure_threshold=int(os.getenv("HEALTH_FAILURE_THRESHOLD", "3")),
            recovery_threshold=int(os.getenv("HEALTH_RECOVERY_THRESHOLD", "2")),
            include_details=os.getenv("HEALTH_INCLUDE_DETAILS", "true").lower() == "true",
        )


class HealthChecker:
    """Manages health checks for all system components"""
    
    def __init__(self, config: HealthConfig):
        self.config = config
        self.components: Dict[str, ComponentHealth] = {}
        self.failure_counts: Dict[str, int] = {}
        self.recovery_counts: Dict[str, int] = {}
        self._check_tasks: Dict[str, asyncio.Task] = {}
        self._custom_checks: Dict[str, Callable] = {}
    
    def register_component(self, name: str, check_func: Optional[Callable] = None) -> None:
        """Register a component for health monitoring"""
        self.components[name] = ComponentHealth(
            name=name,
            status=HealthStatus.HEALTHY,
            message="Not yet checked"
        )
        self.failure_counts[name] = 0
        self.recovery_counts[name] = 0
        
        if check_func:
            self._custom_checks[name] = check_func
    
    async def check_database(self, connection_string: str) -> ComponentHealth:
        """Check database connectivity and performance"""
        start_time = time.time()
        
        try:
            conn = await asyncpg.connect(connection_string)
            try:
                # Simple query to check connectivity
                result = await conn.fetchval("SELECT 1")
                if result != 1:
                    raise ValueError("Unexpected database response")
                
                # Check database size if enabled
                details = {}
                if self.config.include_details:
                    db_size = await conn.fetchval(
                        "SELECT pg_database_size(current_database())"
                    )
                    details["database_size_mb"] = db_size / (1024 * 1024)
                    
                    # Check active connections
                    active_conns = await conn.fetchval(
                        "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"
                    )
                    details["active_connections"] = active_conns
                
                latency_ms = (time.time() - start_time) * 1000
                
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    message="Database is responsive",
                    latency_ms=latency_ms,
                    details=details
                )
            finally:
                await conn.close()
                
        except asyncio.TimeoutError:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message="Database connection timeout",
                latency_ms=(time.time() - start_time) * 1000
            )
        except Exception as e:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database error: {str(e)}",
                latency_ms=(time.time() - start_time) * 1000
            )
    
    async def check_redis(self, redis_url: str) -> ComponentHealth:
        """Check Redis connectivity and performance"""
        start_time = time.time()

        try:
            client = redis.from_url(redis_url)
            try:
                # Ping to check connectivity
                await client.ping()

                # Check memory usage if enabled
                details = {}
                if self.config.include_details:
                    info = await client.info("memory")
                    if info:
                        details["memory_used_mb"] = info.get("used_memory", 0) / (1024 * 1024)
                        details["memory_peak_mb"] = info.get("used_memory_peak", 0) / (1024 * 1024)

                latency_ms = (time.time() - start_time) * 1000

                return ComponentHealth(
                    name="redis",
                    status=HealthStatus.HEALTHY,
                    message="Redis is responsive",
                    latency_ms=latency_ms,
                    details=details
                )
            finally:
                await client.aclose()
                
        except asyncio.TimeoutError:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message="Redis connection timeout",
                latency_ms=(time.time() - start_time) * 1000
            )
        except Exception as e:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=f"Redis error: {str(e)}",
                latency_ms=(time.time() - start_time) * 1000
            )
    
    async def check_event_bus(self, event_bus) -> ComponentHealth:
        """Check event bus health"""
        start_time = time.time()
        
        try:
            # Check if event bus is running
            if not hasattr(event_bus, 'is_running') or not event_bus.is_running():
                return ComponentHealth(
                    name="event_bus",
                    status=HealthStatus.UNHEALTHY,
                    message="Event bus is not running"
                )
            
            details = {}
            if self.config.include_details:
                # Get queue sizes
                if hasattr(event_bus, 'get_queue_sizes'):
                    details["queue_sizes"] = event_bus.get_queue_sizes()
                
                # Get subscriber counts
                if hasattr(event_bus, 'get_subscriber_counts'):
                    details["subscriber_counts"] = event_bus.get_subscriber_counts()
            
            latency_ms = (time.time() - start_time) * 1000
            
            return ComponentHealth(
                name="event_bus",
                status=HealthStatus.HEALTHY,
                message="Event bus is operational",
                latency_ms=latency_ms,
                details=details
            )
            
        except Exception as e:
            return ComponentHealth(
                name="event_bus",
                status=HealthStatus.UNHEALTHY,
                message=f"Event bus error: {str(e)}",
                latency_ms=(time.time() - start_time) * 1000
            )
    
    async def _run_check(self, name: str) -> None:
        """Run a single health check"""
        try:
            # Use custom check if available
            if name in self._custom_checks:
                result = await self._custom_checks[name]()
            else:
                # Default to unhealthy if no check function
                result = ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message="No check function defined"
                )
            
            # Update failure/recovery counts
            if result.status == HealthStatus.UNHEALTHY:
                self.failure_counts[name] += 1
                self.recovery_counts[name] = 0
                
                # Check failure threshold
                if self.failure_counts[name] >= self.config.failure_threshold:
                    result.status = HealthStatus.UNHEALTHY
                    result.message += f" (failed {self.failure_counts[name]} times)"
                else:
                    result.status = HealthStatus.DEGRADED
            else:
                self.recovery_counts[name] += 1

                # Check recovery threshold
                if self.failure_counts[name] > 0:
                    # Still recovering from previous failures
                    if self.recovery_counts[name] >= self.config.recovery_threshold:
                        self.failure_counts[name] = 0
                        result.status = HealthStatus.HEALTHY
                    else:
                        result.status = HealthStatus.DEGRADED
            
            self.components[name] = result
            
        except Exception as e:
            self.components[name] = ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}"
            )
    
    async def start_monitoring(self) -> None:
        """Start continuous health monitoring"""
        for name in self.components:
            if name not in self._check_tasks or self._check_tasks[name].done():
                self._check_tasks[name] = asyncio.create_task(
                    self._monitor_component(name)
                )
    
    async def stop_monitoring(self) -> None:
        """Stop all health monitoring tasks"""
        for task in self._check_tasks.values():
            if not task.done():
                task.cancel()
        
        await asyncio.gather(*self._check_tasks.values(), return_exceptions=True)
        self._check_tasks.clear()
    
    async def _monitor_component(self, name: str) -> None:
        """Continuously monitor a component"""
        while True:
            try:
                await asyncio.wait_for(
                    self._run_check(name),
                    timeout=self.config.timeout
                )
            except asyncio.TimeoutError:
                self.components[name] = ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message="Health check timeout"
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.components[name] = ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Monitoring error: {str(e)}"
                )
            
            await asyncio.sleep(self.config.check_interval)
    
    def get_overall_health(self) -> Dict[str, Any]:
        """Get overall system health status"""
        statuses = [comp.status for comp in self.components.values()]
        
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            overall_status = HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY
        
        return {
            "status": overall_status.value,
            "timestamp": datetime.now().isoformat(),
            "components": {
                name: {
                    "status": comp.status.value,
                    "message": comp.message,
                    "latency_ms": comp.latency_ms,
                    "details": comp.details if self.config.include_details else {},
                    "last_check": comp.last_check.isoformat()
                }
                for name, comp in self.components.items()
            }
        }
    
    async def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks immediately"""
        tasks = [self._run_check(name) for name in self.components]
        await asyncio.gather(*tasks, return_exceptions=True)
        return self.get_overall_health()


class ReadinessChecker:
    """Checks if the application is ready to serve requests"""
    
    def __init__(self):
        self.checks: Dict[str, Callable] = {}
        self.required_components: List[str] = []
    
    def register_check(self, name: str, check_func: Callable, required: bool = True) -> None:
        """Register a readiness check"""
        self.checks[name] = check_func
        if required:
            self.required_components.append(name)
    
    async def is_ready(self) -> Dict[str, Any]:
        """Check if the application is ready"""
        results = {}
        
        for name, check_func in self.checks.items():
            try:
                result = await check_func()
                results[name] = {
                    "ready": result,
                    "required": name in self.required_components
                }
            except Exception as e:
                results[name] = {
                    "ready": False,
                    "required": name in self.required_components,
                    "error": str(e)
                }
        
        # Check if all required components are ready
        all_required_ready = all(
            results.get(name, {}).get("ready", False)
            for name in self.required_components
        )
        
        return {
            "ready": all_required_ready,
            "timestamp": datetime.now().isoformat(),
            "checks": results
        }
