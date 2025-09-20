"""Test JSON Schema validation for all contract schemas."""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

try:
    from jsonschema import Draft7Validator, ValidationError
except ImportError:
    pytest.skip("jsonschema not installed", allow_module_level=True)


def load_schema(schema_path: Path) -> Dict[str, Any]:
    """Load JSON schema from file."""
    with open(schema_path) as f:
        return json.load(f)


def validate_schema_structure(schema: Dict[str, Any], schema_name: str) -> None:
    """Validate the structure of a JSON schema."""
    # Check required top-level fields
    assert "type" in schema, f"{schema_name}: Missing 'type' field"
    assert schema["type"] == "object", f"{schema_name}: Top-level type must be 'object'"

    assert "properties" in schema, f"{schema_name}: Missing 'properties' field"
    assert "required" in schema, f"{schema_name}: Missing 'required' field"
    assert (
        "additionalProperties" in schema
    ), f"{schema_name}: Missing 'additionalProperties' field"

    # Validate required fields
    assert isinstance(
        schema["required"], list
    ), f"{schema_name}: 'required' must be a list"
    for field in schema["required"]:
        assert (
            field in schema["properties"]
        ), f"{schema_name}: Required field '{field}' not in properties"


class TestJSONSchemaValidation:
    """Test JSON Schema validation."""

    @pytest.fixture
    def schema_dir(self) -> Path:
        """Get schema directory."""
        return Path("contracts/jsonschema")

    @pytest.fixture
    def all_schemas(self, schema_dir: Path) -> Dict[str, Dict[str, Any]]:
        """Load all schemas."""
        schemas = {}
        for schema_file in schema_dir.glob("*.schema.json"):
            schema_name = schema_file.stem.replace(".schema", "")
            schemas[schema_name] = load_schema(schema_file)
        return schemas

    def test_all_schemas_are_valid_json(self, schema_dir: Path):
        """All schema files should be valid JSON."""
        schema_files = list(schema_dir.glob("*.schema.json"))
        assert len(schema_files) > 0, "No schema files found"

        for schema_file in schema_files:
            try:
                with open(schema_file) as f:
                    json.load(f)
            except json.JSONDecodeError as e:
                pytest.fail(f"{schema_file.name}: Invalid JSON - {e}")

    def test_all_schemas_are_valid_jsonschema(
        self, all_schemas: Dict[str, Dict[str, Any]]
    ):
        """All schemas should be valid JSON Schema Draft 7."""
        for schema_name, schema in all_schemas.items():
            try:
                Draft7Validator.check_schema(schema)
            except Exception as e:
                pytest.fail(f"{schema_name}: Invalid JSON Schema - {e}")

    def test_schema_structure(self, all_schemas: Dict[str, Dict[str, Any]]):
        """All schemas should have required structure."""
        for schema_name, schema in all_schemas.items():
            validate_schema_structure(schema, schema_name)

    def test_schema_field_types(self, all_schemas: Dict[str, Dict[str, Any]]):
        """Validate field types in schemas."""
        for schema_name, schema in all_schemas.items():
            properties = schema["properties"]

            # Check common fields
            if "version" in properties:
                assert (
                    properties["version"]["type"] == "string"
                ), f"{schema_name}: version must be string"

            if "timestamp" in properties:
                assert (
                    properties["timestamp"]["type"] == "string"
                ), f"{schema_name}: timestamp must be string"
                assert (
                    properties["timestamp"].get("format") == "date-time"
                ), f"{schema_name}: timestamp must have date-time format"

            if "venue" in properties:
                assert (
                    properties["venue"]["type"] == "string"
                ), f"{schema_name}: venue must be string"

            if "symbol" in properties:
                assert (
                    properties["symbol"]["type"] == "string"
                ), f"{schema_name}: symbol must be string"

    def test_required_fields_match_properties(
        self, all_schemas: Dict[str, Dict[str, Any]]
    ):
        """All required fields should exist in properties."""
        for schema_name, schema in all_schemas.items():
            required = set(schema["required"])
            properties = set(schema["properties"].keys())

            missing = required - properties
            assert (
                not missing
            ), f"{schema_name}: Required fields missing from properties: {missing}"

    def test_no_duplicate_required_fields(self, all_schemas: Dict[str, Dict[str, Any]]):
        """Required fields should not have duplicates."""
        for schema_name, schema in all_schemas.items():
            required = schema["required"]
            assert len(required) == len(
                set(required)
            ), f"{schema_name}: Duplicate required fields"

    def test_example_payloads_validate(self, all_schemas: Dict[str, Dict[str, Any]]):
        """Example payloads should validate against schemas."""
        examples_dir = Path("contracts/examples")
        if not examples_dir.exists():
            pytest.skip("No examples directory found")

        for schema_name, schema in all_schemas.items():
            example_file = examples_dir / f"{schema_name}.json"
            if not example_file.exists():
                continue

            with open(example_file) as f:
                example_data = json.load(f)

            validator = Draft7Validator(schema)
            errors = list(validator.iter_errors(example_data))
            if errors:
                error_messages = [
                    f"- {err.message} at {'.'.join(str(p) for p in err.path)}"
                    for err in errors
                ]
                pytest.fail(
                    f"{schema_name} example validation failed:\n"
                    + "\n".join(error_messages)
                )

    def test_numeric_fields_allow_strings(self, all_schemas: Dict[str, Dict[str, Any]]):
        """Numeric fields should allow string representation for precision."""
        numeric_field_names = {
            "open",
            "high",
            "low",
            "close",
            "volume",
            "value",
            "price",
            "quantity",
            "size",
            "leverage",
            "risk_amount",
            "atr",
            "sl",
            "tp",
            "entry",
            "stop_loss",
            "take_profit",
        }

        for schema_name, schema in all_schemas.items():
            properties = schema["properties"]

            for prop_name, prop_schema in properties.items():
                if prop_name in numeric_field_names:
                    prop_type = prop_schema.get("type")
                    # Should be either string or array containing string
                    if isinstance(prop_type, list):
                        assert (
                            "string" in prop_type
                        ), f"{schema_name}.{prop_name}: Numeric field should allow string"
                    else:
                        assert (
                            prop_type == "string"
                        ), f"{schema_name}.{prop_name}: Numeric field should be string"
