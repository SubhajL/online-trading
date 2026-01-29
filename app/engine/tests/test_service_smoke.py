"""
Service smoke tests to verify basic instantiation and startup.

These tests use minimal mocks to verify services can be created
without runtime errors.
"""

from decimal import Decimal
from unittest.mock import Mock, AsyncMock

import pytest

from app.engine.bus import create_event_bus, set_event_bus


def setup_event_bus():
    """Set up event bus for services that need it."""
    bus = create_event_bus()
    set_event_bus(bus)
    return bus


class TestDecisionEngineSmoke:
    """Test DecisionEngine can be instantiated."""

    def test_decision_engine_instantiates(self):
        """DecisionEngine creates without runtime errors using mock config."""
        from app.engine.decision.service import DecisionEngine, RiskManager
        from app.engine.models import RiskParameters

        # Create minimal risk parameters
        risk_params = RiskParameters(
            max_position_size=Decimal("0.1"),  # 10% max position
            max_daily_loss=Decimal("0.02"),     # 2% max daily loss
            max_drawdown=Decimal("0.10"),       # 10% max drawdown
            risk_per_trade=Decimal("0.02"),     # 2% per trade
            max_correlation=Decimal("0.7"),     # 70% max correlation
            max_open_positions=3,
            max_total_exposure_leverage=Decimal("3"),
            max_symbol_exposure_pct=Decimal("0.25"),
            max_position_notional_pct=Decimal("0.10"),
            risk_data_max_age_seconds=120,
            drawdown_lookback_days=30,
            allowed_symbols=["BTCUSDT", "ETHUSDT"]
        )

        # Create mock dependencies
        risk_manager = RiskManager(risk_params)
        router_client = Mock()  # Mock the router client

        # Should instantiate without errors
        engine = DecisionEngine(risk_manager, router_client)
        assert engine is not None
        assert engine.risk_manager is risk_manager
        assert engine.router_client is router_client


class TestFeatureServiceSmoke:
    """Test FeatureService can be instantiated."""

    def test_feature_service_instantiates(self):
        """FeatureService creates with minimal valid configuration."""
        from app.engine.features.feature_service import FeatureService

        # Set up event bus
        setup_event_bus()

        # Should instantiate without errors
        service = FeatureService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_feature_service_starts(self):
        """FeatureService can start without errors."""
        from app.engine.features.feature_service import FeatureService

        # Set up event bus
        setup_event_bus()

        service = FeatureService()

        # Mock the event bus subscription
        service.subscribe = AsyncMock()

        # Should start without errors
        await service.start()
        assert service._running is True


class TestSMCServiceSmoke:
    """Test SMCService can be instantiated."""

    def test_smc_service_instantiates(self):
        """SMCService initializes with required dependencies mocked."""
        from app.engine.smc.smc_service import SMCService

        # Set up event bus
        setup_event_bus()

        # Should instantiate without errors
        service = SMCService()
        assert service is not None


class TestEventBusSmoke:
    """Test EventBus singleton creation."""

    def test_event_bus_creation(self):
        """EventBus singleton creates and accepts subscriptions."""
        # Use setup function which handles singleton
        bus = setup_event_bus()
        assert bus is not None

        # Test subscription works without errors
        test_callback = Mock()

        # Just verify subscribe doesn't throw
        # (internal structure is not part of public API)
        try:
            bus.subscribe("test.event", test_callback)
            subscription_works = True
        except Exception:
            subscription_works = False

        assert subscription_works


class TestIngestServiceSmoke:
    """Test IngestService can be instantiated."""

    def test_ingest_service_instantiates(self):
        """IngestService creates with minimal configuration."""
        from app.engine.ingest.ingest_service import IngestService
        from app.engine.models import BinanceConfig

        # Set up event bus
        setup_event_bus()

        # Create minimal config
        config = {
            "api_key": "test_key",
            "api_secret": "test_secret",
            "testnet": True
        }
        symbols = ["BTCUSDT"]
        from app.engine.models import TimeFrame
        timeframes = [TimeFrame.M15]

        # Should instantiate without errors
        service = IngestService(
            binance_config=config,
            symbols=symbols,
            timeframes=timeframes
        )
        assert service is not None
        # Just verify the service was created without checking internals


class TestAdapterSmoke:
    """Test adapters can be instantiated."""

    @pytest.mark.asyncio
    async def test_redis_adapter_creation(self):
        """RedisAdapter creates with mock client."""
        from app.engine.adapters import RedisAdapter

        # Create with individual parameters (actual connection tested separately)
        adapter = RedisAdapter(
            host="localhost",
            port=6379,
            password=None
        )
        assert adapter is not None

    @pytest.mark.asyncio
    async def test_database_adapter_creation(self):
        """DatabaseAdapter creates with mock pool."""
        from app.engine.adapters import TimescaleDBAdapter

        # Create with individual parameters (actual connection tested separately)
        adapter = TimescaleDBAdapter(
            host="localhost",
            port=5432,
            database="test_db",
            username="test_user",
            password="test_pass"
        )
        assert adapter is not None

    def test_router_client_creation(self):
        """RouterHTTPClient creates with configuration."""
        from app.engine.adapters import RouterHTTPClient

        # Should create with base URL
        client = RouterHTTPClient("http://localhost:8001")
        assert client is not None
        assert client.base_url == "http://localhost:8001"
