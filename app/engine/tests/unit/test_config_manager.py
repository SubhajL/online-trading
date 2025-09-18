"""
Unit tests for configuration manager.
Following T-3: Pure logic unit tests without external dependencies.
Following T-4: Avoiding heavy mocking.
"""

import os
import pytest
import json
from decimal import Decimal
from typing import Any, Dict

from app.engine.core.config_manager import (
    load_config_from_env,
    validate_config_schema,
    merge_config_sources,
    get_config_for_environment,
    watch_config_changes,
    export_config_schema,
    ConfigError,
    Config
)


class TestLoadConfigFromEnv:
    """Tests for environment variable parsing."""

    def test_env_var_parsing_types(self):
        """Correctly parses int, float, bool, list."""
        # Set environment variables
        os.environ['TRADING_MAX_CONNECTIONS'] = '50'
        os.environ['TRADING_RISK_LIMIT'] = '0.02'
        os.environ['TRADING_DEBUG_MODE'] = 'true'
        os.environ['TRADING_SYMBOLS'] = 'BTCUSDT,ETHUSDT,BNBUSDT'
        
        config = load_config_from_env()
        
        assert config.max_connections == 50
        assert config.risk_limit == 0.02
        assert config.debug_mode is True
        assert config.symbols == ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
        
        # Cleanup
        for key in ['TRADING_MAX_CONNECTIONS', 'TRADING_RISK_LIMIT', 
                    'TRADING_DEBUG_MODE', 'TRADING_SYMBOLS']:
            os.environ.pop(key, None)

    def test_env_var_defaults(self):
        """Uses defaults when env vars not set."""
        # Clear any existing env vars
        for key in list(os.environ.keys()):
            if key.startswith('TRADING_'):
                del os.environ[key]
        
        config = load_config_from_env()
        
        # Should have sensible defaults
        assert config.max_connections > 0
        assert 0 < config.risk_limit <= 1
        assert isinstance(config.debug_mode, bool)

    def test_env_var_validation(self):
        """Validates env var values."""
        os.environ['TRADING_MAX_CONNECTIONS'] = '-5'  # Invalid negative
        
        with pytest.raises(ConfigError) as exc:
            load_config_from_env()
        
        assert 'max_connections must be positive' in str(exc.value)
        
        os.environ.pop('TRADING_MAX_CONNECTIONS', None)


class TestValidateConfigSchema:
    """Tests for config schema validation."""

    def test_required_fields_validation(self):
        """Fails fast on missing critical config."""
        invalid_config = {
            'max_connections': 10
            # Missing required fields
        }
        
        with pytest.raises(ConfigError) as exc:
            validate_config_schema(invalid_config)
        
        assert 'required' in str(exc.value).lower()

    def test_type_validation(self):
        """Validates field types."""
        invalid_config = {
            'max_connections': 'not_a_number',  # Should be int
            'risk_limit': 0.02,
            'database_url': 'postgresql://localhost',
            'redis_url': 'redis://localhost'
        }
        
        with pytest.raises(ConfigError) as exc:
            validate_config_schema(invalid_config)
        
        assert 'type' in str(exc.value).lower()

    def test_range_validation(self):
        """Validates value ranges."""
        invalid_config = {
            'max_connections': 10,
            'risk_limit': 1.5,  # Should be <= 1.0
            'database_url': 'postgresql://localhost',
            'redis_url': 'redis://localhost'
        }
        
        with pytest.raises(ConfigError) as exc:
            validate_config_schema(invalid_config)
        
        assert 'risk_limit' in str(exc.value)

    def test_production_config_constraints(self):
        """Enforces stricter limits in prod."""
        prod_config = {
            'environment': 'production',
            'max_connections': 5,  # Too low for production
            'risk_limit': 0.5,  # Too high for production  
            'debug_mode': True,  # Not allowed in production
            'database_url': 'postgresql://localhost',
            'redis_url': 'redis://localhost'
        }
        
        with pytest.raises(ConfigError) as exc:
            validate_config_schema(prod_config)
        
        assert 'production' in str(exc.value).lower()


