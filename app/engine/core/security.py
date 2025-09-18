"""
Security module for environment variable validation and sensitive data protection.

Provides secure handling of configuration, secrets management, and
environment variable validation following security best practices.
"""

import os
import re
import hashlib
import secrets
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union, Callable
from pathlib import Path
import json
from base64 import b64encode, b64decode
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend


logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """Security levels for different environments."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


class SecurityError(Exception):
    """Raised when security checks fail."""
    pass


@dataclass
class ValidationRule:
    """Rule for validating environment variables."""
    name: str
    pattern: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    required: bool = False
    sensitive: bool = False
    allowed_values: Optional[List[str]] = None
    custom_validator: Optional[Callable[[str], bool]] = None
    error_message: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of validation check."""
    is_valid: bool
    variable_name: str
    error: Optional[str] = None
    suggestion: Optional[str] = None


@dataclass
class SecurityAudit:
    """Security audit information."""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    total_variables: int = 0
    validated_variables: int = 0
    failed_validations: List[ValidationResult] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)
    weak_secrets: List[str] = field(default_factory=list)
    security_score: float = 0.0


class EnvironmentValidator:
    """Validates environment variables against security rules."""

    # Common patterns for validation
    PATTERNS = {
        'url': r'^https?://[a-zA-Z0-9.-]+(?:\.[a-zA-Z]{2,})+(?::\d+)?(?:/.*)?$',
        'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
        'uuid': r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        'jwt': r'^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]*$',
        'api_key': r'^[A-Za-z0-9_\-]{32,}$',
        'port': r'^([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])$',
        'ip_address': r'^(\d{1,3}\.){3}\d{1,3}$',
        'hostname': r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
    }

    def __init__(self, security_level: SecurityLevel = SecurityLevel.DEVELOPMENT):
        self.security_level = security_level
        self.rules: Dict[str, ValidationRule] = {}
        self._setup_default_rules()

    def _setup_default_rules(self):
        """Setup default validation rules for common variables."""
        # Database configuration
        self.add_rule(ValidationRule(
            name="DATABASE_URL",
            pattern=self.PATTERNS['url'],
            required=self.security_level == SecurityLevel.PRODUCTION,
            sensitive=True
        ))

        self.add_rule(ValidationRule(
            name="DATABASE_PASSWORD",
            min_length=12 if self.security_level == SecurityLevel.PRODUCTION else 8,
            required=self.security_level == SecurityLevel.PRODUCTION,
            sensitive=True,
            custom_validator=self._validate_password_strength
        ))

        # Redis configuration
        self.add_rule(ValidationRule(
            name="REDIS_HOST",
            pattern=self.PATTERNS['hostname'],
            required=False
        ))

        self.add_rule(ValidationRule(
            name="REDIS_PORT",
            pattern=self.PATTERNS['port'],
            required=False
        ))

        # JWT and authentication
        self.add_rule(ValidationRule(
            name="JWT_SECRET",
            min_length=32,
            required=self.security_level != SecurityLevel.DEVELOPMENT,
            sensitive=True,
            custom_validator=self._validate_jwt_secret
        ))

        # API keys
        self.add_rule(ValidationRule(
            name="BINANCE_API_KEY",
            pattern=self.PATTERNS['api_key'],
            required=False,
            sensitive=True
        ))

        self.add_rule(ValidationRule(
            name="BINANCE_SECRET_KEY",
            min_length=32,
            required=False,
            sensitive=True
        ))

        # Vault configuration
        self.add_rule(ValidationRule(
            name="VAULT_TOKEN",
            min_length=20,
            required=False,
            sensitive=True
        ))

        # Environment
        self.add_rule(ValidationRule(
            name="ENVIRONMENT",
            allowed_values=["development", "staging", "production"],
            required=True
        ))

        # Logging
        self.add_rule(ValidationRule(
            name="LOG_LEVEL",
            allowed_values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            required=False
        ))

    def add_rule(self, rule: ValidationRule):
        """Add a validation rule."""
        self.rules[rule.name] = rule

    def validate_variable(self, name: str, value: Optional[str]) -> ValidationResult:
        """Validate a single environment variable."""
        rule = self.rules.get(name)

        if not rule:
            return ValidationResult(is_valid=True, variable_name=name)

        # Check if required
        if rule.required and not value:
            return ValidationResult(
                is_valid=False,
                variable_name=name,
                error=f"Required variable {name} is not set",
                suggestion=f"Set {name} environment variable"
            )

        # If not required and not set, it's valid
        if not value:
            return ValidationResult(is_valid=True, variable_name=name)

        # Check pattern
        if rule.pattern:
            if not re.match(rule.pattern, value):
                return ValidationResult(
                    is_valid=False,
                    variable_name=name,
                    error=f"Variable {name} does not match required pattern",
                    suggestion=rule.error_message or f"Ensure {name} matches the expected format"
                )

        # Check length constraints
        if rule.min_length and len(value) < rule.min_length:
            return ValidationResult(
                is_valid=False,
                variable_name=name,
                error=f"Variable {name} is too short (min: {rule.min_length})",
                suggestion=f"Use at least {rule.min_length} characters"
            )

        if rule.max_length and len(value) > rule.max_length:
            return ValidationResult(
                is_valid=False,
                variable_name=name,
                error=f"Variable {name} is too long (max: {rule.max_length})",
                suggestion=f"Use at most {rule.max_length} characters"
            )

        # Check allowed values
        if rule.allowed_values and value not in rule.allowed_values:
            return ValidationResult(
                is_valid=False,
                variable_name=name,
                error=f"Variable {name} has invalid value: {value}",
                suggestion=f"Use one of: {', '.join(rule.allowed_values)}"
            )

        # Custom validation
        if rule.custom_validator:
            if not rule.custom_validator(value):
                return ValidationResult(
                    is_valid=False,
                    variable_name=name,
                    error=rule.error_message or f"Variable {name} failed custom validation",
                    suggestion=f"Check {name} meets security requirements"
                )

        return ValidationResult(is_valid=True, variable_name=name)

    def validate_all(self) -> SecurityAudit:
        """Validate all registered environment variables."""
        audit = SecurityAudit()
        audit.total_variables = len(self.rules)

        for name, rule in self.rules.items():
            value = os.getenv(name)
            result = self.validate_variable(name, value)

            if result.is_valid:
                audit.validated_variables += 1
            else:
                audit.failed_validations.append(result)
                if rule.required and not value:
                    audit.missing_required.append(name)

            # Check for weak secrets
            if rule.sensitive and value:
                if self._is_weak_secret(value):
                    audit.weak_secrets.append(name)

        # Calculate security score
        if audit.total_variables > 0:
            base_score = audit.validated_variables / audit.total_variables
            penalty = len(audit.weak_secrets) * 0.1
            audit.security_score = max(0, min(1, base_score - penalty))
        else:
            audit.security_score = 1.0

        return audit

    def _validate_password_strength(self, password: str) -> bool:
        """Validate password strength."""
        if self.security_level == SecurityLevel.PRODUCTION:
            # Production requirements
            if len(password) < 12:
                return False
            if not re.search(r'[A-Z]', password):
                return False
            if not re.search(r'[a-z]', password):
                return False
            if not re.search(r'[0-9]', password):
                return False
            if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
                return False
        return True

    def _validate_jwt_secret(self, secret: str) -> bool:
        """Validate JWT secret strength."""
        # Check entropy
        if len(secret) < 32:
            return False

        # Check for common weak secrets
        weak_patterns = [
            'secret', 'password', '123456', 'admin',
            'default', 'changeme', 'test', 'demo'
        ]

        secret_lower = secret.lower()
        for pattern in weak_patterns:
            if pattern in secret_lower:
                return False

        return True

    def _is_weak_secret(self, value: str) -> bool:
        """Check if a secret value is weak."""
        # Common weak values
        weak_values = {
            'password', '123456', 'admin', 'secret',
            'changeme', 'default', 'test', 'demo'
        }

        if value.lower() in weak_values:
            return True

        # Check for low entropy (repeated characters)
        if len(set(value)) < len(value) / 4:
            return True

        return False


