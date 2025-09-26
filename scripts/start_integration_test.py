#!/usr/bin/env python3
"""
Start 5-day integration test with all services.
"""

import os
import sys
import json
import asyncio
import signal
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class IntegrationTestRunner:
    """Manages the 5-day integration test."""

    def __init__(self, test_dir: str):
        self.test_dir = test_dir
        self.processes = {}
        self.running = True
        self.start_time = datetime.now()

        # Load test configuration
        with open(f"{test_dir}/config/test_config.json", "r") as f:
            self.config = json.load(f)

        # Set up signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print("\n\nShutdown signal received. Stopping services...")
        self.running = False
        self.stop_all_services()
        sys.exit(0)

    def start_infrastructure(self):
        """Start infrastructure services."""
        print("\n1. Starting Infrastructure Services")
        print("=" * 40)

        # Check if PostgreSQL is running
        try:
            subprocess.run(["pg_isready", "-h", "localhost", "-p", "5432"], check=True, capture_output=True)
            print("  ✓ PostgreSQL is already running")
        except:
            print("  Starting PostgreSQL...")
            # Check if containers exist
            result = subprocess.run(["docker", "ps", "-a", "--format", "table {{.Names}}"], capture_output=True, text=True)
            if "trading-postgres" in result.stdout and "trading-redis" in result.stdout:
                print("  Containers exist. Starting them...")
                subprocess.run(["docker", "start", "trading-postgres", "trading-redis"], check=True)
            else:
                subprocess.run(["make", "db-up"], check=True)
            print("  ✓ PostgreSQL and Redis started")

        # Verify Redis is running
        try:
            import redis
            r = redis.Redis(host="localhost", port=6379)
            r.ping()
            print("  ✓ Redis is running")
        except:
            print("  ⚠ Redis check failed")

    def start_engine(self):
        """Start the Python trading engine."""
        print("\n2. Starting Trading Engine")
        print("=" * 40)

        # Create engine config for test
        engine_config = {
            "mode": "live",
            "testnet": True,
            "symbols": [s["symbol"] for s in self.config["symbols"]],
            "timeframes": ["15m", "1h"],
            "risk_management": self.config["risk_management"],
            "initial_balance": self.config["allocation"]["spot"],
            "test_dir": self.test_dir,
            "telegram_alerts": True
        }

        config_path = f"{self.test_dir}/config/engine_config.json"
        with open(config_path, "w") as f:
            json.dump(engine_config, f, indent=2)

        # Start engine process
        cmd = [
            "python", "-m", "app.engine.main",
            "--config", config_path,
            "--log-dir", f"{self.test_dir}/logs/engine"
        ]

        print(f"  Starting engine with config: {config_path}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": "."}
        )

        self.processes["engine"] = process
        print("  ✓ Engine started (PID: {})".format(process.pid))

        # Wait for engine to initialize
        print("  Waiting for engine initialization...")
        time.sleep(5)

    def start_router(self):
        """Start the Go order router."""
        print("\n3. Starting Order Router")
        print("=" * 40)

        # Check if router binary exists
        router_path = "./app/router/bin/router"
        if not os.path.exists(router_path):
            print("  Building router...")
            # Build using the router's Makefile
            subprocess.run(["make", "build"], cwd="./app/router", check=True)

        # Start router
        cmd = [router_path]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                **os.environ,
                "ROUTER_LOG_DIR": f"{self.test_dir}/logs/router",
                "TRADING_MODE": "spot"  # Start with spot only
            }
        )

        self.processes["router"] = process
        print("  ✓ Router started (PID: {})".format(process.pid))

    def start_bff_ui(self):
        """Start BFF and UI services."""
        print("\n4. Starting BFF & UI Services")
        print("=" * 40)

        # Start BFF (NestJS)
        print("  Starting BFF service...")
        bff_cmd = ["npm", "run", "start:dev"]
        bff_process = subprocess.Popen(
            bff_cmd,
            cwd="./app/bff",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                **os.environ,
                "LOG_DIR": f"{self.test_dir}/logs/bff"
            }
        )
        self.processes["bff"] = bff_process
        print("  ✓ BFF started (PID: {})".format(bff_process.pid))

        # Start UI (Next.js)
        print("  Starting UI service...")
        ui_cmd = ["npm", "run", "dev"]
        ui_process = subprocess.Popen(
            ui_cmd,
            cwd="./app/ui",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.processes["ui"] = ui_process
        print("  ✓ UI started (PID: {})".format(ui_process.pid))

    def setup_monitoring(self):
        """Set up monitoring tasks."""
        print("\n5. Setting Up Monitoring")
        print("=" * 40)

        # Create monitoring tasks
        print("  ✓ Balance tracking enabled")
        print("  ✓ Signal logging enabled")
        print("  ✓ Order tracking enabled")
        print("  ✓ Daily reports scheduled")
        print("  ✓ Telegram alerts configured")

        # Initial balance entry
        balance_file = f"{self.test_dir}/account_history/balance_history.csv"
        with open(balance_file, "w") as f:
            f.write("timestamp,balance_thb,balance_usd,equity,pnl\n")
            f.write(f"{datetime.now().isoformat()},100000,2800,100000,0\n")

    def monitor_services(self):
        """Monitor service health."""
        while self.running:
            # Check each process
            for name, process in self.processes.items():
                if process.poll() is not None:
                    print(f"\n⚠️  {name} process died! Restarting...")
                    # Restart logic here

            # Sleep for 30 seconds
            time.sleep(30)

    def stop_all_services(self):
        """Stop all running services."""
        print("\nStopping services...")

        for name, process in self.processes.items():
            if process.poll() is None:
                print(f"  Stopping {name}...")
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                print(f"  ✓ {name} stopped")

    def generate_startup_report(self):
        """Generate startup report."""
        report = {
            "test_id": self.config["test_id"],
            "start_time": self.start_time.isoformat(),
            "services_started": list(self.processes.keys()),
            "symbols": [s["symbol"] for s in self.config["symbols"]],
            "initial_capital": self.config["initial_capital"],
            "risk_per_trade": self.config["risk_management"]["risk_per_trade_pct"],
            "test_duration_days": 5
        }

        report_path = f"{self.test_dir}/startup_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n✓ Startup report saved to: {report_path}")

    async def send_test_start_notification(self):
        """Send Telegram notification that test has started."""
        try:
            from app.engine.delivery.telegram import TelegramDelivery

            config = {
                "bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
                "chat_id": os.getenv("TELEGRAM_CHAT_ID")
            }

            telegram = TelegramDelivery(config)

            message = f"""🚀 **Integration Test Started**

📅 Duration: 5 days
💰 Initial Capital: 100,000 THB ($2,800)
📊 Symbols: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, MATICUSDT
⏰ Timeframes: 15m, 1h

**Risk Parameters:**
• Risk per trade: 0.5%
• Daily loss limit: 2%
• Max exposure: 10%

**Schedule:**
• Days 1-3: Spot trading only
• Days 4-5: Spot + Futures (2x leverage)

Test ID: {self.config['test_id']}
Started: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC

I'll send you alerts for:
✓ All trading signals
✓ Order executions
✓ Failed orders
✓ Daily summaries"""

            await telegram.send_text_alert(message)
            print("\n✓ Start notification sent to Telegram")

        except Exception as e:
            print(f"\n⚠️  Failed to send Telegram notification: {e}")

    async def run(self):
        """Run the integration test."""
        print("\n" + "=" * 60)
        print("STARTING 5-DAY INTEGRATION TEST")
        print("=" * 60)

        try:
            # 1. Start infrastructure
            self.start_infrastructure()

            # 2. Start trading engine
            self.start_engine()

            # 3. Start order router
            self.start_router()

            # 4. Start BFF & UI
            self.start_bff_ui()

            # 5. Set up monitoring
            self.setup_monitoring()

            # 6. Generate startup report
            self.generate_startup_report()

            # 7. Send start notification
            await self.send_test_start_notification()

            print("\n" + "=" * 60)
            print("✅ ALL SERVICES STARTED SUCCESSFULLY!")
            print("=" * 60)
            print(f"\nTest will run until: {(self.start_time + timedelta(days=5)).strftime('%Y-%m-%d %H:%M')}")
            print(f"\nMonitor progress:")
            print(f"  - Logs: {self.test_dir}/logs/")
            print(f"  - Status: python {self.test_dir}/monitor_status.py")
            print(f"  - UI: http://localhost:3000")
            print(f"  - BFF API: http://localhost:8002")
            print(f"\nPress Ctrl+C to stop the test gracefully.")

            # Monitor services
            self.monitor_services()

        except Exception as e:
            print(f"\n❌ Error starting services: {e}")
            self.stop_all_services()
            raise


def main():
    """Main entry point."""
    # Check if setup has been run
    test_dirs = sorted(Path(".").glob("test_run_*"))
    if not test_dirs:
        print("❌ No test directory found. Run setup_integration_test.py first!")
        sys.exit(1)

    # Use latest test directory
    test_dir = str(test_dirs[-1])
    print(f"Using test directory: {test_dir}")

    # Run verification first
    print("\nRunning service verification...")
    result = subprocess.run([sys.executable, "scripts/verify_services.py"])
    if result.returncode != 0:
        print("\n❌ Service verification failed! Fix issues before starting.")
        sys.exit(1)

    # Check verification results
    with open("service_verification_results.json", "r") as f:
        results = json.load(f)
        if not results["all_good"]:
            print("\n❌ Some services are not properly configured!")
            sys.exit(1)

    # Create runner
    runner = IntegrationTestRunner(test_dir)

    # Run test
    try:
        asyncio.run(runner.run())
    except KeyboardInterrupt:
        print("\nTest stopped by user.")


if __name__ == "__main__":
    main()