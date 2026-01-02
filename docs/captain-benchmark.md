# Captain Trading Benchmark System

Compare external Captain Trading signals against your internal SMC engine to measure signal accuracy and robustness.

## Overview

The Captain Trading benchmark system provides:

1. **Signal Ingestion**: Capture signals from Captain Trading's Telegram channel using Telethon
2. **Signal Validation**: Match external signals against internal trading decisions/SMC signals
3. **Outcome Evaluation**: Backtest signals using historical candle data with full cost modeling
4. **Robustness Sweeps**: Test signal performance under varying fee/slippage/funding assumptions
5. **Reporting**: Generate JSON reports with detailed metrics

## Prerequisites

### 1. Telegram API Credentials

You need Telegram User API credentials (not Bot API) to read external channels:

1. Go to https://my.telegram.org/apps
2. Log in with your Telegram account
3. Create a new application
4. Copy your `api_id` and `api_hash`

### 2. System Dependencies

```bash
# Install tesseract for OCR (extracts Entry/SL/TP from chart images)
brew install tesseract  # macOS
apt install tesseract-ocr  # Ubuntu/Debian

# Install Python dependencies
source venv/bin/activate
pip install telethon pytesseract pillow
```

### 3. Database

TimescaleDB must be running with the trading engine schema:

```bash
make db-up
make db-migrate
```

## Configuration

### Environment Variables

Create or update `.env.telegram`:

```bash
# Telegram Bot API (for SENDING alerts from your bot)
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_CHAT_ID=your_chat_id

# Telegram User API (Telethon) - for READING external channels
TELEGRAM_API_ID=your_api_id_from_telegram
TELEGRAM_API_HASH=your_api_hash_from_telegram
TELEGRAM_PHONE=+66xxxxxxxxx

# Captain Trading Channel Configuration
CAPTAIN_TRADING_CHANNEL=2194468323

# Signal matching configuration
SIGNAL_TIME_WINDOW_SECONDS=300
SIGNAL_ENTRY_TOLERANCE=0.002
SIGNAL_OUTCOME_HORIZON_BARS=48
```

Run the setup script:

```bash
python3 scripts/setup_telegram_api.py
```

## Quick Start

### One-Command Benchmark

```bash
# Run full benchmark pipeline (validate + report)
make captain-benchmark

# Run with robustness sweep
make captain-full

# Run benchmark tests
make captain-test
```

### Step-by-Step

```bash
# 1. Ingest recent signals from Captain Trading channel
make captain-ingest CAPTAIN_LIMIT=100

# 2. Validate against internal data
make captain-validate CAPTAIN_HOURS=168

# 3. Generate report with outcomes
make captain-report

# 4. Run robustness sweep (optional)
make captain-sweep CAPTAIN_PRESET=moderate
```

## Makefile Targets

| Target | Description |
|--------|-------------|
| `captain-ingest` | Ingest recent signals from Telegram |
| `captain-listen` | Listen for live signals (continuous) |
| `captain-validate` | Match signals against internal data |
| `captain-report` | Generate benchmark report with outcomes |
| `captain-sweep` | Run robustness sweep |
| `captain-benchmark` | Run validate + report pipeline |
| `captain-full` | Run validate + sweep pipeline |
| `captain-test` | Run all benchmark unit tests |

### Configuration Variables

Override defaults using environment variables:

```bash
# Number of messages to ingest
make captain-ingest CAPTAIN_LIMIT=200

# Hours to look back for validation
make captain-validate CAPTAIN_HOURS=336  # 2 weeks

# Sweep preset (conservative, moderate, aggressive)
make captain-sweep CAPTAIN_PRESET=aggressive

# Signal source identifier
make captain-validate CAPTAIN_SOURCE=captain
```

## CLI Scripts

### Ingestion

```bash
# Ingest last 100 messages
python scripts/captain_benchmark_ingest.py --limit 100

# Listen for live signals
python scripts/captain_benchmark_ingest.py --listen

# Custom source tag
python scripts/captain_benchmark_ingest.py --limit 50 --source my_source
```

