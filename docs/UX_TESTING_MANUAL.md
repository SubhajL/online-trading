# Comprehensive UX Testing Manual - Online Trading Platform

**Version**: 1.0.0  
**Last Updated**: 2024-10-23  
**Target Platform**: Online Trading Platform (Engine + Router + BFF + UI)

---

## Table of Contents

1. [Pre-Test Setup](#pre-test-setup)
2. [Test Case 1: Authentication & Session Management](#test-case-1-authentication--session-management)
3. [Test Case 2: Order Placement Flow](#test-case-2-order-placement-flow)
4. [Test Case 3: Auto-Trading Toggle](#test-case-3-auto-trading-toggle)
5. [Test Case 4: Real-Time Position Monitoring](#test-case-4-real-time-position-monitoring)
6. [Test Case 5: Order Management](#test-case-5-order-management)
7. [Test Case 6: Dashboard & Data Visualization](#test-case-6-dashboard--data-visualization)
8. [Test Case 7: Balance & Portfolio Tracking](#test-case-7-balance--portfolio-tracking)
9. [Test Case 8: Alerts & Notifications](#test-case-8-alerts--notifications)
10. [Test Case 9: Settings & Preferences](#test-case-9-settings--preferences)
11. [Test Case 10: Market Data & Analysis](#test-case-10-market-data--analysis)
12. [Test Case 11: Trade History & Analytics](#test-case-11-trade-history--analytics)
13. [Test Case 12: Error Handling & Edge Cases](#test-case-12-error-handling--edge-cases)
14. [Test Case 13: Responsive Design & Accessibility](#test-case-13-responsive-design--accessibility)
15. [Test Case 14: Performance & Load Testing](#test-case-14-performance--load-testing)
16. [Test Case 15: Integration Points](#test-case-15-integration-points)
17. [Test Case 16: Advanced Features](#test-case-16-advanced-features)
18. [Test Case 17: Administrative Functions](#test-case-17-administrative-functions)
19. [Test Case 18: Security & Compliance](#test-case-18-security--compliance)
20. [Test Execution Guidelines](#test-execution-guidelines)
21. [Test Reporting Template](#test-reporting-template)

---

## Pre-Test Setup

### Environment Preparation

#### Start All Services

```bash
# Start all services in development mode
make dev

# OR start services individually:
make dev-engine  # Python FastAPI (port 8000)
make dev-router  # Go API Gateway (port 8080)
make dev-bff     # NestJS BFF (port 3001)
make dev-ui      # Next.js UI (port 3000)
```

#### Start Infrastructure

```bash
# Start database services
make db-up       # PostgreSQL + Redis

# Start monitoring stack
make monitoring-up  # Prometheus + Grafana
```

#### Database Setup

```bash
# Run migrations
make db-migrate

# Seed test data (if available)
cd app/engine && python -m scripts.seed_test_data
```

### Access URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| **UI** | http://localhost:3000 | trader@test.com / Test123! |
| **BFF API** | http://localhost:3001 | - |
| **Router** | http://localhost:8080 | - |
| **Engine** | http://localhost:8000 | - |
| **Grafana** | http://localhost:3001 | admin / admin |
| **Prometheus** | http://localhost:9090 | - |

### Testing Environment Priorities

1. **Desktop Chrome/Firefox** (Primary trading interface)
2. **Mobile Safari/Chrome** (Monitoring use case)
3. **Tablet landscape** (Hybrid experience)

### Test Data Conditions

- **Empty State**: New user, no trades, no positions
- **Normal State**: 5-10 active positions, 20-50 orders
- **Heavy State**: 50+ positions, 500+ alerts, 1000+ orders
- **Error State**: API down, invalid data, network issues

---

## Test Case 1: Authentication & Session Management

### TC1.1: Login with Valid Credentials

**Priority**: Critical  
**Duration**: 2 minutes

#### Pre-conditions
- Application is running at http://localhost:3000
- Test user credentials available

#### Test Steps

1. Navigate to http://localhost:3000
2. Locate the login form on the page
3. Enter valid username: `trader@test.com`
4. Enter valid password: `Test123!`
5. Click the "Login" button
6. Open browser DevTools → Network tab
7. Locate the POST request to `/auth/login`
8. Examine the response payload

#### Expected Results

- ✅ Login button shows loading state (spinner/disabled state)
- ✅ Network tab shows 200 OK response
- ✅ Response body contains `access_token` and `refresh_token` fields
- ✅ User is redirected to `/` (dashboard) within 1 second
- ✅ `localStorage` contains `auth_token` key
- ✅ Header displays username "Trader" or email address
- ✅ No console errors in DevTools Console tab

#### Pass/Fail Criteria
All checkpoints must pass for test to pass.

---

### TC1.2: Login with Invalid Credentials

**Priority**: Critical  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to http://localhost:3000
2. Enter username: `wrong@user.com`
3. Enter password: `WrongPass123`
4. Click "Login" button
5. Observe the error message display
6. Check Network tab for response status

#### Expected Results

- ✅ Error message appears: "Invalid credentials" or similar
- ✅ Error message displayed in red/warning color
- ✅ Error persists for at least 3 seconds (or until dismissed)
- ✅ Form fields not cleared (username value retained)
- ✅ User remains on login page (no redirect)
- ✅ No authentication token stored in `localStorage`
- ✅ Network response shows: 401 Unauthorized

#### Notes
Record the exact error message text for documentation purposes.

---

### TC1.3: Session Timeout

**Priority**: High  
**Duration**: 5 minutes

#### Test Steps

1. Log in successfully using valid credentials
2. Navigate to Dashboard
3. Open browser DevTools → Console tab
4. Manually expire the token by running:
   ```javascript
   localStorage.setItem('auth_token', 'expired_token_here')
   ```
5. Make an API call (place order or refresh data)
6. Observe the application behavior

#### Expected Results

- ✅ Toast notification appears: "Session expired. Please log in again."
- ✅ User redirected to login page within 3 seconds
- ✅ Current page URL saved for redirect after re-login
- ✅ If open positions exist, warning modal appears before logout
- ✅ No data loss (draft orders saved to `sessionStorage` if applicable)

#### Cleanup
Log in again after test completion.

---

### TC1.4: Token Refresh During Active Trading

**Priority**: High  
**Duration**: 3 minutes

#### Pre-conditions
- Token expiry configured to short duration (5 minutes) via environment variable
- User logged in

#### Test Steps

1. Log in successfully
2. Note the login timestamp
3. Wait until 4 minutes 30 seconds (30 seconds before expiry)
4. Monitor Network tab for automatic refresh token request
5. Continue using the app (e.g., place an order)
6. Verify new token is used in subsequent requests

#### Expected Results

- ✅ Background refresh request sent automatically at ~4:30 mark
- ✅ New `access_token` received and stored in `localStorage`
- ✅ No interruption to user workflow
- ✅ No logout or session expired message displayed
- ✅ Subsequent API requests use the new token (check Authorization header)

---

### TC1.5: Multi-Tab Session Handling

**Priority**: Medium  
**Duration**: 4 minutes

#### Test Steps

1. Log in on **Tab 1** (main window)
2. Open **Tab 2** → navigate to http://localhost:3000
3. Verify authentication state on Tab 2
4. Place an order on **Tab 1**
5. Switch to **Tab 2** and observe order list
6. Log out from **Tab 2**
7. Switch to **Tab 1** and attempt interaction

#### Expected Results

- ✅ Tab 2 automatically authenticated (shared token from localStorage)
- ✅ Order placed in Tab 1 appears in Tab 2 within 2 seconds
- ✅ Logout in Tab 2 triggers logout in Tab 1
- ✅ Tab 1 shows notification: "Session ended in another tab"
- ✅ Both tabs redirect to login page

---

### TC1.6: Logout with Open Positions

**Priority**: High  
**Duration**: 2 minutes

#### Pre-conditions
- Active position exists (place a market order and wait for fill)

#### Test Steps

1. Log in and place a market order for BTCUSDT
2. Wait for order to fill and verify open position
3. Click "Logout" button in the header
4. Read the warning modal content
5. Click "Cancel" button first
6. Click "Logout" button again
7. Click "Confirm Logout" button

#### Expected Results

- ✅ Modal appears with title: "Open Positions Warning"
- ✅ Modal lists active positions (symbol, size, P&L)
- ✅ Modal shows two buttons: "Cancel" and "Confirm Logout"
- ✅ Clicking "Cancel" closes modal, user remains logged in
- ✅ Clicking "Confirm Logout" clears session and redirects to login
- ✅ Authentication token removed from `localStorage`

---

### TC1.7: Remember Me Functionality

**Priority**: Low  
**Duration**: 5 minutes

#### Test Steps

1. Navigate to login page
2. Enter valid credentials
3. Check the "Remember Me" checkbox
4. Click "Login" button
5. Verify successful login
6. Close browser completely (quit the application)
7. Reopen browser and navigate to http://localhost:3000
8. Observe auto-login behavior

#### Expected Results - With "Remember Me"

- ✅ After reopening browser, user is automatically logged in
- ✅ Dashboard loads without showing login page
- ✅ Token stored with extended expiry (e.g., 30 days)
- ✅ Refresh token persists across browser restarts

#### Expected Results - Without "Remember Me"

- ✅ After browser restart, user sees login page
- ✅ Must re-enter credentials

---

## Test Case 2: Order Placement Flow

### TC2.1: Place Market Order for BTCUSDT

**Priority**: Critical  
**Duration**: 3 minutes

#### Pre-conditions

- User logged in
- Sufficient USDT balance (≥ $50)
- Binance testnet configured and running

#### Test Steps

1. Navigate to Dashboard
2. Locate "Place Order" form/panel
3. Select **Symbol**: BTCUSDT
4. Select **Type**: MARKET
5. Select **Side**: BUY
6. Enter **Quantity**: 0.001 BTC
7. Click "Place Order" button
8. **Start timer** to measure response time
9. Observe UI feedback and order status

#### Expected Results

- ✅ Button shows loading spinner immediately upon click
- ✅ Order submission completes within 500ms
- ✅ Success toast notification appears: "Order placed successfully"
- ✅ Order appears in "Active Orders" section
- ✅ USDT balance decrements immediately (optimistic update)
- ✅ Order status changes to "FILLED" within 2 seconds
- ✅ New position appears in "Open Positions" section
- ✅ Network tab shows POST request to `/api/trading/orders`

#### Performance Metrics

| Metric | Target | Actual |
|--------|--------|--------|
| Order submission latency | < 500ms | _____ ms |
| UI feedback delay | < 100ms | _____ ms |

---

### TC2.2: Place Limit Order with Valid Price

**Priority**: Critical  
**Duration**: 3 minutes

#### Test Steps

1. Navigate to Dashboard
2. Select **Symbol**: ETHUSDT
3. Select **Type**: LIMIT
4. Select **Side**: BUY
5. Enter **Quantity**: 0.01 ETH
6. Get current market price (e.g., $2000)
7. Enter **Limit Price**: $1950 (below current market)
8. Click "Place Order" button

#### Expected Results

- ✅ Order accepted with status "NEW"
- ✅ Order appears in "Active Orders" with label/badge "LIMIT"
- ✅ Order displays price: $1950.00
- ✅ USDT balance reduced by (0.01 × $1950) + estimated fees
- ✅ "Cancel" button available next to the order
- ✅ Order persists after page refresh

---

### TC2.3: Place Bracket Order (Entry + TP + SL)

**Priority**: Critical  
**Duration**: 5 minutes

#### Test Steps

1. Navigate to Dashboard
2. Enable "Bracket Order" toggle/mode
3. Select **Symbol**: BTCUSDT
4. Select **Side**: BUY
5. **Entry Type**: MARKET
6. Enter **Quantity**: 0.001 BTC
7. Set **Stop Loss**: -2% (or specific price)
8. Set **Take Profit 1**: +1.5% (40% of position)
9. Set **Take Profit 2**: +2.0% (30% of position)
10. Set **Take Profit 3**: +3.0% (30% of position)
11. Review the order summary
12. Click "Place Bracket Order" button

#### Expected Results

- ✅ Confirmation modal displays all order legs
- ✅ Modal shows: Entry price, SL price, TP1/TP2/TP3 prices
- ✅ Risk-reward ratio calculated and displayed: ≥ 1.5R
- ✅ Click "Confirm" → all orders submitted as a group
- ✅ Entry order fills immediately (MARKET type)
- ✅ Active Orders shows 4 related orders (SL + TP1/TP2/TP3)
- ✅ Stop Loss order type: STOP_MARKET
- ✅ Take Profit orders type: LIMIT
- ✅ All orders linked by a common Bracket ID

#### Network Validation

Check Network tab → POST to `/api/trading/orders` should contain:

```json
{
  "symbol": "BTCUSDT",
  "side": "BUY",
  "quantity": "0.001",
  "orderType": "MARKET",
  "takeProfitPrices": ["1.5%", "2%", "3%"],
  "stopLossPrice": "-2%",
  "isFutures": false
}
```

---

### TC2.4: Order with Insufficient Balance

**Priority**: High  
**Duration**: 2 minutes

#### Test Steps

1. Check current USDT balance (e.g., $100.00)
2. Calculate order amount exceeding balance (e.g., $150.00)
3. Attempt to place order:
   - **Symbol**: BTCUSDT
   - **Type**: MARKET
   - **Quantity**: Calculate amount for $150 worth
4. Click "Place Order" button

#### Expected Results

- ✅ Error message appears immediately (client-side validation)
- ✅ Error message text: "Insufficient balance. Available: $100.00"
- ✅ Error displayed in red/warning color
- ✅ Order form remains populated (fields not cleared)
- ✅ No API request sent (validated before submission)
- ✅ "Available Balance" field highlighted in UI

---

### TC2.5: Order During High Volatility

**Priority**: Medium  
**Duration**: 3 minutes

#### Pre-conditions
- Simulate high volatility OR test during actual volatile market period
- Volatility guard enabled in config

#### Test Steps

1. Monitor ATR or volatility indicator in system
2. Wait for high volatility condition OR manually trigger via settings
3. Attempt to place MARKET order for volatile symbol
4. Read warning modal

#### Expected Results

- ✅ Warning modal appears: "High Volatility Detected"
- ✅ Modal shows: "Slippage may exceed 0.5%"
- ✅ Options provided: "Proceed Anyway" or "Cancel"
- ✅ If "Proceed", order places with slippage logged
- ✅ Post-execution summary shows: Expected price vs Actual price

---

### TC2.6: Invalid Symbol Format

**Priority**: Medium  
**Duration**: 2 minutes

#### Test Steps

Test the following invalid symbol inputs:

1. Enter `BTC` (incomplete symbol)
2. Enter `BTCUSD` (should be BTCUSDT)
3. Enter `btcusdt` (lowercase)
4. Enter `BTC-USDT` (wrong separator)
5. Attempt to submit each

#### Expected Results

- ✅ Real-time validation shows error beneath input field
- ✅ Error message: "Invalid symbol format. Use format: BTCUSDT"
- ✅ Submit button disabled until valid symbol entered
- ✅ Symbol dropdown suggests valid symbols (autocomplete)
- ✅ Autocomplete helps user select correct format

---

### TC2.7: Rapid Successive Orders (Double-Click Prevention)

**Priority**: High  
**Duration**: 2 minutes

#### Test Steps

1. Prepare order configuration:
   - **Symbol**: BTCUSDT
   - **Type**: MARKET
   - **Quantity**: 0.001 BTC
2. Rapidly **double-click** the "Place Order" button
3. Observe button behavior and network requests

#### Expected Results

- ✅ Button disables immediately after first click
- ✅ Only ONE order submitted (verify in Network tab)
- ✅ Button shows loading state during API processing
- ✅ Second click has no effect (event ignored)
- ✅ Button re-enables after response received
- ✅ No duplicate orders appear in "Active Orders" list

---

### TC2.8: Manual Order with Auto-Trading Enabled

**Priority**: High  
**Duration**: 3 minutes

#### Pre-conditions
- Auto-trading toggle is enabled

#### Test Steps

1. Enable "Auto-Trading" toggle
2. Verify status indicator shows: "Auto-Trading: ON"
3. Manually place market order via UI form
4. Observe order execution and logging

#### Expected Results

- ✅ Manual order processes normally without interference
- ✅ No conflict with auto-trading system
- ✅ Order logs show source tag: "MANUAL"
- ✅ Auto-trading continues to operate independently
- ✅ Both manual and auto orders visible in order list
- ✅ Manual orders distinguishable from automated ones

---

### TC2.9: Order During Exchange Downtime (Circuit Breaker)

**Priority**: Critical  
**Duration**: 5 minutes

#### Pre-conditions
- Ability to simulate exchange downtime or circuit breaker activation

#### Test Steps

1. Simulate downtime by stopping router service:
   ```bash
   docker stop trading-router-dev
   ```
2. Attempt to place an order via UI
3. Observe error handling and user feedback
4. Restart router service:
   ```bash
   docker start trading-router-dev
   ```
5. Verify system recovery

#### Expected Results

- ✅ Error message displays: "Exchange temporarily unavailable"
- ✅ Circuit breaker icon/indicator appears in UI
- ✅ "Retry" button available to user
- ✅ Order optionally queued locally (if feature exists)
- ✅ After service recovery, automatic retry occurs
- ✅ User notified: "Connection restored"
- ✅ Queued orders process successfully

---

## Test Case 3: Auto-Trading Toggle

### TC3.1: Enable Auto-Trading from Disabled State

**Priority**: Critical  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to Dashboard
2. Locate "Auto-Trading" toggle switch
3. Verify current state: **OFF** (grey/inactive)
4. Click the toggle switch
5. Read the confirmation modal content

#### Expected Results

- ✅ Confirmation modal appears immediately
- ✅ Modal title: "Enable Auto-Trading?"
- ✅ Modal warning text: "System will place orders automatically based on signals"
- ✅ Buttons displayed: "Cancel" and "Enable"
- ✅ Click "Enable" → toggle switches to ON (green/active)
- ✅ Status text updates: "Auto-Trading: ENABLED"
- ✅ Toast notification: "Auto-trading enabled successfully"
- ✅ API call made: POST `/api/trading/auto-trading` with `{"enabled": true}`

---

### TC3.2: Disable Auto-Trading with Pending Signals

**Priority**: High  
**Duration**: 3 minutes

#### Pre-conditions
- Auto-trading enabled
- Pending trading signal queued

#### Test Steps

1. Verify auto-trading is ON with at least 1 queued signal
2. Click toggle to disable
3. Read the confirmation dialog content
4. Confirm the action

#### Expected Results

- ✅ Modal warns: "1 pending signal will be cancelled"
- ✅ Options: "Cancel" or "Disable & Cancel Signals"
- ✅ Click "Disable" → toggle switches to OFF
- ✅ Pending signals cancelled immediately
- ✅ No new orders placed from cancelled signals
- ✅ Existing open positions remain unaffected

---

### TC3.3: Toggle During Active Execution

**Priority**: High  
**Duration**: 4 minutes

#### Pre-conditions
- Auto-trading system actively placing an order

#### Test Steps

1. Enable auto-trading
2. Wait for system to begin order execution
3. **Immediately** toggle OFF during execution
4. Observe behavior and order completion

#### Expected Results

- ✅ In-flight order completes successfully (not cancelled mid-execution)
- ✅ Auto-trading disabled after current order finishes
- ✅ No new orders initiated after toggle OFF
- ✅ Status shows: "Disabling... (1 order completing)"
- ✅ Final status updates to: "Auto-Trading: DISABLED"

---

### TC3.4: Auto-Trading Persistence After Refresh

**Priority**: Medium  
**Duration**: 2 minutes

#### Test Steps

1. Enable auto-trading toggle
2. Verify toggle state is ON (green)
3. Refresh browser page (F5 or Cmd+R)
4. Observe toggle state after page reload

#### Expected Results

- ✅ Toggle state persists: remains ON after refresh
- ✅ Status retrieved from API on page load
- ✅ No visual flickering (OFF state then ON)
- ✅ State consistent across multiple browser tabs

---

### TC3.5: Auto-Trading Without Strategy Configured

**Priority**: Medium  
**Duration**: 2 minutes

#### Pre-conditions
- No trading strategy configured in settings

#### Test Steps

1. Clear/disable all trading strategies in Settings
2. Navigate to Dashboard
3. Attempt to enable auto-trading toggle
4. Observe guidance provided to user

#### Expected Results

- ✅ Toggle switch disabled (greyed out, not clickable)
- ✅ Tooltip on hover: "Configure trading strategy first"
- ✅ Info message displayed: "No active strategy. Visit Settings to configure."
- ✅ Link provided to Settings page

---

## Test Case 4: Real-Time Position Monitoring

### TC4.1: Live P&L Updates

**Priority**: Critical  
**Duration**: 3 minutes

#### Pre-conditions
- Open position exists (place market order first)

#### Test Steps

1. Place market order for BTCUSDT and wait for fill
2. Locate the position in "Open Positions" section
3. Identify the P&L column
4. Use stopwatch to measure update frequency
5. Monitor P&L updates for 1 full minute

#### Expected Results

- ✅ P&L updates every 1 second (±0.1s tolerance)
- ✅ Values transition smoothly (no flickering/jumping)
- ✅ Positive P&L displayed in green color
- ✅ Negative P&L displayed in red color
- ✅ Both percentage and absolute values update
- ✅ WebSocket connection indicator shows "Connected"

#### Network Validation

Open DevTools → Network → WS tab → verify WebSocket messages arriving every ~1 second

---

### TC4.2: Position Reaches TP1 (Partial Close)

**Priority**: Critical  
**Duration**: Variable (market-dependent)

#### Pre-conditions
- Bracket order placed with TP1 set at +1.5%

#### Test Steps

1. Place bracket order: BUY BTCUSDT with TP1 at +1.5%
2. Wait for entry order to fill
3. Monitor position as price moves toward TP1
4. Observe behavior when TP1 price is reached

#### Expected Results

- ✅ When price ≥ TP1 trigger price: TP1 order fills
- ✅ Position size reduces by 40% immediately (as configured)
- ✅ Notification appears: "TP1 hit for BTCUSDT (+1.5%)"
- ✅ Stop Loss automatically moves to breakeven price
- ✅ Remaining position displays updated size
- ✅ Realized P&L increases by TP1 profit amount

#### Validation

Navigate to Order History → verify TP1 LIMIT order status = FILLED

---

### TC4.3: Position Hits Stop Loss

**Priority**: Critical  
**Duration**: Variable (market-dependent)

#### Pre-conditions
- Open position with stop loss configured at -2%

#### Test Steps

1. Place order with SL set at -2% below entry
2. Simulate or wait for price to drop to SL trigger level
3. Observe position closure

#### Expected Results

- ✅ Stop loss triggers immediately when price touches SL level
- ✅ Entire position closes completely
- ✅ Notification: "Stop Loss hit for BTCUSDT (-2.0%)"
- ✅ Position removed from "Open Positions" section
- ✅ Position appears in "Trade History" with final P&L
- ✅ Account balance updated with loss deducted

---

### TC4.4: Multiple Positions Across Symbols

**Priority**: High  
**Duration**: 5 minutes

#### Test Steps

1. Open position: BTCUSDT (LONG, 0.001 BTC)
2. Open position: ETHUSDT (LONG, 0.01 ETH)
3. Open position: SOLUSDT (SHORT, 0.1 SOL)
4. View all three in "Open Positions" table
5. Observe independent price updates

#### Expected Results

- ✅ All 3 positions visible simultaneously in table
- ✅ Each position updates independently
- ✅ Separate P&L calculations for each
- ✅ Total portfolio P&L sums all positions correctly
- ✅ No cross-contamination of data between positions
- ✅ Each position has own SL/TP orders visible

---

### TC4.5: Rapid Price Movements (No Flickering)

**Priority**: High  
**Duration**: 2 minutes

#### Pre-conditions
- High-frequency price updates (volatile market or simulated)

#### Test Steps

1. Open position in highly volatile symbol
2. Observe P&L display during rapid price changes
3. Record visual quality and performance

#### Expected Results

- ✅ Numbers update smoothly at 60fps (no jank)
- ✅ No jarring color flashes or blinks
- ✅ Font weight and size remain stable
- ✅ Table layout doesn't shift/reflow
- ✅ Transitions use smooth CSS animations (fade/slide)
- ✅ Overall performance remains smooth (no UI lag)

#### Performance Check

DevTools → Performance → Record → verify 60fps maintained

---

### TC4.6: Unrealized vs Realized P&L Accuracy

**Priority**: High  
**Duration**: 5 minutes

#### Test Steps

1. Note starting account balance: $1,000.00
2. Place order: BUY 0.01 ETH at $2,000 = $20.00 cost
3. Wait for price to move to $2,100
4. Observe unrealized P&L: should be ~$1.00
5. Close position at $2,100
6. Verify realized P&L and final balance

#### Expected Results

- ✅ While position open: Unrealized P&L = +$1.00 (green)
- ✅ After position closed: Realized P&L = +$1.00
- ✅ Unrealized P&L resets to $0.00
- ✅ Account balance = $1,000 + $1.00 - fees ≈ $1,000.98
- ✅ Trade appears in history with P&L = +$1.00
- ✅ Calculations match exchange API records

#### Manual Calculation

```
Entry:     0.01 ETH × $2,000 = $20.00
Exit:      0.01 ETH × $2,100 = $21.00
Gross P&L: $21.00 - $20.00 = $1.00
Fees:      ($20.00 + $21.00) × 0.1% = -$0.04
Net P&L:   $1.00 - $0.04 = $0.96
```

---

## Test Case 5: Order Management

### TC5.1: View Active Orders with Filtering

**Priority**: High  
**Duration**: 3 minutes

#### Pre-conditions
- Multiple orders with different statuses exist:
  - 2× LIMIT orders (status: NEW)
  - 1× MARKET order (status: FILLED)
  - 1× Cancelled order (status: CANCELED)

#### Test Steps

1. Navigate to "Orders" page or tab
2. View default order list (all orders)
3. Locate filter dropdown or buttons
4. Select filter: **NEW**
5. Select filter: **FILLED**
6. Select filter: **CANCELED**
7. Select filter: **ALL**

#### Expected Results

- ✅ Default view shows all 4 orders
- ✅ Filter "NEW" displays only 2 orders
- ✅ Filter "FILLED" displays only 1 order
- ✅ Filter "CANCELED" displays only 1 order
- ✅ Filter "ALL" displays all 4 orders
- ✅ Selected filter persists during page navigation
- ✅ Count badge updates to show filtered count

---

### TC5.2: Cancel Pending Limit Order

**Priority**: Critical  
**Duration**: 2 minutes

#### Pre-conditions
- Active LIMIT order exists (not yet filled)

#### Test Steps

1. Locate pending LIMIT order in "Active Orders" list
2. Click "Cancel" button (or X/trash icon)
3. **Start timer** to measure cancellation time
4. Observe order removal from list

#### Expected Results

- ✅ Order removed from list within 2 seconds
- ✅ Loading spinner appears on cancel button during request
- ✅ Success toast notification: "Order cancelled successfully"
- ✅ Locked balance released immediately
- ✅ Order appears in Order History with status: CANCELED
- ✅ Network request: DELETE `/api/trading/orders/:orderId`

#### Performance Metric

| Metric | Target | Actual |
|--------|--------|--------|
| Cancellation latency | < 2000ms | _____ ms |

---

### TC5.3: Cancel All Orders for Symbol

**Priority**: High  
**Duration**: 3 minutes

#### Pre-conditions
- Multiple active LIMIT orders for BTCUSDT

#### Test Steps

1. Place 5 LIMIT orders for BTCUSDT at various prices
2. Locate "Cancel All" button (symbol-specific or global)
3. Click "Cancel All for BTCUSDT"
4. Read confirmation modal
5. Click "Confirm Cancel All" button
6. Observe cancellation progress

#### Expected Results

- ✅ Confirmation modal lists all 5 orders to be cancelled
- ✅ Modal shows estimated time: ~2-5 seconds
- ✅ Progress indicator appears: "Cancelling 1 of 5..."
- ✅ Orders remove from list one by one (or all at once)
- ✅ Final notification: "All orders cancelled (5 successful)"
- ✅ All orders moved to history with CANCELED status
- ✅ If any fail, error shown: "4 of 5 cancelled, 1 failed"

---

### TC5.4: Modify Stop Loss on Open Position

**Priority**: High  
**Duration**: 3 minutes

#### Pre-conditions
- Open position with existing Stop Loss order

#### Test Steps

1. Locate open position for BTCUSDT in positions table
2. Note current Stop Loss price: e.g., $40,000
3. Click "Edit SL" or "Modify" button on position row
4. Change Stop Loss to: $41,000 (tighter stop)
5. Click "Update" button
6. Verify change propagated to exchange

#### Expected Results

- ✅ Edit modal opens with current SL price pre-filled
- ✅ Input field validated (SL must be below entry for LONG)
- ✅ Click "Update" → success confirmation message
- ✅ Position table displays new SL: $41,000
- ✅ Old SL order cancelled on exchange
- ✅ New SL order placed on exchange with new price
- ✅ Order ID updated in UI

#### Exchange Validation

Check Binance testnet order list → verify:
- Old SL order shows status: CANCELED
- New SL order shows status: NEW with price $41,000

---

### TC5.5: Order History Pagination

**Priority**: Medium  
**Duration**: 3 minutes

#### Pre-conditions
- Order history contains 50+ orders

#### Test Steps

1. Navigate to "Order History" page
2. Observe initial page load (should show 20 orders)
3. Scroll to bottom of the list
4. Click "Load More" button OR trigger infinite scroll
5. Verify next batch of 20 orders loads
6. Repeat until all orders visible

#### Expected Results

- ✅ Initial load displays 20 orders
- ✅ Load time < 1 second
- ✅ Smooth scrolling experience (no jank)
- ✅ "Load More" button visible at bottom
- ✅ Next 20 orders append to list (don't replace existing)
- ✅ Scroll position maintained after new data loads
- ✅ When all loaded: "No more orders" message displayed
- ✅ Total count shown: "Showing 50 of 50 orders"

---

### TC5.6: Real-Time Order Status Transitions

**Priority**: High  
**Duration**: 4 minutes

#### Pre-conditions
- WebSocket connection active and healthy

#### Test Steps

1. Place large LIMIT order (unlikely to fill immediately)
2. Keep "Active Orders" list visible on screen
3. Manually fill partial amount on Binance testnet
4. Observe status update in UI
5. Fill remaining amount
6. Observe final status transition

#### Expected Results

- ✅ Initial status displays: NEW
- ✅ After partial fill: status changes to PARTIALLY_FILLED
- ✅ Filled quantity updates: "0.005 of 0.01 filled"
- ✅ Visual progress bar shows 50% completion
- ✅ After full fill: status changes to FILLED
- ✅ Order moves from "Active Orders" to "Completed Orders"
- ✅ All updates occur within 2 seconds of exchange event

#### WebSocket Validation

DevTools → Network → WS tab → verify execution report message:
```json
{
  "type": "executionReport",
  "status": "PARTIALLY_FILLED",
  "filledQuantity": "0.005",
  ...
}
```

---

## Test Case 6: Dashboard & Data Visualization

### TC6.1: Initial Dashboard Load Performance

**Priority**: Critical  
**Duration**: 3 minutes

#### Test Steps

1. Clear browser cache completely (Cmd+Shift+Delete)
2. Log out of application
3. Log in with fresh credentials
4. **Start performance timer**
5. Navigate to dashboard
6. Wait for all widgets to fully populate
7. **Stop timer**

#### Expected Results

- ✅ Total load time: < 3 seconds
- ✅ Skeleton loaders appear immediately (within 100ms)
- ✅ Widgets populate progressively (not all at once)
- ✅ Chart renders within 2 seconds
- ✅ Balances section loads within 1 second
- ✅ No "flash of unstyled content" (FOUC)
- ✅ No layout shifts after initial render

#### Performance Profiling

Open DevTools → Lighthouse → Run audit

- ✅ LCP (Largest Contentful Paint): < 2.5s
- ✅ FID (First Input Delay): < 100ms
- ✅ CLS (Cumulative Layout Shift): < 0.1

---

### TC6.2: Real-Time Candlestick Updates

**Priority**: High  
**Duration**: 2 minutes

#### Pre-conditions
- Chart displaying 5-minute timeframe

#### Test Steps

1. Open chart for BTCUSDT symbol
2. Observe current forming candle (rightmost)
3. Watch candle update in real-time
4. Wait for 5 minutes to complete
5. Observe new candle creation
6. Monitor frame rate throughout

#### Expected Results

- ✅ Current candle updates every 1 second
- ✅ OHLC (Open/High/Low/Close) values change smoothly
- ✅ When 5-minute period expires: new candle appears
- ✅ Previous candle closes at exact timestamp
- ✅ Chart auto-scrolls to display latest data
- ✅ Animation maintains smooth 60fps
- ✅ No gaps or missing data between candles

#### Frame Rate Check

DevTools → Rendering → FPS meter → verify consistent 60fps

---

### TC6.3: Switch Timeframes

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Chart currently showing 5-minute timeframe
2. Click "1m" timeframe button
3. Observe chart redraw
4. Click "15m" button
5. Click "1h" button
6. Click "4h" button
7. Return to "5m" button

#### Expected Results

- ✅ Each switch triggers brief loading indicator
- ✅ Chart redraws within 500ms per switch
- ✅ Correct number of candles displayed for timeframe
- ✅ X-axis time labels update appropriately
- ✅ Y-axis price scale adjusts to new data range
- ✅ Selected timeframe button highlighted (active state)
- ✅ Chart zoom level maintained (if applicable)

#### Data Validation

Verify candle intervals:
- **1m**: Each candle represents 1 minute
- **5m**: Each candle represents 5 minutes
- **1h**: Each candle represents 60 minutes
- **4h**: Each candle represents 240 minutes

---

### TC6.4: Overlay Technical Indicators

**Priority**: Medium  
**Duration**: 4 minutes

#### Test Steps

1. Open chart settings or indicators menu
2. Enable indicator: **EMA 21**
3. Observe EMA line overlay
4. Enable indicator: **RSI**
5. Observe RSI subplot
6. Enable indicator: **MACD**
7. Observe MACD subplot
8. Disable RSI indicator
9. Observe RSI removal
10. Save configuration

#### Expected Results

- ✅ EMA line overlays on main price chart (blue color)
- ✅ RSI subplot appears below chart (0-100 scale, with 30/70 lines)
- ✅ MACD subplot appears with histogram and signal line
- ✅ Indicator values calculate correctly (spot-check accuracy)
- ✅ Disabling RSI removes subplot immediately
- ✅ Configuration persists after page refresh

#### Accuracy Validation

Manually calculate EMA for last candle and compare with displayed value (±0.1% tolerance acceptable)

---

### TC6.5: Empty State (No Positions/Orders)

**Priority**: Medium  
**Duration**: 2 minutes

#### Pre-conditions
- New account with no trading activity

#### Test Steps

1. Log in with fresh test account
2. Navigate to Dashboard
3. Observe each widget/section

#### Expected Results

- ✅ **Open Positions**: "No open positions. Place your first order to get started!"
- ✅ **Active Orders**: "No active orders."
- ✅ **Balances**: Shows initial balance (e.g., $10,000 paper trading funds)
- ✅ **Chart**: Displays with default symbol (BTCUSDT)
- ✅ Call-to-action button prominently displayed: "Place Order"
- ✅ Empty states include helpful icons or illustrations
- ✅ No broken UI elements or errors

---

### TC6.6: Chart Zoom and Pan

**Priority**: Medium  
**Duration**: 3 minutes

#### Test Steps

1. Display chart with ~100 candles visible
2. **Zoom in**: Scroll mouse wheel forward
3. **Zoom out**: Scroll mouse wheel backward
4. **Pan left**: Click and drag chart to the left (view past)
5. **Pan right**: Drag right (return to present)
6. **Reset**: Double-click chart to reset zoom

#### Expected Results

- ✅ Zoom in: Fewer candles displayed, more detail visible
- ✅ Zoom out: More candles displayed, less detail
- ✅ Pan left: Historical data loads automatically (lazy loading)
- ✅ Pan right: Returns to current real-time data
- ✅ Double-click: Resets to default zoom level and timeframe
- ✅ Zoom level indicator displays current scale
- ✅ Performance remains smooth during all interactions

---

### TC6.7: Multiple Chart Tabs

**Priority**: Low  
**Duration**: 3 minutes

#### Test Steps

1. Open chart tab for BTCUSDT (default)
2. Click "+" button to open new tab
3. Switch new tab to ETHUSDT
4. Open third tab for SOLUSDT
5. Switch between all tabs
6. Close the middle tab (ETHUSDT)

#### Expected Results

- ✅ Each tab maintains independent symbol selection
- ✅ Each tab maintains independent timeframe setting
- ✅ Switching tabs is instant (no reload/delay)
- ✅ All tabs update in real-time (background updates)
- ✅ Closing tab removes it smoothly without affecting others
- ✅ Tab order adjustable via drag-and-drop
- ✅ Warning shown when attempting to open > 5 tabs

---

## Test Case 7: Balance & Portfolio Tracking

### TC7.1: View Spot Balances

**Priority**: High  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to Portfolio or Balances page
2. Locate "Spot Balances" section
3. Review asset list and details

#### Expected Results

- ✅ All assets with balance > $0 displayed in list
- ✅ Each row shows: Asset name, Amount, USD Value
- ✅ USD values calculated using current market price
- ✅ Total portfolio value displayed at top
- ✅ Assets sorted by USD value (descending order)
- ✅ Small balances (< $1) optionally hidden by default
- ✅ "Show All Assets" toggle includes dust amounts

#### Example Display

```
Asset    Amount        USD Value
USDT     1,234.56      $1,234.56
BTC      0.0123        $507.30
ETH      0.456         $912.00
────────────────────────────────
Total Portfolio Value: $2,653.86
```

---

### TC7.2: View Futures Balances

**Priority**: High  
**Duration**: 3 minutes

#### Pre-conditions
- USD-M Futures account active and funded

#### Test Steps

1. Switch to "Futures" tab in Balances section
2. Review displayed information

#### Expected Results

- ✅ **Available Balance**: $X,XXX.XX displayed
- ✅ **Margin Balance**: $X,XXX.XX displayed
- ✅ **Unrealized PnL**: +$XXX.XX or -$XXX.XX (color-coded)
- ✅ **Margin Ratio**: XX.X% (with warning colors if high)
- ✅ **Liquidation Price**: $XX,XXX.XX (if position open)
- ✅ **Leverage Indicator**: 3x, 5x, 10x, etc. clearly shown
- ✅ Warning banner if margin ratio > 80%

---

### TC7.3: Balance Updates After Order Fill

**Priority**: Critical  
**Duration**: 3 minutes

#### Test Steps

1. Note starting USDT balance: e.g., $1,000.00
2. Place market order: BUY 0.01 ETH at current price ~$2,000
3. Wait for order to fill
4. Observe balance section update

#### Expected Results

- ✅ **Before fill**: USDT = $1,000.00
- ✅ **After fill**: USDT ≈ $980.00 (minus cost + fees)
- ✅ ETH balance increases: 0 → 0.01 ETH
- ✅ Update occurs within 1 second of fill
- ✅ WebSocket message triggers real-time update
- ✅ No page refresh required
- ✅ Transaction appears in balance change history

#### Manual Calculation

```
Order Cost:  0.01 ETH × $2,000 = $20.00
Trading Fee: $20.00 × 0.1% = $0.02
Total Cost:  $20.00 + $0.02 = $20.02
New Balance: $1,000.00 - $20.02 = $979.98
```

---

### TC7.4: Cross-Margin vs Isolated Margin Display

**Priority**: Medium  
**Duration**: 3 minutes

#### Pre-conditions
- Futures trading enabled with multiple positions

#### Test Steps

1. View futures positions list
2. Locate margin type indicator on each position
3. Switch a position to Isolated margin (if UI allows)
4. Observe display changes

#### Expected Results

- ✅ Cross-Margin positions display: "CROSS" badge
- ✅ Isolated positions display: "ISOLATED" badge
- ✅ Isolated positions show: "Margin: $XXX / $XXX used"
- ✅ Cross-margin positions share total account balance
- ✅ Liquidation price differs between margin modes
- ✅ Clear tooltip/legend explains the difference

---

### TC7.5: Asset Allocation Pie Chart

**Priority**: Medium  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to Portfolio Analytics page
2. Locate "Asset Allocation" pie chart widget
3. Hover over each segment
4. Click legend items to toggle visibility

#### Expected Results

- ✅ Pie chart displays all assets proportionally by value
- ✅ Hover tooltip shows: "BTC: 45.2% ($1,234.56)"
- ✅ All percentages sum to 100% (±0.1% rounding tolerance)
- ✅ Colors are distinct and accessible (WCAG compliant)
- ✅ Legend lists all assets with percentages
- ✅ Small allocations (< 2%) grouped into "Other" category
- ✅ Chart updates dynamically when balances change

---

### TC7.6: Historical Portfolio Value Chart

**Priority**: Medium  
**Duration**: 3 minutes

#### Test Steps

1. Locate "Portfolio Performance" line chart
2. Select time range: **7 Days**
3. Select time range: **30 Days**
4. Select time range: **All Time**
5. Hover over data points

#### Expected Results

- ✅ Line chart displays portfolio value over selected time range
- ✅ Y-axis: USD portfolio value
- ✅ X-axis: Time (clearly labeled with dates)
- ✅ Hover tooltip shows: "Dec 1, 2024: $9,850.32"
- ✅ Line color: green if overall profit, red if overall loss
- ✅ Percentage change displayed: "+5.2%" or "-3.1%"
- ✅ Data points match actual trade history records

#### Accuracy Validation

Cross-reference chart data with trade history to ensure accuracy

---

## Test Case 8: Alerts & Notifications

### TC8.1: Order Fill Notification

**Priority**: High  
**Duration**: 2 minutes

#### Test Steps

1. Place market order for any symbol
2. Wait for order to fill
3. Observe notification appearance

#### Expected Results

- ✅ Toast notification appears (typically top-right corner)
- ✅ Content: "Order Filled: BUY 0.001 BTCUSDT at $41,234.56"
- ✅ Icon: Green checkmark or success icon
- ✅ Auto-dismisses after 5 seconds
- ✅ Click notification → navigates to order details page
- ✅ Sound effect plays (if sound enabled in settings)
- ✅ Browser notification appears (if permission granted)

---

### TC8.2: Price Alert Triggers

**Priority**: High  
**Duration**: Variable (market-dependent)

#### Pre-conditions
- Price alert configured for BTCUSDT at specific price (e.g., $42,000)

#### Test Steps

1. Navigate to Alerts settings
2. Set alert: "Notify when BTC price > $42,000"
3. Wait for price to reach target level
4. Observe multi-channel notification delivery

#### Expected Results

- ✅ In-app toast notification: "Price Alert: BTC reached $42,000"
- ✅ Browser desktop notification (if permission granted)
- ✅ Sound effect or chime plays
- ✅ Alert marked as "Triggered" in alerts list
- ✅ Option provided: "Dismiss" or "Set New Alert"
- ✅ Alert history logs the trigger event

---

### TC8.3: Risk Limit Breach Alert

**Priority**: Critical  
**Duration**: 3 minutes

#### Pre-conditions
- Daily loss limit configured: $100.00

#### Test Steps

1. Configure risk settings: Daily loss limit = $100.00
2. Execute losing trades totaling $100+ in losses
3. Attempt to place another order
4. Observe blocking mechanism

#### Expected Results

- ✅ Modal dialog blocks order submission
- ✅ Modal title: "Risk Limit Reached"
- ✅ Content: "Daily loss limit ($100.00) exceeded. Trading temporarily disabled."
- ✅ Current loss displayed: "Today's Loss: -$102.50"
- ✅ Options: "View Positions" or "Adjust Risk Limits"
- ✅ Cannot bypass without modifying settings or admin override
- ✅ Notification sent to risk manager/admin (if configured)

---

### TC8.4: WebSocket Disconnection Alert

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Open Dashboard with active WebSocket connection
2. Verify connection indicator shows "Connected"
3. Simulate disconnection:
   - **Method A**: DevTools → Network → Set to Offline mode
   - **Method B**: Temporarily stop BFF service
4. Observe alert display
5. Restore connection
6. Observe recovery behavior

#### Expected Results

- ✅ Within 5 seconds: Yellow/warning banner appears
- ✅ Message: "Connection lost. Attempting to reconnect..."
- ✅ Live data stops updating (prices freeze)
- ✅ WebSocket icon shows "Disconnected" state
- ✅ After reconnection: Green success banner "Connected"
- ✅ Data resumes real-time updates
- ✅ Success banner auto-dismisses after 3 seconds

---

### TC8.5: Mark Notification as Read

**Priority**: Medium  
**Duration**: 2 minutes

#### Test Steps

1. Generate 3 notifications (e.g., place 3 orders)
2. Locate notification bell icon in header
3. Verify badge shows: "3"
4. Open notifications dropdown/panel
5. Click "Mark as Read" on first notification
6. Verify badge updates to "2"
7. Click "Mark All as Read" button
8. Verify badge shows "0"

#### Expected Results

- ✅ Badge count updates: 3 → 2 → 0
- ✅ Individual mark: notification appearance changes (grey/lower opacity)
- ✅ "Mark All as Read": badge clears immediately
- ✅ Unread count persists after page refresh
- ✅ API request logged: PUT `/api/alerts/:id/read`
- ✅ Read notifications remain in history

---

### TC8.6: Filter Alerts by Severity

**Priority**: Medium  
**Duration**: 2 minutes

#### Pre-conditions
- Alert history contains alerts of different severities (INFO, WARNING, CRITICAL)

#### Test Steps

1. Navigate to Alerts/Notifications page
2. View all alerts (default: mixed severities)
3. Click filter button: "Critical Only"
4. Observe filtered results
5. Click filter: "Warning Only"
6. Click filter: "All"

#### Expected Results

- ✅ Filter buttons available: All, Info, Warning, Critical
- ✅ Active filter visually highlighted
- ✅ "Critical" filter shows only critical alerts
- ✅ Count updates: "Showing 5 of 20 alerts"
- ✅ Color coding preserved (red for critical, yellow for warning)
- ✅ Filter selection persists in URL query parameter

---

### TC8.7: Export Alerts to CSV

**Priority**: Low  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to Alerts page
2. Apply desired filters (optional)
3. Click "Export" button
4. Select format: **CSV**
5. Click "Download" or "Export"
6. Open downloaded file

#### Expected Results

- ✅ CSV file downloads with name: `alerts.csv` or `alerts_YYYYMMDD.csv`
- ✅ File contains headers: timestamp, severity, message, status
- ✅ All visible (filtered) alerts included in export
- ✅ Data properly formatted (no JSON blobs or escaped characters)
- ✅ File opens correctly in Excel/Google Sheets
- ✅ Timestamps formatted in readable format (ISO 8601)

#### Sample CSV Content

```csv
timestamp,severity,message,status,symbol
2024-10-23T13:40:00Z,INFO,Order filled successfully,READ,BTCUSDT
2024-10-23T13:42:00Z,WARNING,High volatility detected,UNREAD,ETHUSDT
2024-10-23T13:45:00Z,CRITICAL,Stop loss triggered,READ,BTCUSDT
```

---

## Test Case 9: Settings & Preferences

### TC9.1: Change Trading Venue (SPOT ↔ USD-M Futures)

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Navigate to Settings page
2. Locate "Trading Venue" section
3. Current setting: SPOT
4. Switch to: **USD-M Futures**
5. Click "Save" button
6. Return to Trading page/Dashboard
7. Observe UI changes

#### Expected Results

- ✅ Save confirmation message appears
- ✅ Order form adapts to show futures-specific fields
- ✅ Leverage selector appears (1x-125x)
- ✅ Margin type selector appears (Cross/Isolated)
- ✅ Position mode setting visible (One-way/Hedge)
- ✅ Balance section switches to futures balance display
- ✅ Setting persists after page refresh

---

### TC9.2: Configure Risk Parameters

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Navigate to Settings → Risk Management
2. Set **Max Position Size**: $500.00
3. Set **Daily Loss Limit**: $100.00
4. Set **Max Open Positions**: 3
5. Click "Save Changes"
6. Attempt to place order exceeding limits

#### Expected Results

- ✅ Settings save successfully with confirmation
- ✅ Form validation prevents invalid values (e.g., negative numbers)
- ✅ Order placement validates against new limits
- ✅ Exceeding limits triggers blocking modal
- ✅ Settings apply immediately (no restart required)
- ✅ Values persist across sessions

---

### TC9.3: Set Default Order Type

**Priority**: Medium  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to Settings → Trading Defaults
2. Locate "Default Order Type" dropdown
3. Select: **LIMIT**
4. Click "Save"
5. Navigate to order placement form
6. Observe default selection

#### Expected Results

- ✅ Setting saves successfully
- ✅ Order form pre-selects LIMIT type on load
- ✅ User can still change to MARKET if needed
- ✅ Preference persists across browser sessions
- ✅ Different users can have different defaults

---

### TC9.4: Toggle Paper Trading Mode

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Navigate to Settings → Trading Mode
2. Current mode: **Live Trading** (or Paper Trading)
3. Toggle to: **Paper Trading**
4. Read confirmation warning
5. Confirm activation
6. Return to Dashboard

#### Expected Results

- ✅ Confirmation modal warns: "Real orders will be disabled"
- ✅ After activation: Banner appears "🎯 PAPER TRADING MODE"
- ✅ Banner persists on all pages
- ✅ Real orders blocked (cannot execute on exchange)
- ✅ Paper balance displayed separately: $10,000 default
- ✅ All trades simulated with realistic fills
- ✅ Mode persists until manually disabled

---

### TC9.5: Configure Notification Preferences

**Priority**: Medium  
**Duration**: 3 minutes

#### Test Steps

1. Navigate to Settings → Notifications
2. **Disable**: Sound effects
3. **Enable**: Browser notifications
4. **Enable**: Email notifications
5. Click "Save Preferences"
6. Trigger a notification (place order)
7. Verify notification behavior

#### Expected Results

- ✅ Settings save successfully
- ✅ No sound plays on next notification
- ✅ Browser notification appears (if permission granted)
- ✅ Email sent to registered address (check inbox)
- ✅ Changes apply immediately without page refresh
- ✅ Individual notification types configurable separately

---

### TC9.6: Dark/Light Theme Switch

**Priority**: Medium  
**Duration**: 2 minutes

#### Test Steps

1. Locate theme toggle (usually in header or settings)
2. Current theme: Light
3. Click toggle to switch to **Dark Theme**
4. Observe UI rerender
5. Switch back to **Light Theme**
6. Refresh page

#### Expected Results

- ✅ All components rerender with new theme colors
- ✅ Chart colors adapt appropriately (green/red preserved)
- ✅ Text contrast meets accessibility standards
- ✅ No visual glitches during transition
- ✅ Theme preference persists after page refresh
- ✅ Theme syncs across open tabs

---

### TC9.7: Language Selection

**Priority**: Low  
**Duration**: 3 minutes

#### Pre-conditions
- Multi-language support implemented

#### Test Steps

1. Navigate to Settings → Language
2. Current language: English
3. Select: **Thai** (or other available language)
4. Click "Apply"
5. Observe UI changes

#### Expected Results

- ✅ All UI text translates to selected language
- ✅ Chart axis labels translate
- ✅ Error messages display in selected language
- ✅ Date/time formats adapt to locale
- ✅ RTL layout applied if applicable (e.g., Arabic)
- ✅ Language preference persists

---

## Test Case 10: Market Data & Analysis

### TC10.1: 24-Hour Market Summary

**Priority**: Medium  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to Dashboard
2. Locate "Market Overview" or "24h Summary" widget
3. Review displayed information

#### Expected Results

- ✅ Displays data for tracked symbols (BTCUSDT, ETHUSDT, etc.)
- ✅ Shows 24h High price
- ✅ Shows 24h Low price
- ✅ Shows 24h Volume
- ✅ Shows 24h Price Change (percentage and absolute)
- ✅ Color-coded: Green for gains, Red for losses
- ✅ Data updates in real-time (every 1-5 seconds)

---

### TC10.2: Order Book Depth Visualization

**Priority**: Medium  
**Duration**: 3 minutes

#### Test Steps

1. Navigate to Chart page
2. Click "Order Book" tab
3. Observe bid/ask display
4. Monitor real-time updates

#### Expected Results

- ✅ Bids displayed in green (left or bottom side)
- ✅ Asks displayed in red (right or top side)
- ✅ Price levels sorted correctly
- ✅ Depth visualization shows volume at each level
- ✅ Real-time updates as orders added/removed
- ✅ Spread (difference) clearly indicated
- ✅ Click price level to populate order form

---

### TC10.3: Recent Trades List

**Priority**: Medium  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to Chart page
2. Click "Recent Trades" tab
3. Observe trade list
4. Monitor for new trades

#### Expected Results

- ✅ Trades listed in chronological order (newest first)
- ✅ Each row shows: Price, Size/Amount, Timestamp
- ✅ Buy trades highlighted in green
- ✅ Sell trades highlighted in red
- ✅ List updates in real-time as new trades execute
- ✅ Timestamps show seconds precision
- ✅ Auto-scroll to newest trade (optional setting)

---

### TC10.4: Market Regime Indicator

**Priority**: Medium  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to Dashboard
2. Locate "Market Regime" widget or indicator
3. Observe current regime classification

#### Expected Results

- ✅ Displays one of three states:
  - **TRENDING** (green background)
  - **RANGING** (yellow background)
  - **VOLATILE** (red background)
- ✅ Indicator updates based on market conditions
- ✅ Tooltip explains current regime meaning
- ✅ Historical regime chart available (optional)

---

### TC10.5: Economic Calendar Integration

**Priority**: High  
**Duration**: Variable

#### Pre-conditions
- High-impact economic event scheduled (e.g., NFP, FOMC)

#### Test Steps

1. Navigate to Dashboard
2. Locate "Economic Calendar" widget
3. Verify upcoming high-impact event listed
4. Attempt to place order 30 minutes before event
5. Observe blocking behavior

#### Expected Results

- ✅ Calendar lists upcoming events with impact level
- ✅ High-impact events highlighted (red)
- ✅ Countdown timer shows time until event
- ✅ Trading blocked 30 min before event (configurable)
- ✅ Warning modal: "Trading blocked due to NFP release in 15 minutes"
- ✅ Trading resumes 30 min after event
- ✅ Notification when trading enabled again

---

### TC10.6: Funding Rate Display (Futures)

**Priority**: Medium  
**Duration**: 3 minutes

#### Pre-conditions
- Futures trading mode enabled

#### Test Steps

1. Navigate to Futures Dashboard
2. Locate "Funding Rate" widget
3. Review displayed information

#### Expected Results

- ✅ Current funding rate displayed: e.g., "0.0100%" or "-0.0050%"
- ✅ Countdown to next funding: "Next funding in 2h 34m"
- ✅ Historical funding rate chart available
- ✅ Color-coded: Green for positive, Red for negative
- ✅ Explanation tooltip available
- ✅ Predicted funding rate shown (if available)

---

## Test Case 11: Trade History & Analytics

### TC11.1: View Completed Trades with P&L

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Navigate to "History" or "Trade History" page
2. View list of completed trades
3. Review information displayed for each trade

#### Expected Results

- ✅ Each trade shows: Symbol, Side (BUY/SELL), Entry Price, Exit Price
- ✅ P&L displayed in absolute terms ($) and percentage (%)
- ✅ Winning trades highlighted in green
- ✅ Losing trades highlighted in red
- ✅ Timestamp of entry and exit
- ✅ Trade duration calculated and displayed
- ✅ Fees included in P&L calculation

---

### TC11.2: Filter Trades by Date Range

**Priority**: Medium  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to Trade History page
2. Locate date range picker
3. Select: **Last 7 Days**
4. Observe filtered results
5. Select: **Last 30 Days**
6. Select: **Custom Range** (e.g., Oct 1-15)

#### Expected Results

- ✅ Only trades within selected date range displayed
- ✅ Count updates: "Showing 15 of 120 trades"
- ✅ Date picker allows custom start/end dates
- ✅ Filter persists during navigation
- ✅ URL updates with filter parameters
- ✅ Clear filter button available

---

### TC11.3: Sort Trades by Profit/Loss

**Priority**: Medium  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to Trade History page
2. Click "P&L" column header
3. Observe sort order (descending - best trades first)
4. Click "P&L" column header again
5. Observe sort order (ascending - worst trades first)

#### Expected Results

- ✅ First click: Sorts descending (highest profit first)
- ✅ Second click: Sorts ascending (largest loss first)
- ✅ Sort arrow indicator shows current direction
- ✅ Sort state persists during pagination
- ✅ Other columns also sortable (Entry Time, Symbol, etc.)

---

### TC11.4: Win Rate and Risk-Reward Metrics

**Priority**: Medium  
**Duration**: 3 minutes

#### Test Steps

1. Navigate to "Analytics" or "Performance" page
2. Locate performance metrics section
3. Review calculated statistics

#### Expected Results

- ✅ **Win Rate** displayed: e.g., "65.2% (45 wins / 24 losses)"
- ✅ **Average Win**: e.g., "$52.30"
- ✅ **Average Loss**: e.g., "-$28.40"
- ✅ **Risk-Reward Ratio**: e.g., "1.84:1"
- ✅ **Profit Factor**: e.g., "2.15"
- ✅ **Total Trades**: e.g., "69 trades"
- ✅ All metrics accurate (manually verify sample)

---

### TC11.5: Equity Curve Visualization

**Priority**: Medium  
**Duration**: 3 minutes

#### Test Steps

1. Navigate to Analytics page
2. Locate "Equity Curve" chart
3. Review account growth over time

#### Expected Results

- ✅ Line chart shows portfolio value over time
- ✅ X-axis: Time (dates)
- ✅ Y-axis: Account balance ($)
- ✅ Starting balance clearly marked
- ✅ Current balance clearly marked
- ✅ Drawdown periods visible (red shading)
- ✅ Peak balance highlighted
- ✅ Matches actual trade history data

---

### TC11.6: Export Trade History

**Priority**: Low  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to Trade History page
2. Click "Export" button
3. Select format: **JSON**
4. Click "Download"
5. Open downloaded file

#### Expected Results

- ✅ JSON file downloads: `trade_history.json`
- ✅ File contains complete trade data
- ✅ Each trade object includes all fields:
  - entry_time, exit_time, symbol, side, quantity
  - entry_price, exit_price, pnl, fees
- ✅ JSON properly formatted (valid syntax)
- ✅ Data matches UI display

#### Sample JSON Structure

```json
[
  {
    "trade_id": "12345",
    "symbol": "BTCUSDT",
    "side": "BUY",
    "entry_time": "2024-10-23T10:00:00Z",
    "exit_time": "2024-10-23T11:30:00Z",
    "entry_price": 41000.00,
    "exit_price": 41500.00,
    "quantity": 0.001,
    "pnl": 0.50,
    "pnl_percentage": 1.22,
    "fees": 0.04
  }
]
```

---

## Test Case 12: Error Handling & Edge Cases

### TC12.1: WebSocket Disconnection Fallback to REST API

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Verify WebSocket connection active
2. Open DevTools → Network → WS tab
3. Right-click active WS connection → Close connection
4. Immediately attempt to place an order
5. Observe fallback behavior

#### Expected Results

- ✅ Order submission uses REST API as fallback
- ✅ Order placed successfully despite WS disconnection
- ✅ Toast notification: "Using fallback connection"
- ✅ Automatic reconnection attempt within 5 seconds
- ✅ WebSocket reconnects successfully
- ✅ Real-time updates resume

---

### TC12.2: Network Interruption During Order Placement

**Priority**: High  
**Duration**: 4 minutes

#### Test Steps

1. Begin placing an order (fill form)
2. Click "Place Order" button
3. **Immediately** disable network:
   - DevTools → Network → Offline
4. Wait 5 seconds
5. Re-enable network
6. Check order status

#### Expected Results

- ✅ Error message: "Network error. Checking order status..."
- ✅ Automatic order status reconciliation occurs
- ✅ If order placed: Shows as filled/pending correctly
- ✅ If order failed: Clear error message displayed
- ✅ No duplicate orders created
- ✅ User can retry if order failed

---

### TC12.3: Browser Back Button During Order Flow

**Priority**: Medium  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to order placement form
2. Fill in order details (symbol, quantity, price)
3. Click browser **Back** button
4. Observe confirmation dialog

#### Expected Results

- ✅ Confirmation dialog appears: "Discard unsaved changes?"
- ✅ Options: "Stay on Page" or "Leave"
- ✅ "Stay on Page": Form data preserved
- ✅ "Leave": Navigation proceeds, data discarded
- ✅ Draft saved to sessionStorage (optional feature)

---

### TC12.4: Rapid Component Unmounting

**Priority**: Medium  
**Duration**: 3 minutes

#### Test Steps

1. Navigate to Dashboard (heavy data loading)
2. Immediately navigate to Settings (before load completes)
3. Navigate back to Dashboard
4. Repeat rapid navigation 5 times
5. Check browser DevTools Console

#### Expected Results

- ✅ No memory leaks (use Chrome Memory Profiler)
- ✅ No console errors about "setState on unmounted component"
- ✅ Pending API requests cancelled properly
- ✅ No zombie subscriptions or event listeners
- ✅ Application remains responsive

---

### TC12.5: Invalid API Response Structure

**Priority**: High  
**Duration**: 3 minutes

#### Pre-conditions
- Ability to mock API responses (use browser extension or proxy)

#### Test Steps

1. Mock API to return malformed JSON:
   ```json
   {invalid_json_here}
   ```
2. Trigger API call (e.g., load dashboard)
3. Observe error handling

#### Expected Results

- ✅ Error boundary catches exception
- ✅ User-friendly error page displays: "Something went wrong"
- ✅ "Try Again" button available
- ✅ Error logged to monitoring service
- ✅ Application doesn't crash completely
- ✅ Other sections remain functional

---

### TC12.6: Rate Limit Reached

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Write script to send 100 rapid API requests:
   ```javascript
   for(let i=0; i<100; i++) {
     fetch('/api/orders');
   }
   ```
2. Execute script in console
3. Observe application behavior

#### Expected Results

- ✅ API returns 429 Too Many Requests
- ✅ Exponential backoff applied automatically
- ✅ Toast notification: "Too many requests. Please slow down."
- ✅ Requests queued and retried automatically
- ✅ No lost data or failed operations
- ✅ Normal operation resumes after cooldown

---

### TC12.7: Stale Price Data Warning

**Priority**: Medium  
**Duration**: 3 minutes

#### Test Steps

1. Load Dashboard with live prices
2. Simulate stale data by stopping price updates:
   - Stop WebSocket connection
   - Block price API endpoints
3. Wait 60 seconds
4. Observe warning display

#### Expected Results

- ✅ Warning banner appears after 60 seconds
- ✅ Message: "Price data delayed. Last update: 1 minute ago"
- ✅ Timestamp shows age of last update
- ✅ Warning color (yellow/orange)
- ✅ Auto-dismisses when updates resume
- ✅ Order placement disabled during stale data

---

## Test Case 13: Responsive Design & Accessibility

### TC13.1: Dashboard on Mobile Device (320px width)

**Priority**: High  
**Duration**: 5 minutes

#### Test Steps

1. Open Dashboard in Chrome DevTools Device Mode
2. Select device: iPhone SE (320px width)
3. Navigate through all major sections
4. Test order placement flow

#### Expected Results

- ✅ Layout adapts to narrow screen (no horizontal scroll)
- ✅ Navigation collapses to hamburger menu
- ✅ Tables become scrollable or card-based
- ✅ Chart remains readable (simplified view)
- ✅ Order form stacks vertically
- ✅ Buttons remain tappable (44×44px minimum)
- ✅ Text readable without zooming

---

### TC13.2: Tablet Portrait Orientation

**Priority**: Medium  
**Duration**: 3 minutes

#### Test Steps

1. Open in DevTools → iPad (768px portrait)
2. Review layout and usability
3. Test chart interactions

#### Expected Results

- ✅ Two-column layout utilized effectively
- ✅ Chart renders at appropriate size
- ✅ Touch gestures work (pinch zoom, pan)
- ✅ Tables show adequate columns
- ✅ Side panels accessible via tabs/accordions

---

### TC13.3: Keyboard Navigation

**Priority**: High  
**Duration**: 4 minutes

#### Test Steps

1. Open order form
2. Use only keyboard (no mouse):
   - Press **Tab** to navigate between fields
   - Press **Enter** to submit
   - Press **Esc** to close modals
3. Navigate entire application via keyboard

#### Expected Results

- ✅ Tab order logical and intuitive
- ✅ Focus indicator visible on all elements
- ✅ All interactive elements keyboard-accessible
- ✅ Modals trap focus (can't tab out)
- ✅ Skip navigation link available
- ✅ Dropdown menus keyboard-accessible

---

### TC13.4: Screen Reader Compatibility

**Priority**: High  
**Duration**: 5 minutes

#### Test Steps

1. Enable VoiceOver (Mac) or NVDA (Windows)
2. Navigate through application
3. Attempt to place order using only screen reader

#### Expected Results

- ✅ Page title announced on navigation
- ✅ Headings properly structured (h1, h2, h3)
- ✅ Form labels associated with inputs
- ✅ Button purposes clearly announced
- ✅ Dynamic updates announced via ARIA live regions
- ✅ Image alt text descriptive
- ✅ Order status changes announced

---

### TC13.5: High Contrast Mode

**Priority**: Medium  
**Duration**: 3 minutes

#### Test Steps

1. Enable High Contrast Mode:
   - **Windows**: Settings → Ease of Access → High Contrast
   - **Mac**: System Preferences → Accessibility → Display → Increase Contrast
2. Review application appearance
3. Test readability

#### Expected Results

- ✅ Text contrast ratio ≥ 7:1 (WCAG AAA)
- ✅ Interactive elements clearly distinguishable
- ✅ Focus indicators highly visible
- ✅ Color not sole means of conveying information
- ✅ Charts remain readable with high contrast

---

### TC13.6: Touch Target Sizes on Mobile

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Open on actual mobile device (or DevTools mobile view)
2. Measure button and link sizes
3. Test tapping accuracy

#### Expected Results

- ✅ All buttons ≥ 44×44px (Apple guideline)
- ✅ Adequate spacing between tappable elements (8px minimum)
- ✅ No accidental taps on adjacent buttons
- ✅ Icons sufficiently large
- ✅ Form inputs easy to select

---

### TC13.7: Pinch Zoom on Charts

**Priority**: Medium  
**Duration**: 2 minutes

#### Test Steps

1. Open chart on touch-enabled device
2. Use pinch gesture to zoom in
3. Use pinch gesture to zoom out
4. Pan around zoomed chart

#### Expected Results

- ✅ Pinch zoom works smoothly
- ✅ No unexpected page zoom
- ✅ Chart zoom independent of page zoom
- ✅ Double-tap to reset zoom works
- ✅ Zoom level indicator displayed

---

## Test Case 14: Performance & Load Testing

### TC14.1: Dashboard with 50+ Active Alerts

**Priority**: Medium  
**Duration**: 4 minutes

#### Test Steps

1. Generate 50+ alerts (script or manual)
2. Navigate to Dashboard with alerts panel
3. Scroll through alerts list
4. Measure scrolling performance

#### Expected Results

- ✅ Smooth scrolling at 60fps
- ✅ Virtual scrolling implemented (only render visible)
- ✅ No frame drops during scroll
- ✅ Initial load time < 2 seconds
- ✅ Memory usage reasonable (< 200MB increase)

---

### TC14.2: Order History with 1000+ Records

**Priority**: Medium  
**Duration**: 4 minutes

#### Test Steps

1. Seed database with 1000+ order records
2. Navigate to Order History page
3. Test scrolling and filtering

#### Expected Results

- ✅ Pagination or virtual scrolling implemented
- ✅ Initial load shows first 20-50 records only
- ✅ Lazy loading as user scrolls
- ✅ Smooth 60fps scrolling
- ✅ Search/filter remains responsive
- ✅ No browser freeze

---

### TC14.3: Rapid Chart Timeframe Switching

**Priority**: Medium  
**Duration**: 3 minutes

#### Test Steps

1. Open chart
2. Rapidly click timeframe buttons:
   - 1m → 5m → 15m → 1h → 4h → 1d
3. Observe performance and API calls

#### Expected Results

- ✅ API calls debounced (only last request sent)
- ✅ No visual glitches
- ✅ Loading indicators appear briefly
- ✅ Chart redraws smoothly
- ✅ No memory leaks
- ✅ Network tab shows maximum 1 pending request

---

### TC14.4: Multiple WebSocket Streams (10 Symbols)

**Priority**: High  
**Duration**: 5 minutes

#### Test Steps

1. Subscribe to 10 symbol price streams simultaneously
2. Monitor CPU and memory usage
3. Observe UI responsiveness

#### Expected Results

- ✅ All streams update independently
- ✅ No UI freezing or blocking
- ✅ CPU usage < 30% on modern hardware
- ✅ Memory usage stable (no leaks)
- ✅ Updates remain real-time (< 1s delay)

---

### TC14.5: Low Bandwidth Simulation (3G)

**Priority**: Medium  
**Duration**: 4 minutes

#### Test Steps

1. DevTools → Network → Throttling → Slow 3G
2. Navigate through application
3. Place an order

#### Expected Results

- ✅ Progressive loading implemented
- ✅ Critical content loads first
- ✅ Loading indicators displayed
- ✅ Images lazy-loaded
- ✅ Order placement works (may be slow but succeeds)
- ✅ Timeout errors handled gracefully

---

### TC14.6: High Latency Simulation (500ms RTT)

**Priority**: Medium  
**Duration**: 3 minutes

#### Test Steps

1. DevTools → Network → Custom → 500ms latency
2. Interact with application
3. Place order

#### Expected Results

- ✅ Optimistic UI updates (immediate feedback)
- ✅ Loading states displayed during latency
- ✅ Eventual consistency maintained
- ✅ No duplicate actions from impatient clicks
- ✅ Rollback if server rejects optimistic update

---

## Test Case 15: Integration Points

### TC15.1: BFF ↔ Router Communication

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Place order via UI
2. Monitor network traffic:
   - UI → BFF: POST /api/trading/orders
   - BFF → Router: POST /place_bracket
3. Verify order routing

#### Expected Results

- ✅ BFF correctly routes spot orders to SPOT endpoint
- ✅ BFF correctly routes futures orders to USD_M endpoint
- ✅ Request transformation correct
- ✅ Response mapping correct
- ✅ Error handling propagates properly

---

### TC15.2: Engine ↔ Router Signal Processing

**Priority**: High  
**Duration**: Variable

#### Pre-conditions
- Auto-trading enabled
- Trading signal generated by engine

#### Test Steps

1. Monitor engine logs
2. Wait for trading signal generation
3. Verify signal sent to router
4. Verify order execution

#### Expected Results

- ✅ Signal published to Redis pub/sub
- ✅ Router receives signal
- ✅ Order formatted correctly
- ✅ Order placed on exchange
- ✅ Execution report sent back to engine

---

### TC15.3: Redis Pub/Sub for Real-Time Events

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Monitor Redis channels:
   ```bash
   redis-cli MONITOR
   ```
2. Place order via UI
3. Observe event publication
4. Verify subscribers receive event

#### Expected Results

- ✅ Order placed → event published to `orders:new`
- ✅ Order filled → event published to `orders:filled`
- ✅ BFF subscribes and receives events
- ✅ UI updates via WebSocket
- ✅ Message delivery < 100ms

---

### TC15.4: TimescaleDB Historical Data Queries

**Priority**: Medium  
**Duration**: 3 minutes

#### Test Steps

1. Navigate to Analytics page
2. Select date range: Last 90 days
3. Load historical equity curve
4. Measure query time

#### Expected Results

- ✅ Query completes in < 1 second
- ✅ Data accurate and complete
- ✅ No missing data points
- ✅ Aggregations correct
- ✅ Chart renders smoothly

---

### TC15.5: Prometheus Metrics Export

**Priority**: Medium  
**Duration**: 3 minutes

#### Test Steps

1. Navigate to http://localhost:9090 (Prometheus)
2. Query metrics:
   - `order_placement_latency`
   - `websocket_connections`
   - `active_positions`
3. Verify accuracy

#### Expected Results

- ✅ Metrics endpoint accessible: /metrics
- ✅ Counter values incrementing correctly
- ✅ Gauge values accurate
- ✅ Histogram buckets populated
- ✅ Labels applied correctly

---

### TC15.6: Binance Testnet vs Mainnet Toggling

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Current config: Testnet
2. Change environment variable:
   ```bash
   BINANCE_TESTNET=false
   ```
3. Restart router service
4. Verify endpoint switching

#### Expected Results

- ✅ Router connects to mainnet URLs
- ✅ Warning displayed: "LIVE TRADING MODE"
- ✅ Real funds at risk warning shown
- ✅ Confirmation required for all orders
- ✅ Switch back to testnet works correctly

---

## Test Case 16: Advanced Features

### TC16.1: Walk-Forward Optimization Configuration

**Priority**: Low  
**Duration**: 5 minutes

#### Test Steps

1. Navigate to Backtesting → Walk-Forward Optimization
2. Configure parameters:
   - In-sample period: 60 days
   - Out-sample period: 20 days
   - Number of iterations: 5
3. Run optimization

#### Expected Results

- ✅ Parameter validation works
- ✅ Progress indicator shows current iteration
- ✅ Results display for each iteration
- ✅ Best parameters highlighted
- ✅ Out-of-sample performance tracked

---

### TC16.2: Backtest Execution with Historical Data

**Priority**: Low  
**Duration**: 10 minutes

#### Test Steps

1. Navigate to Backtesting page
2. Select strategy: "SMC Retest Strategy"
3. Set date range: Jan 1 - Dec 31, 2023
4. Set symbols: BTCUSDT, ETHUSDT
5. Click "Run Backtest"

#### Expected Results

- ✅ Backtest runs to completion
- ✅ Progress bar updates
- ✅ Results display:
  - Total trades, Win rate, Profit factor
  - Equity curve, Drawdown chart
  - Trade list
- ✅ Export results available

---

### TC16.3: Strategy Parameter Tuning

**Priority**: Low  
**Duration**: 5 minutes

#### Test Steps

1. Navigate to Strategy Settings
2. Adjust parameters:
   - EMA Period: 21 → 50
   - RSI Threshold: 30 → 35
3. Save changes
4. Observe hot-reload

#### Expected Results

- ✅ Parameter changes saved
- ✅ Strategy restarts with new parameters (no full restart)
- ✅ Validation prevents invalid values
- ✅ Previous performance archived

---

### TC16.4: Multi-Symbol Correlation Matrix

**Priority**: Low  
**Duration**: 3 minutes

#### Test Steps

1. Navigate to Analytics → Correlation
2. View correlation matrix for:
   - BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT

#### Expected Results

- ✅ Heatmap displays correlation coefficients
- ✅ Values range from -1.0 to 1.0
- ✅ Color coding: Red (negative) to Green (positive)
- ✅ Diagonal values = 1.0 (self-correlation)
- ✅ Matrix symmetric

---

### TC16.5: Custom Indicator Creation

**Priority**: Low  
**Duration**: 5 minutes

#### Test Steps

1. Navigate to Indicators → Custom
2. Create new indicator: "Custom RSI"
3. Define formula: `RSI(close, 14) + 10`
4. Apply to chart

#### Expected Results

- ✅ Formula editor with syntax highlighting
- ✅ Validation of formula syntax
- ✅ Test calculation on sample data
- ✅ Indicator appears on chart
- ✅ Values calculated correctly

---

### TC16.6: Paper Trading Leaderboard

**Priority**: Low  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to Leaderboard page
2. View paper trading rankings

#### Expected Results

- ✅ Users ranked by paper trading performance
- ✅ Metrics shown: ROI%, Total Trades, Win Rate
- ✅ Current user position highlighted
- ✅ Time period selector (Daily, Weekly, All-Time)

---

## Test Case 17: Administrative Functions

### TC17.1: Health Check Endpoint Monitoring

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Navigate to Admin → System Health
2. Review service statuses
3. Trigger manual health check

#### Expected Results

- ✅ All services show status: Healthy/Unhealthy
- ✅ Engine: Healthy (green)
- ✅ Router: Healthy (green)
- ✅ BFF: Healthy (green)
- ✅ Database: Healthy (green)
- ✅ Redis: Healthy (green)
- ✅ Response times displayed
- ✅ Last check timestamp shown

---

### TC17.2: Circuit Breaker Manual Override

**Priority**: Medium  
**Duration**: 3 minutes

#### Pre-conditions
- Admin authentication required

#### Test Steps

1. Navigate to Admin → Circuit Breakers
2. Locate open circuit breaker
3. Click "Force Close" button
4. Authenticate as admin

#### Expected Results

- ✅ Admin authentication modal appears
- ✅ After auth: Circuit breaker manually closed
- ✅ Override logged in audit trail
- ✅ Confirmation message displayed
- ✅ Trading resumes on affected endpoint

---

### TC17.3: Database Migration Status

**Priority**: Medium  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to Admin → Database
2. View migration history

#### Expected Results

- ✅ List of all migrations displayed
- ✅ Each shows: Version, Name, Status, Timestamp
- ✅ Current version highlighted
- ✅ Pending migrations indicated
- ✅ Failed migrations highlighted in red

---

### TC17.4: Log Streaming Interface

**Priority**: Low  
**Duration**: 3 minutes

#### Test Steps

1. Navigate to Admin → Logs
2. Select service: Engine
3. Set log level: DEBUG
4. Observe real-time logs

#### Expected Results

- ✅ Logs stream in real-time (tail -f style)
- ✅ Color-coded by level (DEBUG, INFO, WARN, ERROR)
- ✅ Search/filter functionality
- ✅ Auto-scroll toggle
- ✅ Download logs button

---

### TC17.5: Feature Flag Toggling

**Priority**: Medium  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to Admin → Feature Flags
2. Locate flag: `enable_smc_trading`
3. Toggle OFF
4. Verify effect on UI
5. Toggle back ON

#### Expected Results

- ✅ Flag toggles immediately
- ✅ Changes apply without restart
- ✅ UI hides/shows features accordingly
- ✅ Confirmation modal for critical flags
- ✅ Audit log records change

---

## Test Case 18: Security & Compliance

### TC18.1: API Key Input Masking

**Priority**: High  
**Duration**: 2 minutes

#### Test Steps

1. Navigate to Settings → API Keys
2. Enter Binance API key
3. Observe masking behavior
4. Inspect DOM with DevTools

#### Expected Results

- ✅ Input displays as: `••••••••••••`
- ✅ DOM shows `type="password"`
- ✅ No plaintext in HTML
- ✅ Copy-paste disabled
- ✅ Autocomplete disabled
- ✅ Key transmitted over HTTPS only

---

### TC18.2: HTTPS Enforcement

**Priority**: Critical  
**Duration**: 2 minutes

#### Test Steps

1. Attempt to access: http://localhost:3000 (HTTP)
2. Observe redirect
3. Verify final URL

#### Expected Results

- ✅ Automatic redirect to HTTPS
- ✅ HSTS header present
- ✅ Certificate valid (in production)
- ✅ No mixed content warnings

---

### TC18.3: CORS Policy Validation

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Open browser console
2. Attempt cross-origin request:
   ```javascript
   fetch('http://localhost:3001/api/orders', {
     headers: {'Origin': 'http://evil-site.com'}
   });
   ```
3. Observe response

#### Expected Results

- ✅ Request blocked by CORS policy
- ✅ Console error: "CORS policy blocked"
- ✅ Only allowed origins can access API
- ✅ Preflight OPTIONS requests handled correctly

---

### TC18.4: Rate Limiting per User

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Send 100 requests rapidly from same user
2. Observe throttling

#### Expected Results

- ✅ After threshold: 429 Too Many Requests
- ✅ Response header: `Retry-After: 60`
- ✅ Rate limit applies per user (not global)
- ✅ Different users have independent limits

---

### TC18.5: Audit Log for Sensitive Actions

**Priority**: High  
**Duration**: 3 minutes

#### Test Steps

1. Perform sensitive action:
   - Change risk limits
   - Add API key
   - Withdraw funds (if implemented)
2. Check audit log

#### Expected Results

- ✅ Action logged with timestamp
- ✅ User ID recorded
- ✅ IP address logged
- ✅ Before/after values captured
- ✅ Logs immutable (append-only)

---

## Test Execution Guidelines

### Before Each Test Session

- [ ] All services running via `make dev`
- [ ] Database migrations applied: `make db-migrate`
- [ ] Test user account created with known credentials
- [ ] Browser cache cleared (for fresh state tests)
- [ ] Browser DevTools open (Network + Console tabs)
- [ ] Screen recording started (for bug documentation)
- [ ] Test data seeded (if required)

### During Testing

- [ ] Take screenshots of all failures
- [ ] Note exact error messages (copy-paste)
- [ ] Record network request/response details
- [ ] Log timestamps for performance tests
- [ ] Document exact reproduction steps
- [ ] Note browser version and OS

### After Testing

- [ ] Complete test report for each test case
- [ ] Mark pass/fail status for each checkpoint
- [ ] Create bug tickets for all failures
- [ ] Update test cases based on findings
- [ ] Share results with development team
- [ ] Archive test artifacts (screenshots, recordings)

---

## Test Reporting Template

### Individual Test Report

```markdown
# Test Case Report: TC1.1

**Test Case ID**: TC1.1  
**Test Case Name**: Login with Valid Credentials  
**Date**: 2024-10-23  
**Tester**: [Your Name]  
**Environment**: Development / Staging / Production  
**Browser**: Chrome 120 / Firefox 119 / Safari 17  
**OS**: macOS 14.0 / Windows 11 / Ubuntu 22.04

## Test Results

| Checkpoint | Expected Result | Actual Result | Status |
|------------|----------------|---------------|--------|
| 1 | Button shows loading state | Button showed spinner | ✅ PASS |
| 2 | Response 200 OK | Response 200 OK | ✅ PASS |
| 3 | Tokens in response | Tokens present | ✅ PASS |
| 4 | Redirect within 1s | Redirected in 0.8s | ✅ PASS |
| 5 | Token in localStorage | Token stored | ✅ PASS |
| 6 | Username displayed | "Trader" displayed | ✅ PASS |
| 7 | No console errors | **ERROR FOUND** | ❌ FAIL |

## Overall Status
**FAILED**

## Failure Details

**Checkpoint 7 Failed:**
- Console error: `TypeError: Cannot read property 'balance' of undefined`
- Occurs after successful login
- Does not block functionality but should be fixed
- Screenshot: `screenshots/tc1-1-console-error.png`

## Bug Ticket
- **Ticket ID**: TRADE-1234
- **Severity**: Low
- **Priority**: Medium

## Notes
- Performance is good (< 1s login time)
- UI feedback is clear and responsive
- Error does not impact user experience significantly

## Reproduction Steps
1. Navigate to http://localhost:3000
2. Enter: trader@test.com / Test123!
3. Click Login
4. Check browser console

## Environment Info
- Node: v20.10.0
- Chrome: 120.0.6099.109
- OS: macOS 14.0 (Sonoma)
```

### Summary Report Template

```markdown
# Test Execution Summary Report

**Test Period**: 2024-10-20 to 2024-10-23  
**Tester(s)**: QA Team  
**Environment**: Development  
**Build Version**: v1.2.0

## Executive Summary

Total test cases executed: **18**  
Passed: **15** (83.3%)  
Failed: **3** (16.7%)  
Blocked: **0** (0%)

## Test Results by Priority

### Critical Priority (5 test cases)
- ✅ TC1.1: Login with Valid Credentials - PASS
- ✅ TC2.1: Place Market Order - PASS
- ✅ TC2.3: Place Bracket Order - PASS
- ✅ TC4.1: Live P&L Updates - PASS
- ✅ TC5.2: Cancel Pending Order - PASS

### High Priority (8 test cases)
- ✅ TC1.2: Invalid Credentials - PASS
- ✅ TC2.2: Place Limit Order - PASS
- ❌ TC3.1: Enable Auto-Trading - **FAIL**
- ✅ TC4.4: Multiple Positions - PASS
- ✅ TC5.1: Filter Active Orders - PASS
- ✅ TC6.1: Dashboard Load Performance - PASS
- ✅ TC7.3: Balance Updates - PASS
- ❌ TC8.3: Risk Limit Alert - **FAIL**

### Medium Priority (5 test cases)
- ✅ TC9.1: Change Trading Venue - PASS
- ✅ TC10.1: Market Summary - PASS
- ✅ TC11.2: Filter by Date - PASS
- ❌ TC13.3: Keyboard Navigation - **FAIL**
- ✅ TC14.1: 50+ Alerts Performance - PASS

## Critical Issues Found

### Issue #1: Auto-Trading Confirmation Modal Missing
- **TC**: TC3.1
- **Severity**: High
- **Description**: Confirmation modal does not appear when enabling auto-trading
- **Impact**: User can accidentally enable auto-trading
- **Ticket**: TRADE-1235

### Issue #2: Risk Limit Not Blocking Orders
- **TC**: TC8.3
- **Severity**: Critical
- **Description**: Daily loss limit not enforced on order placement
- **Impact**: Users can exceed risk limits
- **Ticket**: TRADE-1236

### Issue #3: Keyboard Navigation Skip Link Broken
- **TC**: TC13.3
- **Severity**: Medium
- **Description**: Skip navigation link does not focus main content
- **Impact**: Accessibility issue for keyboard users
- **Ticket**: TRADE-1237

## Performance Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Dashboard Load | < 3s | 2.1s | ✅ |
| Order Placement | < 500ms | 320ms | ✅ |
| Chart Render | < 2s | 1.8s | ✅ |
| WebSocket Reconnect | < 2s | 1.5s | ✅ |

## Test Coverage

- **Authentication**: 100% (7/7 scenarios)
- **Trading**: 90% (9/10 scenarios)
- **Portfolio**: 100% (6/6 scenarios)
- **UI/UX**: 85% (11/13 scenarios)

## Recommendations

1. **High Priority**: Fix TC8.3 risk limit enforcement before production
2. **Medium Priority**: Add confirmation modal for auto-trading toggle
3. **Low Priority**: Improve keyboard navigation accessibility
4. **Documentation**: Update user guide with new features

## Next Steps

- [ ] Development team to review and prioritize bug fixes
- [ ] Retest failed scenarios after fixes deployed
- [ ] Expand test coverage to include edge cases
- [ ] Automate regression tests for critical paths

## Sign-off

**QA Lead**: ________________  Date: __________  
**Dev Lead**: ________________  Date: __________  
**Product Manager**: __________  Date: __________
```

---

## Appendix

### Useful Commands

```bash
# Start all services
make dev

# Start individual services
make dev-engine
make dev-router
make dev-bff
make dev-ui

# Run tests
make test
make test-engine
make test-router
make test-bff
make test-ui

# Check logs
docker logs trading-engine-dev
docker logs trading-router-dev
docker logs trading-bff-dev
docker logs trading-ui-dev

# Database operations
make db-up
make db-migrate
make db-reset

# Clear cache and rebuild
make clean
make build

# Check service health
curl http://localhost:8000/health  # Engine
curl http://localhost:8080/health  # Router
curl http://localhost:3001/health  # BFF
```

### Environment Variables for Testing

```bash
# .env.test
BINANCE_TESTNET=true
ENVIRONMENT=test
LOG_LEVEL=DEBUG
DATABASE_URL=postgresql://test_user:test_pass@localhost:5432/test_db
REDIS_URL=redis://localhost:6379/1
```

### Browser Extensions for Testing

- **React Developer Tools**: Component inspection
- **Redux DevTools**: State debugging
- **Lighthouse**: Performance auditing
- **axe DevTools**: Accessibility testing
- **Requestly**: API mocking and request modification
- **JSON Viewer**: Pretty-print API responses

---

**Document Version**: 1.0.0  
**Last Updated**: 2024-10-23  
**Maintained By**: QA Team  
**Contact**: qa@trading-platform.com

