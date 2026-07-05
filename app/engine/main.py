"""
FastAPI Main Application

Main FastAPI application for the trading engine with health endpoints,
metrics, and service management.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
import json
import logging
import os
import signal
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

from .adapters import RedisAdapter, RouterHTTPClient, TimescaleDBAdapter
from .bus import set_event_bus
from .contracts.contract_publisher import ContractPublisher
from .core.health import build_system_health
from .decision.decision_publisher import DecisionPublisher
from .decision.service import RiskManager
from .features.feature_service import FeatureService
from .ingest.ingest_service import IngestService
from .models import (
    BinanceConfig,
    DatabaseConfig,
    EngineConfig,
    RedisConfig,
    RiskParameters,
)
from .retest.engine import RetestEngine
from .smc.engine import SMCEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global service instances
services: dict[str, Any] = {}


def _merge_order_update_metadata(
    base: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in fallback.items():
        if key not in merged or merged[key] in (None, "", {}):
            merged[key] = value
    return merged


def _metadata_from_order_row(order_row: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}

    decision_id = order_row.get("decision_id")
    if decision_id is not None:
        decision_id_str = str(decision_id).strip()
        if decision_id_str:
            metadata["decision_id"] = decision_id_str

    for key in ("signal_id", "timeframe", "venue"):
        value = order_row.get(key)
        if isinstance(value, str) and value:
            metadata[key] = value

    zone = order_row.get("zone")
    if isinstance(zone, str):
        try:
            zone = json.loads(zone)
        except json.JSONDecodeError:
            zone = None
    if isinstance(zone, dict) and zone:
        metadata["zone"] = zone

    return metadata


# Request/Response Models
class HealthResponse(BaseModel):
    status: str
    timestamp: str
    services: dict[str, Any]
    uptime_seconds: float


class MetricsResponse(BaseModel):
    timestamp: str
    event_bus: dict[str, Any]
    ingest: dict[str, Any]
    features: dict[str, Any]
    smc: dict[str, Any]
    decision: dict[str, Any]
    database: dict[str, Any]
    redis: dict[str, Any]


class ServiceControlRequest(BaseModel):
    action: str  # "start", "stop", "restart"
    service: str | None = None  # None for all services


class EquityHealthResponse(BaseModel):
    """Response model for /health/equity endpoint."""

    status: str  # "healthy" | "stale" | "missing" | "zero"
    equity: Decimal | None
    timestamp: str | None
    age_seconds: float | None
    paper_components: dict[str, str] | None
    message: str


def _cors_allowed_origins_from_env() -> list[str]:
    raw = os.getenv(
        "CORS_ORIGIN",
        "http://localhost:3000,http://localhost:3001,http://localhost:8002",
    )
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or ["http://localhost:3000"]


def _internal_api_token_from_env() -> str:
    return os.getenv("ENGINE_INTERNAL_API_TOKEN", "").strip()


async def _require_internal_api_token(
    authorization: str | None = Header(default=None),
) -> None:
    expected_token = _internal_api_token_from_env()
    if not expected_token:
        raise HTTPException(status_code=503, detail="internal API token not configured")
    if authorization is None:
        raise HTTPException(status_code=401, detail="missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token.strip() != expected_token:
        raise HTTPException(status_code=401, detail="invalid Authorization header")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> Any:
    """Application lifespan management"""
    logger.info("Starting trading engine...")

    try:
        # Initialize tracing provider as early as possible
        init_tracing_from_env()
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
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins_from_env(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track startup time
startup_time = datetime.now(UTC)


def _binance_data_testnet_from_env() -> bool:
    data_source = os.getenv("BINANCE_DATA_SOURCE", "mainnet").strip().lower()
    if data_source == "mainnet":
        return False
    if data_source == "testnet":
        logger.warning(
            "BINANCE_DATA_SOURCE=testnet: testnet market data is thin and unrealistic "
            "for signal generation; prefer mainnet data with ROUTER_EXECUTION_ENV=testnet",
        )
        return True
    raise ValueError("BINANCE_DATA_SOURCE must be 'mainnet' or 'testnet'")


def _pipeline_health_alerts_enabled_from_env() -> bool:
    value = os.getenv("PIPELINE_HEALTH_ALERTS_ENABLED", "1").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _telegram_execution_decision_alerts_enabled_from_env() -> bool:
    """Decision alerts in execution mode are opt-out: unset means enabled.

    Switching EXECUTION_MODE must not silently stop signal alerts; set
    TELEGRAM_EXECUTION_DECISION_ALERTS_ENABLED=0 to opt out explicitly.
    """
    value = os.getenv("TELEGRAM_EXECUTION_DECISION_ALERTS_ENABLED", "1").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _paper_trading_enabled_from_env() -> bool:
    """Check if paper trading mode is enabled via ENABLE_PAPER_TRADING env var."""
    value = os.getenv("ENABLE_PAPER_TRADING", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _live_rest_fallback_enabled_from_env() -> bool:
    value = os.getenv("LIVE_REST_FALLBACK_ENABLED", "1").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _ingest_enabled_from_env() -> bool:
    value = os.getenv("INGEST_ENABLED", "1").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _signal_emitter_subscriber_enabled_from_env() -> bool:
    """Check if SignalEmitterSubscriber should be enabled.

    IMPORTANT: This bypass path emits trading decisions directly from SMC signals
    WITHOUT risk management, proper position sizing, or retest confirmation.
    Disabled by default to ensure only the proper Retest → DecisionPublisher path is used.

    Set SIGNAL_EMITTER_SUBSCRIBER_ENABLED=1 to enable (NOT RECOMMENDED for production).
    """
    value = os.getenv("SIGNAL_EMITTER_SUBSCRIBER_ENABLED", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def _order_update_db_hydration_enabled_from_env() -> bool:
    value = os.getenv("ORDER_UPDATE_DB_HYDRATION_ENABLED", "1").strip().lower()
    return value in {"1", "true", "yes", "on"}


def init_tracing_from_env() -> None:
    """Initialize global tracing provider from environment.

    Delegates to core.tracing.configure_tracing_from_env to respect TRACING_DISABLED.
    """
    from .core.tracing import configure_tracing_from_env

    configure_tracing_from_env()


def load_configuration() -> EngineConfig:
    """Load configuration from environment and config files"""
    try:
        binance_data_testnet = _binance_data_testnet_from_env()

        database_url = os.getenv("DATABASE_URL")
        if database_url:
            import urllib.parse

            parsed = urllib.parse.urlparse(database_url)
            if parsed.scheme not in {"postgresql", "postgres"}:
                raise ValueError("DATABASE_URL must be a postgres URL")
            database_config = DatabaseConfig(
                host=parsed.hostname or "localhost",
                port=parsed.port or 5432,
                database=parsed.path.lstrip("/") or "trading_engine",
                username=urllib.parse.unquote(parsed.username or "postgres"),
                password=urllib.parse.unquote(parsed.password or "password"),
            )
        else:
            # Default configuration - in production, load from environment/config files
            database_config = DatabaseConfig(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", "5432")),
                database=os.getenv("DB_NAME", "trading_engine"),
                username=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", "password"),
            )

        # Parse Redis configuration from URL if provided, otherwise use individual vars
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            # Parse redis://host:port/db format
            import urllib.parse

            parsed = urllib.parse.urlparse(redis_url)
            redis_config = RedisConfig(
                host=parsed.hostname or "localhost",
                port=parsed.port or 6379,
                password=parsed.password,
                database=int(parsed.path.lstrip("/")) if parsed.path.strip("/") else 0,
            )
        else:
            redis_config = RedisConfig(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                password=os.getenv("REDIS_PASSWORD"),
            )

        binance_config = BinanceConfig(
            api_key=os.getenv("BINANCE_API_KEY", ""),
            api_secret=os.getenv("BINANCE_API_SECRET", ""),
            testnet=binance_data_testnet,
        )

        risk_parameters = RiskParameters(
            max_position_size=Decimal(os.getenv("MAX_POSITION_SIZE", "0.1")),
            max_daily_loss=Decimal(os.getenv("MAX_DAILY_LOSS", "0.05")),
            max_drawdown=Decimal(os.getenv("MAX_DRAWDOWN", "0.15")),
            # 0.5% fixed-fractional per trade — the documented risk profile.
            risk_per_trade=Decimal(os.getenv("RISK_PER_TRADE", "0.005")),
            max_correlation=Decimal(os.getenv("MAX_CORRELATION", "0.7")),
            max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "5")),
            max_total_exposure_leverage=Decimal(
                os.getenv("MAX_TOTAL_EXPOSURE_LEVERAGE", "3"),
            ),
            max_symbol_exposure_pct=Decimal(os.getenv("MAX_SYMBOL_EXPOSURE_PCT", "0.25")),
            max_position_notional_pct=Decimal(
                os.getenv("MAX_POSITION_NOTIONAL_PCT", "0.10"),
            ),
            risk_data_max_age_seconds=int(os.getenv("RISK_DATA_MAX_AGE_SECONDS", "120")),
            drawdown_lookback_days=int(os.getenv("DRAWDOWN_LOOKBACK_DAYS", "30")),
        )

        config = EngineConfig(
            environment=os.getenv("ENVIRONMENT", "development"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            database=database_config,
            redis=redis_config,
            binance=binance_config,
            risk_parameters=risk_parameters,
        )

        logger.info(f"Configuration loaded for environment: {config.environment}")
        return config

    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        raise


async def initialize_services(config: EngineConfig) -> None:  # noqa: PLR0915, C901
    """Initialize all services"""
    try:
        # Initialize event bus
        from .bus import create_event_bus

        event_bus = create_event_bus()
        set_event_bus(event_bus)
        services["event_bus"] = event_bus

        # Initialize database adapter
        db_adapter = TimescaleDBAdapter(
            host=config.database.host,
            port=config.database.port,
            database=config.database.database,
            username=config.database.username,
            password=config.database.password,
        )
        await db_adapter.initialize()
        services["database"] = db_adapter

        # Initialize Redis adapter
        redis_url = os.getenv("REDIS_URL")
        redis_adapter = RedisAdapter(
            url=redis_url,
            host=config.redis.host,
            port=config.redis.port,
            password=config.redis.password,
        )
        await redis_adapter.initialize()
        services["redis"] = redis_adapter

        # Publish contract-topic events for BFF/UI via Redis
        services["contract_publisher"] = ContractPublisher(bus=event_bus, redis=redis_adapter)

        # Initialize router client
        from .core.breaker_config import router_breaker_config_from_env

        router_breakers = router_breaker_config_from_env()
        router_client = RouterHTTPClient(
            base_url=os.getenv("ROUTER_URL", "http://localhost:8001"),
            api_key=os.getenv("ROUTER_API_KEY"),
            per_endpoint_breakers_config=router_breakers if router_breakers else None,
        )
        await router_client.initialize()
        services["router"] = router_client

        # Optional: auto-execution subscriber (opt-in)
        from .execution.router_execution_subscriber import (
            ExecutionMode,
            RouterExecutionSubscriber,
            execution_mode_from_env,
        )

        execution_mode = execution_mode_from_env(os.environ)
        services["execution_mode"] = execution_mode  # Store for AlertSubscriber
        execution_enabled = execution_mode != ExecutionMode.DISABLED
        execution_decision_alerts_enabled = (
            execution_enabled and _telegram_execution_decision_alerts_enabled_from_env()
        )
        execution_venue = (
            "USD_M"
            if execution_mode
            in {
                ExecutionMode.FUTURES_TESTNET,
                ExecutionMode.FUTURES_MAINNET,
            }
            else "SPOT"
        )

        # Create separate cooldown instances (execution vs alerts)
        from .core.signal_cooldown import SignalCooldown

        cooldown_seconds = int(os.getenv("SIGNAL_COOLDOWN_SECONDS", "300"))
        execution_cooldown = SignalCooldown(cooldown_seconds=cooldown_seconds, redis=redis_adapter)
        alert_cooldown = SignalCooldown(cooldown_seconds=cooldown_seconds, redis=redis_adapter)
        services["execution_cooldown"] = execution_cooldown
        services["alert_cooldown"] = alert_cooldown

        if execution_enabled:
            min_confidence = Decimal(os.getenv("MIN_CONFIDENCE_TO_EXECUTE", "0.70"))
            from .execution.order_update_correlation import OrderUpdateCorrelationStore

            correlation_ttl_seconds = int(
                os.getenv("ORDER_UPDATE_CORRELATION_TTL_SECONDS", "21600")
            )
            correlation_store = OrderUpdateCorrelationStore(
                ttl_seconds=correlation_ttl_seconds,
                redis=redis_adapter,
            )
            services["order_update_correlation_store"] = correlation_store

            async def execution_readiness_check() -> tuple[bool, str | None, dict[str, object]]:
                ingest_service = services.get("ingest")
                if ingest_service is None or not hasattr(ingest_service, "health_check"):
                    return (
                        False,
                        "Execution blocked: ingest service unavailable",
                        {"blocking_issue_types": ["ingest_unavailable"]},
                    )

                from .monitoring.pipeline_health_service import (
                    PipelineHealthThresholds,
                    evaluate_pipeline_health,
                )

                ingest_health = await ingest_service.health_check()
                issues = evaluate_pipeline_health(
                    ingest_health=ingest_health,
                    now=datetime.now(UTC),
                    thresholds=PipelineHealthThresholds(),
                )
                blocking_issues = [
                    issue
                    for issue in issues
                    if issue.error_type
                    in {
                        "websocket_disconnected",
                        "websocket_stale",
                        "kline_stream_stale",
                        "candle_stale",
                    }
                ]
                if not blocking_issues:
                    return True, None, {}
                issue_types = list(dict.fromkeys(issue.error_type for issue in blocking_issues))
                return (
                    False,
                    f"Execution blocked: {', '.join(issue_types)}",
                    {
                        "blocking_issue_types": issue_types,
                        "blocking_symbols": list(
                            dict.fromkeys(issue.symbol for issue in blocking_issues),
                        ),
                    },
                )

            services["execution_subscriber"] = RouterExecutionSubscriber(
                bus=event_bus,
                router_client=router_client,
                db_adapter=db_adapter,
                risk=config.risk_parameters,
                venue=execution_venue,
                execution_mode=execution_mode,
                order_update_correlation_store=correlation_store,
                cooldown=execution_cooldown,
                min_confidence=min_confidence,
                max_position_size=config.risk_parameters.max_position_size,
                execution_readiness_check=execution_readiness_check,
                router_env_probe_attempts=5,
            )
            logger.info(
                "Execution subscriber enabled: %s (min_confidence=%s, cooldown=%ss)",
                execution_mode.value,
                min_confidence,
                cooldown_seconds,
            )

        # Initialize risk manager
        risk_manager = RiskManager(config.risk_parameters)
        services["risk_manager"] = risk_manager
        from .models import TimeFrame

        timeframes = [TimeFrame.M5, TimeFrame.M15, TimeFrame.H1, TimeFrame.H4]

        if _ingest_enabled_from_env():
            # Initialize ingest service
            raw_symbols = os.getenv("TRADING_SYMBOLS", "BTCUSDT,ETHUSDT").split(",")
            symbols = [s.strip().upper() for s in raw_symbols if s.strip()]
            if not symbols:
                raise RuntimeError(
                    "TRADING_SYMBOLS resolved to an empty list after sanitization. "
                    "Set TRADING_SYMBOLS to a comma-separated list like 'BTCUSDT,ETHUSDT'.",
                )

            from .core.breaker_config import binance_breaker_config_from_env

            binance_breakers = binance_breaker_config_from_env()
            ingest_service = IngestService(
                binance_config={
                    "spot": {
                        "api_key": config.binance.api_key,
                        "api_secret": config.binance.api_secret,
                    },
                    # Optionally extend with futures if present in env/config later
                    "testnet": config.binance.testnet,
                },
                symbols=symbols,
                timeframes=timeframes,
                binance_breakers_config=binance_breakers if binance_breakers else None,
                db_adapter=db_adapter,  # For direct DB writes during backfill
            )
            services["ingest"] = ingest_service

            if _pipeline_health_alerts_enabled_from_env():
                from .monitoring.pipeline_health_service import PipelineHealthService

                services["pipeline_health"] = PipelineHealthService(
                    bus=event_bus,
                    ingest_service=ingest_service,
                )

            if _live_rest_fallback_enabled_from_env():
                from .ingest.live_rest_fallback import LiveRestFallbackService

                if ingest_service.rest_client is not None and ingest_service.ws_client is not None:
                    services["live_rest_fallback"] = LiveRestFallbackService(
                        bus=event_bus,
                        rest_client=ingest_service.rest_client,
                        ws_client=ingest_service.ws_client,
                        ingest_service=ingest_service,
                        symbols=symbols,
                        timeframes=timeframes,
                    )
        else:
            logger.warning("Ingest service disabled (INGEST_ENABLED=0)")

        # Initialize feature service (and persist indicators via canonical `indicators` table)
        feature_service = FeatureService(db_adapter=db_adapter)
        services["features"] = feature_service

        # Initialize SMC engine (single source of truth for SMC)
        services["smc"] = SMCEngine(db_adapter=db_adapter)

        # Wire conservative pipeline: retest -> decision publisher
        services["retest_engine"] = RetestEngine(config={"retest": {}})
        services["decision_publisher"] = DecisionPublisher(
            db_adapter=db_adapter,
            risk=config.risk_parameters,
            venue=execution_venue,
        )

        # Initialize equity sampler for paper trading mode
        # This keeps DecisionPublisher's risk snapshot from rejecting decisions
        # due to stale equity samples
        if _paper_trading_enabled_from_env():
            from .paper.equity_sampler_service import (
                EquitySamplerConfig,
                EquitySamplerService,
            )

            paper_starting_balance = Decimal(os.getenv("PAPER_STARTING_BALANCE", "10000"))
            sampler_config = EquitySamplerConfig(
                starting_balance=paper_starting_balance,
                poll_interval_seconds=60,
            )
            services["equity_sampler"] = EquitySamplerService(
                db_adapter=db_adapter,
                config=sampler_config,
            )
            logger.info(
                "EquitySamplerService initialized (starting_balance=%s)",
                paper_starting_balance,
            )
        else:
            from .execution.router_equity_sampler_service import (
                RouterEquitySamplerConfig,
                RouterEquitySamplerService,
            )

            poll_interval_seconds = int(os.getenv("LIVE_EQUITY_POLL_INTERVAL_SECONDS", "60"))
            if poll_interval_seconds <= 0:
                poll_interval_seconds = 60

            services["equity_sampler"] = RouterEquitySamplerService(
                db_adapter=db_adapter,
                router_client=router_client,
                config=RouterEquitySamplerConfig(
                    venue=execution_venue,
                    poll_interval_seconds=poll_interval_seconds,
                ),
            )
            logger.info(
                "RouterEquitySamplerService initialized (venue=%s, poll_interval_seconds=%s)",
                execution_venue,
                poll_interval_seconds,
            )

        # Initialize alert subscriber (if Telegram configured)
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if telegram_bot_token:
            from .adapters.alert.alert_subscriber import AlertSubscriber
            from .adapters.alert.telegram import TelegramAlertAdapter

            telegram_adapter = TelegramAlertAdapter(
                bot_token=telegram_bot_token,
                chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
                db_adapter=db_adapter,
            )
            await telegram_adapter.start()
            services["telegram_adapter"] = telegram_adapter

            # Mode-aware alert subscriber:
            # - execution_enabled=True: alerts on ORDER_UPDATE and, when enabled, TRADING_DECISION
            # - execution_enabled=False: alerts on TRADING_DECISION (signal-only)
            alert_subscriber = AlertSubscriber(
                telegram_adapter=telegram_adapter,
                execution_enabled=execution_enabled,
                execution_decision_alerts_enabled=execution_decision_alerts_enabled,
                cooldown=None if execution_enabled else alert_cooldown,
                # BFF client for snapshots in disabled mode (set below when available)
            )
            await alert_subscriber.register(event_bus)
            services["alert_subscriber"] = alert_subscriber

            logger.info(
                "Alert subscriber initialized with Telegram (execution_enabled=%s)",
                execution_enabled,
            )

        # Initialize BFF API client (for signal alerts with snapshots)
        bff_url = os.getenv("BFF_URL")
        internal_alerts_token = os.getenv("INTERNAL_ALERTS_TOKEN")
        if bff_url and internal_alerts_token:
            from .adapters.alert.bff_api_client import BffApiClient

            bff_client = BffApiClient(base_url=bff_url, token=internal_alerts_token)
            services["bff_client"] = bff_client

            # Wire bff_client to execution_subscriber for snapshots on order placement
            if "execution_subscriber" in services:
                services["execution_subscriber"]._bff_client = bff_client
                logger.info("BFF client wired to execution subscriber for snapshots")

            # Wire bff_client to alert_subscriber for snapshots in disabled mode
            if "alert_subscriber" in services and not execution_enabled:
                services["alert_subscriber"]._bff_client = bff_client
                logger.info("BFF client wired to alert subscriber for snapshots")

            # SignalEmitterSubscriber is DISABLED by default
            # This bypass path emits decisions WITHOUT risk management
            # Only enable via SIGNAL_EMITTER_SUBSCRIBER_ENABLED=1 for testing
            if _signal_emitter_subscriber_enabled_from_env():
                if execution_enabled:
                    raise RuntimeError(  # noqa: TRY301
                        "Refusing to enable SignalEmitterSubscriber when execution is enabled. "
                        "Set EXECUTION_MODE=disabled or disable SIGNAL_EMITTER_SUBSCRIBER_ENABLED.",
                    )
                from .adapters.alert.signal_emitter import SignalEmitter
                from .adapters.alert.signal_emitter_subscriber import (
                    SignalEmitterSubscriber,
                )

                signal_emitter = SignalEmitter(event_bus=event_bus, bff_client=bff_client)
                services["signal_emitter"] = signal_emitter

                signal_emitter_subscriber = SignalEmitterSubscriber(
                    bus=event_bus,
                    signal_emitter=signal_emitter,
                    venue=os.getenv("TRADING_VENUE", "SPOT"),
                )
                services["signal_emitter_subscriber"] = signal_emitter_subscriber
                logger.warning(
                    "SignalEmitterSubscriber ENABLED - bypasses risk management! "
                    "NOT recommended for production.",
                )
            else:
                logger.info(
                    "SignalEmitterSubscriber DISABLED (default) - "
                    "using proper Retest → DecisionPublisher path",
                )

        logger.info("All services initialized successfully")

    except Exception as e:
        logger.error(f"Error initializing services: {e}")
        raise


async def start_services() -> None:
    """Start all services"""
    try:
        # Start services in dependency order
        await services["event_bus"].start()
        if "contract_publisher" in services:
            await services["contract_publisher"].start()
            logger.info("Started contract_publisher")
        if "ingest" in services:
            await services["ingest"].start()
            logger.info("Started ingest")
        else:
            logger.info("Skipped ingest start (INGEST_ENABLED=0)")
        await services["features"].start()
        await services["smc"].start()
        await services["retest_engine"].start()

        # Start equity sampler BEFORE decision publisher to ensure fresh samples
        if "equity_sampler" in services:
            await services["equity_sampler"].start()
            logger.info("Started equity_sampler")

        await services["decision_publisher"].start()

        if "pipeline_health" in services:
            await services["pipeline_health"].start()
            logger.info("Started pipeline_health")

        if "live_rest_fallback" in services:
            await services["live_rest_fallback"].start()
            logger.info("Started live_rest_fallback")

        if "execution_subscriber" in services:
            await services["execution_subscriber"].start()
            logger.info("Started execution_subscriber")

        # Start BFF client and signal emitter subscriber
        if "bff_client" in services:
            await services["bff_client"].start()
            logger.info("Started bff_client")
        if "signal_emitter_subscriber" in services:
            await services["signal_emitter_subscriber"].start()
            logger.info("Started signal_emitter_subscriber")

        logger.info("All services started successfully")

    except Exception as e:
        logger.error(f"Error starting services: {e}")
        raise


async def shutdown_services() -> None:  # noqa: C901, PLR0912, PLR0915
    """Shutdown all services"""
    try:
        # Stop equity sampler first (before decision publisher stops)
        if "equity_sampler" in services:
            try:
                await services["equity_sampler"].stop()
                logger.info("Stopped equity_sampler")
            except Exception as e:
                logger.error(f"Error stopping equity_sampler: {e}")

        if "execution_subscriber" in services:
            try:
                await services["execution_subscriber"].stop()
                logger.info("Stopped execution_subscriber")
            except Exception as e:
                logger.error(f"Error stopping execution_subscriber: {e}")

        if "pipeline_health" in services:
            try:
                await services["pipeline_health"].stop()
                logger.info("Stopped pipeline_health")
            except Exception as e:
                logger.error(f"Error stopping pipeline_health: {e}")

        if "live_rest_fallback" in services:
            try:
                await services["live_rest_fallback"].stop()
                logger.info("Stopped live_rest_fallback")
            except Exception as e:
                logger.error(f"Error stopping live_rest_fallback: {e}")

        # Stop signal emitter subscriber first (to stop receiving events)
        if "signal_emitter_subscriber" in services:
            try:
                await services["signal_emitter_subscriber"].stop()
                logger.info("Stopped signal_emitter_subscriber")
            except Exception as e:
                logger.error(f"Error stopping signal_emitter_subscriber: {e}")

        # Stop BFF client
        if "bff_client" in services:
            try:
                await services["bff_client"].stop()
                logger.info("Stopped bff_client")
            except Exception as e:
                logger.error(f"Error stopping bff_client: {e}")

        # Stop alert subscriber
        if "alert_subscriber" in services:
            try:
                await services["alert_subscriber"].stop()
                logger.info("Stopped alert_subscriber")
            except Exception as e:
                logger.error(f"Error stopping alert_subscriber: {e}")

        # Stop telegram adapter
        if "telegram_adapter" in services:
            try:
                await services["telegram_adapter"].stop()
                logger.info("Stopped telegram_adapter")
            except Exception as e:
                logger.error(f"Error stopping telegram_adapter: {e}")

        # Stop services in reverse order
        for service_name in [
            "decision_publisher",
            "retest_engine",
            "smc",
            "features",
            "ingest",
            "contract_publisher",
            "event_bus",
        ]:
            if service_name in services:
                try:
                    if hasattr(services[service_name], "stop"):
                        await services[service_name].stop()
                        logger.info(f"Stopped {service_name}")
                except Exception as e:
                    logger.error(f"Error stopping {service_name}: {e}")

        # Close adapters
        for adapter_name in ["router", "redis", "database"]:
            if adapter_name in services:
                try:
                    adapter = services[adapter_name]
                    if hasattr(adapter, "close"):
                        await adapter.close()
                    logger.info(f"Closed {adapter_name}")
                except Exception as e:
                    logger.error(f"Error closing {adapter_name}: {e}")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# Health Check Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Comprehensive health check"""
    try:
        service_health = {}
        overall_status = "healthy"

        # Check each service
        for service_name, service in services.items():
            try:
                if hasattr(service, "health_check"):
                    health = await service.health_check()
                    service_health[service_name] = health

                    # Determine if service is unhealthy
                    if isinstance(health, dict):
                        if health.get("status") in ["unhealthy", "error", "stopped"]:
                            overall_status = "degraded"
                    elif not health:
                        overall_status = "degraded"
                else:
                    service_health[service_name] = {"status": "unknown"}

            except Exception as e:
                logger.error("Health check error for %s: %s", service_name, e)
                service_health[service_name] = {"status": "error", "error": "health check failed"}
                overall_status = "unhealthy"

        uptime = (datetime.now(UTC) - startup_time).total_seconds()

        return HealthResponse(
            status=overall_status,
            timestamp=datetime.now(UTC).isoformat(),
            services=service_health,
            uptime_seconds=uptime,
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail="Health check failed") from e


