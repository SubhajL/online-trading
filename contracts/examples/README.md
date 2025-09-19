# Contract Examples

This directory contains example JSON payloads for each contract type defined in the JSONSchema specifications.

## Event Types

### candles.v1.example.json
OHLCV candle data from exchange. Contains price and volume information for a specific trading period.

### features.v1.example.json
Technical indicators calculated from candle data including moving averages, RSI, MACD, and Bollinger Bands.

### zones.v1.example.json
Supply/demand zones identified by Smart Money Concepts analysis, including order blocks and fair value gaps.

### smc_events.v1.example.json
Smart Money Concepts structural events - Change of Character (CHOCH) and Break of Structure (BOS).

### signals_raw.v1.example.json
Candidate trading signals with suggested entry, stop loss, and take profit levels.

### decision.v1.example.json
Final trading decisions with position sizing and risk management parameters.

### order_update.v1.example.json
Order status updates from the exchange router including fills and executions.

### regime.v1.example.json
Market regime classification (trending, ranging, volatile) with trend strength indicators.

### news_window.v1.example.json
Risk windows for news events that may cause high market volatility.

### funding_window.v1.example.json
Risk windows for funding rate events in perpetual futures markets.

## Usage

These examples can be used for:
- Testing JSON Schema validation
- Understanding the expected data structure
- Developing and testing parsers
- Cross-language serialization testing
- Documentation and onboarding