### Validation

```bash
# Validate last 24 hours
python scripts/captain_benchmark_validate.py --hours 24

# Validate last week
python scripts/captain_benchmark_validate.py --hours 168 --source captain
```

### Reporting

```bash
# Basic report
python scripts/captain_benchmark_report.py --hours 168

# With outcome evaluation
python scripts/captain_benchmark_report.py --hours 168 --outcomes

# With robustness sweep
python scripts/captain_benchmark_report.py --hours 168 --outcomes --sweep

# JSON output
python scripts/captain_benchmark_report.py --hours 168 --outcomes --json

# Custom sweep preset
python scripts/captain_benchmark_report.py --sweep --sweep-preset aggressive --json
```

## Understanding the Reports

### Agreement Metrics

```json
{
  "agreement_metrics": {
    "total_trade_signals": 150,
    "matched_count": 120,
    "match_rate": 0.80,
    "average_score": 0.72,
    "scores_count": 120
  }
}
```

| Metric | Description |
|--------|-------------|
| `total_trade_signals` | Trade signals received (excludes news alerts) |
| `matched_count` | Signals with internal match found |
| `match_rate` | Fraction of signals matched |
| `average_score` | Mean alignment score (0-1) |

### Outcome Metrics

```json
{
  "outcome_metrics": {
    "eligible_count": 100,
    "tp1_count": 55,
    "sl_count": 30,
    "none_count": 15,
    "win_rate": 0.647
  }
}
```

| Metric | Description |
|--------|-------------|
| `eligible_count` | Signals with entry/SL/TP and candle data |
| `tp1_count` | Signals that hit TP1 |
| `sl_count` | Signals that hit SL |
| `none_count` | Signals neither hit TP nor SL |
| `win_rate` | TP1 / (TP1 + SL) |

### Robustness Sweep

```json
{
  "robustness_sweep": {
    "preset": "moderate",
    "configs_tested": 27,
    "signals_swept": 80,
    "avg_pass_rate": 0.65,
    "results": [...]
  }
}
```

| Metric | Description |
|--------|-------------|
| `preset` | Cost preset used |
| `configs_tested` | Number of cost configurations |
| `signals_swept` | Signals with complete data for sweep |
| `avg_pass_rate` | Mean % of configs with positive PnL |

### Sweep Presets

| Preset | Fee Range (bps) | Slippage Range (bps) | Funding Range (bps) | Configs |
|--------|-----------------|----------------------|---------------------|---------|
| conservative | 5-10 | 0-5 | 0-1 | 8 |
| moderate | 5-20 | 0-10 | 0-2 | 27 |
| aggressive | 5-50 | 0-30 | 0-5 | 125 |

## Validation Snapshots

Each validation captures full engine state for reproducibility:

```json
{
  "payload": {
    "zones": [...],           // Active supply/demand zones
    "structures": [...],      // Recent CHOCH/BOS events
    "guards": {               // Risk guard status
      "news_guard_active": false,
      "funding_guard_active": false
    },
    "regime": {               // Market regime
      "regime": "TRENDING",
      "confidence": 0.85
    },
    "internal_match": {...}   // Matched internal signal
  }
}
```

This enables:
- Reproducible reruns
- "Why did we miss this signal?" debugging
- Zone/structure overlap analysis

## Fill Model

The fill model simulates bracket trades with realistic costs:

### Cost Components

1. **Fees**: Trading fees in basis points (default: 10 bps = 0.1%)
2. **Slippage**: Entry/exit price slippage (default: 5 bps)
3. **Funding**: 8-hour funding rate for futures (default: 1 bps)

### Intrabar Policy

When both SL and TP are touched in the same candle:
- `worst_case` (default): SL wins (conservative)
- `best_case`: TP wins (optimistic)

### Example

