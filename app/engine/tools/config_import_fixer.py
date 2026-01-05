"""Tool to fix imports from config module to models module."""

from pathlib import Path
import re


class ConfigImportFixer:
    """Fixes imports that should be from models instead of config."""

    # Model types that should be imported from models, not config
    MODEL_TYPES = {
        "BaseEvent",
        "EventType",
        "Candle",
        "CandleUpdateEvent",
        "TimeFrame",
        "OrderSide",
        "OrderType",
        "OrderStatus",
        "MarketRegime",
        "PivotPoint",
        "PivotType",
        "SMCSignal",
        "SMCSignalEvent",
        "SupplyDemandZone",
        "ZoneType",
        "RetestSignal",
        "RetestSignalEvent",
        "DecisionEvent",
        "TradingDecision",
        "Order",
        "OrderUpdate",
        "OrderFilledEvent",
        "Position",
        "PositionUpdateEvent",
        "FeaturesCalculatedEvent",
        "TechnicalIndicators",
        "MarketCondition",
        "SignalType",
        "SignalStrength",
        "RawSignal",
        "RawSignalEvent",
        "RegimeUpdateEvent",
        "VolatilityRegime",
    }

    # Config types that should remain in config
    CONFIG_TYPES = {
        "EventBusConfig",
        "DatabaseConfig",
        "RedisConfig",
        "IngestConfig",
        "DecisionConfig",
        "BacktestConfig",
        "PaperTradingConfig",
        "SMCConfig",
        "FeatureConfig",
        "AlertConfig",
        "MonitoringConfig",
    }

    @staticmethod
    def fix_config_imports(content: str) -> str:
        """Fix config imports in the given content."""
        if not content.strip():
            return content

        lines = content.split("\n")
        result_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Check for multi-line import from config
            if re.match(r"^from \.\.config import \($", line):
                import_lines = [line]
                config_imports = []
                model_imports = []
                i += 1

                # Collect all imports until closing parenthesis
                while i < len(lines) and ")" not in lines[i]:
                    import_line = lines[i].strip()
                    if import_line and not import_line.startswith("#"):
                        # Remove trailing comma
                        import_name = import_line.rstrip(",").strip()
                        if import_name in ConfigImportFixer.MODEL_TYPES:
                            model_imports.append(import_name)
                        else:
                            config_imports.append(import_name)
                    i += 1

                # Handle the closing parenthesis line
                if i < len(lines):
                    i += 1

                # Add the imports back
                if config_imports:
                    result_lines.append("from ..config import (")
                    for imp in config_imports[:-1]:
                        result_lines.append(f"    {imp},")
                    if config_imports:
                        result_lines.append(f"    {config_imports[-1]},")
                    result_lines.append(")")

                if model_imports:
                    result_lines.append("from ..models import (")
                    for imp in model_imports[:-1]:
                        result_lines.append(f"    {imp},")
                    if model_imports:
                        result_lines.append(f"    {model_imports[-1]},")
                    result_lines.append(")")

            # Check for single-line import from config
            elif re.match(r"^from \.\.config import ", line):
                match = re.match(r"^from \.\.config import (.+)$", line)
                if match:
                    imports_str = match.group(1)
                    imports = [imp.strip() for imp in imports_str.split(",")]

                    config_imports = []
                    model_imports = []

                    for imp in imports:
                        if imp in ConfigImportFixer.MODEL_TYPES:
                            model_imports.append(imp)
                        else:
                            config_imports.append(imp)

                    if config_imports:
                        result_lines.append(
                            f"from ..config import {', '.join(config_imports)}",
                        )
                    if model_imports:
                        result_lines.append(
                            f"from ..models import {', '.join(model_imports)}",
                        )

                i += 1
            else:
                result_lines.append(line)
                i += 1

        return "\n".join(result_lines)

    @staticmethod
    def fix_file(file_path: str) -> None:
        """Fix config imports in a file."""
        with open(file_path) as f:
            content = f.read()

        fixed_content = ConfigImportFixer.fix_config_imports(content)

        if fixed_content != content:
            with open(file_path, "w") as f:
                f.write(fixed_content)

    @staticmethod
    def get_files_with_config_import_errors(directory: str) -> list[str]:
        """Find all Python files with incorrect config imports."""
        files_with_errors = []

        for py_file in Path(directory).rglob("*.py"):
            # Skip virtual environment
            if ".venv" in py_file.parts or "venv" in py_file.parts:
                continue

            try:
                with open(py_file) as f:
                    content = f.read()

                # Check if file imports model types from config
                if re.search(r"from \.\.config import", content):
                    # Parse the imports to see if any are model types
                    for model_type in ConfigImportFixer.MODEL_TYPES:
                        if re.search(rf"\b{model_type}\b", content):
                            files_with_errors.append(str(py_file))
                            break
            except Exception:
                # Skip files that can't be read
                pass

        return files_with_errors

    @staticmethod
    def fix_all_files(directory: str) -> int:
        """Fix all files with config import errors in a directory."""
        files_with_errors = ConfigImportFixer.get_files_with_config_import_errors(
            directory,
        )

        for file_path in files_with_errors:
            print(f"Fixing config imports in {file_path}")
            ConfigImportFixer.fix_file(file_path)

        return len(files_with_errors)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        directory = "app/engine"

    fixed_count = ConfigImportFixer.fix_all_files(directory)
    print(f"Fixed {fixed_count} files")
