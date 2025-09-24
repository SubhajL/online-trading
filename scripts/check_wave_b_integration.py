#!/usr/bin/env python3
"""
Check Wave B Integration Status

This script verifies that Wave B components (Ingestor, Features, UI/BFF)
are properly integrated and can work together.
"""

import os
import sys
import subprocess
import json
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))


class IntegrationChecker:
    def __init__(self):
        self.results = {
            "ingestor": {},
            "features": {},
            "ui_bff": {},
            "integration": {}
        }

    def check_file_exists(self, filepath: str) -> bool:
        """Check if a file exists."""
        return (project_root / filepath).exists()

    def check_imports(self, filepath: str, imports: list[str]) -> dict:
        """Check if specific imports are present in a file."""
        result = {}
        full_path = project_root / filepath
        if not full_path.exists():
            return {imp: False for imp in imports}

        content = full_path.read_text()
        for imp in imports:
            result[imp] = imp in content
        return result

    def run_command(self, cmd: list[str]) -> tuple[bool, str]:
        """Run a command and return success status and output."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=project_root
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)

    def check_ingestor(self):
        """Check ingestor component integration."""
        print("\n=== Checking Ingestor Component ===")

        # Check core files exist
        files = [
            "app/engine/ingest/ingest_service.py",
            "app/engine/ingest/binance_ws.py",
            "app/engine/ingest/binance_rest.py",
            "app/engine/ingest/binance_spot.py",
            "app/engine/ingest/binance_usdm.py"
        ]

        for file in files:
            exists = self.check_file_exists(file)
            self.results["ingestor"][f"file_{Path(file).name}"] = exists
            print(f"  ✓ {file}" if exists else f"  ✗ {file}")

        # Check main.py integration
        imports = self.check_imports(
            "app/engine/main.py",
            ["from .ingest.ingest_service import IngestService", "IngestService("]
        )
        self.results["ingestor"]["main_integration"] = all(imports.values())
        print(f"\n  Main.py integration: {'✓' if all(imports.values()) else '✗'}")

        # Check event publishing
        event_checks = self.check_imports(
            "app/engine/ingest/binance_ws.py",
            ["CandleUpdateEvent", "event_bus.publish", "await self._event_bus.publish"]
        )
        self.results["ingestor"]["publishes_events"] = all(event_checks.values())
        print(f"  Publishes candle events: {'✓' if all(event_checks.values()) else '✗'}")

    def check_features(self):
        """Check features engine integration."""
        print("\n=== Checking Features Engine ===")

        # Check core files exist
        files = [
            "app/engine/features/feature_service.py",
            "app/engine/features/engine.py",
            "app/engine/features/indicators.py"
        ]

        for file in files:
            exists = self.check_file_exists(file)
            self.results["features"][f"file_{Path(file).name}"] = exists
            print(f"  ✓ {file}" if exists else f"  ✗ {file}")

        # Check event subscription
        event_checks = self.check_imports(
            "app/engine/features/feature_service.py",
            ["CandleUpdateEvent", "subscribe", "async def _handle_candle"]
        )
        self.results["features"]["subscribes_to_candles"] = all(event_checks.values())
        print(f"\n  Subscribes to candle events: {'✓' if all(event_checks.values()) else '✗'}")

        # Check feature calculation
        calc_checks = self.check_imports(
            "app/engine/features/indicators.py",
            ["calculate_ema", "calculate_rsi", "calculate_macd", "calculate_bollinger_bands"]
        )
        self.results["features"]["has_indicators"] = any(calc_checks.values())
        print(f"  Has indicator calculations: {'✓' if any(calc_checks.values()) else '✗'}")

    def check_ui_bff(self):
        """Check UI/BFF integration."""
        print("\n=== Checking UI/BFF Integration ===")

        # Check BFF files
        bff_files = [
            "app/bff/src/main.ts",
            "app/bff/src/app.module.ts",
            "app/bff/src/trading/trading.controller.ts",
            "app/bff/src/trading/trading.service.ts"
        ]

        for file in bff_files:
            exists = self.check_file_exists(file)
            self.results["ui_bff"][f"bff_file_{Path(file).name}"] = exists
            print(f"  ✓ {file}" if exists else f"  ✗ {file}")

        # Check UI files
        ui_files = [
            "app/ui/src/hooks/useMarketData.ts",
            "app/ui/src/hooks/useOrders.ts",
            "app/ui/src/services/api.client.ts",
            "app/ui/src/services/websocket.service.ts"
        ]

        for file in ui_files:
            exists = self.check_file_exists(file)
            self.results["ui_bff"][f"ui_file_{Path(file).name}"] = exists
            print(f"  ✓ {file}" if exists else f"  ✗ {file}")

    def check_integration_flow(self):
        """Check end-to-end integration flow."""
        print("\n=== Checking Integration Flow ===")

        # Check event bus setup
        bus_check = self.check_imports(
            "app/engine/bus.py",
            ["class EventBus", "async def publish", "def subscribe"]
        )
        self.results["integration"]["event_bus_ready"] = all(bus_check.values())
        print(f"  Event bus ready: {'✓' if all(bus_check.values()) else '✗'}")

        # Check database models
        model_check = self.check_imports(
            "app/engine/models.py",
            ["CandleUpdateEvent", "FeatureUpdateEvent", "TimeFrame", "Candle"]
        )
        self.results["integration"]["models_defined"] = all(model_check.values())
        print(f"  Event models defined: {'✓' if all(model_check.values()) else '✗'}")

        # Check config setup
        config_check = self.check_file_exists("app/engine/config.yaml")
        self.results["integration"]["config_exists"] = config_check
        print(f"  Config file exists: {'✓' if config_check else '✗'}")

        # Check integration tests
        print("\n  Integration tests:")
        test_files = [
            "app/engine/tests/integration/test_event_bus_integration.py",
            "app/engine/tests/integration/test_database_integration.py"
        ]
        for test_file in test_files:
            exists = self.check_file_exists(test_file)
            self.results["integration"][f"test_{Path(test_file).name}"] = exists
            print(f"    {'✓' if exists else '✗'} {test_file}")

    def generate_report(self):
        """Generate integration status report."""
        print("\n" + "=" * 50)
        print("WAVE B INTEGRATION STATUS REPORT")
        print("=" * 50)

        # Calculate scores
        total_checks = 0
        passed_checks = 0

        for component, checks in self.results.items():
            component_passed = sum(1 for v in checks.values() if v)
            component_total = len(checks)
            total_checks += component_total
            passed_checks += component_passed

            print(f"\n{component.upper()}: {component_passed}/{component_total} checks passed")
            for check, passed in checks.items():
                status = "✓" if passed else "✗"
                print(f"  {status} {check}")

        # Overall score
        percentage = (passed_checks / total_checks * 100) if total_checks > 0 else 0
        print(f"\n{'=' * 50}")
        print(f"OVERALL: {passed_checks}/{total_checks} ({percentage:.1f}%)")
        print(f"{'=' * 50}")

        # Recommendations
        print("\nRECOMMENDATIONS:")
        if self.results["ingestor"]["main_integration"]:
            print("✓ Ingestor is integrated in main.py")
        else:
            print("✗ Need to integrate IngestService in main.py")

        if self.results["features"]["subscribes_to_candles"]:
            print("✓ Features engine subscribes to candle events")
        else:
            print("✗ Need to set up feature service event subscriptions")

        if percentage < 80:
            print("\n⚠️  Integration is incomplete. Review missing components.")
        else:
            print("\n✅ Wave B integration looks good!")

        return percentage >= 80


def main():
    checker = IntegrationChecker()

    print("Checking Wave B Integration Status...")
    print("Project root:", project_root)

    checker.check_ingestor()
    checker.check_features()
    checker.check_ui_bff()
    checker.check_integration_flow()

    success = checker.generate_report()

    # Save results
    results_file = project_root / "wave_b_integration_results.json"
    with open(results_file, 'w') as f:
        json.dump(checker.results, f, indent=2)
    print(f"\nDetailed results saved to: {results_file}")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())