class TestMergeConfigSources:
    """Tests for config source merging."""

    def test_config_merge_precedence(self):
        """Env vars override files override defaults."""
        defaults = {
            'max_connections': 10,
            'risk_limit': 0.01,
            'debug_mode': False
        }
        
        file_config = {
            'max_connections': 20,
            'risk_limit': 0.02
        }
        
        env_config = {
            'max_connections': 30
        }
        
        merged = merge_config_sources(defaults, file_config, env_config)
        
        assert merged['max_connections'] == 30  # From env
        assert merged['risk_limit'] == 0.02  # From file
        assert merged['debug_mode'] is False  # From defaults

    def test_nested_config_merge(self):
        """Correctly merges nested config objects."""
        defaults = {
            'database': {
                'host': 'localhost',
                'port': 5432,
                'pool_size': 10
            }
        }
        
        overrides = {
            'database': {
                'host': 'prod.db.example.com',
                'pool_size': 50
            }
        }
        
        merged = merge_config_sources(defaults, overrides)
        
        assert merged['database']['host'] == 'prod.db.example.com'
        assert merged['database']['port'] == 5432  # Preserved from defaults
        assert merged['database']['pool_size'] == 50


class TestGetConfigForEnvironment:
    """Tests for environment-specific config."""

    def test_development_config(self):
        """Returns relaxed config for development."""
        config = get_config_for_environment('development')
        
        assert config.debug_mode is True
        assert config.risk_limit <= 0.05  # Allow higher risk in dev
        assert config.max_connections >= 5  # Lower requirements

    def test_production_config(self):
        """Returns strict config for production."""
        config = get_config_for_environment('production')
        
        assert config.debug_mode is False
        assert config.risk_limit <= 0.02  # Conservative risk
        assert config.max_connections >= 20  # Higher capacity
        assert config.database_url != 'postgresql://localhost'  # Not local

    def test_staging_config(self):
        """Returns production-like config for staging."""
        config = get_config_for_environment('staging')
        
        assert config.debug_mode is False
        assert config.risk_limit <= 0.03  # Slightly more relaxed than prod
        assert config.max_connections >= 15


class TestWatchConfigChanges:
    """Tests for config change monitoring."""

    def test_config_reload_atomic(self):
        """No partial updates during reload."""
        original_config = load_config_from_env()
        
        # Start watching (in practice would be async)
        watcher = watch_config_changes(original_config)
        
        # Simulate config change
        os.environ['TRADING_MAX_CONNECTIONS'] = '100'
        os.environ['TRADING_RISK_LIMIT'] = '0.001'
        
        # Reload should be atomic
        new_config = watcher.reload()
        
        # Either all changes applied or none
        if new_config.max_connections == 100:
            assert new_config.risk_limit == 0.001
        else:
            assert new_config.max_connections == original_config.max_connections
            assert new_config.risk_limit == original_config.risk_limit
        
        # Cleanup
        os.environ.pop('TRADING_MAX_CONNECTIONS', None)
        os.environ.pop('TRADING_RISK_LIMIT', None)

    def test_config_validation_on_reload(self):
        """Validates config on reload."""
        original_config = load_config_from_env()
        watcher = watch_config_changes(original_config)
        
        # Set invalid config
        os.environ['TRADING_RISK_LIMIT'] = '2.0'  # Too high
        
        # Reload should fail validation
        with pytest.raises(ConfigError):
            watcher.reload()
        
        # Original config should be unchanged
        assert watcher.current_config == original_config
        
        os.environ.pop('TRADING_RISK_LIMIT', None)


class TestExportConfigSchema:
    """Tests for schema export."""

    def test_schema_export_complete(self):
        """All config fields documented."""
        schema = export_config_schema()
        
        # Should be valid JSON schema
        assert schema['$schema'] == 'http://json-schema.org/draft-07/schema#'
        assert 'properties' in schema
        assert 'required' in schema
        
        # Check key fields are documented
        properties = schema['properties']
        assert 'max_connections' in properties
        assert 'risk_limit' in properties
        assert 'database_url' in properties
        
        # Each property should have type and description
        for prop_name, prop_schema in properties.items():
            assert 'type' in prop_schema, f"{prop_name} missing type"
            assert 'description' in prop_schema, f"{prop_name} missing description"

    def test_schema_includes_constraints(self):
        """Schema includes validation constraints."""
        schema = export_config_schema()
        
        # Risk limit should have range
        risk_limit_schema = schema['properties']['risk_limit']
        assert 'minimum' in risk_limit_schema
        assert 'maximum' in risk_limit_schema
        assert risk_limit_schema['minimum'] > 0
        assert risk_limit_schema['maximum'] <= 1
        
        # Max connections should have minimum
        connections_schema = schema['properties']['max_connections']
        assert 'minimum' in connections_schema
        assert connections_schema['minimum'] > 0

    def test_schema_includes_examples(self):
        """Schema includes example values."""
        schema = export_config_schema()
        
        # Should have examples section
        assert 'examples' in schema
        assert len(schema['examples']) > 0
        
        # Example should be valid according to schema
        example = schema['examples'][0]
        assert 'max_connections' in example
        assert 'risk_limit' in example