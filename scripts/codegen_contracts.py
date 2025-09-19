#!/usr/bin/env python3
"""
Generate strongly-typed models from JSONSchema definitions.
Outputs: Pydantic (Python), TypeScript types, and Go structs.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
SCHEMA_DIR = ROOT_DIR / "contracts" / "jsonschema"
GEN_DIR = ROOT_DIR / "contracts" / "gen"

# Valid JSON Schema types
VALID_TYPES = {"string", "number", "integer", "boolean", "object", "array", "null"}


def validate_schema(name: str, schema: Dict[str, Any]) -> List[str]:
    """Validate a JSON Schema and return list of errors."""
    errors = []

    # Check for required 'type' field
    if "type" not in schema:
        errors.append(f"{name}: Missing 'type' field in schema")
    else:
        # Validate type value
        schema_type = schema["type"]
        if isinstance(schema_type, str):
            if schema_type not in VALID_TYPES:
                errors.append(f"{name}: Invalid type '{schema_type}'. Must be one of: {', '.join(VALID_TYPES)}")
        elif isinstance(schema_type, list):
            for t in schema_type:
                if t not in VALID_TYPES:
                    errors.append(f"{name}: Invalid type '{t}' in type array. Must be one of: {', '.join(VALID_TYPES)}")
        else:
            errors.append(f"{name}: Type must be a string or array, got {type(schema_type).__name__}")

    # Validate object-specific requirements
    if schema.get("type") == "object" or (isinstance(schema.get("type"), list) and "object" in schema.get("type", [])):
        if "properties" not in schema:
            errors.append(f"{name}: Missing 'properties' field for object type")
        else:
            # Validate each property
            for prop_name, prop_schema in schema.get("properties", {}).items():
                prop_errors = validate_property_schema(f"{name}.{prop_name}", prop_schema)
                errors.extend(prop_errors)

    return errors


def validate_property_schema(prop_path: str, prop_schema: Dict[str, Any]) -> List[str]:
    """Validate a property schema and return list of errors."""
    errors = []

    # Check for type or enum
    if "type" not in prop_schema and "enum" not in prop_schema:
        errors.append(f"{prop_path}: Missing 'type' field in property")

    # If enum is present, ensure type is also present
    if "enum" in prop_schema and "type" not in prop_schema:
        errors.append(f"{prop_path}: Enum requires 'type' field to be specified")

    # Validate format compatibility
    if "format" in prop_schema:
        prop_type = prop_schema.get("type")
        format_val = prop_schema.get("format")

        # date-time format only valid for strings
        if format_val == "date-time" and prop_type not in ["string", None]:
            errors.append(f"{prop_path}: Format 'date-time' incompatible with type '{prop_type}'")

    return errors


def safe_load_schema(schema_path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Safely load a JSON schema file with error handling."""
    try:
        if not schema_path.exists():
            return None, f"Schema file not found: {schema_path}"

        with open(schema_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.strip():
            return None, f"Schema file is empty: {schema_path}"

        try:
            schema = json.loads(content)
            return schema, None
        except json.JSONDecodeError as e:
            return None, f"Invalid JSON in {schema_path}: {str(e)}"

    except UnicodeDecodeError as e:
        return None, f"Encoding error in {schema_path}: {str(e)}"
    except Exception as e:
        return None, f"Error loading {schema_path}: {str(e)}"


def load_schemas() -> Dict[str, Dict[str, Any]]:
    """Load all JSONSchema files from contracts/jsonschema/ with validation."""
    schemas = {}
    errors = []

    if not SCHEMA_DIR.exists():
        print(f"⚠️  Schema directory not found: {SCHEMA_DIR}")
        return schemas

    schema_files = list(SCHEMA_DIR.glob("*.schema.json"))
    if not schema_files:
        print(f"⚠️  No schema files found in: {SCHEMA_DIR}")
        return schemas

    for schema_path in sorted(schema_files):
        schema_name = schema_path.stem.replace(".schema", "")

        # Load schema with error handling
        schema, load_error = safe_load_schema(schema_path)
        if load_error:
            errors.append(load_error)
            continue

        # Validate schema structure
        validation_errors = validate_schema(schema_name, schema)
        if validation_errors:
            errors.extend(validation_errors)
            continue

        schemas[schema_name] = schema

    # Report any errors encountered
    if errors:
        print("❌ Schema validation errors:")
        for error in errors:
            print(f"   - {error}")
        print()

    return schemas


def snake_to_pascal(name: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in name.split("_"))


def snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase."""
    parts = name.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


def get_python_type(schema: Dict[str, Any]) -> str:
    """Convert JSONSchema type to Python type hint.

    Type mapping logic:
    1. Enums -> Literal types with exact string values
    2. Nullable types (array of types) -> Union types using | operator
    3. Basic types follow Python conventions (string->str, number->float, etc.)
    4. date-time format strings remain as str for JSON serialization compatibility
    5. Arrays become List[T] with recursive type resolution for items
    6. Objects without properties become Dict[str, Any]
    7. Missing type defaults to Any for flexibility
    """
    # Priority 1: Handle enums as Literal types
    # This provides type safety for fixed string values
    if "enum" in schema:
        enum_values = ", ".join(f'"{v}"' for v in schema["enum"])
        return f"Literal[{enum_values}]"

    type_val = schema.get("type", "Any")

    # Priority 2: Handle nullable/union types
    # JSONSchema uses array syntax for multiple types (e.g., ["string", "null"])
    if isinstance(type_val, list):
        types = []
        for t in type_val:
            if t == "string":
                types.append("str")
            elif t == "number":
                types.append("float")
            elif t == "integer":
                types.append("int")
            elif t == "boolean":
                types.append("bool")
            elif t == "null":
                types.append("None")
            elif t == "object":
                # Generic object without schema becomes Dict
                types.append("Dict[str, Any]")
            elif t == "array":
                # Recursively resolve array item types
                item_type = get_python_type(schema.get("items", {}))
                types.append(f"List[{item_type}]")
        # Use Python 3.10+ union syntax with |
        return " | ".join(types)

    # Priority 3: Handle simple types
    if type_val == "string":
        # Keep date-time as string for JSON compatibility
        # Pydantic will handle validation of ISO8601 format
        if schema.get("format") == "date-time":
            return "str"  # Could be datetime, but keeping as str for JSON serialization
        return "str"
    elif type_val == "number":
        # JSON number -> Python float (covers decimals)
        return "float"
    elif type_val == "integer":
        # JSON integer -> Python int
        return "int"
    elif type_val == "boolean":
        # JSON boolean -> Python bool
        return "bool"
    elif type_val == "object":
        # Generic object without specific properties
        return "Dict[str, Any]"
    elif type_val == "array":
        # Arrays require recursive type resolution for items
        item_type = get_python_type(schema.get("items", {}))
        return f"List[{item_type}]"

    # Default fallback for unknown types
    return "Any"


def get_typescript_type(schema: Dict[str, Any]) -> str:
    """Convert JSONSchema type to TypeScript type.

    Type mapping logic:
    1. Enums -> Union of string literals (no explicit enum keyword)
    2. Nullable types -> Union types using | including null
    3. Both number and integer -> number (JS/TS has no integer type)
    4. Arrays use T[] syntax instead of Array<T> for readability
    5. Generic objects -> Record<string, any> for key-value pairs
    6. Missing type defaults to any (TypeScript's escape hatch)

    Key differences from Python:
    - No separate int/float types (all are number)
    - null instead of None
    - Record<K,V> instead of Dict
    - Literal unions instead of Literal["a", "b"]
    """
    # Priority 1: Handle enums as union of string literals
    # TypeScript doesn't need Literal wrapper like Python
    if "enum" in schema:
        enum_values = " | ".join(f'"{v}"' for v in schema["enum"])
        return enum_values

    type_val = schema.get("type", "any")

    # Priority 2: Handle nullable/union types
    # Similar to Python but uses 'null' instead of 'None'
    if isinstance(type_val, list):
        types = []
        for t in type_val:
            if t == "string":
                types.append("string")
            elif t == "number":
                types.append("number")
            elif t == "integer":
                # TypeScript/JavaScript only has number type
                types.append("number")
            elif t == "boolean":
                types.append("boolean")
            elif t == "null":
                # TypeScript uses lowercase null
                types.append("null")
            elif t == "object":
                # Generic key-value object
                types.append("Record<string, any>")
            elif t == "array":
                # Recursively resolve array types
                item_type = get_typescript_type(schema.get("items", {}))
                types.append(f"{item_type}[]")
        return " | ".join(types)

    # Priority 3: Handle simple types
    if type_val == "string":
        return "string"
    elif type_val == "number" or type_val == "integer":
        # JavaScript/TypeScript only has number type (no separate int)
        return "number"
    elif type_val == "boolean":
        return "boolean"
    elif type_val == "object":
        # Record type for generic objects
        return "Record<string, any>"
    elif type_val == "array":
        # Array with bracket syntax (preferred over Array<T>)
        item_type = get_typescript_type(schema.get("items", {}))
        return f"{item_type}[]"

    # Default fallback
    return "any"


def get_go_type(schema: Dict[str, Any], field_name: str = "") -> str:
    """Convert JSONSchema type to Go type.

    Type mapping logic:
    1. Nullable types -> Pointer types (*T) for zero-value differentiation
    2. Basic types follow Go conventions (string, float64, int64, bool)
    3. Arrays -> Slices ([]T) which are more idiomatic than arrays
    4. Objects -> map[string]interface{} for generic key-value pairs
    5. interface{} as the escape hatch (like any/Any in TS/Python)

    Key Go-specific considerations:
    - Pointers (*T) distinguish between zero values and null/missing
    - No union types - we pick the non-null type and make it nullable
    - Slices ([]T) instead of arrays for dynamic sizing
    - int64/float64 for precision and consistency
    - map[string]interface{} for generic JSON objects

    The function avoids double-pointer wrapping (e.g., **string).
    """
    type_val = schema.get("type", "interface{}")

    # Handle nullable/union types
    # Go doesn't have union types, so we use pointers for nullable values
    if isinstance(type_val, list):
        # Find the non-null type in the list
        for t in type_val:
            if t != "null":
                # Create simplified schema to avoid infinite recursion
                simple_schema = {"type": t}
                # Preserve array item schema if present
                if t == "array" and "items" in schema:
                    simple_schema["items"] = schema["items"]
                # Recursively get the base type
                base_type = get_go_type(simple_schema, field_name)
                # Avoid double-pointer wrapping (e.g., **string)
                if base_type.startswith("*"):
                    return base_type
                # Make it a pointer to handle null values
                return f"*{base_type}"

    # Handle simple types
    if type_val == "string":
        return "string"
    elif type_val == "number":
        # Use float64 for JSON numbers (handles decimals)
        return "float64"
    elif type_val == "integer":
        # Use int64 for consistency and range
        return "int64"
    elif type_val == "boolean":
        return "bool"
    elif type_val == "object":
        # Generic JSON object as map
        return "map[string]interface{}"
    elif type_val == "array":
        # Slices are more idiomatic in Go than arrays
        item_type = get_go_type(schema.get("items", {}))
        return f"[]{item_type}"

    # Default to empty interface (can hold any type)
    return "interface{}"


def generate_pydantic_models(schemas: Dict[str, Dict[str, Any]]) -> str:
    """Generate Pydantic v2 models from schemas."""
    imports = [
        "from datetime import datetime",
        "from typing import Dict, List, Literal, Optional, Any",
        "from pydantic import BaseModel, Field, validator",
    ]

    models = []

    for name, schema in schemas.items():
        class_name = snake_to_pascal(name.replace(".", "_"))
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        fields = []
        for prop_name, prop_schema in properties.items():
            py_type = get_python_type(prop_schema)
            description = prop_schema.get("description", "")

            # Check if field is required
            if prop_name in required:
                default = "..."
            else:
                default = "None"

            # Add field with proper annotations
            field_def = f'    {prop_name}: {py_type}'
            if default == "...":
                field_def += f' = Field(description="{description}")'
            else:
                field_def += f' = Field(default={default}, description="{description}")'

            fields.append(field_def)

        model_def = f"""
class {class_name}(BaseModel):
    \"\"\"{schema.get('description', '')}\"\"\"

{chr(10).join(fields)}

    class Config:
        extra = "forbid"  # Equivalent to additionalProperties: false
"""
        models.append(model_def)

    return "\n".join(imports) + "\n\n" + "\n".join(models)


def generate_typescript_types(schemas: Dict[str, Dict[str, Any]]) -> str:
    """Generate TypeScript types from schemas."""
    types = []

    for name, schema in schemas.items():
        interface_name = snake_to_pascal(name.replace(".", "_"))
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        fields = []
        for prop_name, prop_schema in properties.items():
            ts_type = get_typescript_type(prop_schema)
            camel_name = snake_to_camel(prop_name)
            optional = "" if prop_name in required else "?"

            comment = f"  /** {prop_schema.get('description', '')} */"
            field_def = f"  {camel_name}{optional}: {ts_type};"

            fields.append(comment)
            fields.append(field_def)

        interface_def = f"""
/**
 * {schema.get('description', '')}
 */
export interface {interface_name} {{
{chr(10).join(fields)}
}}"""
        types.append(interface_def)

    return "\n".join(types)


def generate_go_structs(schemas: Dict[str, Dict[str, Any]]) -> str:
    """Generate Go structs from schemas."""
    structs = []

    header = """package contracts

// Code generated by codegen_contracts.py. DO NOT EDIT.

import (
    "time"
)
"""
    structs.append(header)

    for name, schema in schemas.items():
        struct_name = snake_to_pascal(name.replace(".", "_"))
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        fields = []
        for prop_name, prop_schema in properties.items():
            go_type = get_go_type(prop_schema, prop_name)
            field_name = snake_to_pascal(prop_name)

            # If field is not required and not already a pointer, make it a pointer
            if prop_name not in required and not go_type.startswith("*"):
                go_type = f"*{go_type}"

            # Add JSON tags
            if prop_name not in required:
                json_tag = f'json:"{prop_name},omitempty"'
            else:
                json_tag = f'json:"{prop_name}"'

            field_def = f'\t{field_name} {go_type} `{json_tag}`'

            # Add comment if description exists
            if desc := prop_schema.get("description"):
                field_def = f'\t// {desc}\n{field_def}'

            fields.append(field_def)

        struct_def = f"""
// {struct_name} - {schema.get('description', '')}
type {struct_name} struct {{
{chr(10).join(fields)}
}}"""
        structs.append(struct_def)

    return "\n".join(structs)


def write_generated_files(
    python_code: str,
    typescript_code: str,
    go_code: str
) -> None:
    """Write generated code to files."""
    # Create output directories
    (GEN_DIR / "python").mkdir(parents=True, exist_ok=True)
    (GEN_DIR / "ts").mkdir(parents=True, exist_ok=True)
    (GEN_DIR / "go").mkdir(parents=True, exist_ok=True)

    # Write Python models
    python_file = GEN_DIR / "python" / "models.py"
    with open(python_file, "w") as f:
        f.write("# Code generated by codegen_contracts.py. DO NOT EDIT.\n\n")
        f.write(python_code)

    # Write __init__.py
    init_file = GEN_DIR / "python" / "__init__.py"
    with open(init_file, "w") as f:
        f.write("# Code generated by codegen_contracts.py. DO NOT EDIT.\n\n")
        f.write("from .models import *\n")

    # Write TypeScript types
    ts_file = GEN_DIR / "ts" / "index.ts"
    with open(ts_file, "w") as f:
        f.write("// Code generated by codegen_contracts.py. DO NOT EDIT.\n\n")
        f.write(typescript_code)

    # Write Go structs
    go_file = GEN_DIR / "go" / "contracts.go"
    with open(go_file, "w") as f:
        f.write(go_code)

    print(f"✅ Generated Python models: {python_file}")
    print(f"✅ Generated TypeScript types: {ts_file}")
    print(f"✅ Generated Go structs: {go_file}")


def main():
    """Main entry point."""
    print("🔄 Loading JSON schemas...")
    schemas = load_schemas()
    print(f"✅ Loaded {len(schemas)} schemas")

    print("🔄 Generating Python models...")
    python_code = generate_pydantic_models(schemas)

    print("🔄 Generating TypeScript types...")
    typescript_code = generate_typescript_types(schemas)

    print("🔄 Generating Go structs...")
    go_code = generate_go_structs(schemas)

    print("🔄 Writing generated files...")
    write_generated_files(python_code, typescript_code, go_code)

    print("✨ Code generation complete!")


if __name__ == "__main__":
    main()