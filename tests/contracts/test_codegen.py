"""Unit tests for codegen_contracts.py following TDD principles."""

import json
import tempfile
from pathlib import Path
from typing import Dict, Any
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.codegen_contracts import (
    snake_to_pascal,
    snake_to_camel,
    get_python_type,
    get_typescript_type,
    get_go_type,
    load_schemas,
    generate_pydantic_models,
    generate_typescript_types,
    generate_go_structs,
    validate_schema,
    safe_load_schema,
    validate_property_schema,
)


class TestSnakeToPascal:
    """Test snake_case to PascalCase conversion."""

    def test_single_word_conversion(self):
        """Single word should be capitalized."""
        assert snake_to_pascal("order") == "Order"

    def test_two_word_conversion(self):
        """Multiple words should each be capitalized."""
        assert snake_to_pascal("order_update") == "OrderUpdate"

    def test_multiple_word_conversion(self):
        """All words in snake_case should be converted."""
        assert snake_to_pascal("smart_money_concept") == "SmartMoneyConcept"

    def test_empty_string(self):
        """Empty string should return empty string."""
        assert snake_to_pascal("") == ""

    def test_already_pascal(self):
        """Already PascalCase without underscores gets treated as single word."""
        # This is expected behavior - the function is designed for snake_case input
        assert snake_to_pascal("OrderUpdate") == "Orderupdate"


class TestSnakeToCamel:
    """Test snake_case to camelCase conversion."""

    def test_single_word_conversion(self):
        """Single word should remain lowercase."""
        assert snake_to_camel("order") == "order"

    def test_two_word_conversion(self):
        """First word lowercase, subsequent capitalized."""
        assert snake_to_camel("order_update") == "orderUpdate"

    def test_multiple_word_conversion(self):
        """First word lowercase, rest capitalized."""
        assert snake_to_camel("smart_money_concept") == "smartMoneyConcept"

    def test_empty_string(self):
        """Empty string should return empty string."""
        assert snake_to_camel("") == ""


class TestGetPythonType:
    """Test JSONSchema to Python type conversion."""

    def test_basic_string_type(self):
        """String type should map to str."""
        schema = {"type": "string"}
        assert get_python_type(schema) == "str"

    def test_basic_number_type(self):
        """Number type should map to float."""
        schema = {"type": "number"}
        assert get_python_type(schema) == "float"

    def test_basic_integer_type(self):
        """Integer type should map to int."""
        schema = {"type": "integer"}
        assert get_python_type(schema) == "int"

    def test_basic_boolean_type(self):
        """Boolean type should map to bool."""
        schema = {"type": "boolean"}
        assert get_python_type(schema) == "bool"

    def test_datetime_string(self):
        """Date-time format should still be str for JSON serialization."""
        schema = {"type": "string", "format": "date-time"}
        assert get_python_type(schema) == "str"

    def test_enum_type(self):
        """Enum should generate Literal type."""
        schema = {"type": "string", "enum": ["BUY", "SELL"]}
        assert get_python_type(schema) == 'Literal["BUY", "SELL"]'

    def test_nullable_type(self):
        """Nullable type should use Union syntax."""
        schema = {"type": ["string", "null"]}
        assert get_python_type(schema) == "str | None"

    def test_array_of_strings(self):
        """Array should map to List with proper item type."""
        schema = {"type": "array", "items": {"type": "string"}}
        assert get_python_type(schema) == "List[str]"

    def test_array_of_numbers(self):
        """Array of numbers should map correctly."""
        schema = {"type": "array", "items": {"type": "number"}}
        assert get_python_type(schema) == "List[float]"

    def test_object_type(self):
        """Object without properties should map to Dict."""
        schema = {"type": "object"}
        assert get_python_type(schema) == "Dict[str, Any]"

    def test_nullable_array(self):
        """Nullable array should handle multiple types."""
        schema = {"type": ["array", "null"], "items": {"type": "string"}}
        assert get_python_type(schema) == "List[str] | None"

    def test_no_type_specified(self):
        """Missing type should default to Any."""
        schema = {}
        assert get_python_type(schema) == "Any"


