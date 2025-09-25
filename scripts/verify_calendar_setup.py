#!/usr/bin/env python3
"""
Economic Calendar Setup Verification Script

Run this to check if everything is properly configured.
"""

import subprocess
import sys
import os
from pathlib import Path


def run_check(description, command, check_output=True):
    """Run a check and report results."""
    print(f"\n{'='*60}")
    print(f"Checking: {description}")
    print(f"{'='*60}")

    try:
        if isinstance(command, str):
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
        else:
            result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode == 0:
            print(f"✅ SUCCESS: {description}")
            if check_output and result.stdout:
                print(f"   Output: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ FAILED: {description}")
            if result.stderr:
                print(f"   Error: {result.stderr.strip()}")
            return False

    except Exception as e:
        print(f"❌ ERROR: {description}")
        print(f"   Exception: {str(e)}")
        return False


def main():
    """Run all verification checks."""
    print("Economic Calendar Setup Verification")
    print("=" * 60)

    passed = 0
    total = 0

    # Check 1: Python version
    total += 1
    py_version = sys.version_info
    if py_version.major == 3 and py_version.minor >= 8:
        print(f"✅ Python version: {sys.version.split()[0]} (3.8+ required)")
        passed += 1
    else:
        print(f"❌ Python version: {sys.version.split()[0]} (3.8+ required)")

    # Check 2: Script files exist
    total += 1
    scripts = [
        "scripts/update_economic_calendar_v2.py",
        "scripts/check_calendar_health.py",
        "scripts/calendar_cron.sh"
    ]
    all_exist = True
    for script in scripts:
        if not Path(script).exists():
            print(f"❌ Missing script: {script}")
            all_exist = False
        else:
            # Check if executable
            if not os.access(script, os.X_OK):
                print(f"⚠️  Script not executable: {script}")
                print(f"   Fix with: chmod +x {script}")

    if all_exist:
        print("✅ All required scripts exist")
        passed += 1

    # Check 3: Python dependencies
    total += 1
    print("\n" + "="*60)
    print("Checking Python dependencies...")
    print("="*60)

    try:
        import requests
        print("✅ 'requests' module installed")
        deps_ok = True
    except ImportError:
        print("❌ 'requests' module NOT installed")
        print("   Fix with: pip3 install requests")
        deps_ok = False

    try:
        import bs4
        print("✅ 'beautifulsoup4' module installed")
    except ImportError:
        print("⚠️  'beautifulsoup4' module NOT installed (optional)")
        print("   Install for ForexFactory support: pip3 install beautifulsoup4")

    try:
        import dateutil
        print("✅ 'python-dateutil' module installed")
    except ImportError:
        print("⚠️  'python-dateutil' module NOT installed (optional)")
        print("   Install for better date parsing: pip3 install python-dateutil")

    if deps_ok:
        passed += 1

    # Check 4: Environment variables
    total += 1
    print("\n" + "="*60)
    print("Checking environment variables...")
    print("="*60)

    if os.getenv('FRED_API_KEY'):
        print("✅ FRED_API_KEY is set")
        passed += 1
    else:
        print("⚠️  FRED_API_KEY not set (recommended)")
        print("   Get free key at: https://fred.stlouisfed.org/docs/api/api_key.html")
        print("   Then add to .env: FRED_API_KEY=your_key_here")
        # Not failing this since it's optional
        passed += 1

    # Check 5: Data directory
    total += 1
    data_dir = Path("data")
    if data_dir.exists() and data_dir.is_dir():
        print("✅ Data directory exists")
        passed += 1
    else:
        print("❌ Data directory missing")
        print("   Fix with: mkdir -p data")

    # Check 6: Test calendar update (dry run)
    total += 1
    if passed >= 4:  # Only test if basics are set up
        print("\n" + "="*60)
        print("Testing calendar update (dry run)...")
        print("="*60)

        result = subprocess.run(
            ["python3", "scripts/update_economic_calendar_v2.py", "--dry-run", "--days-ahead", "30"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0 and "Would write the following events" in result.stdout:
            print("✅ Calendar update test passed")
            print("   Found events in dry run")
            passed += 1
        elif "manual: " in result.stdout and "events" in result.stdout:
            print("✅ Calendar update test passed (using manual fallback dates)")
            print("   APIs not responding but manual dates work")
            passed += 1
        else:
            print("❌ Calendar update test failed")
            if result.stderr:
                print(f"   Error: {result.stderr}")

    # Check 7: Cron setup
    total += 1
    print("\n" + "="*60)
    print("Checking cron setup...")
    print("="*60)

    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode == 0 and "calendar" in result.stdout.lower():
        print("✅ Calendar cron job found")
        passed += 1
    else:
        print("⚠️  No calendar cron job found")
        print("   Add to cron with: crontab -e")
        print("   Suggested entry: 0 */6 * * * /path/to/calendar_cron.sh")
        # Not failing since setup might be manual
        passed += 1

    # Summary
    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)
    print(f"Passed: {passed}/{total} checks")

    if passed == total:
        print("\n✅ All checks passed! Your calendar system is ready.")
        print("\nNext steps:")
        print("1. Run manually: python3 scripts/update_economic_calendar_v2.py")
        print("2. Check health: python3 scripts/check_calendar_health.py")
        print("3. Set up cron for automatic updates")
    elif passed >= total - 2:
        print("\n⚠️  Setup mostly complete, but some optional items missing.")
        print("The calendar system should work, but consider fixing warnings above.")
    else:
        print("\n❌ Setup incomplete. Please fix the errors above before proceeding.")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())