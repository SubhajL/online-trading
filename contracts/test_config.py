import os
import pytest
from unittest import mock
from typing import Dict, Any


class TestContractConfig:
    def test_contract_config_from_env_with_defaults(self):
        """Test loading config with default values when env vars not set"""
        from contracts.config import ContractConfig

        with mock.patch.dict(os.environ, {}, clear=True):
            config = ContractConfig.from_env()

            assert config.schema_version == "1.0.0"
            assert config.schema_path == "contracts/jsonschema"
            assert config.validation_enabled is True
            assert config.validation_mode == "strict"
            assert config.max_payload_size == 1048576
            assert config.validation_timeout == 5000
            assert config.breaking_change_protection is True

    def test_contract_config_from_env_with_custom_values(self):
        """Test loading config from environment variables"""
        from contracts.config import ContractConfig

        env_vars = {
            "CONTRACT_SCHEMA_VERSION": "2.0.0",
            "CONTRACT_SCHEMA_PATH": "custom/schemas",
            "CONTRACT_VALIDATION_ENABLED": "false",
            "CONTRACT_VALIDATION_MODE": "loose",
            "CONTRACT_MAX_PAYLOAD_SIZE": "2097152",
            "CONTRACT_VALIDATION_TIMEOUT": "10000",
            "CONTRACT_BREAKING_CHANGE_PROTECTION": "false",
        }

        with mock.patch.dict(os.environ, env_vars):
            config = ContractConfig.from_env()

            assert config.schema_version == "2.0.0"
            assert config.schema_path == "custom/schemas"
            assert config.validation_enabled is False
            assert config.validation_mode == "loose"
            assert config.max_payload_size == 2097152
            assert config.validation_timeout == 10000
            assert config.breaking_change_protection is False

    def test_validation_modes(self):
        """Test different validation modes behavior"""
        from contracts.config import ContractValidator, ValidationMode

        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name"],
            "additionalProperties": False,
        }

        # Test strict mode - fails on extra fields
        validator = ContractValidator(ValidationMode.STRICT)
        payload = {"name": "test", "age": 25, "extra": "field"}
        with pytest.raises(ValueError) as exc:
            validator.validate_with_mode(payload, schema)
        assert "Additional properties are not allowed" in str(exc.value)

        # Test loose mode - allows extra fields
        validator = ContractValidator(ValidationMode.LOOSE)
        result = validator.validate_with_mode(payload, schema)
        assert result is True

        # Test warning mode - logs but doesn't fail
        validator = ContractValidator(ValidationMode.WARNING)
        with mock.patch("contracts.config.logger") as mock_logger:
            result = validator.validate_with_mode(payload, schema)
            assert result is True
            mock_logger.warning.assert_called_once()

    def test_code_generation_drift_detection(self):
        """Test detection of schema changes requiring regeneration"""
        from contracts.config import CodeGenerator

        generator = CodeGenerator()

        # Test when output doesn't exist
        assert generator.should_regenerate("schema.json", "nonexistent.py") is True

        # Test when schema is newer than output
        with mock.patch("os.path.exists", return_value=True):
            with mock.patch("os.path.getmtime") as mock_getmtime:
                mock_getmtime.side_effect = lambda path: (
                    1000 if "schema" in path else 500
                )
                assert generator.should_regenerate("schema.json", "output.py") is True

        # Test when output is newer than schema
        with mock.patch("os.path.exists", return_value=True):
            with mock.patch("os.path.getmtime") as mock_getmtime:
                mock_getmtime.side_effect = lambda path: (
                    500 if "schema" in path else 1000
                )
                assert generator.should_regenerate("schema.json", "output.py") is False

    def test_event_recording_when_enabled(self):
        """Test invalid event storage when debugging is enabled"""
        from contracts.config import EventRecorder

        # Test with recording enabled
        with mock.patch.dict(os.environ, {"CONTRACT_DEBUG_INVALID_EVENTS": "true"}):
            recorder = EventRecorder()
            event = {"type": "test", "data": "invalid"}
            error = ValueError("Invalid schema")

            with mock.patch("builtins.open", mock.mock_open()) as mock_file:
                with mock.patch("json.dump") as mock_json:
                    recorder.record_invalid_event(event, error)
                    mock_file.assert_called()
                    mock_json.assert_called()

        # Test with recording disabled
        with mock.patch.dict(os.environ, {"CONTRACT_DEBUG_INVALID_EVENTS": "false"}):
            recorder = EventRecorder()
            recorder.record_invalid_event(event, error)
            # Should not write anything

    def test_schema_evolution_compatibility(self):
        """Test backward/forward compatibility validation"""
        from contracts.config import SchemaEvolution

        old_schema = {
            "type": "object",
            "properties": {"field1": {"type": "string"}},
            "required": ["field1"],
        }

        # Test backward compatible change (adding optional field)
        new_schema_compatible = {
            "type": "object",
            "properties": {"field1": {"type": "string"}, "field2": {"type": "integer"}},
            "required": ["field1"],
        }

        evolution = SchemaEvolution("backward_compatible")
        assert evolution.check_compatibility(old_schema, new_schema_compatible) is True

        # Test backward incompatible change (adding required field)
        new_schema_incompatible = {
            "type": "object",
            "properties": {"field1": {"type": "string"}, "field2": {"type": "integer"}},
            "required": ["field1", "field2"],
        }

        with pytest.raises(ValueError) as exc:
            evolution.check_compatibility(old_schema, new_schema_incompatible)
        assert "backward incompatible" in str(exc.value)