class TestGetTypescriptType:
    """Test JSONSchema to TypeScript type conversion."""

    def test_basic_string_type(self):
        """String type should map to string."""
        schema = {"type": "string"}
        assert get_typescript_type(schema) == "string"

    def test_basic_number_type(self):
        """Number type should map to number."""
        schema = {"type": "number"}
        assert get_typescript_type(schema) == "number"

    def test_basic_integer_type(self):
        """Integer type should also map to number."""
        schema = {"type": "integer"}
        assert get_typescript_type(schema) == "number"

    def test_basic_boolean_type(self):
        """Boolean type should map to boolean."""
        schema = {"type": "boolean"}
        assert get_typescript_type(schema) == "boolean"

    def test_enum_type(self):
        """Enum should generate union of string literals."""
        schema = {"type": "string", "enum": ["BUY", "SELL"]}
        assert get_typescript_type(schema) == '"BUY" | "SELL"'

    def test_nullable_type(self):
        """Nullable type should use union with null."""
        schema = {"type": ["string", "null"]}
        assert get_typescript_type(schema) == "string | null"

    def test_array_of_strings(self):
        """Array should use bracket notation."""
        schema = {"type": "array", "items": {"type": "string"}}
        assert get_typescript_type(schema) == "string[]"

    def test_object_type(self):
        """Object should map to Record type."""
        schema = {"type": "object"}
        assert get_typescript_type(schema) == "Record<string, any>"

    def test_no_type_specified(self):
        """Missing type should default to any."""
        schema = {}
        assert get_typescript_type(schema) == "any"


class TestGetGoType:
    """Test JSONSchema to Go type conversion."""

    def test_basic_string_type(self):
        """String type should map to string."""
        schema = {"type": "string"}
        assert get_go_type(schema) == "string"

    def test_basic_number_type(self):
        """Number type should map to float64."""
        schema = {"type": "number"}
        assert get_go_type(schema) == "float64"

    def test_basic_integer_type(self):
        """Integer type should map to int64."""
        schema = {"type": "integer"}
        assert get_go_type(schema) == "int64"

    def test_basic_boolean_type(self):
        """Boolean type should map to bool."""
        schema = {"type": "boolean"}
        assert get_go_type(schema) == "bool"

    def test_nullable_string(self):
        """Nullable types should use pointers."""
        schema = {"type": ["string", "null"]}
        assert get_go_type(schema) == "*string"

    def test_nullable_number(self):
        """Nullable number should be pointer to float64."""
        schema = {"type": ["number", "null"]}
        assert get_go_type(schema) == "*float64"

    def test_array_of_strings(self):
        """Array should map to slice."""
        schema = {"type": "array", "items": {"type": "string"}}
        assert get_go_type(schema) == "[]string"

    def test_nullable_array(self):
        """Nullable array should be pointer to slice."""
        schema = {"type": ["array", "null"], "items": {"type": "string"}}
        assert get_go_type(schema) == "*[]string"

    def test_object_type(self):
        """Object should map to map[string]interface{}."""
        schema = {"type": "object"}
        assert get_go_type(schema) == "map[string]interface{}"

    def test_no_type_specified(self):
        """Missing type should default to interface{}."""
        schema = {}
        assert get_go_type(schema) == "interface{}"


class TestLoadSchemas:
    """Test schema loading functionality."""

    def test_load_valid_schemas(self, tmp_path):
        """Should load all valid JSON schema files."""
        # Create test schemas
        schema1 = {
            "type": "object",
            "properties": {
                "field1": {"type": "string"}
            }
        }
        schema2 = {
            "type": "object",
            "properties": {
                "field2": {"type": "number"}
            }
        }

        # Write to temp directory
        schema_dir = tmp_path / "jsonschema"
        schema_dir.mkdir()

        (schema_dir / "test1.schema.json").write_text(json.dumps(schema1))
        (schema_dir / "test2.schema.json").write_text(json.dumps(schema2))

        # Mock the SCHEMA_DIR
        import scripts.codegen_contracts
        original_schema_dir = scripts.codegen_contracts.SCHEMA_DIR
        scripts.codegen_contracts.SCHEMA_DIR = schema_dir

        try:
            schemas = load_schemas()
            assert len(schemas) == 2
            assert "test1" in schemas
            assert "test2" in schemas
            assert schemas["test1"]["properties"]["field1"]["type"] == "string"
            assert schemas["test2"]["properties"]["field2"]["type"] == "number"
        finally:
            scripts.codegen_contracts.SCHEMA_DIR = original_schema_dir

    def test_empty_schema_directory(self, tmp_path):
        """Should return empty dict for empty directory."""
        schema_dir = tmp_path / "jsonschema"
        schema_dir.mkdir()

        import scripts.codegen_contracts
        original_schema_dir = scripts.codegen_contracts.SCHEMA_DIR
        scripts.codegen_contracts.SCHEMA_DIR = schema_dir

        try:
            schemas = load_schemas()
            assert schemas == {}
        finally:
            scripts.codegen_contracts.SCHEMA_DIR = original_schema_dir


