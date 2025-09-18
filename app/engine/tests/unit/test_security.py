"""
Unit tests for security module.
Written first following TDD principles.
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
from datetime import datetime

from app.engine.core.security import (
    SecurityLevel,
    ValidationError,
    SecurityError,
    ValidationRule,
    ValidationResult,
    SecurityAudit,
    EnvironmentValidator,
    SecretManager,
    SecureConfig,
    SecurityGuard,
    validate_environment,
    get_secure_config,
    get_secret
)


class TestValidationRule:
    def test_validation_rule_creation(self):
        rule = ValidationRule(
            name="TEST_VAR",
            pattern=r'^\d+$',
            min_length=5,
            max_length=10,
            required=True,
            sensitive=True
        )

        assert rule.name == "TEST_VAR"
        assert rule.pattern == r'^\d+$'
        assert rule.min_length == 5
        assert rule.max_length == 10
        assert rule.required is True
        assert rule.sensitive is True


class TestEnvironmentValidator:
    def test_validator_initialization_with_security_level(self):
        validator = EnvironmentValidator(SecurityLevel.PRODUCTION)
        assert validator.security_level == SecurityLevel.PRODUCTION
        assert len(validator.rules) > 0  # Should have default rules

    def test_validate_required_variable_missing(self):
        validator = EnvironmentValidator()
        rule = ValidationRule(name="REQUIRED_VAR", required=True)
        validator.add_rule(rule)

        result = validator.validate_variable("REQUIRED_VAR", None)

        assert result.is_valid is False
        assert "Required variable" in result.error
        assert result.suggestion is not None

    def test_validate_pattern_matching(self):
        validator = EnvironmentValidator()
        rule = ValidationRule(
            name="PORT_VAR",
            pattern=r'^\d{4}$'
        )
        validator.add_rule(rule)

        # Valid port
        result = validator.validate_variable("PORT_VAR", "8080")
        assert result.is_valid is True

        # Invalid port
        result = validator.validate_variable("PORT_VAR", "abc")
        assert result.is_valid is False
        assert "does not match required pattern" in result.error

    def test_validate_length_constraints(self):
        validator = EnvironmentValidator()
        rule = ValidationRule(
            name="PASSWORD",
            min_length=8,
            max_length=20
        )
        validator.add_rule(rule)

        # Too short
        result = validator.validate_variable("PASSWORD", "short")
        assert result.is_valid is False
        assert "too short" in result.error

        # Valid length
        result = validator.validate_variable("PASSWORD", "validpass123")
        assert result.is_valid is True

        # Too long
        result = validator.validate_variable("PASSWORD", "a" * 25)
        assert result.is_valid is False
        assert "too long" in result.error

    def test_validate_allowed_values(self):
        validator = EnvironmentValidator()
        rule = ValidationRule(
            name="LOG_LEVEL",
            allowed_values=["DEBUG", "INFO", "ERROR"]
        )
        validator.add_rule(rule)

        # Valid value
        result = validator.validate_variable("LOG_LEVEL", "INFO")
        assert result.is_valid is True

        # Invalid value
        result = validator.validate_variable("LOG_LEVEL", "TRACE")
        assert result.is_valid is False
        assert "invalid value" in result.error

    def test_custom_validator(self):
        validator = EnvironmentValidator()

        def is_even(value: str) -> bool:
            try:
                return int(value) % 2 == 0
            except ValueError:
                return False

        rule = ValidationRule(
            name="EVEN_NUMBER",
            custom_validator=is_even,
            error_message="Value must be an even number"
        )
        validator.add_rule(rule)

        # Valid
        result = validator.validate_variable("EVEN_NUMBER", "4")
        assert result.is_valid is True

        # Invalid
        result = validator.validate_variable("EVEN_NUMBER", "3")
        assert result.is_valid is False
        assert "even number" in result.error

    def test_validate_all_with_environment_variables(self):
        validator = EnvironmentValidator()
        # Clear default rules first
        validator.rules.clear()

        validator.add_rule(ValidationRule(name="TEST_VAR1", required=True))
        validator.add_rule(ValidationRule(name="TEST_VAR2", min_length=5))

        with patch.dict(os.environ, {"TEST_VAR1": "value1", "TEST_VAR2": "12345"}):
            audit = validator.validate_all()

            assert audit.total_variables == 2
            assert audit.validated_variables == 2
            assert len(audit.failed_validations) == 0
            assert audit.security_score > 0

    def test_password_strength_validation(self):
        validator = EnvironmentValidator(SecurityLevel.PRODUCTION)

        # Weak password
        result = validator._validate_password_strength("weak")
        assert result is False

        # Strong password
        result = validator._validate_password_strength("StrongP@ssw0rd123")
        assert result is True

    def test_jwt_secret_validation(self):
        validator = EnvironmentValidator()

        # Weak secret
        result = validator._validate_jwt_secret("secret123")
        assert result is False

        # Strong secret
        result = validator._validate_jwt_secret("a" * 32 + "B1@#$%")
        assert result is True


class TestSecretManager:
    def test_secret_manager_initialization(self):
        manager = SecretManager(master_key="test_master_key_32_bytes_long!!!")
        assert manager.master_key is not None
        assert manager._cipher is not None

    def test_encrypt_decrypt_cycle(self):
        manager = SecretManager(master_key="test_master_key_32_bytes_long!!!")

        original = "sensitive_data_123"
        encrypted = manager.encrypt(original)

        assert encrypted != original
        assert len(encrypted) > 0

        decrypted = manager.decrypt(encrypted)
        assert decrypted == original

    def test_decrypt_invalid_data_raises_error(self):
        manager = SecretManager(master_key="test_master_key_32_bytes_long!!!")

        with pytest.raises(SecurityError):
            manager.decrypt("invalid_encrypted_data")

    def test_hash_value_with_salt(self):
        manager = SecretManager()

        value = "password123"
        hashed = manager.hash_value(value)

        assert "$" in hashed  # Contains salt separator
        assert len(hashed) > 32  # Has salt and hash

    def test_verify_hash(self):
        manager = SecretManager()

        value = "password123"
        hashed = manager.hash_value(value)

        # Correct password
        assert manager.verify_hash(value, hashed) is True

        # Wrong password
        assert manager.verify_hash("wrong_password", hashed) is False


class TestSecureConfig:
    def test_secure_config_initialization(self):
        config = SecureConfig(SecurityLevel.PRODUCTION, enable_encryption=True)

        assert config.security_level == SecurityLevel.PRODUCTION
        assert config.validator is not None
        assert config.secret_manager is not None

    def test_get_configuration_value(self):
        config = SecureConfig()

        with patch.dict(os.environ, {"TEST_KEY": "test_value"}):
            value = config.get("TEST_KEY")
            assert value == "test_value"

            # Should be cached
            assert "TEST_KEY" in config._cached_values

    def test_get_with_default_value(self):
        config = SecureConfig()

        value = config.get("MISSING_KEY", default="default_value")
        assert value == "default_value"

    def test_get_secret_with_encryption(self):
        config = SecureConfig(enable_encryption=True)

        # Set encrypted secret
        config.set_secret("SECRET_KEY", "secret_value", encrypt=True)

        # Get should decrypt
        value = config.get_secret("SECRET_KEY")
        assert value == "secret_value"

    def test_get_secret_without_encryption_prefix(self):
        config = SecureConfig(enable_encryption=True)

        with patch.dict(os.environ, {"PLAIN_SECRET": "plain_value"}):
            value = config.get_secret("PLAIN_SECRET")
            assert value == "plain_value"

    def test_validation_error_in_production(self):
        config = SecureConfig(SecurityLevel.PRODUCTION)
        config.validator.add_rule(
            ValidationRule(name="INVALID_VAR", pattern=r'^\d+$')
        )

        with patch.dict(os.environ, {"INVALID_VAR": "not_a_number"}):
            with pytest.raises(ValidationError):
                config.get("INVALID_VAR")

    def test_validation_warning_in_development(self):
        config = SecureConfig(SecurityLevel.DEVELOPMENT)
        config.validator.add_rule(
            ValidationRule(name="INVALID_VAR", pattern=r'^\d+$')
        )

        with patch.dict(os.environ, {"INVALID_VAR": "not_a_number"}):
            # Should not raise, just warn
            value = config.get("INVALID_VAR")
            assert value == "not_a_number"

    def test_mask_sensitive_values(self):
        config = SecureConfig()
        config._sensitive_keys.add("API_KEY")

        data = {
            "API_KEY": "secret123456",
            "NORMAL_KEY": "normal_value",
            "PASSWORD": "pass123"  # Auto-detected as sensitive
        }

        masked = config.mask_sensitive_values(data)

        assert masked["API_KEY"] == "se***56"
        assert masked["NORMAL_KEY"] == "normal_value"
        assert masked["PASSWORD"] == "pa***23"

    def test_export_safe_config(self):
        config = SecureConfig()
        config._sensitive_keys.add("SECRET")

        with patch.dict(os.environ, {
            "SECRET": "secret_value",
            "PUBLIC": "public_value"
        }):
            config.get("SECRET", sensitive=True)
            config.get("PUBLIC")

            safe_config = config.export_safe_config()

            assert safe_config["SECRET"] == "***REDACTED***"
            assert safe_config["PUBLIC"] == "public_value"


class TestSecurityGuard:
    def test_security_guard_initialization(self):
        config = SecureConfig()
        guard = SecurityGuard(config)

        assert guard.config is config
        assert guard.violations == []
        assert isinstance(guard.start_time, datetime)

    def test_check_file_permissions(self):
        config = SecureConfig()
        guard = SecurityGuard(config)

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

            # Make file world-readable
            tmp_path.chmod(0o644)
            result = guard.check_file_permissions(tmp_path)
            assert result is False
            assert len(guard.violations) > 0

            # Clean up
            tmp_path.unlink()

    def test_check_secure_communication_production(self):
        config = SecureConfig(SecurityLevel.PRODUCTION)
        guard = SecurityGuard(config)

        with patch.dict(os.environ, {
            "ENFORCE_HTTPS": "false",
            "TLS_MIN_VERSION": "1.0"
        }):
            result = guard.check_secure_communication()
            assert result is False
            assert len(guard.violations) >= 2

    def test_log_violation(self):
        config = SecureConfig()
        guard = SecurityGuard(config)

        guard.log_violation("test_type", "test message", severity="HIGH")

        assert len(guard.violations) == 1
        violation = guard.violations[0]
        assert violation["type"] == "test_type"
        assert violation["message"] == "test message"
        assert violation["severity"] == "HIGH"

    def test_get_security_report(self):
        config = SecureConfig()
        guard = SecurityGuard(config)

        # Add some violations
        guard.log_violation("test", "test violation")

        report = guard.get_security_report()

        assert "timestamp" in report
        assert "security_level" in report
        assert "audit_results" in report
        assert "violations" in report
        assert "recommendations" in report
        assert len(report["violations"]) == 1


class TestConvenienceFunctions:
    def test_validate_environment_function(self):
        with patch('app.engine.core.security.secure_config') as mock_config:
            mock_audit = SecurityAudit()
            mock_config.audit.return_value = mock_audit

            audit = validate_environment()
            assert audit == mock_audit
            mock_config.audit.assert_called_once()

    def test_get_secure_config_function(self):
        with patch('app.engine.core.security.secure_config') as mock_config:
            mock_config.get.return_value = "test_value"

            value = get_secure_config("TEST_KEY", default="default")
            assert value == "test_value"
            mock_config.get.assert_called_once_with("TEST_KEY", "default")

    def test_get_secret_function(self):
        with patch('app.engine.core.security.secure_config') as mock_config:
            mock_config.get_secret.return_value = "secret_value"

            value = get_secret("SECRET_KEY")
            assert value == "secret_value"
            mock_config.get_secret.assert_called_once_with("SECRET_KEY", None)


class TestSecurityAudit:
    def test_security_audit_structure(self):
        audit = SecurityAudit()

        assert isinstance(audit.timestamp, datetime)
        assert audit.total_variables == 0
        assert audit.validated_variables == 0
        assert audit.failed_validations == []
        assert audit.missing_required == []
        assert audit.weak_secrets == []
        assert audit.security_score == 0.0