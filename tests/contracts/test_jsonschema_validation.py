import json
import pytest
from pathlib import Path
from jsonschema import validate, ValidationError, Draft7Validator


def get_all_schemas():
    schema_dir = Path(__file__).parent.parent.parent / "contracts" / "jsonschema"
    return list(schema_dir.glob("*.schema.json"))


def load_schema(schema_path: Path) -> dict:
    with open(schema_path) as f:
        return json.load(f)


class TestAllSchemas:
    def test_all_schemas_are_valid_json(self):
        """Test that all schema files are valid JSON."""
        schemas = get_all_schemas()
        assert len(schemas) == 10, f"Expected 10 schemas, found {len(schemas)}"

        for schema_path in schemas:
            try:
                with open(schema_path) as f:
                    json.load(f)
            except json.JSONDecodeError as e:
                pytest.fail(f"Invalid JSON in {schema_path.name}: {e}")

    def test_all_schemas_are_valid_jsonschema(self):
        """Test that all schemas are valid JSONSchema Draft 7."""
        schemas = get_all_schemas()

        for schema_path in schemas:
            schema = load_schema(schema_path)
            try:
                Draft7Validator.check_schema(schema)
            except Exception as e:
                pytest.fail(f"Invalid JSONSchema in {schema_path.name}: {e}")

    def test_all_schemas_have_version_field(self):
        """Test that every schema includes a version field."""
        schemas = get_all_schemas()

        for schema_path in schemas:
            schema = load_schema(schema_path)
            assert "version" in schema["properties"], f"{schema_path.name} missing version field"
            assert "version" in schema["required"], f"{schema_path.name} version field not required"

            # Check version pattern
            version_schema = schema["properties"]["version"]
            assert version_schema["type"] == "string"
            assert version_schema["pattern"] == r"^\d+\.\d+\.\d+$"

    def test_all_schemas_have_standard_fields(self):
        """Test that all schemas have venue, symbol fields."""
        schemas = get_all_schemas()

        for schema_path in schemas:
            schema = load_schema(schema_path)
            props = schema["properties"]
            required = schema["required"]

            # All events should have venue and symbol
            assert "venue" in props, f"{schema_path.name} missing venue field"
            assert "venue" in required, f"{schema_path.name} venue not required"

            assert "symbol" in props, f"{schema_path.name} missing symbol field"
            assert "symbol" in required, f"{schema_path.name} symbol not required"

    def test_all_schemas_disallow_additional_properties(self):
        """Test that all schemas have additionalProperties: false."""
        schemas = get_all_schemas()

        for schema_path in schemas:
            schema = load_schema(schema_path)
            assert schema.get("additionalProperties") is False, \
                f"{schema_path.name} should have additionalProperties: false"

    def test_timestamp_fields_have_pattern(self):
        """Test that all timestamp fields have ISO8601 pattern."""
        schemas = get_all_schemas()
        timestamp_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z$"

        for schema_path in schemas:
            schema = load_schema(schema_path)

            for prop_name, prop_schema in schema["properties"].items():
                if prop_schema.get("format") == "date-time":
                    assert prop_schema.get("pattern") == timestamp_pattern, \
                        f"{schema_path.name}.{prop_name} missing ISO8601 pattern"

    def test_enum_fields_are_lowercase(self):
        """Test that enum values follow lowercase convention."""
        schemas = get_all_schemas()

        for schema_path in schemas:
            schema = load_schema(schema_path)

            for prop_name, prop_schema in schema["properties"].items():
                if "enum" in prop_schema:
                    for enum_val in prop_schema["enum"]:
                        assert enum_val.islower() or "_" in enum_val, \
                            f"{schema_path.name}.{prop_name} enum value '{enum_val}' should be lowercase"

    def test_numeric_fields_with_constraints(self):
        """Test that numeric fields with constraints are properly defined."""
        test_cases = {
            "features.v1.schema.json": {
                "rsi": {"minimum": 0, "maximum": 100},
                "atr": {"minimum": 0}
            },
            "zones.v1.schema.json": {
                "strength": {"minimum": 0, "maximum": 1},
                "candle_count": {"minimum": 1},
                "touches": {"minimum": 0}
            },
            "signals_raw.v1.schema.json": {
                "confidence": {"minimum": 0, "maximum": 1}
            },
            "regime.v1.schema.json": {
                "strength": {"minimum": 0, "maximum": 1},
                "trend_direction": {"minimum": -1, "maximum": 1},
                "volatility": {"minimum": 0}
            },
            "decision.v1.schema.json": {
                "risk_percentage": {"minimum": 0, "maximum": 1},
                "confidence": {"minimum": 0, "maximum": 1},
                "leverage": {"minimum": 1}
            }
        }

        for schema_file, field_constraints in test_cases.items():
            schema_path = Path(__file__).parent.parent.parent / "contracts" / "jsonschema" / schema_file
            schema = load_schema(schema_path)

            for field, constraints in field_constraints.items():
                field_schema = schema["properties"][field]
                for constraint, value in constraints.items():
                    # Handle nullable fields
                    if isinstance(field_schema["type"], list):
                        assert constraint in field_schema, \
                            f"{schema_file}.{field} missing {constraint} constraint"
                        assert field_schema[constraint] == value, \
                            f"{schema_file}.{field} {constraint} should be {value}"
                    else:
                        assert field_schema.get(constraint) == value, \
                            f"{schema_file}.{field} {constraint} should be {value}"