@app.get("/health/simple")
async def simple_health_check() -> dict[str, Any]:
    """Simple health check for load balancers"""
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}


@app.get("/health/equity", response_model=EquityHealthResponse)
async def equity_health_check() -> EquityHealthResponse:
    """Check equity state for debugging invalid_notional errors.

    Returns current equity from equity_samples table plus paper trading
    components breakdown. Useful for diagnosing why trades are rejected
    with invalid_notional (usually because equity is 0).
    """
    if "database" not in services:
        raise HTTPException(
            status_code=503,
            detail="Database service not initialized",
        )

    db_adapter = services["database"]
    stale_threshold_seconds = 120.0

    try:
        # Get latest equity sample
        equity, timestamp = await db_adapter.get_latest_equity_sample()

        # Get paper equity components for breakdown
        components = await db_adapter.get_paper_equity_components()

        # Handle missing samples
        if equity is None or timestamp is None:
            return EquityHealthResponse(
                status="missing",
                equity=None,
                timestamp=None,
                age_seconds=None,
                paper_components=None,
                message="No equity samples found in database",
            )

        # Normalize naive timestamp to UTC
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        # Calculate age
        now = datetime.now(UTC)
        age_seconds = (now - timestamp).total_seconds()

        # Build paper components dict if available
        paper_components_dict: dict[str, str] | None = None
        if components is not None:
            paper_components_dict = {
                "total_fees": str(components.total_fees),
                "realized_pnl": str(components.realized_pnl),
                "unrealized_pnl": str(components.unrealized_pnl),
                "total_funding": str(components.total_funding),
            }

        # Determine status
        if equity == Decimal("0"):
            status = "zero"
            message = "Equity is zero - trades will fail with invalid_notional"
        elif age_seconds > stale_threshold_seconds:
            status = "stale"
            message = (
                f"Equity sample is {age_seconds:.0f}s old (threshold: {stale_threshold_seconds}s)"
            )
        else:
            status = "healthy"
            message = "Equity is healthy and fresh"

        return EquityHealthResponse(
            status=status,
            equity=equity,
            timestamp=timestamp.isoformat(),
            age_seconds=age_seconds,
            paper_components=paper_components_dict,
            message=message,
        )

    except Exception as e:
        logger.error(f"Error checking equity health: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error checking equity health",
        ) from e


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics() -> MetricsResponse:
    """Get detailed metrics from all services"""
    try:
        metrics = {}

        # Collect metrics from each service
        for service_name, service in services.items():
            try:
                if hasattr(service, "get_metrics"):
                    service_metrics = await service.get_metrics()
                elif hasattr(service, "health_check"):
                    service_metrics = await service.health_check()
                else:
                    service_metrics = {"status": "no_metrics"}

                metrics[service_name] = service_metrics

            except Exception as e:
                logger.error("Metrics error for %s: %s", service_name, e)
                metrics[service_name] = {"error": "metrics collection failed"}

        return MetricsResponse(
            timestamp=datetime.now(UTC).isoformat(),
            event_bus=metrics.get("event_bus", {}),
            ingest=metrics.get("ingest", {}),
            features=metrics.get("features", {}),
            smc=metrics.get("smc", {}),
            decision=metrics.get("decision_publisher", {}),
            database=metrics.get("database", {}),
            redis=metrics.get("redis", {}),
        )

    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail="Metrics collection failed",
        ) from e


