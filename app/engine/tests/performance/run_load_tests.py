#!/usr/bin/env python3
"""
Runner script for load tests.

Usage:
    python run_load_tests.py --scenario normal-load
    python run_load_tests.py --scenario stress-candles --report
    python run_load_tests.py --list-scenarios
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
import json


SCENARIOS = {
    "normal-load": {
        "description": "Normal trading day simulation (50 users)",
        "config": "scenario-normal-load",
        "expected_rps": 100,
        "max_response_time_p95": 500
    },
    "peak-load": {
        "description": "Market open/close peak hours (200 users)",
        "config": "scenario-peak-load",
        "expected_rps": 400,
        "max_response_time_p95": 1000
    },
    "stress-candles": {
        "description": "Stress test candle ingestion pipeline",
        "config": "scenario-stress-candles",
        "expected_rps": 500,
        "max_response_time_p95": 200
    },
    "stress-decisions": {
        "description": "Stress test decision engine",
        "config": "scenario-stress-decisions",
        "expected_rps": 300,
        "max_response_time_p95": 100
    },
    "stress-database": {
        "description": "Database performance testing",
        "config": "scenario-stress-database",
        "expected_rps": 200,
        "max_response_time_p95": 300
    },
    "burst-load": {
        "description": "Test burst load handling (300 users burst)",
        "config": "scenario-burst-load",
        "expected_rps": 1000,
        "max_response_time_p95": 2000
    },
    "endurance": {
        "description": "Long-running endurance test (1 hour)",
        "config": "scenario-endurance",
        "expected_rps": 50,
        "max_response_time_p95": 500
    },
    "hft-simulation": {
        "description": "High-frequency trading simulation",
        "config": "scenario-hft-simulation",
        "expected_rps": 500,
        "max_response_time_p95": 50
    }
}


def list_scenarios():
    """List all available test scenarios."""
    print("\nAvailable Load Test Scenarios:")
    print("=" * 60)
    for name, info in SCENARIOS.items():
        print(f"\n{name}:")
        print(f"  Description: {info['description']}")
        print(f"  Expected RPS: {info['expected_rps']}")
        print(f"  Max P95 Response Time: {info['max_response_time_p95']}ms")


def check_services():
    """Check if required services are running."""
    print("Checking services...")

    # Check if engine is running
    try:
        import requests
        response = requests.get("http://localhost:8001/health/", timeout=2)
        if response.status_code != 200:
            print("⚠️  Engine health check failed")
            return False
        print("✅ Engine is running")
    except Exception as e:
        print(f"❌ Engine is not accessible: {e}")
        return False

    # Check if database is accessible
    try:
        response = requests.get("http://localhost:8001/health/status", timeout=2)
        health_data = response.json()
        db_health = health_data.get("components", {}).get("database", {})
        if db_health.get("status") != "healthy":
            print("⚠️  Database is not healthy")
            return False
        print("✅ Database is healthy")
    except Exception:
        print("❌ Could not check database health")
        return False

    return True


def run_scenario(scenario_name, generate_report=False):
    """Run a specific load test scenario."""
    if scenario_name not in SCENARIOS:
        print(f"❌ Unknown scenario: {scenario_name}")
        list_scenarios()
        return False

    scenario = SCENARIOS[scenario_name]
    print(f"\n🚀 Running scenario: {scenario_name}")
    print(f"   {scenario['description']}")

    # Check services before running
    if not check_services():
        print("\n❌ Required services are not running. Please start the engine first.")
        return False

    # Prepare output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"reports/{scenario_name}_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)

    # Build locust command
    cmd = [
        "locust",
        "--config", "locust_scenarios.conf",
        f"--{scenario['config']}",
        "--csv", f"{output_dir}/stats",
    ]

    if generate_report:
        cmd.extend(["--html", f"{output_dir}/report.html"])

    print(f"\nExecuting: {' '.join(cmd)}")
    print("\n" + "="*60)

    try:
        # Run locust
        result = subprocess.run(cmd, cwd=os.path.dirname(__file__))

        if result.returncode == 0:
            print("\n✅ Load test completed successfully")

            # Analyze results
            analyze_results(output_dir, scenario)

            return True
        else:
            print(f"\n❌ Load test failed with exit code: {result.returncode}")
            return False

    except KeyboardInterrupt:
        print("\n\n⚠️  Load test interrupted by user")
        return False
    except Exception as e:
        print(f"\n❌ Error running load test: {e}")
        return False


def analyze_results(output_dir, scenario):
    """Analyze load test results and check against expectations."""
    print("\n📊 Analyzing Results...")
    print("="*60)

    try:
        # Read stats from CSV
        stats_file = f"{output_dir}/stats_stats.csv"
        if not os.path.exists(stats_file):
            print("⚠️  No stats file found")
            return

        import csv
        with open(stats_file, 'r') as f:
            reader = csv.DictReader(f)
            stats = list(reader)

        if not stats:
            print("⚠️  No statistics collected")
            return

        # Get aggregate stats (usually last row or "Aggregated" row)
        total_stats = None
        for row in stats:
            if row.get('Name') == 'Aggregated' or row.get('Type') == 'Aggregated':
                total_stats = row
                break

        if not total_stats:
            total_stats = stats[-1]  # Use last row if no aggregated

        # Extract metrics
        total_requests = int(total_stats.get('Request Count', 0))
        failure_count = int(total_stats.get('Failure Count', 0))
        median_time = float(total_stats.get('Median Response Time', 0))
        p95_time = float(total_stats.get('95%', 0))
        rps = float(total_stats.get('Requests/s', 0))

        failure_rate = (failure_count / total_requests * 100) if total_requests > 0 else 0

        # Display results
        print(f"Total Requests: {total_requests:,}")
        print(f"Failed Requests: {failure_count:,} ({failure_rate:.2f}%)")
        print(f"Requests/sec: {rps:.2f}")
        print(f"Median Response Time: {median_time:.2f}ms")
        print(f"95th Percentile: {p95_time:.2f}ms")

        # Check against expectations
        print(f"\nPerformance Check:")
        print(f"Expected RPS: {scenario['expected_rps']}")
        print(f"Expected P95: <{scenario['max_response_time_p95']}ms")

        passed = True
        if rps < scenario['expected_rps'] * 0.8:  # Allow 20% margin
            print(f"❌ RPS below expectation: {rps:.2f} < {scenario['expected_rps'] * 0.8:.2f}")
            passed = False
        else:
            print(f"✅ RPS meets expectation")

        if p95_time > scenario['max_response_time_p95']:
            print(f"❌ P95 response time too high: {p95_time:.2f}ms > {scenario['max_response_time_p95']}ms")
            passed = False
        else:
            print(f"✅ P95 response time acceptable")

        if failure_rate > 1.0:  # Allow up to 1% failures
            print(f"❌ Failure rate too high: {failure_rate:.2f}% > 1%")
            passed = False
        else:
            print(f"✅ Failure rate acceptable")

        # Save summary
        summary = {
            "scenario": scenario,
            "timestamp": datetime.now().isoformat(),
            "results": {
                "total_requests": total_requests,
                "failed_requests": failure_count,
                "failure_rate": failure_rate,
                "rps": rps,
                "median_response_time": median_time,
                "p95_response_time": p95_time
            },
            "passed": passed
        }

        with open(f"{output_dir}/summary.json", 'w') as f:
            json.dump(summary, f, indent=2)

        print(f"\n{'✅ PASSED' if passed else '❌ FAILED'}")
        print(f"\nResults saved to: {output_dir}/")

    except Exception as e:
        print(f"❌ Error analyzing results: {e}")


def main():
    parser = argparse.ArgumentParser(description="Run trading platform load tests")
    parser.add_argument("--scenario", "-s", help="Test scenario to run")
    parser.add_argument("--list-scenarios", "-l", action="store_true", help="List available scenarios")
    parser.add_argument("--report", "-r", action="store_true", help="Generate HTML report")
    parser.add_argument("--check-only", "-c", action="store_true", help="Only check if services are running")

    args = parser.parse_args()

    if args.check_only:
        if check_services():
            print("\n✅ All services are running")
            sys.exit(0)
        else:
            print("\n❌ Some services are not running")
            sys.exit(1)

    if args.list_scenarios:
        list_scenarios()
        sys.exit(0)

    if not args.scenario:
        print("❌ No scenario specified. Use --scenario <name> or --list-scenarios")
        list_scenarios()
        sys.exit(1)

    # Check if locust is installed
    try:
        subprocess.run(["locust", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Locust is not installed. Run: pip install locust")
        sys.exit(1)

    # Run the scenario
    success = run_scenario(args.scenario, args.report)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()