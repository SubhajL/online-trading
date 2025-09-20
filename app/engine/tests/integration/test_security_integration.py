"""
Integration tests for security module with EventBus system.
Tests secure configuration, validation, and secret management.
"""

import os
import pytest
from unittest.mock import patch
import tempfile
from pathlib import Path

from app.engine.core.event_bus_factory import (
    EventBusFactory,
    EventBusConfig,
    InvalidConfigurationError,
)
from app.engine.core.security import (
    SecurityLevel,
    SecureConfig,
    SecurityGuard,
    EnvironmentValidator,
    ValidationRule,
    SecretManager,
    validate_environment,
)


class TestSecurityIntegration:
    @pytest.mark.asyncio
    async def test_eventbus_with_secure_configuration(self):
        """Test EventBus creation with secure configuration."""
        factory = EventBusFactory()

        # Set up test environment
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "development",
                "EVENT_BUS_MAX_QUEUE_SIZE": "5000",
                "EVENT_BUS_NUM_WORKERS": "2",
            },
        ):
            event_bus = factory.create_secure_event_bus(SecurityLevel.DEVELOPMENT)

            assert event_bus is not None
            assert event_bus._config.max_queue_size == 5000
            assert event_bus._config.num_workers == 2

            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_eventbus_secure_config_validation_in_production(self):
        """Test that production mode validates required security variables."""
        factory = EventBusFactory()

        # In production without required variables, should get low security score
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            # Create secure config and check validation
            secure_config = SecureConfig(SecurityLevel.PRODUCTION)
            audit = secure_config.audit()

            # Should have missing required variables for production
            assert len(audit.missing_required) > 0

            # The specific missing variables should be critical ones
            assert (
                "DATABASE_PASSWORD" in audit.missing_required
                or "JWT_SECRET" in audit.missing_required
            )

    @pytest.mark.asyncio
    async def test_secure_config_with_encrypted_secrets(self):
        """Test secure configuration with encrypted secrets."""
        secure_config = SecureConfig(SecurityLevel.DEVELOPMENT, enable_encryption=True)

        # Set a secret with encryption
        secure_config.set_secret("API_KEY", "my_secret_api_key_123", encrypt=True)

        # Get should decrypt automatically
        value = secure_config.get_secret("API_KEY")
        assert value == "my_secret_api_key_123"

        # Verify it's stored encrypted
        raw_value = os.environ.get("API_KEY")
        assert raw_value.startswith("enc:")

    def test_environment_validation_with_custom_rules(self):
        """Test custom validation rules for application-specific variables."""
        validator = EnvironmentValidator(SecurityLevel.PRODUCTION)

        # Add custom trading-specific rules
        validator.add_rule(
            ValidationRule(
                name="BINANCE_API_KEY",
                pattern=r"^[A-Za-z0-9]{64}$",
                required=True,
                sensitive=True,
            )
        )

        validator.add_rule(
            ValidationRule(
                name="MAX_POSITION_SIZE", pattern=r"^\d+(\.\d+)?$", required=True
            )
        )

        validator.add_rule(
            ValidationRule(
                name="RISK_PERCENTAGE",
                pattern=r"^[0-9]{1,2}(\.[0-9]+)?$",
                required=True,
                custom_validator=lambda v: 0 < float(v) <= 10,
                error_message="Risk percentage must be between 0 and 10",
            )
        )

        # Test with valid values
        with patch.dict(
            os.environ,
            {
                "BINANCE_API_KEY": "a" * 64,
                "MAX_POSITION_SIZE": "1000.50",
                "RISK_PERCENTAGE": "2.5",
            },
        ):
            audit = validator.validate_all()
            assert (
                len(
                    [
                        v
                        for v in audit.failed_validations
                        if v.variable_name
                        in ["BINANCE_API_KEY", "MAX_POSITION_SIZE", "RISK_PERCENTAGE"]
                    ]
                )
                == 0
            )

        # Test with invalid risk percentage
        with patch.dict(
            os.environ,
            {
                "BINANCE_API_KEY": "a" * 64,
                "MAX_POSITION_SIZE": "1000",
                "RISK_PERCENTAGE": "15",  # Too high
            },
        ):
            audit = validator.validate_all()
            risk_failures = [
                v
                for v in audit.failed_validations
                if v.variable_name == "RISK_PERCENTAGE"
            ]
            assert len(risk_failures) > 0

    def test_security_guard_monitors_configuration(self):
        """Test security guard monitoring and reporting."""
        secure_config = SecureConfig(SecurityLevel.PRODUCTION)
        guard = SecurityGuard(secure_config)

        # Add custom validation rules
        secure_config.validator.add_rule(
            ValidationRule(name="DATABASE_URL", required=True, sensitive=True)
        )

        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "ENFORCE_HTTPS": "true",
                "TLS_MIN_VERSION": "1.2",
            },
        ):
            # Check secure communication
            result = guard.check_secure_communication()
            assert result is True

            # Get security report
            report = guard.get_security_report()

            assert report["security_level"] == "production"
            assert "audit_results" in report
            assert "recommendations" in report

    @pytest.mark.asyncio
    async def test_eventbus_config_from_secure_config(self):
        """Test EventBusConfig loading from SecureConfig."""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "development",
                "EVENT_BUS_MAX_QUEUE_SIZE": "8000",
                "EVENT_BUS_NUM_WORKERS": "6",
                "EVENT_BUS_ENABLE_PERSISTENCE": "true",
                "SUBSCRIPTION_MAX_COUNT": "500",
                "PROCESSING_MAX_TIME": "45.5",
                "CIRCUIT_BREAKER_ENABLED": "false",
            },
        ):
            secure_config = SecureConfig(SecurityLevel.DEVELOPMENT)
            config = EventBusConfig.from_secure_config(secure_config)

            assert config.max_queue_size == 8000
            assert config.num_workers == 6
            assert config.enable_persistence is True
            assert config.subscription_config["max_subscriptions"] == 500
            assert config.processing_config["max_processing_time_seconds"] == 45.5
            assert config.processing_config["circuit_breaker_enabled"] is False

    def test_masked_configuration_export(self):
        """Test that sensitive configuration is masked for export."""
        secure_config = SecureConfig()

        with patch.dict(
            os.environ,
            {
                "DATABASE_PASSWORD": "super_secret_123",
                "API_KEY": "abcdef123456",
                "PUBLIC_ENDPOINT": "https://api.example.com",
                "LOG_LEVEL": "INFO",
            },
        ):
            # Mark some as sensitive
            secure_config.get("DATABASE_PASSWORD", sensitive=True)
            secure_config.get("API_KEY", sensitive=True)
            secure_config.get("PUBLIC_ENDPOINT")
            secure_config.get("LOG_LEVEL")

            # Export safe config
            safe_config = secure_config.export_safe_config()

            # Sensitive values should be redacted
            assert safe_config["DATABASE_PASSWORD"] == "***REDACTED***"
            assert safe_config["API_KEY"] == "***REDACTED***"

            # Non-sensitive values should be visible
            assert safe_config["PUBLIC_ENDPOINT"] == "https://api.example.com"
            assert safe_config["LOG_LEVEL"] == "INFO"

    def test_secret_rotation_workflow(self):
        """Test secret rotation and re-encryption workflow."""
        # Create initial secret manager
        manager1 = SecretManager(master_key="old_master_key")

        # Encrypt some data
        encrypted_data = manager1.encrypt("sensitive_data")

        # Decrypt with same key works
        decrypted = manager1.decrypt(encrypted_data)
        assert decrypted == "sensitive_data"

        # Create new secret manager with new key
        manager2 = SecretManager(master_key="new_master_key")

        # Can't decrypt old data with new key
        with pytest.raises(Exception):
            manager2.decrypt(encrypted_data)

        # Re-encrypt with new key
        re_encrypted = manager2.encrypt(decrypted)

        # Can decrypt with new key
        new_decrypted = manager2.decrypt(re_encrypted)
        assert new_decrypted == "sensitive_data"

    def test_file_permission_security_check(self):
        """Test file permission security validation."""
        secure_config = SecureConfig()
        guard = SecurityGuard(secure_config)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".key") as tmp:
            tmp_path = Path(tmp.name)

            try:
                # Test secure permissions (owner-only)
                tmp_path.chmod(0o600)
                result = guard.check_file_permissions(tmp_path)
                assert result is True
                assert len(guard.violations) == 0

                # Test insecure permissions (world-readable)
                guard.violations.clear()
                tmp_path.chmod(0o644)
                result = guard.check_file_permissions(tmp_path)
                assert result is False
                assert len(guard.violations) > 0

                violation = guard.violations[0]
                assert violation["type"] == "file_permissions"
                assert "world-readable" in violation["message"]

            finally:
                tmp_path.unlink()

    @pytest.mark.asyncio
    async def test_comprehensive_security_audit(self):
        """Test comprehensive security audit of EventBus configuration."""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "staging",
                # Valid configuration
                "EVENT_BUS_MAX_QUEUE_SIZE": "10000",
                "EVENT_BUS_NUM_WORKERS": "4",
                # Weak secrets (for testing)
                "DATABASE_PASSWORD": "password123",  # Weak
                "JWT_SECRET": "a" * 32,  # Meets length but low entropy
                # Missing required (will depend on rules)
                # "VAULT_TOKEN": missing
            },
        ):
            secure_config = SecureConfig(SecurityLevel.STAGING)

            # Perform audit
            audit = validate_environment()

            # Check audit results
            assert audit.total_variables > 0
            assert isinstance(audit.security_score, float)
            assert 0 <= audit.security_score <= 1

            # Generate recommendations
            guard = SecurityGuard(secure_config)
            report = guard.get_security_report()

            assert "recommendations" in report
            assert (
                len(report["recommendations"]) > 0
            )  # Should have some recommendations

    @pytest.mark.asyncio
    async def test_eventbus_lifecycle_with_security(self):
        """Test complete EventBus lifecycle with security features."""
        factory = EventBusFactory()

        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "development",
                "EVENT_BUS_MAX_QUEUE_SIZE": "1000",
                "EVENT_BUS_NUM_WORKERS": "2",
                "LOG_LEVEL": "INFO",
            },
        ):
            # Create secure EventBus
            event_bus = factory.create_secure_event_bus()

            # Start EventBus
            await event_bus.start()

            # Verify it's running
            metrics = await event_bus.get_metrics()
            assert metrics["is_running"] is True

            # Test subscription with secure config
            async def test_handler(event):
                pass

            sub_id = await event_bus.subscribe("test", test_handler)
            assert sub_id is not None

            # Stop EventBus
            await event_bus.stop()

            # Verify stopped
            metrics = await event_bus.get_metrics()
            assert metrics["is_running"] is False
