import { orderTest as test, expect } from '../../fixtures/order.fixture'
import { webSocketTest } from '../../fixtures/websocket.fixture'
import { TestDataSeeder } from '../../utils/test-data-seeder'

test.describe('TC02.01: Place Market Order for BTCUSDT', () => {
  test.beforeEach(async ({ page, orderPage }) => {
    // Set up test data
    const seeder = new TestDataSeeder(page)
    await seeder.seedBalances([
      { asset: 'USDT', free: '10000.00', locked: '0.00', total: '10000.00' },
      { asset: 'BTC', free: '0.00', locked: '0.00', total: '0.00' },
    ])

    await orderPage.goto()
  })

  test('should place a successful market buy order', async ({ orderPage, mockOrderAPI, page }) => {
    // Mock successful order response
    await mockOrderAPI.mockSuccessfulOrder({
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: '0.001',
    })

    // Place market buy order
    await orderPage.placeMarketOrder('BTCUSDT', 'BUY', '0.001')

    // Verify order appears in order list
    await orderPage.waitForOrderExecution()
    await orderPage.expectOrderInList('BTCUSDT', 'BUY', 'NEW')

    // Verify success message
    await expect(page.locator('[data-testid="order-success"]')).toBeVisible()
    await expect(page.locator('[data-testid="order-success"]')).toContainText(/order placed successfully/i)
  })

  test('should place a successful market sell order', async ({ orderPage, mockOrderAPI, page }) => {
    // First seed some BTC balance
    const seeder = new TestDataSeeder(page)
    await seeder.seedBalances([
      { asset: 'USDT', free: '10000.00', locked: '0.00', total: '10000.00' },
      { asset: 'BTC', free: '0.01', locked: '0.00', total: '0.01' },
    ])

    await mockOrderAPI.mockSuccessfulOrder({
      symbol: 'BTCUSDT',
      side: 'SELL',
      type: 'MARKET',
      quantity: '0.001',
    })

    // Place market sell order
    await orderPage.placeMarketOrder('BTCUSDT', 'SELL', '0.001')

    await orderPage.waitForOrderExecution()
    await orderPage.expectOrderInList('BTCUSDT', 'SELL', 'NEW')
  })

  test('should validate required fields', async ({ orderPage, page }) => {
    // Try to submit empty form
    await orderPage.submitButton.click()

    // Verify validation errors
    await expect(page.locator('[data-testid="symbol-error"]')).toContainText(/symbol is required/i)
    await expect(page.locator('[data-testid="quantity-error"]')).toContainText(/quantity is required/i)

    // Fill symbol but leave quantity empty
    await orderPage.symbolInput.fill('BTCUSDT')
    await orderPage.submitButton.click()

    await expect(page.locator('[data-testid="quantity-error"]')).toContainText(/quantity is required/i)
  })

  test('should validate quantity format', async ({ orderPage, page }) => {
    await orderPage.symbolInput.fill('BTCUSDT')

    // Test invalid quantity formats
    const invalidQuantities = ['abc', '-1', '0', '0.0000001'] // Too small

    for (const quantity of invalidQuantities) {
      await orderPage.quantityInput.fill(quantity)
      await orderPage.submitButton.click()

      await expect(page.locator('[data-testid="quantity-error"]')).toBeVisible()
      
      // Clear for next iteration
      await orderPage.quantityInput.fill('')
    }
  })

  test('should handle insufficient balance', async ({ orderPage, mockOrderAPI, page }) => {
    // Mock insufficient balance error
    await mockOrderAPI.mockInsufficientBalance()

    await orderPage.placeMarketOrder('BTCUSDT', 'BUY', '10') // Large quantity

    // Verify error message
    await expect(page.locator('[data-testid="order-error"]')).toBeVisible()
    await expect(page.locator('[data-testid="order-error"]')).toContainText(/insufficient balance/i)
  })

  test('should update balance after order execution', async ({ orderPage, mockWebSocket, page }) => {
    const seeder = new TestDataSeeder(page)
    await seeder.seedBalances([
      { asset: 'USDT', free: '1000.00', locked: '0.00', total: '1000.00' },
    ])

    // Get initial balance
    const initialBalance = await page.locator('[data-testid="usdt-balance"]').textContent()

    await orderPage.placeMarketOrder('BTCUSDT', 'BUY', '0.001')

    // Simulate order fill via WebSocket
    await mockWebSocket.sendOrderUpdate('test-order-1', 'FILLED', {
      symbol: 'BTCUSDT',
      side: 'BUY',
      quantity: '0.001',
      price: '42000.00',
    })

    // Simulate balance update
    await mockWebSocket.sendBalanceUpdate({
      USDT: { free: '958.00', locked: '0.00', total: '958.00' }, // 1000 - 42 (0.001 * 42000)
      BTC: { free: '0.001', locked: '0.00', total: '0.001' },
    })

    // Verify balance updated
    await expect(page.locator('[data-testid="usdt-balance"]')).not.toContainText(initialBalance || '')
    await expect(page.locator('[data-testid="btc-balance"]')).toContainText('0.001')
  })

  test('should handle network errors gracefully', async ({ orderPage, mockOrderAPI, page }) => {
    // Mock network error
    await mockOrderAPI.mockExchangeDowntime()

    await orderPage.placeMarketOrder('BTCUSDT', 'BUY', '0.001')

    // Verify error handling
    await expect(page.locator('[data-testid="order-error"]')).toBeVisible()
    await expect(page.locator('[data-testid="order-error"]')).toContainText(/network error|service unavailable/i)

    // Verify retry button is available
    await expect(page.locator('[data-testid="retry-order-btn"]')).toBeVisible()
  })

  test('should prevent double submission', async ({ orderPage, page }) => {
    await orderPage.symbolInput.fill('BTCUSDT')
    await orderPage.quantityInput.fill('0.001')

    // Click submit button rapidly
    await Promise.all([
      orderPage.submitButton.click(),
      orderPage.submitButton.click(),
      orderPage.submitButton.click(),
    ])

    // Verify button is disabled during submission
    await expect(orderPage.submitButton).toBeDisabled()

    // Verify only one order is created
    await orderPage.waitForOrderExecution()
    const orderCount = await orderPage.getOrderCount()
    expect(orderCount).toBe(1)
  })

  test('should auto-fill symbol from chart context', async ({ orderPage, page }) => {
    // Navigate to specific symbol trading page
    await page.goto('/trading/ETHUSDT')

    // Verify symbol is pre-filled
    await expect(orderPage.symbolInput).toHaveValue('ETHUSDT')

    // Place order without manually entering symbol
    await orderPage.quantityInput.fill('0.1')
    await orderPage.submitButton.click()

    await orderPage.waitForOrderExecution()
    await orderPage.expectOrderInList('ETHUSDT', 'BUY', 'NEW')
  })

  test('should calculate estimated cost', async ({ orderPage, page }) => {
    await orderPage.symbolInput.fill('BTCUSDT')
    await orderPage.quantityInput.fill('0.001')

    // Mock current price
    await page.evaluate(() => {
      ;(window as any).__mockPrice = 42000
    })

    // Verify estimated cost is displayed
    await expect(page.locator('[data-testid="estimated-cost"]')).toContainText('42.00 USDT')

    // Change quantity and verify cost updates
    await orderPage.quantityInput.fill('0.002')
    await expect(page.locator('[data-testid="estimated-cost"]')).toContainText('84.00 USDT')
  })
})
