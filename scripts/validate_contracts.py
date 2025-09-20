#!/usr/bin/env python3
"""
Contract validation script using environment-based configuration
"""
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any

# Add parent directory to path to import contracts module
sys.path.insert(0, str(Path(__file__).parent.parent))

from contracts.config import ContractConfig, ContractValidator, ValidationMode


def validate_payload(
    schema_path: Path, payload_path: Path, config: ContractConfig
) -> bool:
    """Validate a payload against a schema using configured validation mode"""
    # Check payload size
    payload_size = payload_path.stat().st_size
    if payload_size > config.max_payload_size:
        print(
            f"ERROR: Payload size {payload_size} exceeds max {config.max_payload_size}"
        )
        return False

    # Load schema and payload
    with open(schema_path, "r") as f:
        schema = json.load(f)

    with open(payload_path, "r") as f:
        payload = json.load(f)

    # Validate using configured mode
    mode = ValidationMode(config.validation_mode)
    validator = ContractValidator(mode)

    try:
        result = validator.validate_with_mode(payload, schema)
        print(f"✓ Validation passed in {config.validation_mode} mode")
        return result
    except Exception as e:
        print(f"✗ Validation failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Validate contract payloads")
    parser.add_argument("schema", help="Path to JSON schema file")
    parser.add_argument("payload", help="Path to payload file to validate")
    parser.add_argument(
        "--show-config", action="store_true", help="Show current configuration"
    )

    args = parser.parse_args()

    # Load configuration from environment
    config = ContractConfig.from_env()

    if args.show_config:
        print("Current Configuration:")
        print(f"  Schema Version: {config.schema_version}")
        print(f"  Schema Path: {config.schema_path}")
        print(f"  Validation Enabled: {config.validation_enabled}")
        print(f"  Validation Mode: {config.validation_mode}")
        print(f"  Max Payload Size: {config.max_payload_size}")
        print(f"  Breaking Change Protection: {config.breaking_change_protection}")
        print()

    if not config.validation_enabled:
        print("WARNING: Contract validation is disabled")
        return 0

    # Validate the payload
    schema_path = Path(args.schema)
    payload_path = Path(args.payload)

    if not schema_path.exists():
        print(f"ERROR: Schema file not found: {schema_path}")
        return 1

    if not payload_path.exists():
        print(f"ERROR: Payload file not found: {payload_path}")
        return 1

    success = validate_payload(schema_path, payload_path, config)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