class TestGeneratePydanticModels:
    """Test Pydantic model generation."""

    def test_simple_model_generation(self):
        """Should generate valid Pydantic model."""
        schemas = {
            "order_update": {
                "type": "object",
                "description": "Order status update",
                "properties": {
                    "order_id": {"type": "string", "description": "Unique order ID"},
                    "status": {"type": "string", "enum": ["FILLED", "CANCELED"], "description": "Order status"},
                    "filled_qty": {"type": "number", "description": "Filled quantity"},
                },
                "required": ["order_id", "status"],
                "additionalProperties": False
            }
        }

        result = generate_pydantic_models(schemas)

        # Check imports
        assert "from pydantic import BaseModel, Field" in result
        assert "from typing import Dict, List, Literal, Optional, Any" in result

        # Check class definition
        assert "class OrderUpdate(BaseModel):" in result
        assert '"""Order status update"""' in result

        # Check required fields
        assert 'order_id: str = Field(description="Unique order ID")' in result
        assert 'status: Literal["FILLED", "CANCELED"] = Field(description="Order status")' in result

        # Check optional field
        assert 'filled_qty: float = Field(default=None, description="Filled quantity")' in result

        # Check config
        assert 'extra = "forbid"' in result

    def test_nullable_field_generation(self):
        """Should handle nullable fields correctly."""
        schemas = {
            "test_model": {
                "type": "object",
                "properties": {
                    "nullable_field": {"type": ["string", "null"], "description": "Can be null"},
                },
                "required": [],
            }
        }

        result = generate_pydantic_models(schemas)
        assert 'nullable_field: str | None = Field(default=None, description="Can be null")' in result


class TestGenerateTypescriptTypes:
    """Test TypeScript type generation."""

    def test_simple_interface_generation(self):
        """Should generate valid TypeScript interface."""
        schemas = {
            "order_update": {
                "type": "object",
                "description": "Order status update",
                "properties": {
                    "order_id": {"type": "string", "description": "Unique order ID"},
                    "status": {"type": "string", "enum": ["FILLED", "CANCELED"], "description": "Order status"},
                    "filled_qty": {"type": "number", "description": "Filled quantity"},
                },
                "required": ["order_id", "status"],
            }
        }

        result = generate_typescript_types(schemas)

        # Check interface definition
        assert "export interface OrderUpdate {" in result
        assert "* Order status update" in result

        # Check required fields (no ? suffix)
        assert "orderId: string;" in result
        assert 'status: "FILLED" | "CANCELED";' in result

        # Check optional field (with ? suffix)
        assert "filledQty?: number;" in result

        # Check comments
        assert "/** Unique order ID */" in result
        assert "/** Order status */" in result

    def test_camel_case_conversion(self):
        """Should convert snake_case to camelCase."""
        schemas = {
            "test": {
                "type": "object",
                "properties": {
                    "snake_case_field": {"type": "string", "description": "Test field"},
                },
                "required": []
            }
        }

        result = generate_typescript_types(schemas)
        assert "snakeCaseField?" in result


class TestGenerateGoStructs:
    """Test Go struct generation."""

    def test_simple_struct_generation(self):
        """Should generate valid Go struct."""
        schemas = {
            "order_update": {
                "type": "object",
                "description": "Order status update",
                "properties": {
                    "order_id": {"type": "string", "description": "Unique order ID"},
                    "status": {"type": "string", "description": "Order status"},
                    "filled_qty": {"type": "number", "description": "Filled quantity"},
                },
                "required": ["order_id", "status"],
            }
        }

        result = generate_go_structs(schemas)

        # Check package and imports
        assert "package contracts" in result
        assert "import (" in result

        # Check struct definition
        assert "type OrderUpdate struct {" in result
        assert "// OrderUpdate - Order status update" in result

        # Check required fields (no pointer)
        assert 'OrderId string `json:"order_id"`' in result
        assert 'Status string `json:"status"`' in result

        # Check optional field (pointer with omitempty)
        assert 'FilledQty *float64 `json:"filled_qty,omitempty"`' in result

        # Check field comments
        assert "// Unique order ID" in result
        assert "// Order status" in result

    def test_nullable_field_handling(self):
        """Should use pointers for nullable fields."""
        schemas = {
            "test": {
                "type": "object",
                "properties": {
                    "nullable_field": {"type": ["string", "null"], "description": "Can be null"},
                },
                "required": []
            }
        }

        result = generate_go_structs(schemas)
        assert 'NullableField *string `json:"nullable_field,omitempty"`' in result


