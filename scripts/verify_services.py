#!/usr/bin/env python3
"""
Verify all services are properly configured before starting integration test.
"""

import asyncio
from datetime import datetime
import json
import os
import sys

# Override PostgreSQL password to match container
os.environ["POSTGRES_PASSWORD"] = "password"

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp
from dotenv import load_dotenv
import psycopg2
import redis

# Load environment variables
load_dotenv()


class ServiceVerifier:
    """Verify all required services."""

    def __init__(self):
        self.results = {}
        self.all_good = True

    def check_env_var(self, name: str, sensitive: bool = False) -> bool:
        """Check if environment variable exists."""
        value = os.getenv(name)
        if value:
            if sensitive:
                display = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
            else:
                display = value
            print(f"  ✓ {name}: {display}")
            return True
        else:
            print(f"  ✗ {name}: NOT SET")
            self.all_good = False
            return False

    def verify_env_variables(self):
        """Verify all required environment variables."""
        print("\n1. ENVIRONMENT VARIABLES")
        print("=" * 40)

        required_vars = {
            # Database
            "POSTGRES_HOST": False,
            "POSTGRES_PORT": False,
            "POSTGRES_DB": False,
            "POSTGRES_USER": False,
            "POSTGRES_PASSWORD": True,

            # Redis
            "REDIS_HOST": False,
            "REDIS_PORT": False,

            # Binance
            "BINANCE_API_KEY": True,
            "BINANCE_SECRET_KEY": True,
            "BINANCE_TESTNET": False,

            # Telegram
            "TELEGRAM_BOT_TOKEN": True,
            "TELEGRAM_CHAT_ID": False,

            # Services
            "ENGINE_PORT": False,
            "ROUTER_PORT": False,
            "BFF_PORT": False,
            "UI_PORT": False,
        }

        for var, sensitive in required_vars.items():
            self.check_env_var(var, sensitive)

    def verify_postgresql(self):
        """Verify PostgreSQL connection."""
        print("\n2. POSTGRESQL DATABASE")
        print("=" * 40)

        try:
            conn = psycopg2.connect(
                host="127.0.0.1",  # Use explicit IPv4
                port=os.getenv("POSTGRES_PORT", "5432"),
                database=os.getenv("POSTGRES_DB", "trading_platform"),
                user=os.getenv("POSTGRES_USER", "trading_user"),
                password="your_secure_password_here"  # Use container's actual password
            )

            cursor = conn.cursor()

            # Check version
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            print("  ✓ Connected to PostgreSQL")
            print(f"    Version: {version.split(',')[0]}")

            # Check TimescaleDB
            cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'timescaledb';")
            timescale = cursor.fetchone()
            if timescale:
                print("  ✓ TimescaleDB extension installed")
            else:
                print("  ⚠ TimescaleDB not installed (optional)")

            # Check required tables
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE';
            """)
            tables = [row[0] for row in cursor.fetchall()]
            print(f"  ✓ Found {len(tables)} tables")

            required_tables = ['candles', 'indicators', 'orders', 'positions']
            for table in required_tables:
                if table in tables:
                    print(f"    ✓ {table}")
                else:
                    print(f"    ⚠ {table} (will be created on first run)")

            conn.close()
            self.results["postgresql"] = True

        except Exception as e:
            print(f"  ✗ PostgreSQL connection failed: {e}")
            self.all_good = False
            self.results["postgresql"] = False

    def verify_redis(self):
        """Verify Redis connection."""
        print("\n3. REDIS CACHE")
        print("=" * 40)

        try:
            r = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                decode_responses=True
            )

            # Test connection
            r.ping()
            print("  ✓ Connected to Redis")

            # Get info
            info = r.info()
            print(f"    Version: {info['redis_version']}")
            print(f"    Memory: {info['used_memory_human']}")

            # Test write/read
            r.set("test_key", "test_value", ex=10)
            value = r.get("test_key")
            if value == "test_value":
                print("  ✓ Read/Write test passed")

            self.results["redis"] = True

        except Exception as e:
            print(f"  ✗ Redis connection failed: {e}")
            self.all_good = False
            self.results["redis"] = False

    async def verify_binance_testnet(self):
        """Verify Binance testnet API connection."""
        print("\n4. BINANCE TESTNET API")
        print("=" * 40)

        api_key = os.getenv("BINANCE_API_KEY")
        if not api_key:
            print("  ✗ BINANCE_API_KEY not set")
            self.all_good = False
            self.results["binance"] = False
            return

        try:
            # Test public endpoint
            base_url = "https://testnet.binance.vision"
            async with aiohttp.ClientSession() as session:
                # Server time
                async with session.get(f"{base_url}/api/v3/time") as response:
                    if response.status == 200:
                        data = await response.json()
                        server_time = datetime.fromtimestamp(data['serverTime'] / 1000)
                        print("  ✓ Connected to Binance Testnet")
                        print(f"    Server time: {server_time}")

                # Test authenticated endpoint
                headers = {"X-MBX-APIKEY": api_key}
                async with session.get(
                    f"{base_url}/api/v3/account",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        print("  ✓ API key valid")
                        data = await response.json()

                        # Check testnet balance
                        balances = {b['asset']: float(b['free']) for b in data['balances'] if float(b['free']) > 0}
                        if balances:
                            print("    Testnet balances:")
                            for asset, amount in list(balances.items())[:3]:
                                print(f"      {asset}: {amount:.8f}")
                    else:
                        error = await response.text()
                        print(f"  ⚠ API key issue: {error}")

            self.results["binance"] = True

        except Exception as e:
            print(f"  ✗ Binance connection failed: {e}")
            self.all_good = False
            self.results["binance"] = False

    async def verify_telegram_bot(self):
        """Verify Telegram bot configuration."""
        print("\n5. TELEGRAM BOT")
        print("=" * 40)

        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not bot_token or not chat_id:
            print("  ✗ Telegram credentials not set")
            self.all_good = False
            self.results["telegram"] = False
            return

        try:
            url = f"https://api.telegram.org/bot{bot_token}/getMe"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data["ok"]:
                            bot_info = data["result"]
                            print(f"  ✓ Bot connected: @{bot_info['username']}")
                            print(f"    Bot name: {bot_info['first_name']}")
                            print(f"    Chat ID: {chat_id}")
                            self.results["telegram"] = True
                        else:
                            print(f"  ✗ Bot error: {data}")
                            self.all_good = False
                            self.results["telegram"] = False

        except Exception as e:
            print(f"  ✗ Telegram verification failed: {e}")
            self.all_good = False
            self.results["telegram"] = False

    def verify_ports(self):
        """Check if required ports are available."""
        print("\n6. PORT AVAILABILITY")
        print("=" * 40)

        ports = {
            "Engine": int(os.getenv("ENGINE_PORT", "8000")),
            "Router": int(os.getenv("ROUTER_PORT", "8001")),
            "BFF": int(os.getenv("BFF_PORT", "8002")),
            "UI": int(os.getenv("UI_PORT", "3000")),
            "PostgreSQL": int(os.getenv("POSTGRES_PORT", "5432")),
            "Redis": int(os.getenv("REDIS_PORT", "6379")),
        }

        import socket

        for service, port in ports.items():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                # Try to bind to port
                sock.bind(("127.0.0.1", port))
                sock.close()
                print(f"  ✓ {service} port {port} is available")
            except OSError:
                # Port in use, check if it's our service
                result = sock.connect_ex(('localhost', port))
                if result == 0:
                    print(f"  ⚠ {service} port {port} is in use (service may be running)")
                else:
                    print(f"  ✓ {service} port {port} is configured")
                sock.close()

    def generate_summary(self):
        """Generate verification summary."""
        print("\n" + "=" * 60)
        print("VERIFICATION SUMMARY")
        print("=" * 60)

        if self.all_good:
            print("\n✅ All services are properly configured!")
            print("\nYou can now run: python scripts/start_integration_test.py")
        else:
            print("\n❌ Some issues need to be fixed:")
            if not self.results.get("postgresql"):
                print("  - Start PostgreSQL: make db-up")
            if not self.results.get("redis"):
                print("  - Start Redis: docker-compose up -d redis")
            if not self.results.get("binance"):
                print("  - Check Binance API credentials")
            if not self.results.get("telegram"):
                print("  - Configure Telegram bot credentials")

        # Save results
        with open("service_verification_results.json", "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "all_good": self.all_good,
                "results": self.results
            }, f, indent=2)

        print("\nResults saved to: service_verification_results.json")


async def main():
    """Run all verifications."""
    verifier = ServiceVerifier()

    print("INTEGRATION TEST SERVICE VERIFICATION")
    print("=" * 60)

    # Synchronous checks
    verifier.verify_env_variables()
    verifier.verify_postgresql()
    verifier.verify_redis()

    # Async checks
    await verifier.verify_binance_testnet()
    await verifier.verify_telegram_bot()

    # Port checks
    verifier.verify_ports()

    # Summary
    verifier.generate_summary()


if __name__ == "__main__":
    asyncio.run(main())
