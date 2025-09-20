"""
FastAPI Main Application

Main FastAPI application for the trading engine with health endpoints,
metrics, and service management.
"""

import asyncio
import logging
import os
import signal
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

from .bus import EventBus, get_event_bus, set_event_bus
from .ingest.ingest_service import IngestService
from .features.feature_service import FeatureService
from .smc.smc_service import SMCService
from .decision.decision_engine import DecisionEngine
from .decision.risk_manager import RiskManager
from .adapters import TimescaleDBAdapter, RedisAdapter, RouterHTTPClient
from .models import RiskParameters, BinanceConfig, DatabaseConfig, RedisConfig, EngineConfig


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global service instances
services = {}


# Request/Response Models
class HealthResponse(BaseModel):
    status: str
    timestamp: str
    services: Dict[str, Any]
    uptime_seconds: float


class MetricsResponse(BaseModel):
    timestamp: str
    event_bus: Dict[str, Any]
    ingest: Dict[str, Any]
    features: Dict[str, Any]
    smc: Dict[str, Any]
    decision: Dict[str, Any]
    database: Dict[str, Any]
    redis: Dict[str, Any]


class ServiceControlRequest(BaseModel):
    action: str  # "start", "stop", "restart"
    service: Optional[str] = None  # None for all services


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    logger.info("Starting trading engine...")

    try:
        # Load configuration
        config = load_configuration()

        # Initialize services
        await initialize_services(config)

        # Start all services
        await start_services()

        logger.info("Trading engine started successfully")
        yield

    except Exception as e:
        logger.error(f"Failed to start trading engine: {e}")
        raise

    finally:
        logger.info("Shutting down trading engine...")
        await shutdown_services()
        logger.info("Trading engine shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Trading Engine",
    description="Comprehensive trading platform engine with real-time data processing",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track startup time
startup_time = datetime.utcnow()


def load_configuration() -> EngineConfig:
    """Load configuration from environment and config files"""
    try:
        # Default configuration - in production, load from environment/config files
        database_config = DatabaseConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "trading_engine"),
            username=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "password")
        )

        redis_config = RedisConfig(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD")
        )

        binance_config = BinanceConfig(
            api_key=os.getenv("BINANCE_API_KEY", ""),
            api_secret=os.getenv("BINANCE_API_SECRET", ""),
            testnet=os.getenv("BINANCE_TESTNET", "true").lower() == "true"
        )

        risk_parameters = RiskParameters(
            max_position_size=float(os.getenv("MAX_POSITION_SIZE", "0.1")),
            max_daily_loss=float(os.getenv("MAX_DAILY_LOSS", "0.05")),
            max_drawdown=float(os.getenv("MAX_DRAWDOWN", "0.15")),
            risk_per_trade=float(os.getenv("RISK_PER_TRADE", "0.02")),
            max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "5"))
        )

        config = EngineConfig(
            environment=os.getenv("ENVIRONMENT", "development"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            database=database_config,
            redis=redis_config,
            binance=binance_config,
            risk_parameters=risk_parameters
        )

        logger.info(f"Configuration loaded for environment: {config.environment}")
        return config

    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        raise


async def initialize_services(config: EngineConfig):
    """Initialize all services"""
    try:
        # Initialize event bus
        event_bus = EventBus(max_queue_size=10000)
        set_event_bus(event_bus)
        services['event_bus'] = event_bus

        # Initialize database adapter
        db_adapter = TimescaleDBAdapter(
            host=config.database.host,
            port=config.database.port,
            database=config.database.database,
            username=config.database.username,
            password=config.database.password
        )
        await db_adapter.initialize()
        services['database'] = db_adapter

        # Initialize Redis adapter
        redis_adapter = RedisAdapter(
            host=config.redis.host,
            port=config.redis.port,
            password=config.redis.password
        )
        await redis_adapter.initialize()
        services['redis'] = redis_adapter

        # Initialize router client
        router_client = RouterHTTPClient(
            base_url=os.getenv("ROUTER_URL", "http://localhost:8001"),
            api_key=os.getenv("ROUTER_API_KEY")
        )
        await router_client.initialize()
        services['router'] = router_client

        # Initialize risk manager
        risk_manager = RiskManager(config.risk_parameters)
        services['risk_manager'] = risk_manager

        # Initialize ingest service
        symbols = os.getenv("TRADING_SYMBOLS", "BTCUSDT,ETHUSDT").split(",")
        from .models import TimeFrame
        timeframes = [TimeFrame.M5, TimeFrame.M15, TimeFrame.H1, TimeFrame.H4]

        ingest_service = IngestService(
            binance_config={
                'api_key': config.binance.api_key,
                'api_secret': config.binance.api_secret,
                'testnet': config.binance.testnet
            },
            symbols=symbols,
            timeframes=timeframes
        )
        services['ingest'] = ingest_service

        # Initialize feature service
        feature_service = FeatureService()
        services['features'] = feature_service

        # Initialize SMC service
        smc_service = SMCService()
        services['smc'] = smc_service

        # Initialize decision engine
        decision_engine = DecisionEngine(
            risk_manager=risk_manager,
            router_client=router_client
        )
        services['decision'] = decision_engine

        logger.info("All services initialized successfully")

    except Exception as e:
        logger.error(f"Error initializing services: {e}")
        raise


async def start_services():
    """Start all services"""
    try:
        # Start services in dependency order
        await services['event_bus'].start()
        await services['ingest'].start()
        await services['features'].start()
        await services['smc'].start()
        await services['decision'].start()

        logger.info("All services started successfully")

    except Exception as e:
        logger.error(f"Error starting services: {e}")
        raise


async def shutdown_services():
    """Shutdown all services"""
    try:
        # Stop services in reverse order
        for service_name in ['decision', 'smc', 'features', 'ingest', 'event_bus']:
            if service_name in services:
                try:
                    await services[service_name].stop()
                    logger.info(f"Stopped {service_name}")
                except Exception as e:
                    logger.error(f"Error stopping {service_name}: {e}")

        # Close adapters
        for adapter_name in ['router', 'redis', 'database']:
            if adapter_name in services:
                try:
                    await services[adapter_name].close()
                    logger.info(f"Closed {adapter_name}")
                except Exception as e:
                    logger.error(f"Error closing {adapter_name}: {e}")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# Health Check Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Comprehensive health check"""
    try:
        service_health = {}
        overall_status = "healthy"

        # Check each service
        for service_name, service in services.items():
            try:
                if hasattr(service, 'health_check'):
                    health = await service.health_check()
                    service_health[service_name] = health

                    # Determine if service is unhealthy
                    if isinstance(health, dict):
                        if health.get('status') in ['unhealthy', 'error', 'stopped']:
                            overall_status = "degraded"
                    elif not health:
                        overall_status = "degraded"
                else:
                    service_health[service_name] = {"status": "unknown"}

            except Exception as e:
                service_health[service_name] = {"status": "error", "error": str(e)}
                overall_status = "unhealthy"

        uptime = (datetime.utcnow() - startup_time).total_seconds()

        return HealthResponse(
            status=overall_status,
            timestamp=datetime.utcnow().isoformat(),
            services=service_health,
            uptime_seconds=uptime
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@app.get("/health/simple")
async def simple_health_check():
    """Simple health check for load balancers"""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Get detailed metrics from all services"""
    try:
        metrics = {}

        # Collect metrics from each service
        for service_name, service in services.items():
            try:
                if hasattr(service, 'get_metrics'):
                    service_metrics = await service.get_metrics()
                elif hasattr(service, 'health_check'):
                    service_metrics = await service.health_check()
                else:
                    service_metrics = {"status": "no_metrics"}

                metrics[service_name] = service_metrics

            except Exception as e:
                metrics[service_name] = {"error": str(e)}

        return MetricsResponse(
            timestamp=datetime.utcnow().isoformat(),
            event_bus=metrics.get('event_bus', {}),
            ingest=metrics.get('ingest', {}),
            features=metrics.get('features', {}),
            smc=metrics.get('smc', {}),
            decision=metrics.get('decision', {}),
            database=metrics.get('database', {}),
            redis=metrics.get('redis', {})
        )

    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Metrics collection failed: {str(e)}")


# Service Control Endpoints
@app.post("/control/service")
async def control_service(request: ServiceControlRequest, background_tasks: BackgroundTasks):
    """Control individual services"""
    try:
        if request.service and request.service not in services:
            raise HTTPException(status_code=404, detail=f"Service {request.service} not found")

        if request.action == "restart":
            if request.service:
                # Restart specific service
                service = services[request.service]
                background_tasks.add_task(restart_service, request.service, service)
            else:
                # Restart all services
                background_tasks.add_task(restart_all_services)

            return {"message": f"Restart initiated for {request.service or 'all services'}"}

        elif request.action == "stop":
            if request.service:
                service = services[request.service]
                if hasattr(service, 'stop'):
                    await service.stop()
            else:
                await shutdown_services()

            return {"message": f"Stop completed for {request.service or 'all services'}"}

        elif request.action == "start":
            if request.service:
                service = services[request.service]
                if hasattr(service, 'start'):
                    await service.start()
            else:
                await start_services()

            return {"message": f"Start completed for {request.service or 'all services'}"}

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")

    except Exception as e:
        logger.error(f"Error controlling service: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def restart_service(service_name: str, service):
    """Restart a specific service"""
    try:
        logger.info(f"Restarting service: {service_name}")
        if hasattr(service, 'stop'):
            await service.stop()
        if hasattr(service, 'start'):
            await service.start()
        logger.info(f"Successfully restarted: {service_name}")
    except Exception as e:
        logger.error(f"Error restarting {service_name}: {e}")


async def restart_all_services():
    """Restart all services"""
    try:
        logger.info("Restarting all services")
        await shutdown_services()
        await start_services()
        logger.info("Successfully restarted all services")
    except Exception as e:
        logger.error(f"Error restarting all services: {e}")


# Status and Information Endpoints
@app.get("/status")
async def get_status():
    """Get detailed status of all services"""
    try:
        status = {}

        for service_name, service in services.items():
            try:
                if hasattr(service, 'get_status'):
                    service_status = await service.get_status()
                else:
                    service_status = {"available": True}

                status[service_name] = service_status

            except Exception as e:
                status[service_name] = {"error": str(e)}

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": (datetime.utcnow() - startup_time).total_seconds(),
            "services": status
        }

    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/info")
async def get_info():
    """Get general information about the trading engine"""
    return {
        "name": "Trading Engine",
        "version": "1.0.0",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "startup_time": startup_time.isoformat(),
        "uptime_seconds": (datetime.utcnow() - startup_time).total_seconds(),
        "services": list(services.keys())
    }


# Error Handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "timestamp": datetime.utcnow().isoformat()
        }
    )


# Signal handlers for graceful shutdown
def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    # FastAPI will handle the shutdown through the lifespan context manager


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


if __name__ == "__main__":
    # Run the application
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        reload=os.getenv("ENVIRONMENT", "development") == "development"
    )