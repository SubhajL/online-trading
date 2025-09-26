#!/usr/bin/env python3
"""
Setup script for 5-day integration test.
Creates folder structure and configuration.
"""

import os
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path


def create_test_structure():
    """Create test folder structure."""
    base_dir = f"test_run_{datetime.now().strftime('%Y_%m_%d')}"

    # Create directory structure
    dirs = [
        f"{base_dir}/config",
        f"{base_dir}/logs/engine",
        f"{base_dir}/logs/router",
        f"{base_dir}/logs/bff",
        f"{base_dir}/signals/BTCUSDT",
        f"{base_dir}/signals/ETHUSDT",
        f"{base_dir}/signals/BNBUSDT",
        f"{base_dir}/signals/SOLUSDT",
        f"{base_dir}/signals/MATICUSDT",
        f"{base_dir}/orders/executed",
        f"{base_dir}/orders/failed",
        f"{base_dir}/orders/cancelled",
        f"{base_dir}/snapshots",
        f"{base_dir}/metrics/prometheus_data",
        f"{base_dir}/daily_reports",
        f"{base_dir}/account_history",
    ]

    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)
        print(f"Created: {dir_path}")

    # Create test configuration
    test_config = {
        "test_id": f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "start_date": datetime.now().isoformat(),
        "end_date": (datetime.now() + timedelta(days=5)).isoformat(),
        "initial_capital": {
            "amount": 100000,
            "currency": "THB",
            "usd_equivalent": 2800
        },
        "allocation": {
            "spot": 70000,
            "futures": 30000,
            "reserve_pct": 0.20
        },
        "symbols": [
            {"symbol": "BTCUSDT", "enabled": True, "timeframes": ["15m", "1h"]},
            {"symbol": "ETHUSDT", "enabled": True, "timeframes": ["15m", "1h"]},
            {"symbol": "BNBUSDT", "enabled": True, "timeframes": ["15m", "1h"]},
            {"symbol": "SOLUSDT", "enabled": True, "timeframes": ["15m", "1h"]},
            {"symbol": "MATICUSDT", "enabled": True, "timeframes": ["15m", "1h"]}
        ],
        "risk_management": {
            "risk_per_trade_pct": 0.005,
            "max_concurrent_positions_per_symbol": 3,
            "daily_loss_limit_pct": 0.02,
            "max_exposure_pct": 0.10,
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.03
        },
        "trading_schedule": {
            "days_1_3": {
                "markets": ["spot"],
                "max_leverage": 1
            },
            "days_4_5": {
                "markets": ["spot", "futures"],
                "max_leverage": 2
            }
        },
        "monitoring": {
            "telegram_alerts": True,
            "snapshot_all_signals": True,
            "daily_report_time": "00:00",
            "alert_on_failures": True,
            "prometheus_scrape_interval": "15s"
        }
    }

    # Save configuration
    config_path = f"{base_dir}/config/test_config.json"
    with open(config_path, "w") as f:
        json.dump(test_config, f, indent=2)
    print(f"\nSaved configuration to: {config_path}")

    # Create monitoring script
    create_monitoring_script(base_dir)

    # Create daily report template
    create_report_template(base_dir)

    return base_dir


def create_monitoring_script(base_dir: str):
    """Create monitoring script for the test."""
    script_content = '''#!/usr/bin/env python3
"""
Monitor integration test progress.
Run this to see current status.
"""

import json
import os
from datetime import datetime
from pathlib import Path


def get_test_status():
    """Get current test status."""
    config_path = "config/test_config.json"

    with open(config_path, "r") as f:
        config = json.load(f)

    print("=" * 60)
    print(f"INTEGRATION TEST STATUS - {datetime.now()}")
    print("=" * 60)

    # Count signals
    signal_count = 0
    for symbol_dir in Path("signals").iterdir():
        if symbol_dir.is_dir():
            signals = len(list(symbol_dir.glob("*.json")))
            if signals > 0:
                print(f"{symbol_dir.name}: {signals} signals")
                signal_count += signals

    print(f"\\nTotal signals: {signal_count}")

    # Count orders
    executed = len(list(Path("orders/executed").glob("*.json")))
    failed = len(list(Path("orders/failed").glob("*.json")))
    cancelled = len(list(Path("orders/cancelled").glob("*.json")))

    print(f"\\nOrders:")
    print(f"  Executed: {executed}")
    print(f"  Failed: {failed}")
    print(f"  Cancelled: {cancelled}")

    # Check latest balance
    balance_file = "account_history/balance_history.csv"
    if os.path.exists(balance_file):
        with open(balance_file, "r") as f:
            lines = f.readlines()
            if len(lines) > 1:
                last_line = lines[-1].strip()
                print(f"\\nLatest balance: {last_line}")

    print("=" * 60)


if __name__ == "__main__":
    get_test_status()
'''

    script_path = f"{base_dir}/monitor_status.py"
    with open(script_path, "w") as f:
        f.write(script_content)
    os.chmod(script_path, 0o755)
    print(f"Created monitoring script: {script_path}")


def create_report_template(base_dir: str):
    """Create daily report template."""
    template = '''<!DOCTYPE html>
<html>
<head>
    <title>Daily Trading Report - {date}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background: #2E86C1; color: white; padding: 20px; }
        .metric { background: #f0f0f0; padding: 15px; margin: 10px 0; }
        .positive { color: green; }
        .negative { color: red; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #4CAF50; color: white; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Daily Trading Report</h1>
        <h2>Date: {date}</h2>
    </div>

    <div class="metric">
        <h3>Account Summary</h3>
        <p>Starting Balance: {start_balance} THB</p>
        <p>Ending Balance: {end_balance} THB</p>
        <p>Daily P&L: <span class="{pnl_class}">{daily_pnl} THB ({pnl_pct}%)</span></p>
    </div>

    <div class="metric">
        <h3>Trading Activity</h3>
        <p>Signals Generated: {signal_count}</p>
        <p>Orders Executed: {order_count}</p>
        <p>Win Rate: {win_rate}%</p>
        <p>Average Win: {avg_win} THB</p>
        <p>Average Loss: {avg_loss} THB</p>
    </div>

    <h3>Trade Details</h3>
    <table>
        <tr>
            <th>Time</th>
            <th>Symbol</th>
            <th>Side</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>P&L</th>
            <th>Result</th>
        </tr>
        {trade_rows}
    </table>

    <div class="metric">
        <h3>System Performance</h3>
        <p>Uptime: {uptime}%</p>
        <p>Failed Orders: {failed_orders}</p>
        <p>Average Latency: {avg_latency}ms</p>
    </div>
</body>
</html>'''

    template_path = f"{base_dir}/config/report_template.html"
    with open(template_path, "w") as f:
        f.write(template)
    print(f"Created report template: {template_path}")


if __name__ == "__main__":
    print("Setting up 5-day integration test...")
    print("=" * 60)

    base_dir = create_test_structure()

    print("\n" + "=" * 60)
    print("Setup complete!")
    print(f"Test directory: {base_dir}")
    print("\nNext steps:")
    print("1. Run verify_services.py to check all services")
    print("2. Run start_integration_test.py to begin the test")
    print("3. Monitor progress with monitor_status.py")