"""
Test basic module imports to ensure all engine components are importable.

These tests verify Python import mechanics work before any initialization.
Following TDD, these tests document the expected module structure.
"""

import sys
from pathlib import Path

import pytest


class TestCoreModuleImports:
    """Verify all core engine modules can be imported without errors."""

    def test_main_module_imports(self):
        """Main module and FastAPI app should be importable."""
        from app.engine import main
        assert hasattr(main, 'app')  # FastAPI application instance

    def test_event_bus_imports(self):
        """Event bus and related functionality should be importable."""
        from app.engine.bus import EventBus, set_event_bus
        assert EventBus is not None
        assert callable(set_event_bus)

    def test_model_imports(self):
        """All model/type definitions should be importable."""
        from app.engine.models import (
            BinanceConfig,
            EngineConfig,
            DatabaseConfig,
            RedisConfig
        )
        # Verify these are proper types/classes
        assert all(isinstance(cls, type) for cls in [
            BinanceConfig, EngineConfig,
            DatabaseConfig, RedisConfig
        ])


class TestServiceImports:
    """Check that expected service classes exist with correct names."""

    def test_decision_service_imports(self):
        """Decision engine functions and risk components should be importable."""
        from app.engine.decision.engine import (
            generate_decision,
            fuse_signals,
            apply_trading_guards
        )
        assert callable(generate_decision)
        assert callable(fuse_signals)
        assert callable(apply_trading_guards)

        from app.engine.decision.risk_guards import RiskGuardManager
        assert RiskGuardManager is not None

    def test_feature_service_imports(self):
        """Feature service and indicators should be importable."""
        from app.engine.features.feature_service import FeatureService
        from app.engine.features.indicators import (
            calculate_ema,
            calculate_rsi,
            calculate_macd,
            calculate_bollinger_bands
        )
        assert FeatureService is not None
        assert all(callable(fn) for fn in [
            calculate_ema, calculate_rsi, calculate_macd,
            calculate_bollinger_bands
        ])

    def test_ingest_service_imports(self):
        """Ingest service and Binance connectors should be importable."""
        from app.engine.ingest.ingest_service import IngestService
        from app.engine.ingest.binance_ws import BinanceWebSocketClient
        from app.engine.ingest.binance_rest import BinanceRestClient

        assert all(cls is not None for cls in [
            IngestService, BinanceWebSocketClient, BinanceRestClient
        ])

    def test_smc_service_imports(self):
        """SMC service and analysis components should be importable."""
        from app.engine.smc.smc_service import SMCService
        from app.engine.smc.pivot_detector import PivotDetector
        from app.engine.smc.zone_identifier import ZoneIdentifier
        from app.engine.smc.engine import SMCEngine

        assert all(cls is not None for cls in [
            SMCService, PivotDetector, ZoneIdentifier, SMCEngine
        ])

    def test_retest_service_imports(self):
        """Retest analysis components should be importable."""
        from app.engine.retest.engine import RetestEngine
        from app.engine.retest.retest_analyzer import RetestAnalyzer

        assert RetestEngine is not None
        assert RetestAnalyzer is not None


class TestAdapterImports:
    """Ensure database, cache, and router adapters import correctly."""

    def test_database_adapter_imports(self):
        """TimescaleDB adapter should be importable."""
        from app.engine.adapters import TimescaleDBAdapter
        from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter as TDB

        assert TimescaleDBAdapter is not None
        assert TDB is not None

    def test_cache_adapter_imports(self):
        """Redis adapter should be importable."""
        from app.engine.adapters import RedisAdapter
        from app.engine.adapters.redis.redis_adapter import RedisAdapter as RA

        assert RedisAdapter is not None
        assert RA is not None

    def test_router_client_imports(self):
        """Router HTTP client should be importable."""
        from app.engine.adapters import RouterHTTPClient
        from app.engine.adapters.router_client.http_client import RouterHTTPClient as RHC

        assert RouterHTTPClient is not None
        assert RHC is not None


class TestTypeDefinitions:
    """Verify all type definitions and models can be imported."""

    def test_event_type_imports(self):
        """All event types should be importable."""
        from app.engine.models import (
            BaseEvent,
            CandleUpdateEvent,
            FeaturesCalculatedEvent,
            SMCSignalEvent,
            RetestSignalEvent,
            TradingDecisionEvent,
            OrderPlacedEvent,
            OrderFilledEvent,
            EventType
        )

        # Verify these are proper types
        assert all(isinstance(cls, type) for cls in [
            BaseEvent, CandleUpdateEvent, FeaturesCalculatedEvent,
            SMCSignalEvent, RetestSignalEvent, TradingDecisionEvent,
            OrderPlacedEvent, OrderFilledEvent
        ])

    def test_config_type_imports(self):
        """Configuration types should be properly defined."""
        from app.engine.decision.risk_guards import RiskGuardConfig
        from app.engine.models import EngineConfig, BinanceConfig

        assert RiskGuardConfig is not None
        assert all(isinstance(cls, type) for cls in [
            EngineConfig, BinanceConfig
        ])


class TestImportIntegrity:
    """Test for import issues like circular dependencies."""

    def test_no_circular_imports(self):
        """Verify module graph is acyclic by importing in different orders."""
        # First order - should not raise ImportError
        try:
            from app.engine.bus import EventBus
            from app.engine.decision.engine import generate_decision
            first_import_success = True
        except ImportError:
            first_import_success = False

        # Clear module cache
        modules_to_clear = [m for m in sys.modules if m.startswith('app.engine')]
        for module in modules_to_clear:
            del sys.modules[module]

        # Reverse order should also work without ImportError
        try:
            from app.engine.decision.engine import generate_decision
            from app.engine.bus import EventBus
            second_import_success = True
        except ImportError:
            second_import_success = False

        assert first_import_success, "First import order failed"
        assert second_import_success, "Second import order failed"