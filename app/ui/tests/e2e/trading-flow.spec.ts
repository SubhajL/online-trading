import { test, expect } from '../fixtures'

test.describe('Trading Flow', () => {
  test.beforeEach(async ({ tradingPage }) => {
    await tradingPage.goto()
    await expect(tradingPage.orderForm.symbolInput).toBeVisible()
  })

  test('should complete a full market order flow', async ({ tradingPage }) => {
    // Check initial state
    await expect(tradingPage.accountBalance.totalBalance).toBeVisible()
    await expect(tradingPage.positionsList.container).toBeVisible()

    // Place a market buy order
    await tradingPage.placeOrder({
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.001,
    })

    // Wait for order execution
    await tradingPage.waitForOrderExecution()

    // Verify order appears in history
    const orders = await tradingPage.orderHistory.orders.all()
    expect(orders.length).toBeGreaterThan(0)

    const latestOrder = orders[0]
    await expect(latestOrder).toContainText('BTCUSDT')
    await expect(latestOrder).toContainText('BUY')
    await expect(latestOrder).toContainText('MARKET')

    // Verify position is created/updated
    const positions = await tradingPage.positionsList.positions.all()
    const btcPosition = positions.find(async pos => {
      const text = await pos.textContent()
      return text?.includes('BTCUSDT')
    })

    expect(btcPosition).toBeTruthy()
  })

  test('should complete a limit order flow with price', async ({ tradingPage }) => {
    // Place a limit sell order
    await tradingPage.placeOrder({
      symbol: 'ETHUSDT',
      side: 'SELL',
      type: 'LIMIT',
      quantity: 0.1,
      price: 4000,
    })

    // Wait for order to appear
    await tradingPage.waitForOrderExecution()

    // Verify order details
    const latestOrder = tradingPage.orderHistory.orders.first()
    await expect(latestOrder).toContainText('ETHUSDT')
    await expect(latestOrder).toContainText('SELL')
    await expect(latestOrder).toContainText('LIMIT')
    await expect(latestOrder).toContainText('4000')
  })

  test('should handle order validation errors', async ({ tradingPage }) => {
    // Try to submit without filling required fields
    await tradingPage.orderForm.submitButton.click()

    // Check for validation errors
    await expect(tradingPage.page.locator('text=Symbol is required')).toBeVisible()

    // Fill symbol but leave quantity empty
    await tradingPage.orderForm.symbolInput.fill('BTCUSDT')
    await tradingPage.orderForm.submitButton.click()

    // Check for quantity validation
    await expect(tradingPage.page.locator('text=Quantity must be greater than 0')).toBeVisible()

    // Try negative quantity
    await tradingPage.orderForm.quantityInput.fill('-1')
    await tradingPage.orderForm.submitButton.click()

    await expect(tradingPage.page.locator('text=Quantity must be greater than 0')).toBeVisible()
  })

  test('should filter orders by status', async ({ tradingPage }) => {
    // Ensure we have some orders
    await tradingPage.placeOrder({
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.001,
    })

    await tradingPage.waitForOrderExecution()

    // Filter by FILLED status
    await tradingPage.filterOrdersByStatus('FILLED')

    // Verify filtered results
    const orders = await tradingPage.orderHistory.orders.all()
    for (const order of orders) {
      await expect(order).toContainText('FILLED')
    }

    // Filter by PENDING status
    await tradingPage.filterOrdersByStatus('PENDING')

    // If no pending orders, list should be empty or show no results
    const pendingOrders = await tradingPage.orderHistory.orders.count()
    if (pendingOrders > 0) {
      const orders = await tradingPage.orderHistory.orders.all()
      for (const order of orders) {
        await expect(order).toContainText('PENDING')
      }
    }
  })

  test('should update positions after order execution', async ({ tradingPage }) => {
    // Get initial position count
    const initialPositions = await tradingPage.positionsList.positions.count()

    // Place multiple orders
    await tradingPage.placeOrder({
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.001,
    })

    await tradingPage.waitForOrderExecution()

    await tradingPage.placeOrder({
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.002,
    })

    await tradingPage.waitForOrderExecution()

    // Verify position is updated
    const positions = await tradingPage.positionsList.positions.all()
    const btcPosition = await positions.find(async pos => {
      const text = await pos.textContent()
      return text?.includes('BTCUSDT')
    })

    expect(btcPosition).toBeTruthy()

    // Verify quantity is accumulated
    if (btcPosition) {
      const positionText = await btcPosition.textContent()
      expect(positionText).toContain('0.003') // 0.001 + 0.002
    }
  })

  test('should handle order cancellation', async ({ tradingPage }) => {
    // Place a limit order (which can be cancelled)
    await tradingPage.placeOrder({
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'LIMIT',
      quantity: 0.01,
      price: 30000, // Low price to ensure it doesn't fill immediately
    })

    await tradingPage.waitForOrderExecution()

    // Find and cancel the order
    const cancelButton = await tradingPage.page
      .locator('[data-testid="order-item"]')
      .filter({ hasText: 'PENDING' })
      .locator('button:has-text("Cancel")')
      .first()

    if (await cancelButton.isVisible()) {
      await cancelButton.click()

      // Wait for cancellation confirmation
      await expect(tradingPage.page.locator('text=Order cancelled successfully')).toBeVisible()

      // Verify order status is updated
      const cancelledOrder = await tradingPage.orderHistory.orders
        .filter({ hasText: 'CANCELLED' })
        .first()

      await expect(cancelledOrder).toBeVisible()
    }
  })

  test('should display real-time balance updates', async ({ tradingPage }) => {
    // Get initial balance
    const initialBalance = await tradingPage.accountBalance.totalBalance.textContent()

    // Place an order
    await tradingPage.placeOrder({
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.001,
    })

    await tradingPage.waitForOrderExecution()

    // Wait for balance update
    await tradingPage.page.waitForTimeout(1000) // Wait for WebSocket update

    // Verify balance changed
    const updatedBalance = await tradingPage.accountBalance.totalBalance.textContent()
    expect(updatedBalance).not.toBe(initialBalance)
  })

  test('should handle keyboard shortcuts for order placement', async ({ tradingPage }) => {
    // Focus on order form
    await tradingPage.orderForm.symbolInput.focus()
    await tradingPage.orderForm.symbolInput.fill('BTCUSDT')

    // Use Tab to navigate
    await tradingPage.page.keyboard.press('Tab')
    await tradingPage.page.keyboard.press('ArrowDown') // Select BUY

    await tradingPage.page.keyboard.press('Tab')
    await tradingPage.page.keyboard.press('ArrowDown') // Select MARKET

    await tradingPage.page.keyboard.press('Tab')
    await tradingPage.page.keyboard.type('0.001')

    // Submit with Enter
    await tradingPage.page.keyboard.press('Enter')

    // Verify order was placed
    await tradingPage.waitForOrderExecution()
    const latestOrder = await tradingPage.orderHistory.orders.first()
    await expect(latestOrder).toContainText('BTCUSDT')
  })
})