class TestValidateSchema:
    """Test schema validation functionality."""

    def test_valid_schema(self):
        """Valid schema should pass validation."""
        schema = {
            "type": "object",
            "properties": {
                "field1": {"type": "string"},
            }
        }
        errors = validate_schema("test_schema", schema)
        assert errors == []

    def test_missing_type(self):
        """Schema without type should fail validation."""
        schema = {
            "properties": {
                "field1": {"type": "string"},
            }
        }
        errors = validate_schema("test_schema", schema)
        assert len(errors) == 1
        assert "missing 'type' field" in errors[0].lower()

    def test_invalid_type(self):
        """Schema with invalid type should fail validation."""
        schema = {
            "type": "invalid_type",
            "properties": {}
        }
        errors = validate_schema("test_schema", schema)
        assert len(errors) == 1
        assert "invalid type" in errors[0].lower()

    def test_missing_properties_for_object(self):
        """Object type without properties should fail validation."""
        schema = {
            "type": "object"
        }
        errors = validate_schema("test_schema", schema)
        assert len(errors) == 1
        assert "missing 'properties'" in errors[0].lower()

    def test_multiple_errors(self):
        """Schema with multiple errors should report all."""
        schema = {
            "type": ["object", "invalid"],
            "properties": {
                "field1": {}  # Missing type
            }
        }
        errors = validate_schema("test_schema", schema)
        assert len(errors) >= 2


class TestValidatePropertySchema:
    """Test property schema validation."""

    def test_valid_property(self):
        """Valid property schema should pass."""
        prop_schema = {"type": "string", "description": "A field"}
        errors = validate_property_schema("field_name", prop_schema)
        assert errors == []

    def test_property_missing_type(self):
        """Property without type should fail."""
        prop_schema = {"description": "A field"}
        errors = validate_property_schema("field_name", prop_schema)
        assert len(errors) == 1
        assert "missing 'type'" in errors[0].lower()

    def test_invalid_enum_without_type(self):
        """Enum without type should fail."""
        prop_schema = {"enum": ["A", "B", "C"]}
        errors = validate_property_schema("field_name", prop_schema)
        assert len(errors) == 1
        assert "enum requires 'type'" in errors[0].lower()

    def test_conflicting_types(self):
        """Array type with non-array format should fail."""
        prop_schema = {"type": "array", "format": "date-time"}
        errors = validate_property_schema("field_name", prop_schema)
        assert len(errors) == 1
        assert "format 'date-time' incompatible" in errors[0].lower()


class TestSafeLoadSchema:
    """Test safe schema loading with error handling."""

    def test_load_valid_json(self, tmp_path):
        """Should load valid JSON successfully."""
        schema = {"type": "object", "properties": {"test": {"type": "string"}}}
        schema_file = tmp_path / "test.schema.json"
        schema_file.write_text(json.dumps(schema))

        result, error = safe_load_schema(schema_file)
        assert error is None
        assert result == schema

    def test_load_invalid_json(self, tmp_path):
        """Should handle invalid JSON gracefully."""
        schema_file = tmp_path / "invalid.schema.json"
        schema_file.write_text("{ invalid json }")

        result, error = safe_load_schema(schema_file)
        assert result is None
        assert error is not None
        assert "invalid json" in error.lower()

    def test_load_nonexistent_file(self, tmp_path):
        """Should handle missing file gracefully."""
        schema_file = tmp_path / "missing.schema.json"

        result, error = safe_load_schema(schema_file)
        assert result is None
        assert error is not None
        assert "not found" in error.lower() or "no such file" in error.lower()

    def test_load_empty_file(self, tmp_path):
        """Should handle empty file gracefully."""
        schema_file = tmp_path / "empty.schema.json"
        schema_file.write_text("")

        result, error = safe_load_schema(schema_file)
        assert result is None
        assert error is not None

    def test_load_with_encoding_issues(self, tmp_path):
        """Should handle encoding issues gracefully."""
        schema_file = tmp_path / "encoding.schema.json"
        # Write invalid UTF-8 bytes
        schema_file.write_bytes(b'{\xff\xfe"type": "object"}')

        result, error = safe_load_schema(schema_file)
        assert result is None
        assert error is not None