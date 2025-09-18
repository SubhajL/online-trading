# E2E and Integration Tests

This directory contains end-to-end (E2E) and integration tests for the trading platform UI.

## Test Structure

```
tests/
├── e2e/                    # End-to-end tests
│   ├── trading-flow.spec.ts    # Order placement and management flows
│   ├── market-data.spec.ts     # Chart and market data updates
│   └── auto-trading.spec.ts    # Auto-trading functionality
├── integration/            # Integration tests
│   └── websocket-updates.spec.ts # WebSocket real-time updates
└── fixtures.ts            # Shared page objects and test fixtures
```

## Running Tests

### Prerequisites

Make sure the development server is running on port 3001:

```bash
npm run dev
```

### Run All Tests

```bash
npm run test:e2e
```

### Run Specific Test File

```bash
npx playwright test tests/e2e/trading-flow.spec.ts
```

### Run Tests in UI Mode

```bash
npx playwright test --ui
```

### Run Tests with Specific Browser

```bash
# Chrome only
npx playwright test --project=chromium

# Firefox only
npx playwright test --project=firefox

# Safari only
npx playwright test --project=webkit
```

### Debug Tests

```bash
# Debug mode
npx playwright test --debug

# With browser headed mode
npx playwright test --headed
```

## Test Coverage

### Trading Flow Tests
- Market order placement
- Limit order placement with price
- Order validation and error handling
- Order filtering by status
- Position updates after execution
- Order cancellation
- Real-time balance updates
- Keyboard shortcuts

### Market Data Tests
- Candlestick chart display
- Volume chart display
- Timeframe switching
- Chart zoom and pan
- Loading states
- Error handling
- Data persistence
- Real-time price updates

### Auto Trading Tests
- Toggle auto trading on/off
- Confirmation dialogs
- Statistics display
- Manual order restrictions
- Auto trading indicators
- State persistence
- Error handling
- Emergency stop
- Configuration options

### WebSocket Integration Tests
- Connection establishment
- Real-time price updates
- Order book updates
- Reconnection handling
- Order synchronization
- Subscription management
- Update throttling
- Data consistency
- Error states

## Page Objects

The `fixtures.ts` file contains page object models for better test maintainability:

- **TradingPage**: Main page object with locators for all trading components
  - Order form elements
  - Positions list
  - Order history
  - Auto trading controls
  - Account balance
  - Charts

## Writing New Tests

1. Import the custom test fixture:
   ```typescript
   import { test, expect } from '../fixtures'
   ```

2. Use the `tradingPage` fixture:
   ```typescript
   test('your test name', async ({ tradingPage }) => {
     await tradingPage.goto()
     // Your test logic
   })
   ```

3. Use page object methods for common actions:
   ```typescript
   await tradingPage.placeOrder({
     symbol: 'BTCUSDT',
     side: 'BUY',
     type: 'MARKET',
     quantity: 0.001
   })
   ```

## CI/CD Integration

The tests are configured to run in CI environments:

- Retries: 2 attempts on CI
- Workers: Single worker on CI
- Screenshots: Only on failure
- Videos: Retained on failure
- Traces: Captured on first retry

## Troubleshooting

### Tests Failing Due to Timeouts
- Increase timeout in specific tests: `test.setTimeout(60000)`
- Check if dev server is running on correct port (3001)

### WebSocket Tests Flaky
- WebSocket tests depend on real-time data
- May fail during low market volatility
- Consider mocking WebSocket for more stable tests

### Locator Not Found
- Check if data-testid attributes are present in components
- Update locators in `fixtures.ts` if UI structure changes

### Permission Errors
- Make sure Playwright has necessary permissions
- Run `npx playwright install` to ensure browsers are installed