# System health endpoint including per-endpoint breaker metrics
@app.get("/health/system")
async def get_system_health() -> Any:
    try:
        health = await build_system_health(services)
        body: dict[str, Any] = {
            "status": health.status.value,
            "message": health.message,
            "timestamp": health.timestamp,
            "latency_ms": health.latency_ms,
            "components": {},
        }
        for name, comp in health.components.items():
            body["components"][name] = {
                "status": comp.status.value,
                "message": comp.message,
                "latency_ms": comp.latency_ms,
                "details": comp.details,
            }
        return JSONResponse(content=body, status_code=200)
    except Exception as e:
        logger.error(f"system health error: {e}")
        return JSONResponse(
            content={"status": "unhealthy", "message": "system health error"},
            status_code=503,
        )


@app.post("/internal/order_update", dependencies=[Depends(_require_internal_api_token)])
async def ingest_order_update(update: dict[str, Any]) -> dict[str, str]:
    """Ingest router/exchange order updates for execution-mode alerting.

    Router POSTs `order_update.v1` payloads; we correlate client_order_id back to
    the originating trading decision and publish an OrderUpdateEvent on the bus.
    """
    if "event_bus" not in services:
        raise HTTPException(status_code=503, detail="event_bus not initialized")

    from .models import OrderUpdate, OrderUpdateEvent

    try:
        parsed = OrderUpdate.model_validate(update)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid order update payload") from exc

    ts = parsed.update_time or datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)

    metadata: dict[str, Any] = {}
    store = services.get("order_update_correlation_store")
    if store is not None:
        corr = await store.get(client_order_id=parsed.client_order_id)
        if corr is not None:
            metadata = dict(corr.metadata)

    db_adapter = services.get("database")
    hydration_enabled = _order_update_db_hydration_enabled_from_env()
    if (
        not metadata
        and hydration_enabled
        and db_adapter is not None
        and hasattr(db_adapter, "get_order_by_client_order_id")
    ):
        try:
            hydrated_order_row = await db_adapter.get_order_by_client_order_id(
                client_order_id=parsed.client_order_id,
                venue=parsed.venue,
            )
            if hydrated_order_row is not None:
                metadata = _merge_order_update_metadata(
                    metadata,
                    _metadata_from_order_row(hydrated_order_row),
                )
        except Exception:
            logger.exception(
                "Failed to hydrate order update metadata from DB (client_order_id=%s)",
                parsed.client_order_id,
            )

    event = OrderUpdateEvent(
        timestamp=ts,
        symbol=parsed.symbol,
        metadata=metadata,
        update=parsed,
        payload=update,
    )

    normalized_status = parsed.status.strip().upper()
    if normalized_status == "CANCELLED":
        normalized_status = "CANCELED"
    terminal_statuses = {"FILLED", "REJECTED", "CANCELED", "EXPIRED"}
    terminal_update_persisted = False

    # Persist order updates for auditability (best-effort; do not block alerting).
    if hydration_enabled and db_adapter is not None and hasattr(db_adapter, "upsert_order"):
        try:
            venue = parsed.venue or metadata.get("venue")
            if isinstance(venue, str) and venue:
                raw_type = (parsed.order_type or "").strip().upper()
                order_type = "STOP_LOSS" if raw_type == "STOP_MARKET" else raw_type

                order_row: dict[str, Any] = {
                    "venue": venue,
                    "client_order_id": parsed.client_order_id,
                    "symbol": parsed.symbol,
                    "side": (parsed.side or "").strip().upper(),
                    "type": order_type,
                    "quantity": parsed.quantity or parsed.executed_qty,
                    "price": parsed.price,
                    "status": normalized_status,
                    "filled_quantity": parsed.executed_qty,
                    "average_fill_price": parsed.price if normalized_status == "FILLED" else None,
                    "exchange_order_id": str(parsed.order_id)
                    if parsed.order_id is not None
                    else None,
                    "last_update_time": ts,
                }
                decision_id = metadata.get("decision_id")
                if isinstance(decision_id, str) and decision_id:
                    order_row["decision_id"] = decision_id
                signal_id = metadata.get("signal_id")
                if isinstance(signal_id, str) and signal_id:
                    order_row["signal_id"] = signal_id
                timeframe = metadata.get("timeframe")
                if isinstance(timeframe, str) and timeframe:
                    order_row["timeframe"] = timeframe
                zone = metadata.get("zone")
                if isinstance(zone, dict) and zone:
                    order_row["zone"] = zone
                persisted = await db_adapter.upsert_order(order_row)
                terminal_update_persisted = (
                    bool(persisted) and normalized_status in terminal_statuses
                )
        except Exception:
            logger.exception(
                "Failed to persist order update to DB (client_order_id=%s)", parsed.client_order_id
            )

    await services["event_bus"].publish(event, priority=7)

    if store is not None and terminal_update_persisted:
        await store.delete(client_order_id=parsed.client_order_id)

    return {"status": "ok"}