```python
from app.engine.telegram_validator.fill_model import (
    BracketSpec, CostConfig, simulate_bracket_fills
)

bracket = BracketSpec(
    side="SELL",
    entry_price=Decimal("95000"),
    stop_loss=Decimal("96500"),
    take_profits=[Decimal("93500")],
    tp_sizes=[Decimal("1.0")],
)

result = simulate_bracket_fills(
    candles=candles,
    bracket=bracket,
    cost_config=CostConfig(fee_bps=10, slippage_bps=5),
)

print(f"Outcome: {result.outcome}")  # TP_FULL, SL, NONE, TIMEOUT
print(f"Net PnL: {result.net_pnl}")
print(f"Fees: {result.fees}")
```

## Troubleshooting

### Authentication Errors

```
Invalid code. Please try again.
```

- Telegram verification code comes via **Telegram app message**, not SMS
- The code expires quickly - enter it promptly
- If you have 2FA enabled, you'll be prompted for your password

### OCR Issues

```
Could not extract levels from image
```

- Ensure `tesseract` is installed: `brew install tesseract`
- Check image quality - OCR works best with clear text
- Some signals don't include chart images with levels

### Database Connection

```
connection refused
```

- Ensure PostgreSQL is running: `make db-up`
- Check `.env` has correct `DB_HOST`, `DB_PORT`, `DB_NAME`
- Run migrations: `make db-migrate`

### No Candle Data

```
Outcome eligible: 0
```

- Signals need historical candle data to evaluate outcomes
- Ensure candles are ingested for the symbols/timeframes
- Check timeframe mapping matches between Captain and your system

## Architecture

```
Captain Trading                    Your System
┌──────────────────┐              ┌──────────────────┐
│ SMC Hybrid       │              │ SMC Engine       │
│ Automation       │              │ (smc/engine.py)  │
└────────┬─────────┘              └────────┬─────────┘
         │                                  │
         ▼                                  ▼
┌──────────────────┐              ┌──────────────────┐
│ Telegram Message │              │ decision.v1      │
│ (via Telethon)   │              │ Event Bus        │
└────────┬─────────┘              └────────┬─────────┘
         │                                  │
         └──────────────┬──────────────────┘
                        ▼
              ┌──────────────────┐
              │ Benchmark        │
              │ Validator        │
              └────────┬─────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │    ValidationResult          │
         │ ├── direction_match: 85%     │
         │ ├── entry_tolerance: 92%     │
         │ ├── smc_pattern_match: 78%   │
         │ └── overall_score: 82%       │
         └─────────────────────────────┘
```

## Files Reference

### Core Modules

| File | Purpose |
|------|---------|
| `app/engine/telegram_validator/captain_ingest.py` | Telethon ingestion |
| `app/engine/telegram_validator/captain_parse.py` | Thai text parsing |
| `app/engine/telegram_validator/captain_image_levels.py` | OCR extraction |
| `app/engine/telegram_validator/benchmark_matcher.py` | Signal matching |
| `app/engine/telegram_validator/benchmark_validator.py` | Validation orchestration |
| `app/engine/telegram_validator/validation_snapshot.py` | Engine state snapshots |
| `app/engine/telegram_validator/fill_model.py` | Bracket simulation |
| `app/engine/telegram_validator/robustness_sweeps.py` | Cost sweeps |
| `app/engine/telegram_validator/outcome_eval.py` | Outcome evaluation |

### Scripts

| File | Purpose |
|------|---------|
| `scripts/captain_benchmark_ingest.py` | Ingestion CLI |
| `scripts/captain_benchmark_validate.py` | Validation CLI |
| `scripts/captain_benchmark_report.py` | Reporting CLI |
| `scripts/setup_telegram_api.py` | Credential setup |
| `scripts/captain_trading_listener.py` | Interactive listener |

### Tests

| File | Coverage |
|------|----------|
| `test_captain_*.py` | Parsing, ingestion, DB |
| `test_benchmark_*.py` | Matching, validation |
| `test_validation_snapshot.py` | Snapshot serialization |
| `test_fill_model.py` | Fill simulation |
| `test_robustness_sweeps.py` | Sweep runner |

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review test files for usage examples
3. Open an issue in the repository