class SecretManager:
    """Manages encryption and decryption of sensitive data."""

    def __init__(self, master_key: Optional[str] = None):
        """Initialize with master key or generate one."""
        if master_key:
            self.master_key = master_key.encode()
        else:
            self.master_key = self._get_or_create_master_key()

        self._cipher = self._create_cipher()

    def _get_or_create_master_key(self) -> bytes:
        """Get master key from environment or create one."""
        master_key = os.getenv('MASTER_ENCRYPTION_KEY')

        if master_key:
            return b64decode(master_key.encode())

        # Generate new key
        new_key = Fernet.generate_key()
        logger.warning(
            "No MASTER_ENCRYPTION_KEY found. Generated new key. "
            "Set MASTER_ENCRYPTION_KEY environment variable to persist."
        )
        return new_key

    def _create_cipher(self) -> Fernet:
        """Create cipher from master key."""
        # Always derive key using PBKDF2 for consistency
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'stable_salt',  # Use stable salt for deterministic key
            iterations=100000,
            backend=default_backend()
        )
        key = b64encode(kdf.derive(self.master_key))
        return Fernet(key)

    def encrypt(self, data: str) -> str:
        """Encrypt sensitive data."""
        encrypted = self._cipher.encrypt(data.encode())
        return b64encode(encrypted).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt sensitive data."""
        try:
            encrypted = b64decode(encrypted_data.encode())
            decrypted = self._cipher.decrypt(encrypted)
            return decrypted.decode()
        except Exception as e:
            raise SecurityError(f"Failed to decrypt data: {e}")

    def hash_value(self, value: str, salt: Optional[str] = None) -> str:
        """Create secure hash of value."""
        if salt is None:
            salt = secrets.token_hex(16)

        hash_input = f"{salt}{value}".encode()
        hash_value = hashlib.pbkdf2_hmac('sha256', hash_input, salt.encode(), 100000)
        return f"{salt}${hash_value.hex()}"

    def verify_hash(self, value: str, hashed: str) -> bool:
        """Verify value against hash."""
        try:
            salt, hash_hex = hashed.split('$')
            test_hash = self.hash_value(value, salt)
            return secrets.compare_digest(test_hash, hashed)
        except Exception:
            return False


class SecureConfig:
    """Secure configuration manager with validation and encryption."""

    def __init__(
        self,
        security_level: SecurityLevel = SecurityLevel.DEVELOPMENT,
        enable_encryption: bool = True
    ):
        self.security_level = security_level
        self.validator = EnvironmentValidator(security_level)
        self.secret_manager = SecretManager() if enable_encryption else None
        self._cached_values: Dict[str, Any] = {}
        self._sensitive_keys: Set[str] = set()

    def get(self, key: str, default: Any = None, sensitive: bool = False) -> Any:
        """Get configuration value with validation."""
        # Check cache first
        if key in self._cached_values:
            return self._cached_values[key]

        # Get from environment
        value = os.getenv(key, default)

        # Validate
        result = self.validator.validate_variable(key, value)
        if not result.is_valid:
            if self.security_level == SecurityLevel.PRODUCTION:
                raise ValidationError(result.error)
            else:
                logger.warning(f"Validation warning: {result.error}")

        # Mark as sensitive if needed
        if sensitive:
            self._sensitive_keys.add(key)

        # Cache the value
        self._cached_values[key] = value
        return value

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get secret value with decryption if needed."""
        value = self.get(key, default, sensitive=True)

        if not value:
            return None

        # Check if value is encrypted (starts with 'enc:')
        if value.startswith('enc:') and self.secret_manager:
            try:
                return self.secret_manager.decrypt(value[4:])
            except SecurityError as e:
                logger.error(f"Failed to decrypt {key}: {e}")
                if self.security_level == SecurityLevel.PRODUCTION:
                    raise
                return None

        return value

    def set_secret(self, key: str, value: str, encrypt: bool = True):
        """Set secret value with optional encryption."""
        if encrypt and self.secret_manager:
            encrypted = self.secret_manager.encrypt(value)
            os.environ[key] = f"enc:{encrypted}"
        else:
            os.environ[key] = value

        self._sensitive_keys.add(key)
        self._cached_values[key] = value

    def audit(self) -> SecurityAudit:
        """Perform security audit of configuration."""
        return self.validator.validate_all()

    def mask_sensitive_values(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive values in dictionary for logging."""
        masked = {}

        for key, value in data.items():
            if key in self._sensitive_keys or self._is_sensitive_key(key):
                if value:
                    # Show first 2 and last 2 characters
                    if len(str(value)) > 4:
                        masked[key] = f"{str(value)[:2]}***{str(value)[-2:]}"
                    else:
                        masked[key] = "***"
                else:
                    masked[key] = None
            else:
                masked[key] = value

        return masked

    def _is_sensitive_key(self, key: str) -> bool:
        """Check if key name indicates sensitive data."""
        sensitive_patterns = [
            'password', 'secret', 'token', 'api_key', 'apikey',
            'credential', 'auth', 'private', 'cert'
        ]

        key_lower = key.lower()
        # Exact match or contains the pattern as a word
        for pattern in sensitive_patterns:
            if pattern == key_lower or f'_{pattern}' in key_lower or f'{pattern}_' in key_lower:
                return True
        return False

    def export_safe_config(self) -> Dict[str, Any]:
        """Export configuration with sensitive values masked."""
        config = {}

        for key in os.environ:
            if key in self._cached_values:
                value = self._cached_values[key]
            else:
                value = os.environ[key]

            if key in self._sensitive_keys or self._is_sensitive_key(key):
                config[key] = "***REDACTED***"
            else:
                config[key] = value

        return config


class SecurityGuard:
    """Runtime security guard for monitoring and protecting the application."""

    def __init__(self, config: SecureConfig):
        self.config = config
        self.violations: List[Dict[str, Any]] = []
        self.start_time = datetime.utcnow()

    def check_file_permissions(self, path: Path) -> bool:
        """Check if file has secure permissions."""
        if not path.exists():
            return True

        # Check if file is world-readable (security risk for sensitive files)
        stat_info = path.stat()
        mode = stat_info.st_mode

        # Check if others have read permission
        if mode & 0o004:
            self.log_violation(
                "file_permissions",
                f"File {path} is world-readable",
                severity="HIGH"
            )
            return False

        return True

    def check_secure_communication(self) -> bool:
        """Verify secure communication settings."""
        issues = []

        # Check for HTTPS enforcement
        if self.config.security_level == SecurityLevel.PRODUCTION:
            if not os.getenv('ENFORCE_HTTPS', 'false').lower() == 'true':
                issues.append("HTTPS not enforced in production")

            # Check TLS version
            tls_version = os.getenv('TLS_MIN_VERSION', '1.2')
            if float(tls_version) < 1.2:
                issues.append(f"TLS version {tls_version} is below minimum 1.2")

        if issues:
            for issue in issues:
                self.log_violation("secure_communication", issue, severity="HIGH")
            return False

        return True

    def log_violation(self, violation_type: str, message: str, severity: str = "MEDIUM"):
        """Log a security violation."""
        violation = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": violation_type,
            "message": message,
            "severity": severity
        }

        self.violations.append(violation)
        logger.warning(f"Security violation: {violation}")

    def get_security_report(self) -> Dict[str, Any]:
        """Generate security report."""
        audit = self.config.audit()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "uptime": str(datetime.utcnow() - self.start_time),
            "security_level": self.config.security_level.value,
            "audit_results": {
                "score": audit.security_score,
                "total_variables": audit.total_variables,
                "validated": audit.validated_variables,
                "failed": len(audit.failed_validations),
                "missing_required": audit.missing_required,
                "weak_secrets": len(audit.weak_secrets)
            },
            "violations": self.violations,
            "recommendations": self._get_recommendations(audit)
        }

    def _get_recommendations(self, audit: SecurityAudit) -> List[str]:
        """Get security recommendations based on audit."""
        recommendations = []

        if audit.missing_required:
            recommendations.append(
                f"Set required environment variables: {', '.join(audit.missing_required)}"
            )

        if audit.weak_secrets:
            recommendations.append(
                f"Strengthen weak secrets for: {', '.join(audit.weak_secrets)}"
            )

        if audit.security_score < 0.8:
            recommendations.append(
                "Security score below 80%, review configuration security"
            )

        if self.config.security_level == SecurityLevel.DEVELOPMENT:
            recommendations.append(
                "Running in development mode - ensure production uses stronger security"
            )

        return recommendations


# Global secure configuration instance
secure_config = SecureConfig()


# Convenience functions
def validate_environment() -> SecurityAudit:
    """Validate all environment variables."""
    return secure_config.audit()


def get_secure_config(key: str, default: Any = None) -> Any:
    """Get configuration value securely."""
    return secure_config.get(key, default)


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get secret value with decryption."""
    return secure_config.get_secret(key, default)