# Service Control Endpoints
@app.post("/control/service", dependencies=[Depends(_require_internal_api_token)])
async def control_service(  # noqa: C901, PLR0912
    request: ServiceControlRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Control individual services"""
    try:
        if request.service and request.service not in services:
            raise HTTPException(  # noqa: TRY301
                status_code=404,
                detail=f"Service {request.service} not found",
            )

        if request.action == "restart":
            if request.service:
                # Restart specific service
                service = services[request.service]
                background_tasks.add_task(restart_service, request.service, service)
            else:
                # Restart all services
                background_tasks.add_task(restart_all_services)

            return {
                "message": f"Restart initiated for {request.service or 'all services'}",
            }

        if request.action == "stop":
            if request.service:
                service = services[request.service]
                if hasattr(service, "stop"):
                    await service.stop()
            else:
                await shutdown_services()

            return {
                "message": f"Stop completed for {request.service or 'all services'}",
            }

        if request.action == "start":
            if request.service:
                service = services[request.service]
                if hasattr(service, "start"):
                    await service.start()
            else:
                await start_services()

            return {
                "message": f"Start completed for {request.service or 'all services'}",
            }

        raise HTTPException(  # noqa: TRY301
            status_code=400,
            detail=f"Unknown action: {request.action}",
        )

    except Exception as e:
        logger.error(f"Error controlling service: {e}")
        raise HTTPException(status_code=500, detail="Service control failed") from e


async def restart_service(service_name: str, service: Any) -> None:
    """Restart a specific service"""
    try:
        logger.info(f"Restarting service: {service_name}")
        if hasattr(service, "stop"):
            await service.stop()
        if hasattr(service, "start"):
            await service.start()
        logger.info(f"Successfully restarted: {service_name}")
    except Exception as e:
        logger.error(f"Error restarting {service_name}: {e}")


async def restart_all_services() -> None:
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
async def get_status() -> dict[str, Any]:
    """Get detailed status of all services"""
    try:
        status = {}

        for service_name, service in services.items():
            try:
                if hasattr(service, "get_status"):
                    service_status = await service.get_status()
                else:
                    service_status = {"available": True}

                status[service_name] = service_status

            except Exception as e:
                logger.error("Status error for %s: %s", service_name, e)
                status[service_name] = {"error": "status check failed"}

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "uptime_seconds": (datetime.now(UTC) - startup_time).total_seconds(),
            "services": status,
        }

    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail="Error getting status") from e


@app.get("/info")
async def get_info() -> dict[str, Any]:
    """Get general information about the trading engine"""
    return {
        "name": "Trading Engine",
        "version": "1.0.0",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "startup_time": startup_time.isoformat(),
        "uptime_seconds": (datetime.now(UTC) - startup_time).total_seconds(),
        "services": list(services.keys()),
    }


# Error Handlers
@app.exception_handler(Exception)
async def global_exception_handler(_request: Any, exc: Exception) -> JSONResponse:
    """Global exception handler"""
    logger.error("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


# Signal handlers for graceful shutdown
def signal_handler(signum: Any, _frame: Any) -> None:
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
        host="0.0.0.0",  # noqa: S104
        port=int(os.getenv("PORT", "8000")),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        reload=os.getenv("ENVIRONMENT", "development") == "development",
    )
