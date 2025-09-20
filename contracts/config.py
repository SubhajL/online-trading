import os
import json
import logging
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import jsonschema

logger = logging.getLogger(__name__)


class ValidationMode(Enum):
    STRICT = "strict"
    LOOSE = "loose"
    WARNING = "warning"


@dataclass
class ContractConfig:
    schema_version: str
    schema_path: str
    validation_enabled: bool
    validation_mode: str
    max_payload_size: int
    validation_timeout: int
    breaking_change_protection: bool
    debug_invalid_events: bool = False
    metrics_enabled: bool = False
    event_store_path: str = "contracts/events"
    evolution_mode: str = "backward_compatible"

    @classmethod
    def from_env(cls) -> "ContractConfig":
        return cls(
            schema_version=os.getenv("CONTRACT_SCHEMA_VERSION", "1.0.0"),
            schema_path=os.getenv("CONTRACT_SCHEMA_PATH", "contracts/jsonschema"),
            validation_enabled=os.getenv("CONTRACT_VALIDATION_ENABLED", "true").lower() == "true",
            validation_mode=os.getenv("CONTRACT_VALIDATION_MODE", "strict"),
            max_payload_size=int(os.getenv("CONTRACT_MAX_PAYLOAD_SIZE", "1048576")),
            validation_timeout=int(os.getenv("CONTRACT_VALIDATION_TIMEOUT", "5000")),
            breaking_change_protection=os.getenv("CONTRACT_BREAKING_CHANGE_PROTECTION", "true").lower() == "true",
            debug_invalid_events=os.getenv("CONTRACT_DEBUG_INVALID_EVENTS", "false").lower() == "true",
            metrics_enabled=os.getenv("CONTRACT_METRICS_ENABLED", "false").lower() == "true",
            event_store_path=os.getenv("CONTRACT_EVENT_STORE_PATH", "contracts/events"),
            evolution_mode=os.getenv("SCHEMA_EVOLUTION_MODE", "backward_compatible"),
        )


class ContractValidator:
    def __init__(self, mode: ValidationMode):
        self.mode = mode

    def validate_with_mode(self, payload: Dict[str, Any], schema: Dict[str, Any]) -> bool:
        if self.mode == ValidationMode.STRICT:
            # Strict mode - fail on any violation
            try:
                jsonschema.validate(payload, schema)
                return True
            except jsonschema.ValidationError as e:
                if "Additional properties are not allowed" in str(e):
                    raise ValueError(f"Additional properties are not allowed: {e}")
                raise

        elif self.mode == ValidationMode.LOOSE:
            # Loose mode - allow extra fields
            schema_copy = schema.copy()
            schema_copy["additionalProperties"] = True
            jsonschema.validate(payload, schema_copy)
            return True

        elif self.mode == ValidationMode.WARNING:
            # Warning mode - log but don't fail
            try:
                jsonschema.validate(payload, schema)
            except jsonschema.ValidationError as e:
                logger.warning(f"Validation warning: {e}")
            return True

        raise ValueError(f"Unknown validation mode: {self.mode}")


class CodeGenerator:
    def should_regenerate(self, schema_path: str, output_path: str) -> bool:
        # Check if output exists
        if not os.path.exists(output_path):
            return True

        # Check if schema is newer than output
        schema_mtime = os.path.getmtime(schema_path)
        output_mtime = os.path.getmtime(output_path)

        return schema_mtime > output_mtime


class EventRecorder:
    def __init__(self):
        self.enabled = os.getenv("CONTRACT_DEBUG_INVALID_EVENTS", "false").lower() == "true"
        self.store_path = Path(os.getenv("CONTRACT_EVENT_STORE_PATH", "contracts/events"))

    def record_invalid_event(self, event: Dict[str, Any], error: Exception) -> None:
        if not self.enabled:
            return

        # Create directory if it doesn't exist
        self.store_path.mkdir(parents=True, exist_ok=True)

        # Create filename with timestamp
        timestamp = datetime.now().isoformat()
        filename = f"invalid_event_{timestamp.replace(':', '-')}.json"
        filepath = self.store_path / filename

        # Record event with error details
        record = {
            "timestamp": timestamp,
            "event": event,
            "error": str(error),
            "error_type": type(error).__name__
        }

        with open(filepath, 'w') as f:
            json.dump(record, f, indent=2)


class SchemaEvolution:
    def __init__(self, mode: str):
        self.mode = mode

    def check_compatibility(self, old_schema: Dict[str, Any], new_schema: Dict[str, Any]) -> bool:
        if self.mode == "backward_compatible":
            # Check if new schema can read old data
            # New required fields are not allowed
            old_required = set(old_schema.get("required", []))
            new_required = set(new_schema.get("required", []))

            new_requirements = new_required - old_required
            if new_requirements:
                raise ValueError(
                    f"Schema change is backward incompatible: "
                    f"new required fields {new_requirements}"
                )

            # Removed fields are allowed (old data has them but new schema ignores)
            # Type changes would need deeper inspection
            return True

        elif self.mode == "forward_compatible":
            # Check if old schema can read new data
            # This means we can't remove required fields
            old_required = set(old_schema.get("required", []))
            new_required = set(new_schema.get("required", []))

            removed_requirements = old_required - new_required
            if removed_requirements:
                raise ValueError(
                    f"Schema change is forward incompatible: "
                    f"removed required fields {removed_requirements}"
                )
            return True

        elif self.mode == "full_compatible":
            # Must be both backward and forward compatible
            self.mode = "backward_compatible"
            backward_ok = self.check_compatibility(old_schema, new_schema)

            self.mode = "forward_compatible"
            forward_ok = self.check_compatibility(old_schema, new_schema)

            self.mode = "full_compatible"
            return backward_ok and forward_ok

        raise ValueError(f"Unknown evolution mode: {self.mode}")